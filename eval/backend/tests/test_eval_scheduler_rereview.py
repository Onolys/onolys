"""Continuation uses the deployed two-attempt queue policy; lookups fail per session."""

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from test_eval_scheduler import SEL1, active_runs, create, finish, tick

from onolys_eval_backend import eval_scheduler as sched

pytest_plugins = ["test_runs", "test_eval_scheduler"]


class ScheduledQueue:
    """Deterministic Cloud Tasks delivery: named-task dedupe, two attempts, 5 s backoff."""

    def __init__(self, now):
        self.now = now
        self.tasks = []
        self.ids = set()

    def enqueue(self, kind, payload, *, delay_seconds=0, task_id=None):
        if task_id in self.ids:
            return
        self.ids.add(task_id)
        self.tasks.append((self.now + timedelta(seconds=delay_seconds), payload, 1))

    def deliver(self, env):
        self.tasks.sort(key=lambda t: t[0])
        self.now, payload, attempt = self.tasks.pop(0)
        try:
            sched.tick_task(SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(services=env))), payload)
        except HTTPException:
            if attempt < 2:
                self.tasks.append((self.now + timedelta(seconds=5), payload, attempt + 1))


@pytest.mark.parametrize("crashed_owner", [True, False])
def test_closed_browser_continuation_outlives_queue_retry_budget(env, monkeypatch, crashed_owner):
    root = Path(__file__).resolve().parents[3]
    infra = (root / "infra/modules/environment/main.tf").read_text()
    assert 'max_attempts = 2' in infra and 'min_backoff  = "5s"' in infra
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    start = sched._now()
    queue = ScheduledQueue(start)
    env.queue = queue
    monkeypatch.setattr(sched, "_now", lambda: queue.now)
    owner = "paused-owner"
    assert env.repository.claim_tick(rid, 1, start.isoformat(), owner,
                                     (start + timedelta(seconds=sched.TICK_LEASE_S)).isoformat()) == "claimed"
    queue.enqueue("tick", {"eval_run_id": rid, "n": 2}, delay_seconds=10, task_id="initial-successor")
    completed = False
    for _ in range(20):
        if not queue.tasks:
            break
        if not crashed_owner and not completed and min(t[0] for t in queue.tasks) > start + timedelta(seconds=20):
            queue.now = start + timedelta(seconds=20)
            doc = env.repository.get_run(rid)
            doc["_tick_owner"] = owner
            sched._run_owned_tick(env, rid, doc)
            env.repository.release_tick(rid, owner)
            completed = True
        queue.deliver(env)
        for sid, run in active_runs(env):
            finish(env, sid, run)
        if env.repository.get_run(rid)["status"] not in sched.ACTIVE:
            break
    doc = env.repository.get_run(rid)
    assert doc["status"] == "done" and doc["done_units"] == 1
    assert env.repository.get_slots("anthropic")["holders"] == {}


@pytest.mark.parametrize("started", [False, True])
def test_missing_session_lookup_is_bounded_and_other_sessions_complete(env, started):
    rid = create(env, ["one", "two"], selection=SEL1, repeats=1)
    if started:
        tick(env, rid)
    doc = env.repository.get_run(rid)
    bad, other = sorted(doc["sessions"], key=lambda sid: doc["sessions"][sid]["order"])
    env.repo.delete_session("eval-owner", bad)
    for _ in range(5):
        tick(env, rid)
        for sid, run in active_runs(env):
            finish(env, sid, run)
        if env.repository.get_run(rid)["status"] not in sched.ACTIVE:
            break
    doc = env.repository.get_run(rid)
    assert doc["status"] == "partial"
    assert doc["sessions"][bad]["runs"][-1]["error"] == "scheduler_error"
    assert doc["sessions"][other]["runs"][-1]["status"] == "done"
    assert (doc["failed_units"], doc["done_units"]) == (1, 1)
    assert env.repository.get_slots("anthropic")["holders"] == {}


def test_unavailable_lookup_preserves_existing_active_reference_and_slot(env, monkeypatch):
    rid = create(env, ["one", "two"], selection=SEL1, repeats=1)
    tick(env, rid)
    doc = env.repository.get_run(rid)
    bad, other = sorted(doc["sessions"])
    run_id = doc["sessions"][bad]["active_run_id"]
    real = env.repo.get_runs
    failures = []

    def unavailable(uid, sid, ids):
        if sid == bad:
            failures.append(1)
            raise RuntimeError("temporary database failure")
        return real(uid, sid, ids)

    monkeypatch.setattr(env.repo, "get_runs", unavailable)
    for _ in range(4):
        tick(env, rid)
        for sid, run in active_runs(env):
            if sid == other:
                finish(env, sid, run)
    doc = env.repository.get_run(rid)
    assert doc["sessions"][bad]["active_run_id"] == run_id
    assert run_id in env.repository.get_slots("anthropic")["holders"]
    assert doc["sessions"][other]["runs"][-1]["status"] == "done"
    assert len(failures) == 4  # one isolated lookup per failing session per tick
    monkeypatch.setattr(env.repo, "get_runs", real)
    for sid, run in active_runs(env):
        finish(env, sid, run)
    tick(env, rid)
    assert env.repository.get_run(rid)["status"] == "done"


@pytest.mark.parametrize("outcome", ["done", "failed"])
def test_accepted_cancel_wins_even_when_no_cells_were_skipped(env, outcome):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    tick(env, rid)
    env.repository.cancel_run(rid)
    for sid, run in active_runs(env):
        finish(env, sid, run, outcome, "deadline_exceeded" if outcome == "failed" else None)
    tick(env, rid)
    doc = env.repository.get_run(rid)
    assert doc["cancelled_units"] == 0
    assert doc["status"] == ("partial" if outcome == "done" else "cancelled")
    assert (doc["done_units"], doc["failed_units"]) == (int(outcome == "done"), int(outcome == "failed"))


def test_duplicate_busy_deliveries_share_one_durable_timer_and_queue_errors_propagate(env, monkeypatch):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    now = sched._now()
    assert env.repository.claim_tick(rid, 1, now.isoformat(), "paused",
                                     (now + timedelta(seconds=sched.TICK_LEASE_S)).isoformat()) == "claimed"
    before = len(env.queue.tasks)
    assert sched.run_tick(env, rid, 2) == sched.run_tick(env, rid, 2) == "busy"
    timer, = env.queue.tasks[before:]
    assert timer["payload"] == {
        "eval_run_id": rid, "n": 2, "recover": True, "resume_key": "paused",
    }
    assert timer["delay_seconds"] > sched.TICK_DELAY_S + 5

    def unavailable(*args, **kwargs):
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(env.queue, "enqueue", unavailable)
    with pytest.raises(RuntimeError, match="queue unavailable"):
        sched.tick_task(SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(services=env))),
                        {"eval_run_id": rid, "n": 2})


def test_recovery_after_enqueue_before_claim_crash_avoids_consumed_successor_name(env, monkeypatch):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    queue = ScheduledQueue(sched._now())
    env.queue = queue
    monkeypatch.setattr(sched, "_now", lambda: queue.now)
    # Tick 1 enqueued tick 2, then died before changing tick_seq. The future task is consumed
    # once it records recovery; reusing tick 2's normal Cloud Tasks name cannot send it again.
    queue.enqueue("tick", {"eval_run_id": rid, "n": 2}, task_id=f"{rid}-tick-2")
    for _ in range(10):
        if not queue.tasks:
            break
        queue.deliver(env)
        for sid, run in active_runs(env):
            finish(env, sid, run)
        if env.repository.get_run(rid)["status"] not in sched.ACTIVE:
            break
    assert env.repository.get_run(rid)["status"] == "done"


@pytest.mark.parametrize("outcome", ["done", "failed"])
def test_cancel_accepted_during_final_save_has_terminal_precedence(env, monkeypatch, outcome):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    tick(env, rid)
    for sid, run in active_runs(env):
        finish(env, sid, run, outcome, "deadline_exceeded" if outcome == "failed" else None)
    real = env.repository.save_tick

    def cancel_before_commit(run_id, owner, updates):
        if updates.get("status") in {"done", "failed"}:
            env.repository.cancel_run(run_id)
        return real(run_id, owner, updates)

    monkeypatch.setattr(env.repository, "save_tick", cancel_before_commit)
    tick(env, rid)
    doc = env.repository.get_run(rid)
    assert doc["cancel_requested"] is True
    assert doc["status"] == ("partial" if outcome == "done" else "cancelled")
