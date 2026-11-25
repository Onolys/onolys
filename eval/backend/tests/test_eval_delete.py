# ruff: noqa: F811
"""Delete flow (05 R8, Decision 7): refuse while active, ordered resumable steps, group doc last.

Reuses the fake harness of test_eval_scheduler (no LLM, no network).
"""

import pytest
from onolys_api.repo.models import ReportDoc
from test_app import AUTH, client
from test_eval_scheduler import SEL1, all_runs, create, drive, env, finish, provider, tick  # noqa: F401

from onolys_eval_backend.eval_delete import run_delete

pytest_plugins = ["test_runs", "test_eval_scheduler"]  # fixtures: services, env
UID = "eval-owner"


def seed(env, rid):
    """A report + an output file per run, as the prod worker leaves them."""
    keys = []
    for sid, run in all_runs(env):
        if run.run_id not in refs(env, rid):
            continue
        env.repo.put_report(UID, sid, run.run_id,
                            ReportDoc(version=1, run_id=run.run_id, report={"k": run.run_id}))
        key = f"{UID}/{sid}/runs/{run.run_id}/code.json"
        env.blobs.put_bytes(key, b"{}")
        keys.append(key)
    return keys


def refs(env, rid):
    return {r["run_id"] for e in env.repository.get_run(rid)["sessions"].values()
            for r in e["runs"] if r["run_id"]}


def finished_run(env, sessions=("one", "two")):
    rid = create(env, list(sessions), selection=SEL1, repeats=1)
    drive(env, [rid])
    assert env.repository.get_run(rid)["status"] == "done"
    return rid


def delete(env, rid, confirm=None, **kw):
    return client(services=env, **kw).post(
        f"/v1/runs/{rid}/delete", headers=AUTH, json={"confirm_run_id": rid if confirm is None else confirm})


def present(env, rid, ids=None):
    """(RunDocs, ReportDocs, output blobs) still stored for this eval run's refs."""
    ids = refs(env, rid) if ids is None else ids
    runs = [r for _, r in all_runs(env) if r.run_id in ids]
    reports = [(s, r) for s, run in all_runs(env) if run.run_id in ids
               for r in env.repo.list_reports(UID, s) if r.run_id in ids]
    blobs = [k for k in env.blobs.list_keys(f"{UID}/") if any(f"/runs/{i}/" in k for i in ids)]
    return runs, reports, blobs


def test_refused_while_active(env):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    tick(env, rid)
    r = delete(env, rid)
    assert r.status_code == 409 and r.json()["error"]["code"] == "run_active"
    assert env.repository.get_run(rid)["status"] == "running"
    assert env.queue.tasks == [] or all(t["kind"] != "delete" for t in env.queue.tasks)


def test_mismatched_confirm_id_rejected_and_unknown_is_404(env):
    rid = finished_run(env)
    assert delete(env, rid, confirm="other").status_code == 422
    assert delete(env, rid, confirm="").status_code == 422
    assert env.repository.get_run(rid)["status"] == "done"
    assert delete(env, "nope", confirm="nope").status_code == 404


def test_delete_is_allowlisted_users_only(env):
    rid = finished_run(env)
    r = delete(env, rid, claims={"email": "outsider@example.com", "email_verified": True})
    assert r.status_code == 403
    assert env.repository.get_run(rid)["status"] == "done"


def test_accepts_with_202_marks_deleting_and_enqueues_task_then_history_shows_it(env):
    rid = finished_run(env)
    r = delete(env, rid)
    assert r.status_code == 202 and r.json() == {"run_id": rid, "status": "deleting"}
    assert env.repository.get_run(rid)["status"] == "deleting"
    task = [t for t in env.queue.tasks if t["kind"] == "delete"]
    assert task == [{"kind": "delete", "payload": {"eval_run_id": rid, "n": 1}, "delay_seconds": 0}]
    rows = client(services=env).get("/v1/runs", headers=AUTH).json()["runs"]
    assert [x["status"] for x in rows if x["run_id"] == rid] == ["deleting"]
    assert tick(env, rid) == "noop"  # the tick ignores a deleting run
    assert delete(env, rid).status_code == 202  # same POST again is a safe retry


def test_handler_removes_everything_of_this_run_and_keeps_the_rest(env):
    a = finished_run(env)
    b = finished_run(env)
    assert refs(env, a).isdisjoint(refs(env, b))
    seed(env, a)
    seed(env, b)
    session_ids = {sid for sid, _ in all_runs(env)}
    env.audio_bucket.write_json("gold/abc.json", {"x": 1})
    before_b = present(env, b)
    assert all(before_b) and all(present(env, a))
    a_ids = refs(env, a)
    delete(env, a)
    c = client(services=env)
    assert c.post("/internal/tasks/delete", headers=AUTH,
                  json={"eval_run_id": a, "n": 1}).status_code == 200
    assert present(env, a, a_ids) == ([], [], [])
    assert env.repository.get_run(a) is None
    assert c.get(f"/v1/runs/{a}", headers=AUTH).status_code == 404
    assert [x["run_id"] for x in c.get("/v1/runs", headers=AUTH).json()["runs"]] == [b]
    after_b = present(env, b)
    assert [r.run_id for r in after_b[0]] == [r.run_id for r in before_b[0]]
    assert len(after_b[1]) == len(before_b[1]) and sorted(after_b[2]) == sorted(before_b[2])
    assert {sid for sid, _ in all_runs(env)} == session_ids  # sessions stay
    assert env.repo.get_session(UID, sorted(session_ids)[0]) is not None
    assert env.audio_bucket.read_json("gold/abc.json") == {"x": 1}
    assert env.repository.get_run(b)["status"] == "done"


def test_killed_mid_way_then_retry_completes(env, monkeypatch):
    rid = finished_run(env)
    seed(env, rid)
    delete(env, rid)
    real, calls = env.repo.delete_run_data, []

    def flaky(uid, sid, run_id):
        calls.append(run_id)
        if len(calls) == 2:
            raise RuntimeError("killed")
        return real(uid, sid, run_id)

    monkeypatch.setattr(env.repo, "delete_run_data", flaky)
    assert run_delete(env, rid, 1) == "failed"
    doc = env.repository.get_run(rid)
    assert doc["status"] == "deleting" and doc["delete_error"] == "internal_error"
    assert doc["sessions"]  # the refs survive for the retry
    half = client(services=env).get(f"/v1/runs/{rid}", headers=AUTH)  # half-deleted: still readable
    assert half.status_code == 200 and half.json()["status"] == "deleting"
    nxt = [t for t in env.queue.tasks if t["kind"] == "delete"][-1]
    assert nxt["payload"] == {"eval_run_id": rid, "n": 2} and nxt["delay_seconds"] > 0
    monkeypatch.setattr(env.repo, "delete_run_data", real)
    assert run_delete(env, rid, 2) == "deleted"
    assert env.repository.get_run(rid) is None and present_ids(env) == set()


def present_ids(env):
    return {r.run_id for _, r in all_runs(env)}


def test_second_run_of_handler_is_a_noop_and_failed_blob_delete_keeps_deleting(env, monkeypatch):
    rid = finished_run(env, ["one"])
    seed(env, rid)
    delete(env, rid)
    monkeypatch.setattr(env.blobs, "delete_prefix",
                        lambda p: (_ for _ in ()).throw(OSError("boom")))
    assert run_delete(env, rid, 1) == "failed"
    assert env.repository.get_run(rid)["status"] == "deleting"
    monkeypatch.undo()
    assert run_delete(env, rid, 2) == "deleted"
    assert run_delete(env, rid, 3) == "noop"  # group doc gone


def test_slots_released_and_audit_line_hashes_the_email(env, caplog):
    rid = finished_run(env, ["one"])
    providers = {p for _, run in all_runs(env) for p in [provider(run)]}
    for _, run in all_runs(env):  # a stale holder left behind
        env.repository.claim_slot(provider(run), run.run_id, rid, 2)
    assert any(env.repository.get_slots(p)["holders"] for p in providers)
    caplog.set_level("INFO")
    delete(env, rid)
    run_delete(env, rid, 1)
    assert all(not env.repository.get_slots(p).get("holders") for p in providers)
    line = [r for r in caplog.records if r.getMessage() == "eval_run_delete_requested"]
    assert len(line) == 1
    assert line[0].eval_run_id == rid
    assert "alice@example.com" not in str(line[0].__dict__) and len(line[0].email_hash) == 16


def test_cloud_queue_accepts_the_delete_kind():
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from onolys_eval_backend.queue import CloudTasksQueue
    cfg = SimpleNamespace(service_url="https://e", tasks_sa="sa", task_audience="aud",
                          tasks_queue="projects/p/locations/l/queues/q")
    q = CloudTasksQueue(cfg, MagicMock())
    q.enqueue("delete", {"eval_run_id": "x", "n": 1}, task_id="x-delete-1")
    assert q.client.create_task.call_args.kwargs["task"]["http_request"]["url"].endswith(
        "/internal/tasks/delete")


def test_deleting_first_group_keeps_queued_and_new_groups_schedulable(env):
    first = finished_run(env, ["one", "two"])
    queued = create(env, ["one", "two"], selection=SEL1, repeats=1)
    sessions = env.repository.get_run(first)["sessions"]
    snapshots = {
        sid: (env.repo.get_session(UID, sid), env.repo.get_transcript(UID, sid, "current"))
        for sid in sessions
    }
    assert all(s.first_run_id in refs(env, first) for s, _ in snapshots.values())
    delete(env, first)
    assert run_delete(env, first, 1) == "deleted"
    assert not all_runs(env)
    fresh = create(env, ["one", "two"], selection=SEL1, repeats=1)
    assert set(env.repository.get_run(fresh)["sessions"]) == set(sessions)
    drive(env, [queued, fresh])
    for group in (queued, fresh):
        assert env.repository.get_run(group)["status"] == "done"
    for sid, run in all_runs(env):
        session, transcript = snapshots[sid]
        assert run.transcript_sha256 == transcript.sha256
        assert run.clinician_speaker == session.clinician_speaker
        assert run.change_goal == (session.change_goal or "")
        assert env.repo.get_transcript(UID, sid, "current") == transcript


@pytest.mark.parametrize("tamper", ["transcript", "speaker", "goal"])
def test_deleted_first_run_cannot_hide_changed_eval_inputs(env, tamper):
    first = finished_run(env, ["one"])
    queued = create(env, ["one"], selection=SEL1, repeats=1)
    ((sid, _),) = env.repository.get_run(first)["sessions"].items()
    delete(env, first)
    assert run_delete(env, first, 1) == "deleted"
    if tamper == "transcript":
        doc = env.repo._get(f"sessions/{sid}/transcripts/current")
        env.repo._put(f"sessions/{sid}/transcripts/current", {**doc, "sha256": "replaced"})
    else:
        key = "clinician_speaker" if tamper == "speaker" else "change_goal"
        env.repo.update_session(UID, sid, {key: "replacement"})
    tick(env, queued)
    assert all_runs(env) == []
    assert env.repository.get_slots("anthropic")["holders"] == {}
