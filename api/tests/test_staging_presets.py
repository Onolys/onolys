"""Staging-only forced-failure presets (SP09 R6, D4, AC7, AC8): config only, no code hooks."""

from pathlib import Path

import pytest
import yaml
from onolys_engine_core.errors import ConfigError
from onolys_engine_core.llm.routes import allowed_presets, load_registry, resolve_preset

from onolys_api.config import Settings
from onolys_api.presets import PresetResolver, UnknownPreset

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "config/staging/routes.yaml"
PROD = ROOT / "config/prod/routes.yaml"
BROKEN = ("test-broken-llm", "test-broken-tiers")
ALL = ("cheap", "mid", "strong", "miti_code", "miti_globals", "tips")
TIERS = ("cheap", "mid", "strong")
TASK = ("miti_code", "miti_globals", "tips")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for v in (
        "ROUTES_FILE", "DEFAULT_PRESET", "MITI_MODEL_CHEAP", "MITI_MODEL_MID",
        "MITI_MODEL_STRONG", "MITI_LLM_RESPONSE_FORMAT",
    ):  # fmt: skip
        monkeypatch.delenv(v, raising=False)


@pytest.fixture(scope="module")
def staging():
    return load_registry(STAGING, env={})


def test_staging_registers_both_presets(staging):
    assert set(BROKEN) <= set(staging.presets) and "default" in staging.presets


def test_broken_llm_points_every_route_at_a_missing_model(staging):
    routes, _ = resolve_preset("test-broken-llm", staging, {})
    good, _ = resolve_preset("default", staging, {})
    for name in ALL:
        assert routes[name].litellm_id != good[name].litellm_id
        assert "does-not-exist" in routes[name].litellm_id


def test_broken_tiers_breaks_tiers_only(staging):
    routes, _ = resolve_preset("test-broken-tiers", staging, {})
    good, _ = resolve_preset("default", staging, {})
    for name in TIERS:
        assert "does-not-exist" in routes[name].litellm_id
    for name in TASK:
        assert routes[name] == good[name]
        assert "does-not-exist" not in routes[name].litellm_id


def test_broken_tiers_task_routes_are_full_routes_not_aliases(staging):
    ov = staging.presets["test-broken-tiers"].routes
    for name in TASK:
        assert "litellm_id" in ov[name] and "alias" not in ov[name]
    # no alias chain from miti/tips (in the effective table) reaches a broken route
    eff = {**staging.raw_routes, **{k: v for k, v in ov.items()}}
    for name in TASK:
        assert "alias" not in eff[name]
        assert "does-not-exist" not in eff[name]["litellm_id"]


def test_default_preset_on_staging_is_unbroken(staging):
    routes, _ = resolve_preset("default", staging, {})
    assert not any("does-not-exist" in r.litellm_id for r in routes.values())


def test_prod_routes_contain_neither_preset():
    reg = load_registry(PROD, env={})
    assert not set(BROKEN) & set(reg.presets)
    text = PROD.read_text()
    assert "test-broken" not in text and "does-not-exist" not in text
    assert not set(BROKEN) & set(allowed_presets(reg))


def test_runs_preset_check_accepts_staging_presets_and_prod_rejects(tmp_path):
    """POST /runs {preset} and POST /sessions share PresetResolver (registry keys = allowlist)."""
    stg = PresetResolver(Settings(env="staging", routes_file=str(STAGING)))
    for name in BROKEN:
        assert stg.resolve(name, "en")[0] == name
    prod = PresetResolver(Settings(env="prod", routes_file=str(PROD)))
    for name in BROKEN:
        with pytest.raises(UnknownPreset):
            prod.resolve(name, "en")


def test_staging_yaml_has_no_secrets():
    data = yaml.safe_load(STAGING.read_text())
    assert "sk-" not in STAGING.read_text() and "presets" in data


# ---- FX43 / A6, A8: public preset allowlist ---------------------------------------------------


def _resolver(env, **kw):
    return PresetResolver(Settings(env=env, routes_file=str(STAGING), **kw))


def test_public_users_get_only_default_preset():
    r = _resolver("prod")
    assert r.resolve(None, "en")[0] == "default"
    assert r.resolve("default", "en")[0] == "default"
    for name in ("claude", "test-broken-llm"):
        with pytest.raises(UnknownPreset, match="not available"):
            r.resolve(name, "en")


def test_test_presets_only_outside_prod():
    assert _resolver("staging").resolve("test-broken-llm", "en")[0] == "test-broken-llm"
    with pytest.raises(UnknownPreset):
        _resolver("staging").resolve("claude", "en")


def test_extra_presets_flag_enables_claude():
    r = _resolver("prod", extra_presets=("claude",))
    assert r.resolve("claude", "en")[0] == "claude"


def test_extra_presets_env_parsed_and_unknown_name_fails_fast():
    s = Settings.from_env({"ENV": "test", "ENABLED_EXTRA_PRESETS": "claude, other"})
    assert s.extra_presets == ("claude", "other")
    assert Settings.from_env({"ENV": "test"}).extra_presets == ()
    with pytest.raises(ConfigError, match="nope"):
        _resolver("test", extra_presets=("nope",)).check_keys({})


def test_enabled_preset_missing_key_fails_in_staging_warns_locally(caplog):
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        _resolver("staging", extra_presets=("claude",)).check_keys({"GEMINI_API_KEY": "k"})
    _resolver("staging").check_keys({"GEMINI_API_KEY": "k"})  # claude not enabled: not needed
    _resolver("test", extra_presets=("claude",)).check_keys({"GEMINI_API_KEY": "k"})
    assert "ANTHROPIC_API_KEY" in caplog.text
