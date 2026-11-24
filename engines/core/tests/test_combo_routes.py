import copy
from pathlib import Path

import pytest

from onolys_engine_core.llm.models import find_model, load_models
from onolys_engine_core.llm.routes import EFFORT_OUTPUT_CAP, Route, combo_routes, load_registry

pytestmark = pytest.mark.unit

MODELS = Path(__file__).resolve().parents[3] / "config" / "models.yaml"


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


def test_caps_table():
    assert EFFORT_OUTPUT_CAP == {"low": 16000, "medium": 32000, "high": 48000, "max": 64000}


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
        assert r.max_output_tokens == 48000
        assert r.timeout_s == 300
        assert r.extra_params["reasoning_effort"] == "high"
    mid = out["mid"]
    assert mid.structured_output_mode == "json_schema"
    assert (mid.max_concurrency, mid.max_retries, mid.backoff_s) == (5, 7, 9)
    assert mid.extra_params == {"keep": 1, "reasoning_effort": "high"}


def test_gemini_snapshot(base):
    model = find_model(load_models(MODELS), "gemini", "gemini-4-neon")
    out = combo_routes(base, model, "gemini-4-neon", "max")  # cap 64000 < 65536
    assert out["mid"].max_output_tokens == 64000
    out = combo_routes(base, model, "gemini-4-neon", "low")
    r = out["cheap"]
    assert r.litellm_id == "gemini/gemini-4-neon"
    assert r.api_key_env == "GEMINI_API_KEY"
    assert r.caching_mode == "provider_implicit"
    assert r.context_tokens == 1048576
    assert r.max_output_tokens == 16000


def test_cap_bounded_by_model_max(base):
    model = find_model(load_models(MODELS), "gemini", "gemini-4-neon")
    small = type(model)(**{**model.__dict__, "max_output_tokens": 20000})
    assert combo_routes(base, small, "gemini-4-neon", "high")["mid"].max_output_tokens == 20000


def test_base_not_mutated(base):
    before = copy.deepcopy(base)
    model = find_model(load_models(MODELS), "anthropic", "claude-opus-5-5")
    combo_routes(base, model, "claude-opus-5-5", "medium")
    assert base == before
