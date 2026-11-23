import json

import pytest

from onolys_engine_core.llm.routes import Preset, RouteRegistry, load_registry, resolve_preset
from onolys_engine_core.presets import list_presets


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("ROUTES_FILE", raising=False)
    monkeypatch.delenv("DEFAULT_PRESET", raising=False)


def test_packaged_catalog_uses_effective_models_and_explicit_prod():
    registry = load_registry(env={})
    catalog = {info.name: info for info in list_presets(registry, "claude")}
    assert set(catalog) == {"default", "claude"}
    assert catalog["claude"].prod is True
    assert catalog["default"].prod is False
    for name, info in catalog.items():
        routes, _ = resolve_preset(name, registry)
        assert info.models == {route: model.litellm_id for route, model in routes.items()}
    assert catalog["default"].models != catalog["claude"].models


def test_prod_name_uses_env_and_default_fallback(monkeypatch):
    registry = load_registry(env={})
    assert [info.name for info in list_presets(registry) if info.prod] == ["default"]
    monkeypatch.setenv("DEFAULT_PRESET", "claude")
    assert [info.name for info in list_presets(registry) if info.prod] == ["claude"]
    assert [info.name for info in list_presets(registry, "default") if info.prod] == ["default"]
    monkeypatch.setenv("DEFAULT_PRESET", "")
    assert [info.name for info in list_presets(registry) if info.prod] == ["default"]


def test_catalog_resolves_alias_overrides_and_contains_no_key_material(monkeypatch):
    monkeypatch.setenv("PRIVATE_PROVIDER_KEY", "secret-key-value")
    registry = RouteRegistry(
        raw_routes={
            "base": {"litellm_id": "provider/base", "api_key_env": "PRIVATE_PROVIDER_KEY",
                     "extra_params": {"api_key": "inline-secret"}},
            "other": {"litellm_id": "provider/other"},
            "task": {"alias": "base"},
            "chain": {"alias": "task"},
        },
        presets={
            "default": Preset(routes={}),
            "custom": Preset(routes={"base": {"litellm_id": "provider/override"},
                                     "task": {"alias": "other"}}),
            "test-failure": Preset(routes={}),
        },
    )
    catalog = {info.name: info for info in list_presets(registry, "custom")}
    assert catalog["custom"].models == {
        "base": "provider/override", "other": "provider/other",
        "task": "provider/other", "chain": "provider/other",
    }
    assert catalog["default"].models["chain"] == "provider/base"
    assert "test-failure" in catalog
    serialized = json.dumps([info.model_dump() for info in catalog.values()])
    for forbidden in ("PRIVATE_PROVIDER_KEY", "secret-key-value", "inline-secret", "api_key"):
        assert forbidden not in serialized
    assert registry.raw_routes["base"]["litellm_id"] == "provider/base"


def test_empty_presets_list_synthetic_default():
    registry = RouteRegistry(raw_routes={"task": {"litellm_id": "provider/model"}}, presets={})
    assert [info.model_dump() for info in list_presets(registry, None)] == [
        {"name": "default", "prod": True, "models": {"task": "provider/model"}},
    ]
