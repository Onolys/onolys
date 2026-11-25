"""LLM_PROVIDER / LLM_MODEL override (01-llm-outage-claude R6, D2-D5)."""

from pathlib import Path

import pytest

from onolys_engine_core.errors import ConfigError
from onolys_engine_core.llm.models import load_models
from onolys_engine_core.llm.routes import (
    COMBO_TIMEOUT_S,
    EFFORT_OUTPUT_CAP,
    load_registry,
    resolve_preset,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
STAGING = ROOT / "config/staging/routes.yaml"
TEXT = ("cheap", "mid", "strong", "miti_code", "miti_globals", "tips")
CLAUDE = "anthropic/claude-sonnet-5-5"
GEMINI = "gemini/gemini-4-neon"
MODEL_MAX = {
    f"{m.provider}/{t}": m.max_output_tokens
    for m in load_models(ROOT / "config/models.yaml").values()
    for t in m.tiers
}


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
    with pytest.raises(ConfigError, match="LLM_PROVIDER='unknown'"):
        load_registry(STAGING, env={"LLM_PROVIDER": "unknown", "LLM_MODEL": "gpt-5"})


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


def test_high_effort_raises_output_cap_and_timeout(baseline):
    for effort in ("high", "max"):
        r = routes({"LLM_EFFORT": effort})
        for name in TEXT:
            want = EFFORT_OUTPUT_CAP[effort]
            assert r[name].max_output_tokens == min(want, MODEL_MAX[r[name].litellm_id])
            assert r[name].max_output_tokens > baseline[name].max_output_tokens
            assert r[name].timeout_s == COMBO_TIMEOUT_S


@pytest.mark.parametrize("effort", ["low", "medium"])
def test_low_effort_never_lowers_cap(effort, baseline):
    r = routes({"LLM_EFFORT": effort})
    for name in TEXT:
        assert r[name].max_output_tokens >= baseline[name].max_output_tokens
        assert r[name].timeout_s >= baseline[name].timeout_s


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


@pytest.mark.parametrize("effort", ["low", "medium", "high", "max"])
def test_effort_override_on_default_text_routes(effort, baseline):
    r = routes({"LLM_EFFORT": effort})
    for name in TEXT:
        assert r[name].extra_params["reasoning_effort"] == effort
        assert r[name].litellm_id == baseline[name].litellm_id
        assert r[name].max_output_tokens >= baseline[name].max_output_tokens
    assert r["oneshot"] == baseline["oneshot"]


def test_effort_override_with_model_and_preset_precedence():
    env = {"LLM_PROVIDER": "gemini", "LLM_MODEL": "gemini-4-neon", "LLM_EFFORT": "high"}
    assert routes(env)["miti_code"].extra_params["reasoning_effort"] == "high"
    assert routes(env, "claude")["miti_code"].extra_params == {}
    assert routes(env, "test-broken-llm")["miti_code"].extra_params["reasoning_effort"] == "low"


@pytest.mark.parametrize("effort", ["LOW", "High", " high", "high\n", "", "ultra", "low,EVIL=1", "low\nEVIL=1"])
def test_invalid_effort_is_rejected(effort):
    if not effort:
        assert routes({"LLM_EFFORT": effort}) == routes({})
        return
    with pytest.raises(ConfigError, match="LLM_EFFORT"):
        routes({"LLM_EFFORT": effort})


def test_effort_must_be_supported_by_selected_model():
    with pytest.raises(ConfigError, match="LLM_EFFORT.*max"):
        routes({"LLM_PROVIDER": "gemini", "LLM_MODEL": "gemini-4-neon", "LLM_EFFORT": "max"})


def test_effort_only_validates_effective_miti_model():
    with pytest.raises(ConfigError, match="LLM_EFFORT"):
        routes({"MITI_MODEL_MID": "gemini/gemini-4-neon", "LLM_EFFORT": "max"})
    with pytest.raises(ConfigError, match="LLM_EFFORT"):
        routes({"MITI_MODEL_MID": "unknown/model", "LLM_EFFORT": "low"})


@pytest.mark.parametrize("field,value", [("LLM_PROVIDER", "anthropic\n"), ("LLM_MODEL", "claude-sonnet-5-5\n"), ("LLM_MODEL", "claude-sonnet-5-5,EVIL=1")])
def test_override_rejects_values_unsafe_for_deployment(field, value):
    env = {"LLM_PROVIDER": "anthropic", "LLM_MODEL": "claude-sonnet-5-5", field: value}
    with pytest.raises(ConfigError):
        routes(env)


def test_effort_preserves_other_extra_params(tmp_path):
    import yaml

    data = yaml.safe_load(STAGING.read_text())
    data["cheap"]["extra_params"] = {"reasoning_effort": "low", "other": 42}
    source = tmp_path / "routes.yaml"
    source.write_text(yaml.safe_dump(data))
    env = {"MODELS_FILE": str(ROOT / "config/models.yaml"), "LLM_EFFORT": "medium"}
    r = load_registry(source, env).routes()
    assert r["cheap"].extra_params == {"reasoning_effort": "medium", "other": 42}


@pytest.mark.parametrize("tier,effort", [
    ("gpt-6.1-sol", "xhigh"), ("gpt-6.1-terra", "none"), ("gpt-6-luna", "max"),
])
def test_openai_deployment_override(tier, effort, baseline):
    out = routes({"LLM_PROVIDER": "openai", "LLM_MODEL": tier, "LLM_EFFORT": effort})
    for name in TEXT:
        assert out[name].litellm_id == f"openai/{tier}"
        assert out[name].api_key_env == "OPENAI_API_KEY"
        assert out[name].caching_mode == "provider_implicit"
        assert out[name].extra_params["reasoning_effort"] == effort
        assert out[name].max_output_tokens >= baseline[name].max_output_tokens
    assert out["oneshot"] == baseline["oneshot"]


def test_sol_none_effort_rejected():
    with pytest.raises(ConfigError, match="LLM_EFFORT.*none"):
        routes({"LLM_PROVIDER": "openai", "LLM_MODEL": "gpt-6.1-sol", "LLM_EFFORT": "none"})
