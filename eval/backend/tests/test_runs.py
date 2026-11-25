"""Run creation (sessions, grouping doc, tick 1) from datasets and uploads; synthetic data only."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from onolys_api.repo.fake import FakeRepo
from onolys_api.storage.fake import FakeBlobStore
from onolys_engine_core.llm.models import load_models
from onolys_engine_core.llm.routes import Preset, RouteRegistry
from onolys_engine_core.registry import EngineRegistry
from onolys_miti.engine import MitiEngine
from onolys_oneshot.engine import OneshotEngine
from test_app import AUTH, client
from test_catalog import manifest
from test_uploads import gold, transcript

from onolys_eval_backend.queue import InMemoryTaskQueue
from onolys_eval_backend.repository import InMemoryEvalRepository
from onolys_eval_backend.storage import InMemoryBucket

REPO_CONFIG = Path(__file__).parents[3] / "config"


@pytest.fixture(autouse=True)
def eval_routes(tmp_path, monkeypatch):
    """Real route/model files (the worker's drift check reads them) plus the test preset names."""
    text = (REPO_CONFIG / "staging" / "routes.yaml").read_text()
    extra = "presets:\n  configured-prod:\n    routes: {}\n  other:\n    routes: {}\n"
    assert "presets:\n" in text
    path = tmp_path / "routes.yaml"
    path.write_text(text.replace("presets:\n", extra, 1))
    monkeypatch.setenv("ROUTES_FILE", str(path))
    monkeypatch.setenv("MODELS_FILE", str(REPO_CONFIG / "models.yaml"))


@pytest.fixture
def services(eval_routes):
    registry = EngineRegistry()
    registry.register(MitiEngine())
    registry.register(OneshotEngine(config="miti"))
    s = SimpleNamespace(
        repository=InMemoryEvalRepository(),
        audio_bucket=InMemoryBucket(),
        datasets=InMemoryBucket(),
        queue=InMemoryTaskQueue(),
        registry=registry,
        models=load_models(Path(__file__).parents[3] / "config" / "models.yaml"),
        routes=RouteRegistry(
            {"oneshot": {"litellm_id": "synthetic/model"}},
            {"configured-prod": Preset({}), "other": Preset({}), "test-hidden": Preset({})},
        ),
    )
    source = manifest()
    source["sessions"][0]["coded_span"]["end_turn"] = 2
    # Prod repo/blobs for sessions; datasets and the audio bucket (uploads) are separate stores.
    s.blobs = FakeBlobStore()
    s.repo = FakeRepo(s.blobs)
    s.repo.ensure_user("eval-owner")
    s.config = SimpleNamespace(eval_owner_uid="eval-owner", default_preset="configured-prod")
    s.datasets.write_json("datasets/synthetic/manifest.json", source)
    s.datasets.write_json("datasets/synthetic/one/transcript.json", transcript())
    s.datasets.write_json("datasets/synthetic/one/gold.json", gold())
    return s


SEL1 = {"models": ["claude"], "tiers": ["claude-sonnet-5-5"], "efforts": ["low"]}
SEL2 = {"models": ["claude"], "tiers": ["claude-sonnet-5-5"], "efforts": ["low", "high"]}


def start(c, **overrides):
    return c.post(
        "/v1/runs",
        headers=AUTH,
        json={
            "input": {"dataset_id": "synthetic", "session_ids": ["one"]},
            "engines": ["human", "miti"],
            "selection": SEL1,
            "repeats": 1,
            **overrides,
        },
    )




@pytest.mark.parametrize(
    "overrides",
    [
        {"engines": ["unknown"]},
        {"selection": {"models": ["claude"], "tiers": ["claude-sonnet-5-5"], "efforts": ["xhigh"]}},
        {"presets": ["configured-prod"]},
        {"repeats": 2},
        {"input": {"dataset_id": "synthetic", "session_ids": ["missing"]}},
        {"coded_span": {"start_turn": 0, "end_turn": 1}},
        {"engines": ["miti", "miti"]},
    ],
)
def test_bad_selection_never_writes(services, overrides):
    before = (services.audio_bucket.list(""), services.datasets.list(""))
    response = start(client(services=services), **overrides)
    assert response.status_code == 422
    assert services.repository.list_runs() == {} and services.queue.tasks == []
    assert (services.audio_bucket.list(""), services.datasets.list("")) == before




def saved_upload(services, *, ready=True, has_gold=False):
    services.audio_bucket.write_json("uploads/saved/transcript.json", transcript())
    if has_gold:
        services.audio_bucket.write_json("uploads/saved/gold.json", gold())
    services.repository.create_upload(
        "saved",
        {
            "status": "ready" if ready else "awaiting_speakers",
            "has_gold": has_gold,
            "transcript_path": "uploads/saved/transcript.json",
            "gold_path": "uploads/saved/gold.json",
            "change_goal": "saved goal",
            "language": "en",
            "coded_span": {"start_turn": 0, "end_turn": 2},
        },
    )




@pytest.mark.parametrize("clients", [["Morgan"], ["Morgan", "Sam"]])
def test_named_text_upload_with_multiple_clients_runs_without_losing_speakers(services, clients):
    c = client(services=services)
    labels = ["Alex", *clients, "Alex", *clients]
    texts = ["synthetic clinician words " * 20, *[f"synthetic client {i} words" for i in range(len(clients))], "synthetic closing words", *[f"synthetic client {i} closing words" for i in range(len(clients))]]
    raw = "\n".join(f"{label}: {text}" for label, text in zip(labels, texts, strict=True))
    response = c.post(
        "/v1/uploads", headers=AUTH,
        files={"file": ("named-session.txt", raw.encode(), "text/plain")},
        data={"change_goal": "Synthetic change goal", "language": "en"},
    )
    assert response.status_code == 200, response.text
    upload = response.json()
    assert upload["status"] == "awaiting_speakers"
    upload_id = upload["upload_id"]
    selection = {"input": {"upload_id": upload_id}, "engines": ["oneshot:miti"]}
    assert start(c, **selection).status_code == 409
    ready = c.post(
        f"/v1/uploads/{upload_id}/speakers", headers=AUTH,
        json={"clinician_speaker": "Alex"},
    )
    assert ready.status_code == 200 and ready.json()["status"] == "ready"
    uploaded = services.repository.get_upload(upload_id)
    confirmed = services.audio_bucket.read_json(uploaded["transcript_path"])
    assert [turn["speaker"] for turn in confirmed["turns"]] == labels
    assert [turn["text"] for turn in confirmed["turns"]] == [text.strip() for text in texts]
    assert [turn["role"] for turn in confirmed["turns"]] == ["clinician", *["client"] * len(clients), "clinician", *["client"] * len(clients)]
    response = start(c, **selection)
    assert response.status_code == 200, response.text
    rid = response.json()["run_id"]
    ((sid, _),) = services.repository.get_run(rid)["sessions"].items()
    session = services.repo.get_session("eval-owner", sid)
    assert session.clinician_speaker == "Alex" and session.eval.source == "upload"
    stored = services.repo.get_transcript("eval-owner", sid, "current").transcript
    assert stored.model_dump(mode="json") == confirmed
    assert services.repo.list_runs("eval-owner", sid) == []  # nothing runs at create time




@pytest.mark.parametrize("invalid_speakers", ["unresolved", "no_client"])
def test_run_still_rejects_unresolved_or_missing_client(services, invalid_speakers):
    saved_upload(services)
    data = transcript(roles=invalid_speakers != "unresolved")
    if invalid_speakers == "no_client":
        for turn in data["turns"]:
            turn.update(speaker="T", role="clinician")
    services.audio_bucket.write_json("uploads/saved/transcript.json", data)
    response = start(client(services=services), input={"upload_id": "saved"}, engines=["miti"])
    assert response.status_code == 422
    assert services.repository.list_runs() == {} and services.queue.tasks == []


def test_upload_readiness_gold_gate_and_override_snapshot(services):
    saved_upload(services, has_gold=True)
    c = client(services=services)
    response = start(
        c,
        input={"upload_id": "saved"},
        change_goal="override goal",
        language="fr",
        coded_span={"start_turn": 0, "end_turn": 1},
    )
    assert response.status_code == 200, response.text
    rid = response.json()["run_id"]
    doc = services.repository.get_run(rid)
    assert (doc["change_goal"], doc["language"]) == ("override goal", "fr")
    assert doc["coded_span"] == {"start_turn": 0, "end_turn": 1} and doc["human"] is True
    ((sid, entry),) = doc["sessions"].items()
    assert entry["dataset_session_id"] == "saved"
    session = services.repo.get_session("eval-owner", sid)
    assert session.change_goal == "override goal" and session.language == "fr"
    assert session.coded_span.model_dump() == {"start_turn": 0, "end_turn": 1}
    assert session.eval.gold is not None  # gold copied once (the Human reference)
    # The session snapshot is immutable: corrupting the upload cannot change it.
    services.audio_bucket.write_json("uploads/saved/transcript.json", {"corrupted": True})
    assert services.repo.get_transcript("eval-owner", sid, "current").transcript is not None
    services.repository.update_upload("saved", {"has_gold": False})
    assert start(c, input={"upload_id": "saved"}).status_code == 422
    services.repository.update_upload("saved", {"status": "awaiting_speakers"})
    assert start(c, input={"upload_id": "saved"}, engines=["miti"]).status_code == 409


def test_bad_upload_span_before_writes(services):
    saved_upload(services)
    before = services.audio_bucket.list("")
    response = start(
        client(services=services),
        input={"upload_id": "saved"},
        engines=["miti"],
        coded_span={"start_turn": 0, "end_turn": 900},
    )
    assert response.status_code == 422
    assert services.audio_bucket.list("") == before and services.repository.list_runs() == {}




def test_firestore_batch_capacity_checked_before_writes(services):
    from test_app import ENV

    from onolys_eval_backend.config import EvalConfig
    from onolys_eval_backend.runs import RunRequest, create_run

    body = RunRequest.model_validate(
        {
            "input": {"dataset_id": "synthetic", "session_ids": [f"s-{i}" for i in range(500)]},
            "engines": ["human"],
            "selection": {},
            "repeats": 1,
        }
    )
    before = services.datasets.list("")
    with pytest.raises(ValueError, match="maximum is 499"):
        create_run(services, EvalConfig.from_env(ENV), body, "alice@example.com")
    assert services.repository.list_runs() == {} and services.datasets.list("") == before




def test_expansion_human_once_and_immutable_provenance(services):
    c = client(services=services)
    response = start(
        c,
        engines=["human", "miti", "oneshot:miti"],
        selection=SEL2,
        repeats=3,
    )
    assert response.status_code == 200, response.text
    rid = response.json()["run_id"]
    run = services.repository.get_run(rid)
    # 1 Human + 2 AI engines x 2 combos x 3 repeats = 13 planned; Human is done at creation.
    assert run["total_units"] == 13 and run["completed_units"] == 1
    assert [t["kind"] for t in services.queue.tasks] == ["tick"]
    assert run["created_by"] == "alice@example.com"
    assert run["engine_versions"]["oneshot:miti"] and run["engine_git_sha"]
    assert "presets" not in run and "resolved_presets" not in run["saved_config"]
    assert set(run["saved_config"]["resolved_combos"]) == {
        "claude/claude-sonnet-5-5/low",
        "claude/claude-sonnet-5-5/high",
    }
    ((sid, entry),) = run["sessions"].items()
    assert entry["dataset_session_id"] == "one" and entry["transcript_sha256"]
    assert services.repo.get_session("eval-owner", sid).eval.source == "dataset"


def test_eight_session_defaults_and_two_session_matrix(services):
    from copy import deepcopy

    source = services.datasets.read_json("datasets/synthetic/manifest.json")
    session = source["sessions"][0]
    source["sessions"] = []
    for number in range(8):
        sid = f"session-{number}"
        source["sessions"].append({**deepcopy(session), "session_id": sid})
        data = {**gold(), "session_id": sid}
        services.datasets.write_json(f"datasets/synthetic/{sid}/transcript.json", transcript())
        services.datasets.write_json(f"datasets/synthetic/{sid}/gold.json", data)
    services.datasets.write_json("datasets/synthetic/manifest.json", source)
    c = client(services=services)
    ids = [s["session_id"] for s in source["sessions"]]
    rid = start(c, input={"dataset_id": "synthetic", "session_ids": ids}).json()["run_id"]
    assert services.repository.get_run(rid)["total_units"] == 16
    rid = start(
        c,
        input={"dataset_id": "synthetic", "session_ids": ids[:2]},
        engines=["human", "miti", "oneshot:miti"],
        selection=SEL2,
        repeats=3,
    ).json()["run_id"]
    assert services.repository.get_run(rid)["total_units"] == 26


def test_dataset_full_session_null_span_creates_human_only_run_done(services):
    source = services.datasets.read_json("datasets/synthetic/manifest.json")
    source["sessions"][0]["coded_span"] = None
    services.datasets.write_json("datasets/synthetic/manifest.json", source)
    response = start(client(services=services), engines=["human"], selection={})
    assert response.status_code == 200, response.text
    run = services.repository.get_run(response.json()["run_id"])
    assert run["status"] == "done" and run["total_units"] == 1
    ((sid, _),) = run["sessions"].items()
    assert services.repo.get_session("eval-owner", sid).coded_span is None


def test_dataset_session_without_gold_runs_without_human_unit(services):
    # LM-11: human is only auto-added when every selected session has gold.
    services.datasets._objects.pop("datasets/synthetic/one/gold.json")
    response = start(client(services=services), engines=["miti"])
    assert response.status_code == 200, response.text
    run = services.repository.get_run(response.json()["run_id"])
    assert run["engines"] == ["miti"] and run["human"] is False and run["completed_units"] == 0


def test_explicit_human_without_gold_is_422_without_orphans(services):
    services.datasets._objects.pop("datasets/synthetic/one/gold.json")
    before = services.audio_bucket.list("")
    response = start(client(services=services), engines=["human", "miti"])
    assert response.status_code == 422 and "gold" in response.text
    assert services.repository.list_runs() == {} and services.queue.tasks == []
    assert services.audio_bucket.list("") == before


def test_oneshot_without_change_goal_is_422_before_writes(services):
    # B15: an empty goal would fail every one-shot cell at execution.
    saved_upload(services)
    services.repository.update_upload("saved", {"change_goal": ""})
    before = services.audio_bucket.list("")
    response = start(client(services=services), input={"upload_id": "saved"}, engines=["oneshot:miti"])
    assert response.status_code == 422 and "change goal" in response.text
    assert services.repository.list_runs() == {} and services.audio_bucket.list("") == before


def test_dataset_runs_never_read_the_audio_bucket(services):
    services.audio_bucket.read_json = services.audio_bucket.write_json = None  # would raise
    assert start(client(services=services)).status_code == 200
