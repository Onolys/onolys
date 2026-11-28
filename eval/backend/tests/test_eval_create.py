"""Eval run create/rerun on the grouping doc: no RunDocs at create time."""

import json
from copy import deepcopy

from test_app import AUTH, client
from test_runs import SEL1, SEL2, start

from onolys_eval_backend.eval_group import build_group_doc, session_entry
from onolys_eval_backend.matrix import MAX_UNITS

pytest_plugins = ["test_runs"]
UID = "eval-owner"


def rerun(c, rid, **changes):
    return c.post(
        f"/v1/runs/{rid}/rerun", headers=AUTH,
        json={"engines": ["human", "miti"], "selection": SEL1, "repeats": 1, **changes},
    )


def sessions_of(services):
    return [p for p in services.repo._docs if p.startswith("sessions/") and p.count("/") == 1]


def test_create_response_shape_and_group_doc_without_run_docs(services):
    c = client(services=services)
    response = start(c, engines=["miti"], selection=SEL2, repeats=3, name="N", description="D")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"run_id", "status", "engines"}
    assert body["status"] == "queued" and body["engines"] == ["miti", "human"]
    rid = body["run_id"]
    doc = services.repository.get_run(rid)
    # one dataset session x (human + 2 combos x 3 repeats)
    assert (doc["total_units"], doc["completed_units"], doc["done_units"]) == (7, 1, 1)
    assert doc["created_by"] == "alice@example.com" and doc["human"] is True
    assert (doc["name"], doc["description"], doc["repeats"]) == ("N", "D", 3)
    assert (doc["tick_seq"], doc["skipped_units"], doc["cancel_requested"]) == (1, 0, False)
    assert doc["consecutive_failures"] == doc["provider_skips"] == doc["cells_wait"] == {}
    assert doc["saved_config"]["base_preset"] == "configured-prod"
    assert set(doc["saved_config"]["resolved_combos"]) == {
        "claude/claude-sonnet-5-5/low", "claude/claude-sonnet-5-5/high"}
    assert "input_ref" not in doc
    ((sid, entry),) = doc["sessions"].items()
    assert len(sid) == 32 and entry["dataset_session_id"] == "one" and entry["runs"] == []
    assert (entry["order"], entry["cursor"], entry["active_run_id"]) == (0, 0, None)
    assert services.repo.list_runs(UID, sid) == []  # no RunDoc at create time
    assert services.repo.get_session(UID, sid).eval.dataset_session_id == "one"
    assert services.queue.tasks == [
        {"kind": "tick", "payload": {"eval_run_id": rid, "n": 1}, "delay_seconds": 0}
    ]


def test_human_auto_added_only_when_every_session_has_gold(services):
    c = client(services=services)
    rid = start(c, engines=["miti"]).json()["run_id"]
    assert services.repository.get_run(rid)["engines"] == ["miti", "human"]
    services.datasets.write_json("datasets/synthetic/manifest.json", _two_sessions(services))
    # session "two" has no gold: Human is not added
    rid2 = start(c, engines=["miti"], input={"dataset_id": "synthetic",
                                              "session_ids": ["one", "two"]}).json()["run_id"]
    doc = services.repository.get_run(rid2)
    assert doc["engines"] == ["miti"] and doc["human"] is False
    assert doc["completed_units"] == 0 and len(doc["sessions"]) == 2
    assert [s["order"] for s in doc["sessions"].values()] == [0, 1]
    # explicit Human without gold is refused before anything is written
    before = (len(services.queue.tasks), len(sessions_of(services)))
    r = start(c, engines=["human", "miti"],
              input={"dataset_id": "synthetic", "session_ids": ["one", "two"]})
    assert r.status_code == 422 and "gold" in r.json()["detail"].lower()
    assert before == (len(services.queue.tasks), len(sessions_of(services)))


def _two_sessions(services):
    from test_catalog import manifest
    from test_uploads import transcript

    m = manifest()
    m["sessions"][0]["coded_span"]["end_turn"] = 2
    m["sessions"].append({**m["sessions"][0], "session_id": "two", "title": "Two"})
    services.datasets.write_json("datasets/synthetic/two/transcript.json", transcript())
    return m


def test_human_only_run_is_done_at_creation_without_a_tick(services):
    c = client(services=services)
    r = start(c, engines=["human"], selection={})
    assert r.status_code == 200, r.text
    doc = services.repository.get_run(r.json()["run_id"])
    assert (doc["status"], doc["total_units"], doc["completed_units"]) == ("done", 1, 1)
    assert services.queue.tasks == []


def test_enqueue_failure_marks_the_run_failed(services):
    def boom(*a, **k):
        raise RuntimeError("queue down")

    services.queue.enqueue = boom
    c = client(services=services)
    r = start(c)
    assert r.status_code == 200 and r.json()["status"] == "failed"


def test_same_inputs_reuse_one_session_across_runs(services):
    c = client(services=services)
    a = start(c).json()["run_id"]
    b = start(c).json()["run_id"]
    assert list(services.repository.get_run(a)["sessions"]) == list(
        services.repository.get_run(b)["sessions"])
    assert len(sessions_of(services)) == 1


def test_rerun_reuses_pinned_sid_and_keeps_response_shape(services):
    c = client(services=services)
    rid = start(c, name="Orig").json()["run_id"]
    old = services.repository.get_run(rid)
    before = len(sessions_of(services))
    r = rerun(c, rid)
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"run_id", "status", "engines"}
    new = services.repository.get_run(r.json()["run_id"])
    assert new["name"] == old["name"]
    assert list(new["sessions"]) == list(old["sessions"]) and len(sessions_of(services)) == before
    assert new["saved_config"] == old["saved_config"] and new["input"] == old["input"]
    assert (services.repo.list_runs(UID, next(iter(new["sessions"]))) == [])


def test_rerun_refused_when_pinned_session_missing_or_transcript_changed(services):
    c = client(services=services)
    rid = start(c).json()["run_id"]
    saved = services.repository.get_run(rid)
    (sid, entry), = saved["sessions"].items()
    snapshot = (len(services.queue.tasks), len(services.repository.list_runs()))

    services.repository.update_run(rid, {"sessions": {"f" * 32: entry}})
    r = rerun(c, rid)
    assert r.status_code == 409 and "no longer" in r.json()["detail"].lower()

    changed = deepcopy(entry)
    changed["transcript_sha256"] = "0" * 64
    services.repository.update_run(rid, {"sessions": {sid: changed}})
    r = rerun(c, rid)
    assert r.status_code == 409 and "changed" in r.json()["detail"].lower()
    assert snapshot == (len(services.queue.tasks), len(services.repository.list_runs()))


def test_rerun_drift_rule_refuses_changed_resolved_combo(services):
    c = client(services=services)
    rid = start(c).json()["run_id"]
    saved = services.repository.get_run(rid)["saved_config"]
    key = next(iter(saved["resolved_combos"]))
    saved["resolved_combos"][key]["litellm_id"] = "historical/model"
    services.repository.update_run(rid, {"saved_config": saved})
    before = len(services.repository.list_runs())
    r = rerun(c, rid)
    assert r.status_code == 409 and "new run" in r.json()["detail"].lower()
    assert len(services.repository.list_runs()) == before


def test_resolved_combos_come_from_the_worker_snapshot_function(services, monkeypatch):
    from onolys_api.engines import eval_snapshot

    c = client(services=services)
    rid = start(c).json()["run_id"]
    combos = services.repository.get_run(rid)["saved_config"]["resolved_combos"]
    snap, _ = eval_snapshot(
        c.app.state.config.settings, "configured-prod", "miti",
        {"model": "claude", "tier": "claude-sonnet-5-5", "effort": "low"},
    )
    assert combos == {"claude/claude-sonnet-5-5/low": snap}


def test_worst_case_group_doc_is_under_one_mib():
    """499 units x 8 attempts of embedded refs (+ per-cell wait state) must fit in 1 MiB."""
    sessions = {}
    per_session = 3
    for i in range(MAX_UNITS // per_session + 1):
        entry = session_entry(f"dataset-session-{i:03d}", i, "f" * 64)
        sessions[f"{i:032x}"] = entry
    cells = 0
    for entry in sessions.values():
        for j in range(per_session):
            if cells == MAX_UNITS:
                break
            cells += 1
            combo = f"claude/claude-sonnet-5-5/high-{j}"
            entry["runs"] += [
                {"run_id": f"{cells:016x}{a:016x}", "combo_key": combo, "repeat": j % 3,
                 "attempt": a, "status": "failed"}
                for a in range(8)
            ]
    doc = build_group_doc(
        name="n" * 200, description="d" * 4000, input={"dataset_id": "d", "session_ids": ["s"]},
        created_by="a@example.com", created_at="2026-11-25T00:00:00+00:00",
        engines=["miti", "human"], selection={"models": ["claude"]},
        combos=[{"model": "claude", "tier": "t", "effort": "low"}] * 6, repeats=3,
        base_preset="p", resolved_combos={f"c{i}": {"litellm_id": "x" * 40} for i in range(6)},
        engine_versions={"miti": "1"}, engine_git_sha="a" * 40, change_goal="g" * 4000,
        language="en", coded_span=None, sessions=sessions, total_units=MAX_UNITS, human_units=0,
    )
    doc["cells_wait"] = {
        f"{sid}/{j}": {"overload_waited_s": 300, "next_try_at": 1.7e9, "internal_retries": 1}
        for sid in sessions for j in range(per_session)
    }
    assert sum(len(e["runs"]) for e in sessions.values()) == MAX_UNITS * 8
    size = len(json.dumps(doc, ensure_ascii=False).encode())
    assert size < 1024 * 1024, size


def test_rerun_does_not_read_dataset_sources_again(services):
    c = client(services=services)
    rid = start(c).json()["run_id"]
    # The pinned prod session is immutable: the dataset may be edited or removed afterwards.
    for path in list(services.datasets.list("datasets/")):
        services.datasets.delete(path)
    r = rerun(c, rid)
    assert r.status_code == 200, r.text
    assert len(sessions_of(services)) == 1


def test_rerun_of_a_run_without_pinned_sessions_is_refused(services):
    c = client(services=services)
    rid = start(c).json()["run_id"]
    services.repository.update_run(rid, {"sessions": {}})
    assert rerun(c, rid).status_code == 422
