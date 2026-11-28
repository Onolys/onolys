import copy
from pathlib import Path

import pytest

from onolys_engine.llm.models import EFFORTS, find_model, load_models
from onolys_engine.llm.routes import Route, combo_routes, load_registry

pytestmark = pytest.mark.unit

MODELS = Path(__file__).resolve().parents[2] / "config" / "models.yaml"


@pytest.fixture
def base():
    reg = load_registry(env={})
    routes = reg.routes()
    # make inheritance observable
    routes["mid"] = Route(
        litellm_id="x/y", structured_output_mode="json_schema", max_concurrency=5,
        max_retries=7, backoff_s=9, extra_params={"reasoning_effort": "low", "keep": 1},
    )
    return routes


@pytest.mark.parametrize("effort", sorted(EFFORTS))
def test_cap_is_the_model_max_for_every_effort(base, effort):
    for _provider, model in load_models(MODELS).items():
        tier = next(iter(model.tiers))
        out = combo_routes(base, model, tier, effort)
        assert {r.max_output_tokens for r in out.values()} == {model.max_output_tokens}
        assert model.max_output_tokens >= 64000


def test_claude_snapshot(base):
    model = find_model(load_models(MODELS), "anthropic", "claude-sonnet-5-5")
    out = combo_routes(base, model, "claude-sonnet-5-5", "high")
    assert set(out) == set(base)
    for name, r in out.items():
        assert r.litellm_id == "anthropic/claude-sonnet-5-5", name
        assert r.api_key_env == "ANTHROPIC_API_KEY"
        assert r.caching_mode == "anthropic_ephemeral"
        assert r.supports_temperature is False
        assert r.context_tokens == 1_000_000
        assert r.max_output_tokens == 128000  # the model's own max
        assert r.timeout_s == 600  # scales with the cap: 300 s per 64000 tokens
        assert r.extra_params["reasoning_effort"] == "high"
    mid = out["mid"]
    assert mid.structured_output_mode == "json_schema"
    assert (mid.max_concurrency, mid.max_retries, mid.backoff_s) == (5, 7, 9)
    assert mid.extra_params == {"keep": 1, "reasoning_effort": "high"}


def test_gemini_snapshot(base):
    model = find_model(load_models(MODELS), "gemini", "gemini-4-neon")
    out = combo_routes(base, model, "gemini-4-neon", "max")  # the model's max, 65536
    assert out["mid"].max_output_tokens == 65536
    out = combo_routes(base, model, "gemini-4-neon", "low")
    r = out["cheap"]
    assert r.litellm_id == "gemini/gemini-4-neon"
    assert r.api_key_env == "GEMINI_API_KEY"
    assert r.caching_mode == "provider_implicit"
    assert r.context_tokens == 1048576
    assert r.max_output_tokens == 65536


def test_cap_bounded_by_model_max(base):
    model = find_model(load_models(MODELS), "gemini", "gemini-4-neon")
    small = type(model)(**{**model.__dict__, "max_output_tokens": 20000})
    assert combo_routes(base, small, "gemini-4-neon", "high")["mid"].max_output_tokens == 20000


def test_base_not_mutated(base):
    before = copy.deepcopy(base)
    model = find_model(load_models(MODELS), "anthropic", "claude-opus-5-5")
    combo_routes(base, model, "claude-opus-5-5", "medium")
    assert base == before


@pytest.mark.parametrize("tier,effort", [
    (tier, effort)
    for tier in ("gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna")
    for effort in ("none", "low", "medium", "high", "xhigh", "max")
    if (tier, effort) != ("gpt-6.1-sol", "none")
])
def test_openai_combo_routes_preserve_explicit_effort_and_provider_caps(base, tier, effort):
    model = load_models(MODELS)["openai"]
    out = combo_routes(base, model, tier, effort)
    for route in out.values():
        assert route.litellm_id == f"openai/{tier}"
        assert route.api_key_env == "OPENAI_API_KEY"
        assert route.extra_params["reasoning_effort"] == effort
        assert route.max_output_tokens == model.max_output_tokens
        assert route.context_tokens == 1050000
        assert route.supports_temperature is False
