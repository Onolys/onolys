"""Deployment preflight calls the runtime loader before emitting any env values."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/validate_staging_llm.py"
pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "provider,model,effort,valid",
    [
        ("", "", "", True),
        ("", "", "max", True),
        ("anthropic", "claude-sonnet-5-5", "high", True),
        ("gemini", "gemini-4-neon", "medium", True),
        ("openai", "gpt-6.1-sol", "xhigh", True),
        ("openai", "gpt-6.1-terra", "none", True),
        ("openai", "gpt-6-luna", "max", True),
        ("openai", "gpt-6.1-sol", "none", False),
        ("gemini", "gemini-4-neon", "max", False),
        ("anthropic", "gemini-4-neon", "low", False),
        ("anthropic", "missing", "low", False),
        ("anthropic", "", "low", False),
        ("", "claude-sonnet-5-5", "low", False),
        ("", "", "HIGH", False),
        ("", "", "low\nEVIL=1", False),
        ("anthropic\n", "claude-sonnet-5-5", "low", False),
        ("anthropic", "claude-sonnet-5-5,EVIL=1", "low", False),
        ("anthropic", "$(touch /tmp/unsafe)", "low", False),
    ],
)
def test_preflight_uses_runtime_validation_and_emits_only_valid_values(
    tmp_path, provider, model, effort, valid
):
    output = tmp_path / "output"
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        env={
            **os.environ,
            "LLM_PROVIDER": provider,
            "LLM_MODEL": model,
            "LLM_EFFORT": effort,
            "GITHUB_OUTPUT": str(output),
        },
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) is valid, result.stderr
    if valid:
        assert output.read_text() == f"provider={provider}\nmodel={model}\neffort={effort}\n"
    else:
        assert not output.exists()
        assert "Invalid staging LLM configuration" in result.stderr


@pytest.mark.parametrize(
    'provider,model,effort,valid',
    [('', '', '', True), ('', '', 'max', False), ('', '', 'low', True),
     ('openai', 'gpt-6.1-sol', 'medium', True), ('openai', '', '', False),
     ('openai', 'gpt-6.1-sol', 'none', False),
     ('openai', 'gpt-6.1-sol\nEVIL=1', 'medium', False)],
)
def test_production_preflight_uses_prod_routes_and_stdout(tmp_path, provider, model, effort, valid):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--environment', 'prod', '--config-root', str(ROOT / 'config'), '--stdout'],
        env={**os.environ, 'LLM_PROVIDER': provider, 'LLM_MODEL': model, 'LLM_EFFORT': effort},
        capture_output=True, text=True,
    )
    assert (result.returncode == 0) is valid, result.stderr
    if valid:
        assert result.stdout == f'provider={provider}\nmodel={model}\neffort={effort}\n'
    else:
        assert result.stdout == ''


def test_production_rejects_a_historical_loader_that_cannot_apply_effort(tmp_path):
    # Historical image runtime ignores unknown env keys: a nonblank override must
    # fail explicitly rather than silently deploying settings that have no effect.
    package = tmp_path / 'onolys_engine'
    (package / 'llm').mkdir(parents=True)
    (package / '__init__.py').write_text('')
    (package / 'llm/__init__.py').write_text('')
    (package / 'errors.py').write_text('class ConfigError(Exception): pass\n')
    (package / 'llm/routes.py').write_text('def load_registry(*args, **kwargs): pass\n')
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--environment', 'prod', '--stdout'],
        env={**os.environ, 'PYTHONPATH': str(tmp_path), 'LLM_PROVIDER': '', 'LLM_MODEL': '', 'LLM_EFFORT': 'low'},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0 and result.stdout == ''
    assert 'does not support LLM_EFFORT' in result.stderr
