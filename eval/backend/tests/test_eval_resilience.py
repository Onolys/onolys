"""Provider resilience on the tick scheduler (05 R6b-R6d): overload backoff, isolation, breaker.

Reuses the fake harness of test_eval_scheduler. Fake clock + fixed jitter: no sleeping, no RNG.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from test_eval_scheduler import (  # noqa: F401  (fixtures and helpers)
    SEL1,
    TWO_PROVIDERS,
    UID,
    active_runs,
    all_runs,
    create,
    drive,
    finish,
    runs_of,
    tick,
)

from onolys_eval_backend import eval_scheduler as sched

pytest_plugins = ["test_runs", "test_eval_scheduler"]  # fixtures: services, env
T0 = datetime(2030, 1, 1, tzinfo=UTC)


class Clock:
    def __init__(self):
        self.t = T0

    def advance(self, seconds):
        self.t += timedelta(seconds=seconds)


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(sched, "_now", lambda: c.t)
    monkeypatch.setattr(sched, "_jitter", lambda: 1.0)
    return c


def finish_at(env, sid, run, seconds, status="done", error=None):
    finish(env, sid, run, status, error)
    env.repo.update_run(UID, sid, run.run_id, {"ended": T0 + timedelta(seconds=seconds)})


def by_sid(env):
    return {sid: run for sid, run in active_runs(env)}


def sid_of(env, rid, name):
    sessions = env.repository.get_run(rid)["sessions"]
    return next(s for s, e in sessions.items() if e["dataset_session_id"] == name)


def entry_of(env, rid, sid):
    return env.repository.get_run(rid)["sessions"][sid]


def test_overload_waits_cooldown_blocks_only_that_provider_and_success_clears_it(env, clock):
    rid = create(env, ["one", "two"], selection=TWO_PROVIDERS, repeats=1)
    tick(env, rid)
    runs = by_sid(env)
    assert len(runs) == 2 and all(sched_p == "anthropic" for sched_p in
                                  [r.eval.resolved_route["litellm_id"].split("/")[0] for r in runs.values()])
    one, two = sorted(runs)
    finish_at(env, two, runs[two], 1, "done")  # folded first (by `ended`), so it cannot clear the cooldown
    finish_at(env, one, runs[one], 2, "failed", "upstream_unavailable")
    tick(env, rid)
    doc = env.repository.get_run(rid)
    key = f"{one}|miti|claude/claude-sonnet-5-5/low|0"
    wait = doc["cells_wait"][key]
    assert doc["sessions"][one]["state"] == "waiting" and doc["sessions"][one]["cursor"] == 0
    assert doc["sessions"][one]["runs"][0]["status"] == "waiting"
    assert wait["overload_waited_s"] == 15 and wait["next_try_at"] == (T0 + timedelta(seconds=15)).isoformat()
    assert (doc["completed_units"], doc["failed_units"]) == (1, 0)  # waiting is not a failure
    slots = env.repository.get_slots("anthropic")
    assert slots["overload_streak"] == 1 and slots["cooldown_until"] == (T0 + timedelta(seconds=15)).isoformat()
    # other provider kept filling: session two moved on to its gemini cell; one stays blocked
    assert {r.eval.resolved_route["litellm_id"].split("/")[0] for r in by_sid(env).values()} == {"gemini"}
    assert one not in by_sid(env) and len(runs_of(env, one)) == 1
    clock.advance(14)
    tick(env, rid)
    assert len(runs_of(env, one)) == 1  # still cooling down
    clock.advance(2)
    tick(env, rid)
    assert len(runs_of(env, one)) == 2  # retried as a new attempt
    assert entry_of(env, rid, one)["runs"][1]["attempt"] == 1
    finish(env, one, by_sid(env)[one], "done")
    tick(env, rid)
    slots = env.repository.get_slots("anthropic")
    assert slots["overload_streak"] == 0 and slots["cooldown_until"] is None


def test_retry_started_marks_the_earlier_waiting_ref_failed(env, clock):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    tick(env, rid)
    (sid, run), = by_sid(env).items()
    finish(env, sid, run, "failed", "upstream_unavailable")
    tick(env, rid)
    assert entry_of(env, rid, sid)["runs"][0]["status"] == "waiting"
    clock.advance(16)
    tick(env, rid)  # retry starts as attempt 1
    refs = entry_of(env, rid, sid)["runs"]
    assert [r["status"] for r in refs] == ["failed", "running"]
    assert refs[0]["error"] == "upstream_unavailable"
    finish(env, sid, by_sid(env)[sid], "done")
    tick(env, rid)
    refs = entry_of(env, rid, sid)["runs"]
    assert [(r["attempt"], r["status"]) for r in refs] == [(0, "failed"), (1, "done")]
    assert not any(r["status"] == "waiting" for r in refs)


def test_cooldown_blocks_other_eval_runs_on_that_provider(env, clock):
    a = create(env, ["one"], selection=SEL1, repeats=1)
    b = create(env, ["two"], selection=SEL1, repeats=1)
    tick(env, a)
    (sid, run), = by_sid(env).items()
    finish(env, sid, run, "failed", "rate_limited")
    tick(env, a)  # cooldown recorded on the shared slots doc
    two = sid_of(env, b, "two")
    tick(env, b)
    assert runs_of(env, two) == [] and env.repository.get_run(b)["sessions"][two]["state"] == "pending"
    clock.advance(20)
    tick(env, b)
    assert len(runs_of(env, two)) == 1


def test_waits_double_within_budget_then_failed_and_counted(env, clock):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    waits = []
    for _ in range(10):
        tick(env, rid)
        for sid, run in active_runs(env):
            finish(env, sid, run, "failed", "upstream_unavailable")
        tick(env, rid)
        doc = env.repository.get_run(rid)
        if doc["status"] != "running":
            break
        ((key, w),) = doc["cells_wait"].items()
        waits.append(w["overload_waited_s"])
        clock.advance(121)
    assert waits == [15, 45, 105, 225]  # 15, 30, 60, 120: the next 120 would pass 300 s
    assert doc["status"] == "failed" and (doc["failed_units"], doc["completed_units"]) == (1, 1)
    assert doc["consecutive_failures"] == {"anthropic": 1}
    assert len(runs_of(env, sid_of(env, rid, "one"))) == 5
    assert doc["sessions"][sid_of(env, rid, "one")]["runs"][-1]["error"] == "upstream_unavailable"


def test_jitter_scales_the_wait_and_budget_is_configurable(env, clock, monkeypatch):
    monkeypatch.setattr(sched, "_jitter", lambda: 0.5)
    env.config = replace(env.config, overload_max_wait_s=5)
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    tick(env, rid)
    (sid, run), = by_sid(env).items()
    finish(env, sid, run, "failed", "upstream_unavailable")
    tick(env, rid)
    doc = env.repository.get_run(rid)
    assert doc["status"] == "failed"  # 7.5 s > 5 s budget: no wait at all, failed with its code
    assert doc["cells_wait"].get(f"{sid}|miti|claude/claude-sonnet-5-5/low|0", {}).get("overload_waited_s", 0) == 0


def test_one_raising_cell_leaves_others_progressing_and_fails_only_after_three(env, clock, monkeypatch):
    rid = create(env, ["one", "two", "three"], selection=SEL1, repeats=1)
    bad = sorted(env.repository.get_run(rid)["sessions"], key=lambda s: env.repository.get_run(rid)["sessions"][s]["order"])[0]
    real = sched._fill_session

    def boom(services, doc, eval_run_id, sid, cells):
        if sid == bad:
            raise RuntimeError("handler bug")
        return real(services, doc, eval_run_id, sid, cells)

    monkeypatch.setattr(sched, "_fill_session", boom)
    tick(env, rid)
    doc = env.repository.get_run(rid)
    assert bad not in {sid for sid, _ in all_runs(env)} and len(all_runs(env)) == 2
    assert doc["cells_wait"][f"{bad}|miti|claude/claude-sonnet-5-5/low|0"]["handler_errors"] == 1
    assert doc["failed_units"] == 0 and doc["status"] == "running"
    drive(env, [rid])
    doc = env.repository.get_run(rid)
    entry = doc["sessions"][bad]
    assert entry["runs"][-1]["error"] == "scheduler_error" and entry["runs"][-1]["status"] == "failed"
    assert (doc["status"], doc["done_units"], doc["failed_units"], doc["completed_units"]) == ("partial", 2, 1, 3)
    assert doc.get("consecutive_failures", {}) == {"anthropic": 0}  # a scheduler error is not a provider failure


def test_raising_fold_is_isolated_too(env, clock, monkeypatch):
    rid = create(env, ["one", "two"], selection=SEL1, repeats=1)
    tick(env, rid)
    runs = by_sid(env)
    bad = sorted(runs)[0]
    real = sched._fold_session

    def boom(services, doc, sid, cells, run=None):
        if sid == bad:
            doc["completed_units"] += 99  # half-applied change must be rolled back
            raise RuntimeError("fold bug")
        return real(services, doc, sid, cells, run)

    monkeypatch.setattr(sched, "_fold_session", boom)
    for sid, run in runs.items():
        finish(env, sid, run)
    tick(env, rid)
    doc = env.repository.get_run(rid)
    other = [s for s in runs if s != bad][0]
    assert doc["completed_units"] == 1 and doc["sessions"][other]["state"] == "done"
    assert doc["sessions"][bad]["active_run_id"] == runs[bad].run_id  # left for the next tick
    tick(env, rid)
    tick(env, rid)
    doc = env.repository.get_run(rid)
    assert doc["status"] == "partial" and doc["sessions"][bad]["runs"][0]["error"] == "scheduler_error"
    assert doc["failed_units"] == 1 and doc["done_units"] == 1


def provider_outcome(fail_provider, status="failed", error="deadline_exceeded", only_run=None):
    def outcome(sid, run, n):
        failing = provider_of(run) == fail_provider and (only_run is None or run.eval.eval_run_id == only_run)
        return (status, error) if failing else ("done", None)
    return outcome


def provider_of(run):
    return run.eval.resolved_route["litellm_id"].split("/")[0]


def test_breaker_skips_only_that_provider_other_completes(env, clock):
    env.config = replace(env.config, provider_fail_limit=2)
    rid = create(env, ["one", "two", "three"], selection=TWO_PROVIDERS, repeats=1)
    drive(env, [rid], outcome=provider_outcome("anthropic"))
    doc = env.repository.get_run(rid)
    assert doc["status"] == "partial"
    assert (doc["failed_units"], doc["skipped_units"], doc["done_units"], doc["completed_units"]) == (2, 1, 3, 5)
    skip = doc["provider_skips"]["anthropic"]
    assert skip["after_failures"] == 2 and skip["skipped_cells"] == 1 and skip["skipped_at"]
    assert "gemini" not in doc["provider_skips"]
    skipped = [(sid, r) for sid, e in doc["sessions"].items() for r in e["runs"] if r["status"] == "skipped"]
    assert len(skipped) == 1 and skipped[0][1]["error"] == "provider_unavailable"
    assert len(all_runs(env)) == 5  # no run was created for the skipped cell
    assert all(e["state"] == "done" for e in doc["sessions"].values())


def test_breaker_skips_waiting_cells_and_status_failed_with_no_done(env, clock):
    env.config = replace(env.config, provider_fail_limit=1)
    rid = create(env, ["one", "two"], selection=SEL1, repeats=1)
    tick(env, rid)
    runs = by_sid(env)
    one, two = sorted(runs)
    finish_at(env, one, runs[one], 1, "failed", "upstream_unavailable")
    finish_at(env, two, runs[two], 2, "failed", "deadline_exceeded")
    tick(env, rid)  # fold order by ended: `one` goes waiting, then `two` fails final and trips
    doc = env.repository.get_run(rid)
    assert doc["skipped_units"] == 1 and doc["provider_skips"]["anthropic"]["skipped_cells"] == 1
    assert doc["sessions"][one]["state"] == "done"  # its waiting cell was skipped
    assert (doc["status"], doc["failed_units"]) == ("failed", 1)  # nothing done


def test_success_resets_the_count(env, clock):
    env.config = replace(env.config, provider_fail_limit=2, max_per_provider=1)
    rid = create(env, ["one", "two", "three"], selection=SEL1, repeats=1)
    order = ["fail", "done", "fail"]

    def outcome(sid, run, n):
        pick = order.pop(0)
        return ("failed", "deadline_exceeded") if pick == "fail" else ("done", None)

    drive(env, [rid], outcome=outcome)
    doc = env.repository.get_run(rid)
    assert doc["provider_skips"] == {} and doc["skipped_units"] == 0
    assert (doc["status"], doc["done_units"], doc["failed_units"]) == ("partial", 1, 2)
    assert doc["consecutive_failures"] == {"anthropic": 1}


def test_cancelled_neither_counts_nor_resets(env, clock):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    doc = env.repository.get_run(rid)
    cells = sched.plan_cells(doc)
    doc["consecutive_failures"] = {"anthropic": 1}
    sched._record_outcome(env, doc, cells, "anthropic", "cancelled")
    sched._record_outcome(env, doc, cells, "anthropic", "skipped")
    assert doc["consecutive_failures"] == {"anthropic": 1}
    sched._record_outcome(env, doc, cells, "anthropic", "done")
    assert doc["consecutive_failures"] == {"anthropic": 0}


def test_in_flight_runs_are_kept_after_the_trip_and_do_not_change_the_breaker(env, clock):
    env.config = replace(env.config, provider_fail_limit=2, max_per_provider=3)
    rid = create(env, ["one", "two", "three"], selection=SEL1, repeats=2)
    tick(env, rid)
    runs = by_sid(env)
    a, b, c = sorted(runs)
    finish_at(env, a, runs[a], 1, "failed", "deadline_exceeded")
    finish_at(env, b, runs[b], 2, "failed", "deadline_exceeded")
    tick(env, rid)  # trips; `c` still in flight
    doc = env.repository.get_run(rid)
    assert doc["provider_skips"]["anthropic"]["after_failures"] == 2
    assert doc["sessions"][c]["active_run_id"] == runs[c].run_id and len(all_runs(env)) == 3
    finish_at(env, c, runs[c], 3, "done")
    tick(env, rid)
    doc = env.repository.get_run(rid)
    assert doc["consecutive_failures"]["anthropic"] == 2  # the late success did not reset it
    assert doc["sessions"][c]["runs"][0]["status"] == "done"
    assert (doc["status"], doc["done_units"], doc["failed_units"], doc["skipped_units"]) == ("partial", 1, 2, 3)


def test_another_eval_run_is_unaffected_by_the_breaker(env, clock):
    env.config = replace(env.config, provider_fail_limit=2)
    a = create(env, ["one", "two", "three"], selection=SEL1, repeats=1)
    b = create(env, ["four", "five"], selection=SEL1, repeats=1)
    drive(env, [a, b], outcome=provider_outcome("anthropic", only_run=a))
    da, db = env.repository.get_run(a), env.repository.get_run(b)
    assert da["status"] == "failed" and da["provider_skips"]["anthropic"]["after_failures"] == 2
    assert (db["status"], db["done_units"], db["skipped_units"]) == ("done", 2, 0)
    assert db.get("provider_skips", {}) == {}
