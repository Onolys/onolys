"""Cancel rework (05 R7, Decision 6): stop new runs only, keep completed work, no worker edit.

Reuses the fake harness of test_eval_scheduler / test_eval_resilience (fake clock, no sleeping).
Delete (Task 8) is not built: "delete refused until terminal" is covered by the status staying
`running` (non-terminal) while in-flight runs exist; the 409 itself belongs to Task 8's tests.
"""

from dataclasses import replace

from test_app import AUTH, client
from test_eval_resilience import by_sid, finish_at
from test_eval_scheduler import SEL1, SEL2, all_runs, create, finish, tick

pytest_plugins = ["test_runs", "test_eval_scheduler", "test_eval_resilience"]  # services, env, clock


def cancel(env, rid):
    return client(services=env).post(f"/v1/runs/{rid}/cancel", headers=AUTH)


def cells_by_status(env, rid):
    out = {}
    for entry in env.repository.get_run(rid)["sessions"].values():
        for ref in entry["runs"]:
            out[ref["status"]] = out.get(ref["status"], 0) + 1
    return out


def test_cancel_sets_flags_and_replies_with_cancelled_at(env, clock):
    rid = create(env, ["one"], selection=SEL2, repeats=2)
    tick(env, rid)
    r = cancel(env, rid)
    assert r.status_code == 200
    doc = env.repository.get_run(rid)
    assert doc["cancel_requested"] is True and doc["cancelled_at"]
    assert r.json() == {"run_id": rid, "status": "running", "cancelled_at": doc["cancelled_at"]}


def test_no_new_run_after_request_in_flight_kept_status_stays_running(env, clock):
    rid = create(env, ["one", "two"], selection=SEL2, repeats=2)  # 4 cells per session
    tick(env, rid)
    cancel(env, rid)
    in_flight = {sid: run.run_id for sid, run in by_sid(env).items()}
    tick(env, rid)
    doc = env.repository.get_run(rid)
    assert len(all_runs(env)) == 2  # nothing new started
    assert doc["status"] == "running" and doc["cancel_requested"] is True  # winding down: not deletable
    assert doc["cancelled_units"] == 6 and doc["completed_units"] == 0
    for sid, entry in doc["sessions"].items():
        assert entry["active_run_id"] == in_flight[sid] and entry["state"] == "running"
        statuses = [r["status"] for r in entry["runs"]]
        assert statuses == ["running", "cancelled", "cancelled", "cancelled"]
        assert all(r["error"] == "cancelled" and r["run_id"] is None for r in entry["runs"][1:])
    tick(env, rid)  # a further tick changes nothing
    again = env.repository.get_run(rid)
    assert again["cancelled_units"] == 6 and again["status"] == "running"
    assert len(all_runs(env)) == 2


def test_in_flight_done_ends_partial_and_is_kept(env, clock):
    rid = create(env, ["one", "two"], selection=SEL2, repeats=2)
    tick(env, rid)
    cancel(env, rid)
    tick(env, rid)
    one, two = sorted(by_sid(env))
    finish(env, one, by_sid(env)[one], "done")
    tick(env, rid)
    doc = env.repository.get_run(rid)
    assert doc["status"] == "running"  # `two` is still in flight
    finish(env, two, by_sid(env)[two], "failed", "deadline_exceeded")
    tick(env, rid)
    doc = env.repository.get_run(rid)
    assert doc["status"] == "partial" and doc["finished_at"]
    assert (doc["done_units"], doc["failed_units"], doc["cancelled_units"]) == (1, 1, 6)
    assert doc["cancelled_at"] and len(all_runs(env)) == 2
    assert all(e["state"] == "done" and e["active_run_id"] is None for e in doc["sessions"].values())


def test_no_run_completed_ends_cancelled(env, clock):
    rid = create(env, ["one"], selection=SEL2, repeats=2)
    tick(env, rid)
    cancel(env, rid)
    ((sid, run),) = by_sid(env).items()
    finish(env, sid, run, "failed", "deadline_exceeded")  # in-flight failed, nothing done
    tick(env, rid)
    doc = env.repository.get_run(rid)
    assert (doc["status"], doc["done_units"], doc["failed_units"], doc["cancelled_units"]) == (
        "cancelled", 0, 1, 3)


def test_cancel_before_any_run_starts_is_cancelled_at_once(env, clock):
    rid = create(env, ["one"], selection=SEL1, repeats=2)
    assert cancel(env, rid).json()["status"] == "queued"
    tick(env, rid)
    doc = env.repository.get_run(rid)
    assert (doc["status"], doc["cancelled_units"], doc["done_units"]) == ("cancelled", 2, 0)
    assert all_runs(env) == []
    assert env.repository.get_run(rid)["cancelled_at"]


def test_waiting_cell_becomes_cancelled_and_does_not_touch_the_breaker(env, clock):
    rid = create(env, ["one"], selection=SEL1, repeats=2)
    tick(env, rid)
    ((sid, run),) = by_sid(env).items()
    finish_at(env, sid, run, 1, "failed", "upstream_unavailable")
    tick(env, rid)
    doc = env.repository.get_run(rid)
    assert doc["sessions"][sid]["state"] == "waiting" and doc["cells_wait"]
    before = (doc["consecutive_failures"], doc["failed_units"])
    cancel(env, rid)
    tick(env, rid)
    doc = env.repository.get_run(rid)
    refs = doc["sessions"][sid]["runs"]
    assert [r["status"] for r in refs] == ["cancelled", "cancelled"] and doc["cells_wait"] == {}
    assert refs[0]["run_id"] == run.run_id  # the attempt that hit overload is kept as the cell's ref
    assert doc["cancelled_units"] == 2 and (doc["consecutive_failures"], doc["failed_units"]) == before
    assert (doc["status"], doc["done_units"]) == ("cancelled", 0)
    assert len(all_runs(env)) == 1


def test_cancel_during_retry_cancels_the_newest_waiting_ref(env, clock):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    tick(env, rid)
    ((sid, run),) = by_sid(env).items()
    finish_at(env, sid, run, 1, "failed", "upstream_unavailable")
    tick(env, rid)
    clock.advance(16)
    tick(env, rid)  # retry (attempt 1) starts
    finish(env, sid, by_sid(env)[sid], "failed", "upstream_unavailable")
    tick(env, rid)  # attempt 1 waits again
    cancel(env, rid)
    tick(env, rid)
    refs = env.repository.get_run(rid)["sessions"][sid]["runs"]
    assert [(r["attempt"], r["status"]) for r in refs] == [(0, "failed"), (1, "cancelled")]
    assert refs[0]["error"] == "upstream_unavailable"


def test_cancel_cells_picks_the_newest_of_several_waiting_refs():
    from onolys_eval_backend.eval_scheduler import _cancel_cells

    cell = {"engine": "miti", "combo_key": "c", "repeat": 0}
    ref = lambda n: {"run_id": f"r{n}", "engine": "miti", "combo_key": "c", "repeat": 0,  # noqa: E731
                     "attempt": n, "status": "waiting"}
    entry = {"cursor": 0, "active_run_id": None, "state": "waiting", "runs": [ref(0), ref(1)],
             "skipped_idx": []}
    doc = {"sessions": {"s": entry}, "cells_wait": {}, "cancelled_units": 0}
    _cancel_cells(doc, [cell])
    assert [r["status"] for r in entry["runs"]] == ["waiting", "cancelled"]


def test_second_cancel_is_a_no_op_with_the_same_cancelled_at(env, clock):
    rid = create(env, ["one"], selection=SEL2, repeats=2)
    tick(env, rid)
    first = cancel(env, rid).json()
    clock.advance(60)
    tick(env, rid)
    snapshot = env.repository.get_run(rid)
    second = cancel(env, rid)
    assert second.status_code == 200 and second.json() == first
    assert env.repository.get_run(rid) == snapshot


def test_cancel_on_terminal_run_is_a_200_no_op(env, clock):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    tick(env, rid)
    ((sid, run),) = by_sid(env).items()
    finish(env, sid, run)
    tick(env, rid)
    done = env.repository.get_run(rid)
    assert done["status"] == "done"
    r = cancel(env, rid)
    assert r.status_code == 200 and r.json() == {"run_id": rid, "status": "done", "cancelled_at": None}
    assert env.repository.get_run(rid) == done  # not even cancel_requested
    for status in ("partial", "failed", "cancelled", "deleting"):
        env.repository.update_run(rid, {"status": status})
        assert cancel(env, rid).json()["status"] == status
        assert env.repository.get_run(rid)["cancel_requested"] is False


def test_unknown_run_is_404(env):
    assert cancel(env, "no-such-run").status_code == 404


def test_slots_free_as_in_flight_runs_end_and_none_is_claimed_after_the_request(env, clock):
    rid = create(env, ["one", "two"], selection=SEL2, repeats=2)
    tick(env, rid)
    cancel(env, rid)
    tick(env, rid)
    assert len(env.repository.get_slots("anthropic")["holders"]) == 2  # cancel releases nothing early
    one, two = sorted(by_sid(env))
    finish(env, one, by_sid(env)[one])
    tick(env, rid)
    assert list(env.repository.get_slots("anthropic")["holders"].values()) == [rid]
    assert len(env.repository.get_slots("anthropic")["holders"]) == 1
    finish(env, two, by_sid(env)[two])
    tick(env, rid)
    assert env.repository.get_slots("anthropic")["holders"] == {}
    assert len(all_runs(env)) == 2


def test_skipped_cells_stay_skipped_and_cancelled_cells_do_not_feed_the_breaker(env, clock):
    env.config = replace(env.config, provider_fail_limit=2, max_per_provider=3)
    rid = create(env, ["one", "two", "three"], selection=SEL1, repeats=2)
    tick(env, rid)
    runs = by_sid(env)
    a, b, c = sorted(runs)
    finish_at(env, a, runs[a], 1, "failed", "deadline_exceeded")
    finish_at(env, b, runs[b], 2, "failed", "deadline_exceeded")
    tick(env, rid)  # breaker trips: the 3 unstarted cells are skipped; `c` is in flight
    skipped = env.repository.get_run(rid)["skipped_units"]
    assert skipped == 3
    cancel(env, rid)
    finish_at(env, c, runs[c], 3, "done")
    tick(env, rid)
    doc = env.repository.get_run(rid)
    assert (doc["skipped_units"], doc["cancelled_units"]) == (3, 0)  # nothing left to cancel
    assert cells_by_status(env, rid)["skipped"] == 3 and "cancelled" not in cells_by_status(env, rid)
    assert doc["status"] == "partial" and doc["consecutive_failures"]["anthropic"] == 2
