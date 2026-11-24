from pathlib import Path

import pytest

from onolys_engine_core.llm.models import load_models
from onolys_engine_core.llm.routes import load_registry, resolve_preset

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[3]
TEXT_ROUTES = ("cheap", "mid", "strong", "miti_code", "miti_globals", "tips")


def test_staging_text_routes_use_claude_low_and_keep_gemini_baseline():
    registry = load_registry(ROOT / "config/staging/routes.yaml", env={})
    routes, _ = resolve_preset("default", registry, {})
    for name in TEXT_ROUTES:
        route = routes[name]
        assert route.litellm_id == "anthropic/claude-sonnet-5-5"
        assert route.api_key_env == "ANTHROPIC_API_KEY"
        assert route.caching_mode == "anthropic_ephemeral"
        assert route.extra_params == {"reasoning_effort": "low"}
        assert route.supports_temperature is False
        assert route.max_output_tokens == 16000
    assert routes["oneshot"].litellm_id == "gemini/gemini-4-neon"
    assert routes["oneshot"].max_output_tokens == 4096
    broken, _ = resolve_preset("test-broken-tiers", registry, {})
    assert broken["miti_code"].litellm_id == "gemini/gemini-4-neon"
    assert "does-not-exist" in broken["mid"].litellm_id


@pytest.mark.parametrize("environment", ["staging", "prod"])
def test_shipped_routes_and_non_test_presets_match_model_capabilities(environment):
    registry = load_registry(ROOT / f"config/{environment}/routes.yaml", env={})
    models = load_models(ROOT / "config/models.yaml")
    known = {
        f"{model.provider}/{tier_id}": (model, tier)
        for model in models.values() for tier_id, tier in model.tiers.items()
    }
    for preset in registry.presets:
        if preset.startswith("test-"):
            continue
        routes, _ = resolve_preset(preset, registry, {})
        for route in routes.values():
            model, tier = known[route.litellm_id]
            effort = route.extra_params.get("reasoning_effort")
            if effort is not None:
                assert effort in tier.efforts
            assert route.max_output_tokens <= model.max_output_tokens


def test_prod_base_routes_remain_gemini():
    routes = load_registry(ROOT / "config/prod/routes.yaml", env={}).routes()
    assert routes["cheap"].litellm_id == "gemini/gemini-4-hydrogen"
    for name in TEXT_ROUTES[1:]:
        assert routes[name].litellm_id == "gemini/gemini-4-neon"
