"""Offline concurrency regressions for scheduler ownership and start admission."""

from datetime import timedelta

import pytest
from test_eval_scheduler import (
    SEL1,
    active_runs,
    all_runs,
    create,
    drive,
    finish,
    tick,
)

from onolys_eval_backend import eval_scheduler as sched

pytest_plugins = ["test_runs", "test_eval_scheduler"]


def test_slow_tick_excludes_next_delivery_without_losing_created_refs(env, monkeypatch):
    rid = create(env, ["one", "two"], selection=SEL1, repeats=1)
    real = sched._create
    overlaps = []

    def slow(*args):
        overlaps.append(sched.run_tick(env, rid, 2))
        return real(*args)

    monkeypatch.setattr(sched, "_create", slow)
    tick(env, rid)
    assert overlaps == ["busy", "busy"]
    doc = env.repository.get_run(rid)
    assert sum(bool(e["active_run_id"]) for e in doc["sessions"].values()) == 2
    drive(env, [rid])
    assert env.repository.get_run(rid)["done_units"] == 2


def test_cancel_between_idle_sessions_prevents_later_start(env, monkeypatch):
    rid = create(env, ["one", "two"], selection=SEL1, repeats=1)
    real = sched._create

    def cancel_after_first(*args):
        result = real(*args)
        env.repository.cancel_run(rid)
        return result

    monkeypatch.setattr(sched, "_create", cancel_after_first)
    tick(env, rid)
    assert len(all_runs(env)) == 1
    doc = env.repository.get_run(rid)
    assert doc["cancelled_units"] == 1
    drive(env, [rid])
    assert env.repository.get_run(rid)["status"] == "partial"


def test_cancel_just_before_transactional_start_admission_prevents_creation(env, monkeypatch):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    real = sched.api_create_run

    def cancel_before_start(*args, **kwargs):
        env.repository.cancel_run(rid)
        return real(*args, **kwargs)

    monkeypatch.setattr(sched, "api_create_run", cancel_before_start)
    tick(env, rid)
    assert all_runs(env) == []
    assert env.repository.get_slots("anthropic")["holders"] == {}
    assert env.repository.get_run(rid)["status"] == "cancelled"


def test_expired_owner_cannot_create_or_overwrite_recovered_tick(env, monkeypatch):
    rid = create(env, ["one", "two"], selection=SEL1, repeats=1)
    real = sched.api_create_run
    original_now = sched._now()
    recovered = []

    def pause_before_start(*args, **kwargs):
        if not recovered:
            recovered.append(True)
            monkeypatch.setattr(sched, "_now", lambda: original_now + timedelta(hours=1))
            assert sched.run_tick(env, rid, 2) == "ran"
            for sid, run in active_runs(env):
                finish(env, sid, run)
            assert tick(env, rid) == "ran"
        return real(*args, **kwargs)

    monkeypatch.setattr(sched, "api_create_run", pause_before_start)
    tick(env, rid)
    doc = env.repository.get_run(rid)
    assert doc["status"] == "done" and doc["done_units"] == 2
    assert len(all_runs(env)) == 2
    assert env.repository.get_slots("anthropic")["holders"] == {}


def test_persistent_create_failure_reaches_isolation_limit_and_releases_slots(env, monkeypatch):
    rid = create(env, ["one", "two"], selection=SEL1, repeats=1)

    def broken(*args, **kwargs):
        raise RuntimeError("persistent create error")

    monkeypatch.setattr(sched, "api_create_run", broken)
    for _ in range(3):
        tick(env, rid)
        assert env.repository.get_slots("anthropic")["holders"] == {}
    doc = env.repository.get_run(rid)
    assert doc["status"] == "failed" and doc["failed_units"] == 2
    assert all(e["runs"][-1]["error"] == "scheduler_error" for e in doc["sessions"].values())


@pytest.mark.parametrize("cancel", [True, False])
def test_human_completion_does_not_make_unsuccessful_ai_partial(env, cancel):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    doc = env.repository.get_run(rid)
    env.repository.update_run(rid, {
        "human": True, "engines": [*doc["engines"], "human"],
        "total_units": 2, "completed_units": 1, "done_units": 1,
    })
    if cancel:
        env.repository.cancel_run(rid)
        tick(env, rid)
    else:
        drive(env, [rid], outcome=lambda *a: ("failed", "deadline_exceeded"))
    doc = env.repository.get_run(rid)
    assert doc["status"] == ("cancelled" if cancel else "failed")
    assert doc["done_units"] == 1  # keep the public Human counter convention


def test_busy_next_tick_does_not_enqueue_a_successor_early(env, monkeypatch):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    real = sched._create

    def overlap(*args):
        before = len(env.queue.tasks)
        assert sched.run_tick(env, rid, 2) == "busy"
        added = env.queue.tasks[before:]
        assert len(added) == 1 and added[0]["payload"]["recover"] is True
        assert added[0]["payload"]["n"] == 2
        return real(*args)

    monkeypatch.setattr(sched, "_create", overlap)
    tick(env, rid)


def test_successor_delivered_before_predecessor_claim_retries(env, monkeypatch):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    real = env.queue.enqueue

    def enqueue(kind, payload, **kwargs):
        if kwargs.get("task_id") == f"{rid}-tick-2":
            assert sched.run_tick(env, rid, 2) == "busy"
        return real(kind, payload, **kwargs)

    monkeypatch.setattr(env.queue, "enqueue", enqueue)
    tick(env, rid)
    drive(env, [rid])
    assert env.repository.get_run(rid)["status"] == "done"


def test_enqueue_failure_preserves_sequence_and_can_retry(env, monkeypatch):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    original = env.queue.enqueue

    def fail(*args, **kwargs):
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(env.queue, "enqueue", fail)
    with pytest.raises(RuntimeError, match="queue unavailable"):
        tick(env, rid)
    doc = env.repository.get_run(rid)
    assert doc["tick_seq"] == 1 and not doc.get("tick_owner")
    monkeypatch.setattr(env.queue, "enqueue", original)
    drive(env, [rid])
    assert env.repository.get_run(rid)["status"] == "done"


def test_cancel_recovery_fences_paused_create_even_after_group_deletion(env, monkeypatch):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    real = sched.api_create_run
    original_now = sched._now()

    def expired_before_create(*args, **kwargs):
        env.repository.cancel_run(rid)
        monkeypatch.setattr(sched, "_now", lambda: original_now + timedelta(hours=1))
        assert sched.run_tick(env, rid, 2) == "ran"
        assert env.repository.get_run(rid)["status"] == "cancelled"
        assert env.repository.get_slots("anthropic")["holders"] == {}
        env.repository.delete_run(rid)
        return real(*args, **kwargs)

    monkeypatch.setattr(sched, "api_create_run", expired_before_create)
    tick(env, rid)
    assert all_runs(env) == []
    assert env.repository.get_run(rid) is None
    assert env.repository.get_slots("anthropic")["holders"] == {}


def test_cancel_after_create_before_ref_save_adopts_in_flight_work(env, monkeypatch):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    real = env.repository.update_run
    broken = []

    def crash(run_id, updates):
        if not broken and any(e["active_run_id"] for e in updates.get("sessions", {}).values()):
            broken.append(True)
            raise RuntimeError("died before recording")
        return real(run_id, updates)

    monkeypatch.setattr(env.repository, "update_run", crash)
    with pytest.raises(RuntimeError, match="died before recording"):
        tick(env, rid)
    env.repository.cancel_run(rid)
    tick(env, rid)
    doc = env.repository.get_run(rid)
    assert doc["status"] == "running" and doc["cancelled_units"] == 0
    assert len(active_runs(env)) == 1
    assert len(env.repository.get_slots("anthropic")["holders"]) == 1
    drive(env, [rid])
    assert env.repository.get_run(rid)["status"] == "partial"
