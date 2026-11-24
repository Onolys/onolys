"""Catalog wire behavior against synthetic metadata and private storage fakes."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from onolys_engine_core.llm.models import load_models
from onolys_engine_core.llm.routes import Preset, RouteRegistry, load_registry, resolve_preset
from test_app import AUTH, ENV, Verifier

from onolys_eval_backend import create_app
from onolys_eval_backend.repository import InMemoryEvalRepository
from onolys_eval_backend.storage import InMemoryBucket

MODELS_YAML = Path(__file__).resolve().parents[3] / "config" / "models.yaml"
STAGING_ROUTES = Path(__file__).resolve().parents[3] / "config" / "staging" / "routes.yaml"


def manifest():
    return {
        "dataset_id": "synthetic", "title": "Synthetic", "license_note": "Test only",
        "source_page": "https://example.org", "miti_version": "4.2.1",
        "source_media": ["video", "transcript"], "transcript_origin": "human",
        "labels_summary": "MITI counts", "overlaps_with": [{"dataset_id": "other", "note": "Shared"}],
        "sessions": [{"session_id": "one", "title": "One",
                      "coded_url": "https://example.org/coded.pdf",
                      "uncoded_url": "https://example.org/uncoded.pdf",
                      "clinician_labels": ["I"], "code_header": "Code",
                      "change_goal": "Test goal", "change_goal_source": "curated",
                      "coded_span": {"start_turn": 0, "end_turn": 4}, "notes": "Synthetic"}],
    }


@pytest.fixture
def services():
    return SimpleNamespace(
        bucket=InMemoryBucket(), repository=InMemoryEvalRepository(),
        models=load_models(MODELS_YAML),
        routes=RouteRegistry({
            "oneshot": {"litellm_id": "synthetic/model"},
            "mid": {"litellm_id": "anthropic/claude-sonnet-5-5",
                    "extra_params": {"reasoning_effort": "low"}},
        }, {
            "default": Preset({}), "configured-prod": Preset({}),
            "test-failure": Preset({}),
        }),
    )


def client(services=None, **env):
    return TestClient(create_app(
        {**ENV, **env}, verifier=Verifier({"email": "alice@example.com", "email_verified": True}),
        services=services,
    ))


def test_options_exact_ids_config_prod_and_mode_defaults(services):
    c = client(services, PROD_ENGINE="oneshot:miti")
    response = c.get("/v1/options?mode=dataset", headers=AUTH)
    assert response.status_code == 200
    data = response.json()
    assert [e["id"] for e in data["engines"]] == ["human", "miti", "oneshot:miti"]
    human, lean, oneshot = data["engines"]
    assert human["engine"] == "human" and human["prod"] is False
    assert lean["prod"] is False and "(prod)" not in lean["label"]
    assert oneshot["engine"] == "oneshot" and oneshot["config"] == "miti"
    assert oneshot["prod"] is True and "(prod)" in oneshot["label"]
    assert oneshot["version"]
    assert "presets" not in data
    assert data["defaults"] == {
        "dataset": {"engines": ["human", "oneshot:miti"], "selection": SELECTION,
                    "label": "Claude / claude-sonnet-5-5 / low (prod)"},
        "upload": {"engines": ["oneshot:miti"], "selection": SELECTION,
                   "label": "Claude / claude-sonnet-5-5 / low (prod)"},
    }


SELECTION = {"models": ["claude"], "tiers": ["claude-sonnet-5-5"], "efforts": ["low"]}


def test_options_models_match_models_yaml(services):
    data = client(services).get("/v1/options", headers=AUTH).json()
    expected = [
        {"id": m.id, "label": m.label, "context_tokens": m.context_tokens,
         "max_output_tokens": m.max_output_tokens,
         "tiers": [{"id": t.id, "efforts": list(t.efforts), "default_effort": t.default_effort}
                   for t in m.tiers.values()]}
        for m in load_models(MODELS_YAML).values()
    ]
    assert data["models"] == expected
    assert [m["id"] for m in data["models"]] == ["claude", "gemini"]
    assert "presets" not in data


def test_default_selection_equals_resolved_mid_route_of_staging_config(services):
    registry = load_registry(STAGING_ROUTES, env={})
    mid = resolve_preset("default", registry, {})[0]["mid"]
    services.routes = registry
    data = client(services, DEFAULT_PRESET="default").get("/v1/options", headers=AUTH).json()
    tier = mid.litellm_id.split("/", 1)[1]
    effort = mid.extra_params["reasoning_effort"]
    sel = data["defaults"]["dataset"]["selection"]
    assert sel == {"models": ["claude"], "tiers": [tier], "efforts": [effort]}
    assert data["defaults"]["upload"]["selection"] == sel
    assert data["defaults"]["dataset"]["label"].endswith(f"{tier} / {effort} (prod)")


def test_default_selection_follows_a_preset_overriding_mid(services):
    services.routes = RouteRegistry(services.routes.raw_routes, {
        "configured-prod": Preset({"mid": {
            "litellm_id": "gemini/gemini-4-neon", "extra_params": {"reasoning_effort": "high"},
        }}),
    })
    data = client(services).get("/v1/options", headers=AUTH).json()
    assert data["defaults"]["dataset"]["selection"] == {
        "models": ["gemini"], "tiers": ["gemini-4-neon"], "efforts": ["high"],
    }


def test_mid_route_outside_models_yaml_makes_options_unavailable(services):
    services.routes = RouteRegistry({"mid": {"litellm_id": "anthropic/unknown-tier"}}, {})
    response = client(services, DEFAULT_PRESET="default").get("/v1/options", headers=AUTH)
    assert response.status_code == 503
    assert response.json() == {"detail": "Engine options unavailable."}


def test_miti_production_flag_follows_config(services):
    data = client(services).get("/v1/options?mode=dataset", headers=AUTH).json()
    assert [e["id"] for e in data["engines"] if e["prod"]] == ["miti"]
    assert data["defaults"]["dataset"]["engines"] == ["human", "miti"]


@pytest.mark.parametrize("has_gold", [False, True])
def test_human_upload_gate_uses_saved_record(services, has_gold):
    services.repository.create_upload("saved", {"has_gold": has_gold})
    c = client(services)
    data = c.get("/v1/options?mode=upload&upload_id=saved&has_gold=true", headers=AUTH).json()
    assert ("human" in [e["id"] for e in data["engines"]]) is has_gold
    assert data["defaults"]["upload"]["engines"] == ["miti"]
    data = c.get("/v1/options?mode=upload&has_gold=true", headers=AUTH).json()
    assert "human" not in [e["id"] for e in data["engines"]]


def test_missing_upload_and_invalid_mode(services):
    c = client(services)
    assert c.get("/v1/options?mode=upload&upload_id=missing", headers=AUTH).status_code == 404
    assert c.get("/v1/options?mode=unknown", headers=AUTH).status_code == 422


def test_dataset_list_detail_and_gold_presence(services):
    source = manifest()
    services.bucket.write_json("datasets/synthetic/manifest.json", source)
    services.bucket.write_json("datasets/synthetic/one/gold.json", {})
    services.bucket.write_json("datasets/ignored/nested/manifest.json", source)
    services.bucket.write_json("uploads/ignored/manifest.json", source)
    c = client(services)
    response = c.get("/v1/datasets", headers=AUTH)
    assert response.status_code == 200
    expected = {k: v for k, v in source.items() if k != "sessions"}
    assert response.json() == {"datasets": [{**expected, "session_count": 1}]}
    row = response.json()["datasets"][0]
    assert row["source_media"] == ["video", "transcript"] and row["transcript_origin"] == "human"
    assert row["labels_summary"] == "MITI counts" and row["miti_version"] == "4.2.1"
    detail = c.get("/v1/datasets/synthetic", headers=AUTH)
    assert detail.status_code == 200
    result = detail.json()
    assert result["source_media"] == ["video", "transcript"]
    assert result["dataset_id"] == "synthetic"
    session = result["sessions"][0]
    assert session["session_id"] == "one" and session["has_gold"] is True
    assert session["coded_span"] == source["sessions"][0]["coded_span"]
    assert session["change_goal"] == "Test goal"
    services.bucket._objects.pop("datasets/synthetic/one/gold.json")
    assert c.get("/v1/datasets/synthetic", headers=AUTH).json()["sessions"][0]["has_gold"] is False
    assert c.get("/v1/datasets/missing", headers=AUTH).status_code == 404


@pytest.mark.parametrize("change", ["extra", "identity", "span"])
def test_invalid_manifests_fail_with_fixed_message(services, change):
    source = deepcopy(manifest())
    if change == "extra":
        source["private-secret"] = "must-never-leak"
    elif change == "identity":
        source["dataset_id"] = "different"
    else:
        source["sessions"][0]["coded_span"] = {"start_turn": 10, "end_turn": 1}
    services.bucket.write_json("datasets/synthetic/manifest.json", source)
    c = client(services)
    for path in ["/v1/datasets", "/v1/datasets/synthetic"]:
        response = c.get(path, headers=AUTH)
        assert response.status_code == 503
        assert response.json() == {"detail": "Dataset catalog unavailable."}


def test_default_composition_is_lazy_but_usable_without_cloud(tmp_path, monkeypatch):
    from google.cloud import firestore, storage

    def forbidden(*args, **kwargs):
        raise AssertionError("ADC must remain lazy")

    monkeypatch.setattr(storage, "Client", forbidden)
    monkeypatch.setattr(firestore, "Client", forbidden)
    routes = tmp_path / "routes.yaml"
    routes.write_text(
        "oneshot:\n  litellm_id: synthetic/model\n"
        "mid:\n  litellm_id: anthropic/claude-sonnet-5-5\n  extra_params: {reasoning_effort: low}\n"
        "presets:\n  configured-prod: {}\n"
    )
    monkeypatch.setenv("MODELS_FILE", str(MODELS_YAML))
    c = client(ROUTES_FILE=str(routes))
    assert c.app.state.services is not None
    assert c.get("/v1/datasets").status_code == 401
    assert c.get("/v1/options?mode=dataset", headers=AUTH).status_code == 200
    engine = c.app.state.services.engine("oneshot:miti")
    assert engine.name == "oneshot"
    assert c.app.state.services.engine("oneshot:miti") is engine
    assert engine.output_schema()["$id"]


def test_bucket_failures_never_expose_details(services):
    def fail(prefix):
        raise RuntimeError("private paths and credentials")

    services.bucket.list = fail
    response = client(services).get("/v1/datasets", headers=AUTH)
    assert response.status_code == 503
    assert response.json() == {"detail": "Dataset catalog unavailable."}


def test_injected_registry_drives_future_engine_options(services):
    from onolys_engine_core.registry import EngineRegistry
    from onolys_miti.engine import MitiEngine

    class FutureEngine(MitiEngine):
        name = "future"
        version = "future-version"

    services.registry = EngineRegistry()
    services.registry.register(MitiEngine())
    services.registry.register(FutureEngine())
    data = client(services, PROD_ENGINE="future").get("/v1/options", headers=AUTH).json()
    assert [e["id"] for e in data["engines"]] == ["human", "miti", "future"]
    assert data["engines"][-1] == {
        "id": "future", "label": "future (prod)", "engine": "future", "prod": True,
        "version": "future-version",
    }
    assert data["defaults"]["upload"]["engines"] == ["future"]


def test_production_cloud_adapters_use_explicit_project_and_staging_database(monkeypatch):
    from google.cloud import firestore, storage

    from onolys_eval_backend.config import EvalConfig
    from onolys_eval_backend.services import EvalServices

    calls = []

    class StorageClient:
        def __init__(self, **kwargs):
            calls.append(("storage", kwargs))

        def bucket(self, name):
            calls.append(("bucket", name))
            return "bucket-object"

    class FirestoreClient:
        def __init__(self, **kwargs):
            calls.append(("firestore", kwargs))

        def collection(self, name):
            calls.append(("collection", name))
            return name

    monkeypatch.setattr(storage, "Client", StorageClient)
    monkeypatch.setattr(firestore, "Client", FirestoreClient)
    services = EvalServices(EvalConfig.from_env(ENV))
    assert calls == []
    assert services.bucket.bucket == "bucket-object"
    assert services.repository.uploads == "eval_uploads"
    assert services.bucket is services.bucket and services.repository is services.repository
    assert calls == [
        ("storage", {"project": "onolys-test"}), ("bucket", "eval-test"),
        ("firestore", {"project": "onolys-test", "database": "staging"}),
        ("collection", "eval_uploads"), ("collection", "eval_runs"),
    ]


def test_options_storage_failure_and_unavailable_production_choices_are_safe(services):
    def fail(upload_id):
        raise RuntimeError("private diagnostic")

    services.repository.get_upload = fail
    response = client(services).get("/v1/options?mode=upload&upload_id=saved", headers=AUTH)
    assert response.status_code == 503
    assert response.json() == {"detail": "Upload unavailable."}
    for env in [{"PROD_ENGINE": "missing"}, {"DEFAULT_PRESET": "test-failure"}]:
        response = client(services, **env).get("/v1/options", headers=AUTH)
        assert response.status_code == 503
        assert response.json() == {"detail": "Engine options unavailable."}
