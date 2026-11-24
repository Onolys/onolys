"""Run fanout and transactional unit execution using synthetic data only."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from onolys_engine_core.engine import EngineResult, RunInfo, RunUsage
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


@pytest.fixture
def services():
    registry = EngineRegistry()
    registry.register(MitiEngine())
    registry.register(OneshotEngine(config="miti"))
    s = SimpleNamespace(
        repository=InMemoryEvalRepository(),
        bucket=InMemoryBucket(),
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
    s.bucket.write_json("datasets/synthetic/manifest.json", source)
    s.bucket.write_json("datasets/synthetic/one/transcript.json", transcript())
    s.bucket.write_json("datasets/synthetic/one/gold.json", gold())
    s.engine = lambda engine_id: s.fake_engine
    s.llm_factory = lambda routes, metrics: SimpleNamespace(routes=routes)
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


def dispatch(c, run_id, unit_id):
    return c.post("/internal/tasks/unit", headers=AUTH, json={"run_id": run_id, "unit_id": unit_id})


class FakeEngine:
    name = "oneshot"
    version = OneshotEngine(config="miti").version
    accepts_feedback = True

    def __init__(self, *, invalid=False, fail=False):
        self.calls = []
        self.invalid, self.fail = invalid, fail

    def output_schema(self):
        return OneshotEngine(config="miti").output_schema()

    async def run(self, ctx, value, params, progress_cb=None):
        self.calls.append((ctx.feedback, params))
        if self.fail:
            raise ValueError("PRIVATE transcript exception")
        data = gold()
        return EngineResult(
            output={}
            if self.invalid
            else {"counts": data["counts"], "globals": data["globals"], "tips": []},
            run_info=RunInfo(
                usage=RunUsage(input_tokens=10, output_tokens=2, calls=1, cost_usd=0.1)
            ),
        )


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
    units = services.repository.list_units(rid)
    assert len(units) == 13 and run["total_units"] == 13
    assert len([u for u in units.values() if u["engine"] == "human"]) == 1
    assert all(t["kind"] == "unit" and t["payload"]["run_id"] == rid for t in services.queue.tasks)
    assert run["created_by"] == "alice@example.com"
    assert run["engine_versions"]["oneshot:miti"] and run["engine_git_sha"]
    assert "presets" not in run and "resolved_presets" not in run
    assert set(run["resolved_combos"]) == {
        "claude/claude-sonnet-5-5/low",
        "claude/claude-sonnet-5-5/high",
    }
    assert all(u["preset"] is None for u in units.values())
    saved = run["input_ref"]["sessions"][0]
    assert saved["coded_span"] == {"start_turn": 0, "end_turn": 2}
    assert saved["change_goal"] == "Test goal" and saved["transcript_sha256"]
    assert saved["transcript_path"].startswith(f"runs/{rid}/inputs/")


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
    before = services.bucket.list("")
    response = start(client(services=services), **overrides)
    assert response.status_code == 422
    assert services.repository.list_runs() == {} and services.queue.tasks == []
    assert services.bucket.list("") == before


def test_human_no_llm_terminal_redelivery_and_cancel(services):
    c = client(services=services)
    rid = start(c).json()["run_id"]
    units = services.repository.list_units(rid)
    human = next(k for k, u in units.items() if u["engine"] == "human")
    ai = next(k for k, u in units.items() if u["engine"] == "miti")
    assert dispatch(c, rid, human).status_code == 200
    assert dispatch(c, rid, human).status_code == 200
    assert services.repository.get_run(rid)["completed_units"] == 1
    assert c.post(f"/v1/runs/{rid}/cancel", headers=AUTH).status_code == 200
    assert dispatch(c, rid, ai).status_code == 200
    run = services.repository.get_run(rid)
    assert run["status"] == "partial" and run["completed_units"] == 2
    assert services.repository.get_unit(rid, ai)["status"] == "cancelled"


@pytest.mark.parametrize(
    "invalid,feedback,attempts", [(False, True, 1), (True, True, 2), (True, False, 1)]
)
def test_shared_wrapper_attempts_and_billable_failures(services, invalid, feedback, attempts):
    engine = services.fake_engine = FakeEngine(invalid=invalid)
    engine.accepts_feedback = feedback
    c = client(services=services)
    rid = start_ai(services, c, engines=["oneshot:miti"]).json()["run_id"]
    uid = next(iter(services.repository.list_units(rid)))
    assert dispatch(c, rid, uid).status_code == 200
    assert dispatch(c, rid, uid).status_code == 200
    unit = services.repository.get_unit(rid, uid)
    run = services.repository.get_run(rid)
    assert len(engine.calls) == attempts
    assert unit["status"] == ("failed" if invalid else "done")
    assert run["status"] == ("failed" if invalid else "done")
    assert unit["run_info"]["usage"]["input_tokens"] == attempts * 10
    assert run["usage"]["input_tokens"] == attempts * 10
    assert run["cost_usd_est"] == pytest.approx(attempts * 0.1)
    assert engine.calls[0][1]["config"] == "miti"
    assert engine.calls[0][1]["speaker_map"] == {"subject": "T", "other": "C"}
    if invalid:
        assert unit["error"]["code"] == "output_invalid"


def test_simultaneous_claims_execute_only_once(services):
    from onolys_eval_backend.runs import execute_unit

    entered, release = Event(), Event()
    engine = services.fake_engine = FakeEngine()
    original = engine.run

    async def waiting(*args, **kwargs):
        entered.set()
        release.wait(5)
        return await original(*args, **kwargs)

    engine.run = waiting
    c = client(services=services)
    rid = start(c, engines=["oneshot:miti"]).json()["run_id"]
    uid = next(iter(services.repository.list_units(rid)))
    with ThreadPoolExecutor() as pool:
        first = pool.submit(asyncio.run, execute_unit(services, rid, uid))
        assert entered.wait(5)
        asyncio.run(execute_unit(services, rid, uid))
        release.set()
        first.result()
    assert len(engine.calls) == 1
    assert services.repository.get_run(rid)["completed_units"] == 1


@pytest.mark.parametrize("read_method", ["get_run", "get_unit"])
def test_transient_execution_snapshot_read_failure_can_retry(services, monkeypatch, read_method):
    engine = services.fake_engine = FakeEngine()
    c = client(services=services)
    rid = start(c, engines=["oneshot:miti"]).json()["run_id"]
    uid = next(iter(services.repository.list_units(rid)))
    repository = services.repository
    original_read = getattr(repository, read_method)
    original_transact = repository.transact_unit
    in_transaction = False
    fail_next = True

    def transact(*args):
        nonlocal in_transaction
        in_transaction = True
        try:
            return original_transact(*args)
        finally:
            in_transaction = False

    def flaky_read(*args):
        nonlocal fail_next
        # Firestore transaction reads do not call the standalone repository getters.
        if not in_transaction and fail_next:
            fail_next = False
            raise RuntimeError("PRIVATE storage details")
        return original_read(*args)

    monkeypatch.setattr(repository, "transact_unit", transact)
    monkeypatch.setattr(repository, read_method, flaky_read)
    c = TestClient(c.app, raise_server_exceptions=False)
    response = dispatch(c, rid, uid)
    assert response.status_code == 500
    assert "PRIVATE" not in response.text
    assert engine.calls == []
    assert repository.get_unit(rid, uid)["status"] == "queued"
    assert dispatch(c, rid, uid).status_code == 200
    assert dispatch(c, rid, uid).status_code == 200
    assert repository.get_unit(rid, uid)["status"] == "done"
    assert repository.get_run(rid)["completed_units"] == 1
    assert len(engine.calls) == 1


@pytest.mark.parametrize("changed", ["sha", "version", "models"])
def test_execution_config_drift_fails_before_provider_work(services, monkeypatch, changed):
    engine = services.fake_engine = FakeEngine()
    monkeypatch.setenv("GIT_SHA", "before-deployment")
    c = client(services=services)
    rid = start_ai(services, c, engines=["oneshot:miti"]).json()["run_id"]
    uid = next(iter(services.repository.list_units(rid)))
    factory = services.llm_factory = Mock(wraps=services.llm_factory)
    if changed == "sha":
        monkeypatch.setenv("GIT_SHA", "after-deployment")
    elif changed == "version":
        engine.version = "after-deployment"
    else:
        services.models = {
            k: replace(m, provider="changed-provider") for k, m in services.models.items()
        }
    assert dispatch(c, rid, uid).status_code == 200
    assert dispatch(c, rid, uid).status_code == 200
    unit = services.repository.get_unit(rid, uid)
    run = services.repository.get_run(rid)
    assert unit["status"] == "failed"
    assert unit["error"] == {"code": "execution_config_changed", "retryable": False}
    assert run["status"] == "failed" and run["completed_units"] == 1
    assert run["usage"]["calls"] == 0 and run["cost_usd_est"] == 0
    assert engine.calls == []
    factory.assert_not_called()


def test_rerun_uses_current_execution_snapshot_and_matching_config_runs(services, monkeypatch):
    engine = services.fake_engine = FakeEngine()
    monkeypatch.setenv("GIT_SHA", "before-deployment")
    c = client(services=services)
    rid = start(c, engines=["oneshot:miti"]).json()["run_id"]
    original = services.repository.get_run(rid)
    monkeypatch.setenv("GIT_SHA", "after-deployment")
    engine.version = "after-deployment"
    monkeypatch.setattr(services.registry.get("oneshot"), "version", engine.version)
    response = c.post(
        f"/v1/runs/{rid}/rerun", headers=AUTH,
        json={"engines": ["oneshot:miti"], "selection": SEL1, "repeats": 1},
    )
    assert response.status_code == 200, response.text
    rerun_id = response.json()["run_id"]
    saved = services.repository.get_run(rerun_id)
    assert saved["engine_git_sha"] == "after-deployment" != original["engine_git_sha"]
    assert saved["engine_versions"]["oneshot:miti"] == engine.version
    assert saved["resolved_combos"]["claude/claude-sonnet-5-5/low"]["litellm_id"] == (
        "anthropic/claude-sonnet-5-5"
    )
    uid = next(iter(services.repository.list_units(rerun_id)))
    assert dispatch(c, rerun_id, uid).status_code == 200
    assert services.repository.get_unit(rerun_id, uid)["status"] == "done"
    assert len(engine.calls) == 1


def test_human_gold_remains_available_after_runtime_config_changes(services, monkeypatch):
    c = client(services=services)
    rid = start(c, engines=["human"]).json()["run_id"]
    monkeypatch.setenv("GIT_SHA", "after-deployment")
    services.routes.raw_routes["oneshot"]["litellm_id"] = "synthetic/changed-model"
    uid = next(iter(services.repository.list_units(rid)))
    assert dispatch(c, rid, uid).status_code == 200
    assert services.repository.get_unit(rid, uid)["status"] == "done"


def test_queue_partial_failure_finishes_unqueued_units(services):
    original = services.queue.enqueue
    calls = 0

    def flaky(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("PRIVATE queue details")
        original(*args, **kwargs)

    services.queue.enqueue = flaky
    c = client(services=services)
    response = start(c)
    assert response.status_code == 200
    rid = response.json()["run_id"]
    assert "PRIVATE" not in response.text
    for task in services.queue.tasks:
        assert dispatch(c, **task["payload"]).status_code == 200
    run = services.repository.get_run(rid)
    assert run["status"] == "partial" and run["completed_units"] == 2


def start_ai(services, c, **overrides):
    """AI-only run: an upload without gold, since dataset runs always add human."""
    saved_upload(services)
    return start(c, input={"upload_id": "saved"}, **overrides)


def saved_upload(services, *, ready=True, has_gold=False):
    services.bucket.write_json("uploads/saved/transcript.json", transcript())
    if has_gold:
        services.bucket.write_json("uploads/saved/gold.json", gold())
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
    engine = services.fake_engine = FakeEngine()
    original_run = engine.run
    observed = []

    async def capture(ctx, value, params, progress_cb=None):
        observed.append(value.model_dump(mode="json"))
        return await original_run(ctx, value, params, progress_cb)

    engine.run = capture
    c = client(services=services)
    labels = ["Alex", *clients, "Alex"]
    texts = ["synthetic clinician words " * 20, *[f"synthetic client {i} words" for i in range(len(clients))], "synthetic closing words"]
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
    confirmed = services.bucket.read_json(uploaded["transcript_path"])
    assert [turn["speaker"] for turn in confirmed["turns"]] == labels
    assert [turn["text"] for turn in confirmed["turns"]] == [text.strip() for text in texts]
    assert [turn["role"] for turn in confirmed["turns"]] == ["clinician", *["client"] * len(clients), "clinician"]
    response = start(c, **selection)
    assert response.status_code == 200, response.text
    rid = response.json()["run_id"]
    source = services.repository.get_run(rid)["input_ref"]["sessions"][0]
    expected_map = {"subject": "Alex", **({"other": clients[0]} if len(clients) == 1 else {})}
    assert source["speaker_map"] == expected_map
    assert services.bucket.read_json(source["transcript_path"]) == confirmed
    uid = next(iter(services.repository.list_units(rid)))
    assert dispatch(c, rid, uid).status_code == 200
    assert services.repository.get_unit(rid, uid)["status"] == "done"
    assert observed == [confirmed]
    assert len(engine.calls) == 1 and engine.calls[0][1]["speaker_map"] == expected_map


@pytest.mark.parametrize("invalid_speakers", ["unresolved", "no_client"])
def test_run_still_rejects_unresolved_or_missing_client(services, invalid_speakers):
    saved_upload(services)
    data = transcript(roles=invalid_speakers != "unresolved")
    if invalid_speakers == "no_client":
        for turn in data["turns"]:
            turn.update(speaker="T", role="clinician")
    services.bucket.write_json("uploads/saved/transcript.json", data)
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
    saved = services.repository.get_run(rid)["input_ref"]["sessions"][0]
    assert saved["change_goal"] == "override goal" and saved["language"] == "fr"
    assert saved["coded_span"] == {"start_turn": 0, "end_turn": 1}
    human = next(u for u in services.repository.list_units(rid).values() if u["engine"] == "human")
    assert human["coded_span"] == {"start_turn": 0, "end_turn": 2}
    assert human["warnings"] == ["human_span_differs"]
    services.bucket.write_json("uploads/saved/transcript.json", {"corrupted": True})
    from onolys_engine_core.transcript_input import validate_transcript_input

    assert services.bucket.read_json(saved["transcript_path"]) == validate_transcript_input(
        transcript()
    ).model_dump(mode="json")
    services.repository.update_upload("saved", {"has_gold": False})
    assert start(c, input={"upload_id": "saved"}).status_code == 422
    services.repository.update_upload("saved", {"status": "awaiting_speakers"})
    assert start(c, input={"upload_id": "saved"}, engines=["miti"]).status_code == 409


def test_bad_upload_span_before_writes(services):
    saved_upload(services)
    before = services.bucket.list("")
    response = start(
        client(services=services),
        input={"upload_id": "saved"},
        engines=["miti"],
        coded_span={"start_turn": 0, "end_turn": 900},
    )
    assert response.status_code == 422
    assert services.bucket.list("") == before and services.repository.list_runs() == {}


def test_all_cancelled_and_mixed_failure_finalization(services):
    c = client(services=services)
    rid = start(c).json()["run_id"]
    assert c.post(f"/v1/runs/{rid}/cancel", headers=AUTH).json()["status"] == "failed"
    assert services.repository.get_run(rid)["cancelled_units"] == 2
    assert all(u["status"] == "cancelled" for u in services.repository.list_units(rid).values())
    services.fake_engine = FakeEngine(fail=True)
    rid = start(c, engines=["human", "oneshot:miti"]).json()["run_id"]
    for uid in services.repository.list_units(rid):
        assert dispatch(c, rid, uid).status_code == 200
    run = services.repository.get_run(rid)
    assert run["status"] == "partial" and run["failed_units"] == 1 and run["done_units"] == 1
    assert "PRIVATE" not in str(services.repository.list_units(rid))


def test_real_oneshot_with_fake_llm_and_real_lean_invalid_wrapper(services, monkeypatch):
    from onolys_engine_core.llm.types import LLMResult, Usage

    calls = []

    class FakeLLM:
        def __init__(self, routes):
            self.routes = routes

        async def complete_json(self, request, metrics):
            calls.append(request)
            usage = Usage(input_tokens=7, output_tokens=3, cost_usd=0.02)
            metrics.record(request, "synthetic/model", usage, 1, 1, True)
            return LLMResult(parsed={}, usage=usage, model="synthetic/model")

    services.llm_factory = lambda routes, metrics: FakeLLM(routes)
    services.engine = lambda engine_id: (
        OneshotEngine(config="miti") if ":" in engine_id else MitiEngine()
    )
    lean_calls = []

    async def invalid_lean(self, ctx, value, params, progress_cb=None):
        lean_calls.append(params)
        return EngineResult(
            output={},
            run_info=RunInfo(
                usage=RunUsage(input_tokens=7, output_tokens=3, calls=1, cost_usd=0.02)
            ),
        )

    monkeypatch.setattr(MitiEngine, "run", invalid_lean)
    c = client(services=services)
    rid = start_ai(services, c, engines=["miti", "oneshot:miti"]).json()["run_id"]
    for uid in services.repository.list_units(rid):
        assert dispatch(c, rid, uid).status_code == 200
    assert len(lean_calls) == 1 and len(calls) == 2
    assert calls[0].deadline is not None
    from onolys_engine_core.transcript_v1 import TranscriptV1
    from onolys_miti.prepare import mark_roles

    roles, _ = mark_roles(TranscriptV1.model_validate(transcript()), lean_calls[0]["speaker_map"])
    assert [turn.role for turn in roles] == ["subject", "other"]
    run = services.repository.get_run(rid)
    assert run["status"] == "failed" and run["usage"]["input_tokens"] == 21
    assert run["cost_usd_est"] == pytest.approx(0.06)


def test_exception_keeps_metrics_usage_and_unknown_pricing(services):
    from onolys_engine_core.llm.types import LLMRequest, Usage

    services.fake_engine = FakeEngine()

    async def fail(ctx, value, params, progress_cb=None):
        ctx.metrics.record(
            LLMRequest(tier="oneshot", system="", user="", call_tag="test", response_schema={}),
            "unknown/model",
            Usage(input_tokens=11, output_tokens=4),
            1,
            1,
            False,
        )
        raise RuntimeError("PRIVATE transcript")

    services.fake_engine.run = fail
    c = client(services=services)
    rid = start(c, engines=["oneshot:miti"]).json()["run_id"]
    uid = next(iter(services.repository.list_units(rid)))
    assert dispatch(c, rid, uid).status_code == 200
    unit = services.repository.get_unit(rid, uid)
    run = services.repository.get_run(rid)
    assert unit["run_info"]["usage"]["input_tokens"] == 11
    assert run["unpriced_units"] == 1 and run["usage"]["cost_usd"] is None
    assert "PRIVATE" not in str(unit)


def test_unit_queue_target_and_deadline():
    import json

    from test_app import ENV

    from onolys_eval_backend.config import EvalConfig
    from onolys_eval_backend.queue import CloudTasksQueue

    calls = []
    CloudTasksQueue(
        EvalConfig.from_env(ENV), SimpleNamespace(create_task=lambda **kwargs: calls.append(kwargs))
    ).enqueue("unit", {"run_id": "r", "unit_id": "u"})
    task = calls[0]["task"]
    assert calls[0]["parent"] == ENV["TASKS_QUEUE"]
    assert task["http_request"]["url"] == ENV["SERVICE_URL"] + "/internal/tasks/unit"
    assert task["http_request"]["oidc_token"]["audience"] == ENV["SERVICE_URL"]
    assert task["http_request"]["oidc_token"]["service_account_email"] == ENV["TASKS_SA"]
    assert json.loads(task["http_request"]["body"]) == {"run_id": "r", "unit_id": "u"}
    assert task["dispatch_deadline"] == {"seconds": 900}


def test_eight_session_defaults_and_two_session_matrix(services):
    from copy import deepcopy

    source = services.bucket.read_json("datasets/synthetic/manifest.json")
    session = source["sessions"][0]
    source["sessions"] = []
    for number in range(8):
        sid = f"session-{number}"
        source["sessions"].append({**deepcopy(session), "session_id": sid})
        data = {**gold(), "session_id": sid}
        services.bucket.write_json(f"datasets/synthetic/{sid}/transcript.json", transcript())
        services.bucket.write_json(f"datasets/synthetic/{sid}/gold.json", data)
    services.bucket.write_json("datasets/synthetic/manifest.json", source)
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


def test_concurrent_terminal_accounting_once_and_last_unit_status(services):
    from onolys_eval_backend.runs import finish_unit

    c = client(services=services)
    rid = start(
        c,
        engines=["human", "miti", "oneshot:miti"],
        selection=SEL2,
        repeats=3,
    ).json()["run_id"]
    uids = list(services.repository.list_units(rid))

    def finish(uid):
        return finish_unit(services.repository, rid, uid, {"status": "done"})

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(finish, uids * 3)) == 13
    run = services.repository.get_run(rid)
    assert run["status"] == "done" and run["completed_units"] == 13 and run["done_units"] == 13


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
    before = services.bucket.list("")
    with pytest.raises(ValueError, match="maximum is 499"):
        create_run(services, EvalConfig.from_env(ENV), body, "alice@example.com")
    assert services.repository.list_runs() == {} and services.bucket.list("") == before


def test_success_spills_large_output_and_uses_model_price_fallback(services):
    from onolys_eval_backend.costs import PriceBook
    from onolys_eval_backend.storage import INLINE_OUTPUT_LIMIT, load_output

    services.prices = PriceBook(
        {
            "anthropic/claude-sonnet-5-5": {
                "input_usd_per_million": 2,
                "output_usd_per_million": 8,
            }
        }
    )
    engine = services.fake_engine = FakeEngine()
    original = engine.run

    async def large(*args, **kwargs):
        result = await original(*args, **kwargs)
        result.run_info.usage.cost_usd = None
        result.output["tips"] = [
            {
                "rank": 1,
                "item_id": "gi",
                "observation": "x" * INLINE_OUTPUT_LIMIT,
                "alternative": "synthetic",
                "why_it_matters": "synthetic",
            }
        ]
        return result

    engine.run = large
    c = client(services=services)
    rid = start(c, engines=["oneshot:miti"]).json()["run_id"]
    uid = next(iter(services.repository.list_units(rid)))
    assert dispatch(c, rid, uid).status_code == 200
    unit = services.repository.get_unit(rid, uid)
    assert unit["status"] == "done" and unit["output"] is None
    assert unit["output_ref"] == f"runs/{rid}/{uid}.json"
    assert len(load_output(services.bucket, unit)["tips"][0]["observation"]) == INLINE_OUTPUT_LIMIT
    assert unit["cost_usd_est"] == pytest.approx((10 * 2 + 2 * 8) / 1_000_000)
    assert unit["unpriced"] is False


def test_price_metadata_failure_cannot_strand_billable_unit(services):
    class BrokenPrices:
        def estimate(self, usage, model):
            raise ValueError("PRIVATE price configuration")

    services.prices = BrokenPrices()
    engine = services.fake_engine = FakeEngine()
    original = engine.run

    async def unpriced(*args, **kwargs):
        result = await original(*args, **kwargs)
        result.run_info.usage.cost_usd = None
        return result

    engine.run = unpriced
    c = client(services=services)
    rid = start_ai(services, c, engines=["oneshot:miti"]).json()["run_id"]
    uid = next(iter(services.repository.list_units(rid)))
    assert dispatch(c, rid, uid).status_code == 200
    run = services.repository.get_run(rid)
    assert run["status"] == "done" and run["unpriced_units"] == 1
    assert run["usage"]["input_tokens"] == 10


def test_internal_creation_helper_can_reuse_immutable_saved_input(services):
    from test_app import ENV

    from onolys_eval_backend.config import EvalConfig
    from onolys_eval_backend.runs import RunRequest, create_run

    c = client(services=services)
    original = start(c).json()["run_id"]
    snapshot = services.repository.get_run(original)["input_ref"]
    services.bucket.write_json("datasets/synthetic/one/transcript.json", {"changed": True})
    services.bucket.write_json("datasets/synthetic/manifest.json", {"changed": True})
    body = RunRequest.model_validate(
        {
            "input": {"dataset_id": "synthetic", "session_ids": ["one"]},
            "engines": ["oneshot:miti"],
            "selection": SEL1,
            "repeats": 3,
        }
    )
    rid, status = create_run(
        services, EvalConfig.from_env(ENV), body, "alice@example.com", input_ref=snapshot
    )
    saved = services.repository.get_run(rid)["input_ref"]["sessions"][0]
    assert saved["transcript_sha256"] == snapshot["sessions"][0]["transcript_sha256"]
    assert saved["change_goal"] == snapshot["sessions"][0]["change_goal"]
    assert saved["coded_span"] == snapshot["sessions"][0]["coded_span"]
    assert status == "queued" and services.repository.get_run(rid)["total_units"] == 4


def test_dataset_full_session_null_span_creates_and_executes_human_unit(services):
    source = services.bucket.read_json("datasets/synthetic/manifest.json")
    source["sessions"][0]["coded_span"] = None
    services.bucket.write_json("datasets/synthetic/manifest.json", source)
    c = client(services=services)
    response = start(c, engines=["human"], selection={})
    assert response.status_code == 200, response.text
    rid = response.json()["run_id"]
    saved = services.repository.get_run(rid)["input_ref"]["sessions"][0]
    assert saved["coded_span"] is None
    uid = next(iter(services.repository.list_units(rid)))
    assert dispatch(c, rid, uid).status_code == 200
    assert services.repository.get_run(rid)["status"] == "done"
    assert services.repository.get_unit(rid, uid)["scores"]["counts"] == gold()["counts"]


def test_dataset_session_without_gold_is_422_without_orphans(services):
    # Human is auto-added for datasets, so a missing gold must be rejected cleanly (no
    # TypeError/503) even when the body omits `human`.
    services.bucket._objects.pop("datasets/synthetic/one/gold.json")
    before = services.bucket.list("")
    response = start(client(services=services), engines=["miti"])
    assert response.status_code == 422, response.text
    assert services.repository.list_runs() == {} and services.queue.tasks == []
    assert services.bucket.list("") == before


def test_combo_unit_executes_on_combo_routes(services):
    engine = services.fake_engine = FakeEngine()
    seen = []
    services.llm_factory = lambda routes, metrics: seen.append(routes) or SimpleNamespace(
        routes=routes
    )
    c = client(services=services)
    rid = start_ai(services, c, engines=["oneshot:miti"], selection=SEL2).json()["run_id"]
    run = services.repository.get_run(rid)
    assert run["resolved_combos"]["claude/claude-sonnet-5-5/high"] == {
        "litellm_id": "anthropic/claude-sonnet-5-5",
        "effort": "high",
        "max_output_tokens": 48000,
        "context_tokens": 1000000,
        "supports_temperature": False,
        "caching_mode": "anthropic_ephemeral",
    }
    units = services.repository.list_units(rid)
    uid = next(u for u, v in units.items() if v["combo"]["effort"] == "high")
    assert dispatch(c, rid, uid).status_code == 200
    assert services.repository.get_unit(rid, uid)["status"] == "done"
    (routes,) = seen
    route = routes["oneshot"]
    assert route.litellm_id == "anthropic/claude-sonnet-5-5"
    assert route.extra_params["reasoning_effort"] == "high"
    assert route.max_output_tokens == 48000 and route.timeout_s == 300
    ((_, params),) = engine.calls
    assert params["preset"] is None


def test_legacy_preset_unit_still_executes_via_preset_branch(services):
    engine = services.fake_engine = FakeEngine()
    seen = []
    services.llm_factory = lambda routes, metrics: seen.append(routes) or SimpleNamespace(
        routes=routes
    )
    c = client(services=services)
    rid = start_ai(services, c, engines=["oneshot:miti"]).json()["run_id"]
    uid = next(iter(services.repository.list_units(rid)))
    services.repository.update_run(
        rid,
        {"resolved_presets": {"configured-prod": {"oneshot": "synthetic/model"}},
         "resolved_combos": {}},
    )
    services.repository.update_unit(
        rid, uid, {"preset": "configured-prod", "combo": None, "combo_key": None}
    )
    assert dispatch(c, rid, uid).status_code == 200
    assert services.repository.get_unit(rid, uid)["status"] == "done"
    assert seen[0]["oneshot"].litellm_id == "synthetic/model"
    ((_, params),) = engine.calls
    assert params["preset"] == "configured-prod"


# ---- Task 5: unit retry on transient errors (R7, D5, D6, AC5) ----


class _Err:
    @staticmethod
    def make(cls, **attrs):
        e = cls("provider said no")
        for k, v in attrs.items():
            setattr(e, k, v)
        return e


def _scripted(services, script, usage_per_attempt=True):
    """Engine whose n-th call raises script[n] (an exception) or succeeds when it is None."""
    from onolys_engine_core.llm.types import LLMRequest, Usage

    engine = services.fake_engine = FakeEngine()
    ok = engine.run
    engine.n = 0

    async def run(ctx, value, params, progress_cb=None):
        step = script[min(engine.n, len(script) - 1)]
        engine.n += 1
        if usage_per_attempt:
            ctx.metrics.record(
                LLMRequest(tier="oneshot", system="", user="", call_tag="t", response_schema={}),
                "unknown/model",
                Usage(input_tokens=7, output_tokens=1),
                1,
                1,
                False,
            )
        if step is not None:
            raise step
        return await ok(ctx, value, params, progress_cb)

    engine.run = run
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)

    services.sleep = fake_sleep
    return engine, sleeps


def _one_unit(services, **kw):
    c = client(services=services)
    rid = start_ai(services, c, engines=["oneshot:miti"], **kw).json()["run_id"]
    uid = next(iter(services.repository.list_units(rid)))
    return c, rid, uid


def test_retry_503_then_success(services):
    from onolys_engine_core.llm.errors import LLMUnavailable

    engine, sleeps = _scripted(services, [_Err.make(LLMUnavailable, http_status=503), None])
    c, rid, uid = _one_unit(services)
    assert dispatch(c, rid, uid).status_code == 200
    unit = services.repository.get_unit(rid, uid)
    assert unit["status"] == "done" and unit["attempts"] == 2
    assert len(sleeps) == 1 and 2.5 <= sleeps[0] <= 5
    assert services.repository.get_run(rid)["status"] == "done"
    # failed attempt's metrics usage (7 in) is summed with the success usage (10 in)
    assert unit["run_info"]["usage"]["input_tokens"] == 17


def test_three_429_fail_with_all_attempt_usage(services):
    from onolys_engine_core.llm.errors import LLMRateLimited

    # Real shape: the client marks no_retry=True once its own backoff has used the deadline.
    err = _Err.make(LLMRateLimited, no_retry=True, http_status=429, retry_after=None)
    engine, sleeps = _scripted(services, [err])
    c, rid, uid = _one_unit(services)
    assert dispatch(c, rid, uid).status_code == 200
    unit = services.repository.get_unit(rid, uid)
    assert unit["status"] == "failed" and unit["attempts"] == 3 and engine.n == 3
    assert unit["error"] == {"code": "llm_rate_limited", "retryable": True}
    assert unit["run_info"]["usage"]["input_tokens"] == 21
    assert services.repository.get_run(rid)["usage"]["input_tokens"] == 21
    assert len(sleeps) == 2
    assert 2.5 <= sleeps[0] <= 5 and 10 <= sleeps[1] <= 20


def test_all_runs_failed_wrapping_transient_is_retried(services):
    from onolys_engine_core.llm.errors import LLMTimeout
    from onolys_miti.run import AllRunsFailed

    try:
        try:
            raise LLMTimeout("t")
        except LLMTimeout as inner:
            raise AllRunsFailed("all 1 run(s) failed") from inner
    except AllRunsFailed as wrapped:
        err = wrapped
    engine, _ = _scripted(services, [err, None])
    c, rid, uid = _one_unit(services)
    dispatch(c, rid, uid)
    unit = services.repository.get_unit(rid, uid)
    assert unit["status"] == "done" and unit["attempts"] == 2


def _with_cause(err, cause):
    err.__cause__ = cause
    return err


def _permanent_cases():
    from onolys_engine_core.errors import ConfigError, InputError
    from onolys_engine_core.llm.errors import LLMBadOutput, LLMUnavailable
    from onolys_miti.run import AllRunsFailed

    def wrapped(inner):
        try:
            try:
                raise inner
            except Exception as e:
                raise AllRunsFailed("all failed") from e
        except AllRunsFailed as w:
            return w

    return {
        "bad_output": LLMBadOutput("truncated"),
        "auth_401": _Err.make(LLMUnavailable, http_status=401),
        "bad_request_400": _Err.make(LLMUnavailable, http_status=400),
        "not_found_404": _Err.make(LLMUnavailable, http_status=404),
        "context_window_400_cause": _with_cause(
            _Err.make(LLMUnavailable, http_status=400, error_type="ContextWindowExceededError"),
            _Err.make(Exception, status_code=400),
        ),
        "unprocessable_422_cause": _with_cause(
            _Err.make(LLMUnavailable, http_status=422), _Err.make(Exception, status_code=422)
        ),
        "auth_error_type": _Err.make(LLMUnavailable, error_type="auth"),
        "all_runs_failed_auth": wrapped(_Err.make(LLMUnavailable, http_status=401)),
        "input_error": InputError("bad"),
        "config_error": ConfigError("bad"),
    }


@pytest.mark.parametrize("name", list(_permanent_cases()))
def test_permanent_errors_make_one_attempt(services, name):
    err = _permanent_cases()[name]
    engine, sleeps = _scripted(services, [err])
    c, rid, uid = _one_unit(services)
    dispatch(c, rid, uid)
    unit = services.repository.get_unit(rid, uid)
    assert unit["status"] == "failed" and unit["attempts"] == 1 and engine.n == 1
    assert unit["error"]["retryable"] is False and sleeps == []


def test_cancel_requested_during_attempt_stops_retrying(services):
    from onolys_engine_core.llm.errors import LLMUnavailable

    engine, sleeps = _scripted(services, [_Err.make(LLMUnavailable, http_status=503), None])
    c, rid, uid = _one_unit(services)
    scripted = engine.run

    async def run_then_cancel(ctx, value, params, progress_cb=None):
        services.repository.cancel_run(rid)  # cancel lands while the attempt is in flight
        return await scripted(ctx, value, params, progress_cb)

    engine.run = run_then_cancel
    dispatch(c, rid, uid)
    unit = services.repository.get_unit(rid, uid)
    assert engine.n == 1 and sleeps == []
    assert unit["status"] == "failed" and unit["attempts"] == 1
    assert unit["error"] == {"code": "llm_unavailable", "retryable": True}
    assert unit["run_info"]["usage"]["input_tokens"] == 7


def test_drift_guard_is_not_retried(services, monkeypatch):
    engine, sleeps = _scripted(services, [None])
    c, rid, uid = _one_unit(services)
    monkeypatch.setattr("onolys_eval_backend.runs._git_sha", lambda: "changed")
    dispatch(c, rid, uid)
    unit = services.repository.get_unit(rid, uid)
    assert unit["error"] == {"code": "execution_config_changed", "retryable": False}
    assert engine.n == 0 and sleeps == []


def test_no_retry_when_budget_under_120s(services, monkeypatch):
    from onolys_engine_core.llm.errors import LLMUnavailable

    engine, sleeps = _scripted(services, [_Err.make(LLMUnavailable, http_status=503), None])
    # clock: 800 s elapse during the first attempt, leaving 40 s of the 840 s budget
    ticks = iter([0, 0, 800, 800, 800, 800, 800])
    monkeypatch.setattr("onolys_eval_backend.runs.monotonic", lambda: next(ticks, 800))
    c, rid, uid = _one_unit(services)
    dispatch(c, rid, uid)
    unit = services.repository.get_unit(rid, uid)
    assert unit["status"] == "failed" and unit["attempts"] == 1 and sleeps == []
    assert unit["error"] == {"code": "llm_unavailable", "retryable": True}


def test_sibling_units_unaffected(services):
    from onolys_engine_core.llm.errors import LLMUnavailable

    engine, _ = _scripted(
        services, [_Err.make(LLMUnavailable, http_status=503), None, None], usage_per_attempt=False
    )
    c, rid, _ = _one_unit(services, selection=SEL2)
    units = list(services.repository.list_units(rid))
    for u in units:
        dispatch(c, rid, u)
    got = [services.repository.get_unit(rid, u) for u in units]
    assert sorted(u["attempts"] for u in got if u["engine"] != "human") == [1, 2]
    assert all(u["status"] == "done" for u in got)
