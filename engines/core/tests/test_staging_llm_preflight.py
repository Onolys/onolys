"""Deployment preflight calls the runtime loader before emitting any env values."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
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
