"""LLM_PROVIDER / LLM_MODEL override (01-llm-outage-claude R6, D2-D5)."""

from pathlib import Path

import pytest

from onolys_engine_core.errors import ConfigError
from onolys_engine_core.llm.routes import load_registry, resolve_preset

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
STAGING = ROOT / "config/staging/routes.yaml"
TEXT = ("cheap", "mid", "strong", "miti_code", "miti_globals", "tips")
CLAUDE = "anthropic/claude-sonnet-5-5"
GEMINI = "gemini/gemini-4-neon"


def routes(env, preset="default"):
    reg = load_registry(STAGING, env=env)
    return resolve_preset(preset, reg, env)[0]


@pytest.fixture(scope="module")
def baseline():
    return routes({})


@pytest.mark.parametrize("env", [{}, {"LLM_PROVIDER": "", "LLM_MODEL": ""}])
def test_unset_or_empty_is_ignored(env, baseline):
    assert routes(env) == baseline


@pytest.mark.parametrize(
    "env",
    [
        {"LLM_PROVIDER": "gemini"},
        {"LLM_MODEL": "gemini-4-neon"},
        {"LLM_PROVIDER": "gemini", "LLM_MODEL": ""},
        {"LLM_PROVIDER": "", "LLM_MODEL": "gemini-4-neon"},
    ],
)
def test_one_of_two_is_config_error(env):
    with pytest.raises(ConfigError, match="LLM_PROVIDER and LLM_MODEL"):
        load_registry(STAGING, env=env)


def test_unknown_provider():
    with pytest.raises(ConfigError, match="LLM_PROVIDER='openai'"):
        load_registry(STAGING, env={"LLM_PROVIDER": "openai", "LLM_MODEL": "gpt-5"})


@pytest.mark.parametrize(
    "provider,model",
    [("gemini", "nope"), ("anthropic", "gemini-4-neon"), ("gemini", "claude-sonnet-5-5")],
)
def test_unknown_model_or_wrong_provider(provider, model):
    with pytest.raises(ConfigError, match="LLM_MODEL"):
        load_registry(STAGING, env={"LLM_PROVIDER": provider, "LLM_MODEL": model})


def test_gemini_override(baseline):
    r = routes({"LLM_PROVIDER": "gemini", "LLM_MODEL": "gemini-4-neon"})
    for name in TEXT:
        assert r[name].litellm_id == GEMINI
        assert r[name].api_key_env == "GEMINI_API_KEY"
        assert r[name].caching_mode == "provider_implicit"
        assert r[name].extra_params == baseline[name].extra_params
        assert r[name].max_output_tokens == baseline[name].max_output_tokens
    assert r["oneshot"] == baseline["oneshot"]


def test_anthropic_override_and_oneshot_untouched(baseline):
    r = routes({"LLM_PROVIDER": "anthropic", "LLM_MODEL": "claude-haiku-5-5"})
    for name in TEXT:
        assert r[name].litellm_id == "anthropic/claude-haiku-5-5"
        assert r[name].api_key_env == "ANTHROPIC_API_KEY"
        assert r[name].caching_mode == "anthropic_ephemeral"
    assert r["oneshot"].litellm_id == baseline["oneshot"].litellm_id == GEMINI


def test_beats_miti_model_env():
    r = routes(
        {"MITI_MODEL_MID": "x/y", "LLM_PROVIDER": "anthropic", "LLM_MODEL": "claude-sonnet-5-5"}
    )
    assert r["mid"].litellm_id == CLAUDE


def test_broken_preset_beats_env_override():
    env = {"LLM_PROVIDER": "anthropic", "LLM_MODEL": "claude-sonnet-5-5"}
    r = routes(env, "test-broken-llm")
    for name in TEXT:
        assert r[name].litellm_id == "gemini/gemini-does-not-exist-0"
    assert routes(env, "test-broken-tiers")["cheap"].litellm_id.endswith("does-not-exist-0")
