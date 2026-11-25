"""Tick scheduler core (05 R6): a deterministic fake harness, no LLM, no network.

The prod worker is simulated by flipping RunDocs to done/failed between ticks. Ticks are driven
by calling `run_tick` with the group doc's own `tick_seq`, as the queue would; nothing calls GET.
"""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from onolys_api.repo.models import utcnow
from test_app import AUTH, ENV, client
from test_eval_create import _two_sessions
from test_runs import SEL1, SEL2, start
from test_uploads import transcript

from onolys_eval_backend import eval_scheduler as sched
from onolys_eval_backend.config import EvalConfig
from onolys_eval_backend.costs import PriceBook
from onolys_eval_backend.eval_scheduler import run_tick

pytest_plugins = ["test_runs"]
UID = "eval-owner"
TWO_PROVIDERS = {
    "models": ["claude", "gemini"], "tiers": ["claude-sonnet-5-5", "gemini-4-neon"],
    "efforts": ["low"],
}


class RunQueue:
    """Stands in for the api's CloudTasksQueue (run tasks)."""

    def __init__(self):
        self.tasks = []

    def enqueue(self, payload):
        self.tasks.append(payload)


@pytest.fixture
def env(services):
    config = EvalConfig.from_env({**ENV})
    services.config = replace(config, eval_owner_uid=UID)
    services.run_queue = RunQueue()
    services.prices = PriceBook({})
    return services


def add_sessions(services, *names):
    m = _two_sessions(services)
    base = m["sessions"][1]
    for name in names:
        if name in {s["session_id"] for s in m["sessions"]}:
            continue
        m["sessions"].append({**base, "session_id": name, "title": name.title()})
        data = transcript()
        data["turns"][0]["text"] = f"unique opening for {name} " + "actual speech " * 30  # distinct content => distinct sid
        services.datasets.write_json(f"datasets/synthetic/{name}/transcript.json", data)
    services.datasets.write_json("datasets/synthetic/manifest.json", m)
    services.datasets.delete("datasets/synthetic/one/gold.json")  # no gold => no auto Human unit


def create(env, sessions, *, selection=SEL2, repeats=2, engines=("miti",)):
    add_sessions(env, *sessions)
    c = client(services=env)
    r = start(c, engines=list(engines), selection=selection, repeats=1 if repeats == 2 else repeats,
              input={"dataset_id": "synthetic", "session_ids": list(sessions)})
    assert r.status_code == 200, r.text
    rid = r.json()["run_id"]
    if repeats == 2:  # the API only offers 1 or 3 repeats; the scheduler must not care
        doc = env.repository.get_run(rid)
        cells = len(doc["combos"]) * len([e for e in doc["engines"] if e != "human"])
        env.repository.update_run(rid, {"repeats": 2, "total_units": len(sessions) * cells * 2})
    return rid


def runs_of(env, sid):
    return env.repo.list_runs(UID, sid)


def all_runs(env):
    out = []
    for p in env.repo._docs:
        if p.startswith("sessions/") and p.count("/") == 1:
            out += [(p.split("/")[1], r) for r in runs_of(env, p.split("/")[1])]
    return out


def active_runs(env):
    return [(sid, r) for sid, r in all_runs(env) if r.status not in ("done", "failed")]


def provider(run):
    return run.eval.resolved_route["litellm_id"].split("/")[0]


def finish(env, sid, run, status="done", error=None, usage=None):
    env.repo.update_run(UID, sid, run.run_id, {
        "status": status, "error": error, "ended": utcnow(),
        "run_info": {"usage": usage or {"input_tokens": 10, "output_tokens": 5, "calls": 1,
                                        "cost_usd": 0.25}},
    })
    env.repo.update_session(
        UID, sid, {"state": "report_ready" if status == "done" else "failed"},
        status={"state": "report_ready" if status == "done" else "failed"},
    )


def tick(env, rid):
    doc = env.repository.get_run(rid)
    return run_tick(env, rid, doc["tick_seq"])


def check_invariants(env, peaks=None):
    per_session, per_provider = {}, {}
    for sid, run in active_runs(env):
        per_session[sid] = per_session.get(sid, 0) + 1
        per_provider[provider(run)] = per_provider.get(provider(run), 0) + 1
    assert all(n == 1 for n in per_session.values()), per_session  # one active run per session
    cap = env.config.max_per_provider
    assert all(n <= cap for n in per_provider.values()), (per_provider, cap)
    if peaks is not None:
        for name, n in per_provider.items():
            peaks[name] = max(peaks.get(name, 0), n)


def drive(env, rids, *, rounds=60, outcome=lambda sid, run, n: ("done", None), peaks=None):
    """Tick every eval run, then let the worker finish the runs that were already active."""
    for _ in range(rounds):
        before = {r.run_id for _, r in active_runs(env)}
        for rid in rids:
            tick(env, rid)
        check_invariants(env, peaks)
        for sid, run in active_runs(env):
            if run.run_id in before:
                status, error = outcome(sid, run, len(runs_of(env, sid)))
                finish(env, sid, run, status, error)
        if all(env.repository.get_run(r)["status"] not in sched.ACTIVE for r in rids):
            return
    raise AssertionError("eval runs did not finish")


def test_three_sessions_two_combos_two_repeats_all_twelve_cells_terminal(env):
    rid = create(env, ["one", "two", "three"])
    doc = env.repository.get_run(rid)
    assert doc["total_units"] == 12 and doc["completed_units"] == 0 and len(doc["sessions"]) == 3
    drive(env, [rid])  # no GET anywhere: ticks and the worker alone finish the run
    doc = env.repository.get_run(rid)
    assert doc["status"] == "done" and "finished_at" in doc
    assert (doc["completed_units"], doc["done_units"], doc["failed_units"]) == (12, 12, 0)
    assert len(all_runs(env)) == 12 and not active_runs(env)
    for entry in doc["sessions"].values():
        assert entry["cursor"] == 4 and entry["active_run_id"] is None and entry["state"] == "done"
        assert [(r["combo_key"], r["repeat"], r["attempt"], r["status"]) for r in entry["runs"]] == [
            ("claude/claude-sonnet-5-5/low", 0, 0, "done"),
            ("claude/claude-sonnet-5-5/low", 1, 0, "done"),
            ("claude/claude-sonnet-5-5/high", 0, 0, "done"),
            ("claude/claude-sonnet-5-5/high", 1, 0, "done"),
        ]
    assert doc["usage"] == {"input_tokens": 120, "output_tokens": 60, "calls": 12, "cost_usd": 3.0}
    assert doc["cost_usd_est"] == pytest.approx(3.0) and doc["unpriced_units"] == 0
    assert env.repository.get_slots("anthropic")["holders"] == {}  # no leaked slot
    # one RunDoc per cell, each an eval run on this group, n_runs=1, one route
    sample = all_runs(env)[0][1]
    assert (sample.eval.eval_run_id, sample.n_runs) == (rid, 1)
    assert sample.eval.engine == "miti" and sample.eval.route_override["effort"] in {"low", "high"}
    assert len(env.run_queue.tasks) == 12


def test_tick_enqueues_next_tick_first_and_stops_after_rollup(env):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    assert env.queue.tasks[-1]["payload"] == {"eval_run_id": rid, "n": 1}
    assert tick(env, rid) == "ran"
    last = env.queue.tasks[-1]
    assert last["payload"] == {"eval_run_id": rid, "n": 2} and last["delay_seconds"] == 10
    doc = env.repository.get_run(rid)
    assert (doc["tick_seq"], doc["status"]) == (2, "running") and doc["last_tick_at"]
    ((sid, entry),) = doc["sessions"].items()
    finish(env, sid, runs_of(env, sid)[0])
    assert tick(env, rid) == "ran"
    assert env.repository.get_run(rid)["status"] == "done"
    assert tick(env, rid) == "noop"  # the already-enqueued tick 3 does nothing and enqueues none
    sent = len(env.queue.tasks)
    assert run_tick(env, rid, 3) == "noop" and len(env.queue.tasks) == sent


def test_stale_or_duplicate_ticks_are_noops(env):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    assert run_tick(env, rid, 5) == "noop" and run_tick(env, "missing", 1) == "noop"
    assert run_tick(env, rid, 1) == "ran"
    created = len(all_runs(env))
    assert run_tick(env, rid, 1) == "noop"  # redelivery of tick 1: tick_seq is already 2
    assert len(all_runs(env)) == created == 1
    # the compare-and-set alone also refuses a second winner for the same n
    assert env.repository.advance_tick(rid, 1, "x") is False


def test_two_eval_runs_on_two_providers_never_exceed_the_cap(env):
    a = create(env, ["one", "two", "three"], selection=TWO_PROVIDERS, repeats=1)
    b = create(env, ["four", "five", "six"], selection=TWO_PROVIDERS, repeats=1)
    peaks = {}
    drive(env, [a, b], peaks=peaks)
    assert peaks == {"anthropic": 2, "gemini": 2}  # the cap is reached and never passed
    for rid in (a, b):
        doc = env.repository.get_run(rid)
        assert (doc["status"], doc["done_units"], doc["total_units"]) == ("done", 6, 6)
    assert len(all_runs(env)) == 12
    assert env.repository.get_slots("anthropic")["holders"] == {}
    assert env.repository.get_slots("gemini")["holders"] == {}


@pytest.mark.parametrize("cap", [1, 2, 3])
def test_a_changed_cap_changes_behaviour(env, cap):
    env.config = replace(env.config, max_per_provider=cap)
    rid = create(env, ["one", "two", "three"], selection=SEL1, repeats=1)
    peaks = {}
    drive(env, [rid], peaks=peaks)
    assert peaks == {"anthropic": cap}
    assert env.repository.get_run(rid)["status"] == "done"


def test_lowering_the_cap_mid_run_drains_to_the_new_cap(env):
    rid = create(env, ["one", "two", "three"], selection=SEL1, repeats=2)
    tick(env, rid)
    assert len(active_runs(env)) == 2
    env.config = replace(env.config, max_per_provider=1)
    peaks = {}
    for _ in range(4):  # the two in flight finish; afterwards one at a time
        for sid, run in active_runs(env):
            finish(env, sid, run)
        tick(env, rid)
        assert len(active_runs(env)) <= 1
    drive(env, [rid], peaks=peaks)
    assert peaks.get("anthropic", 0) <= 1


def test_crash_between_create_and_record_leaves_no_duplicate_or_leaked_slot(env, monkeypatch):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    real = env.repository.update_run
    state = {"boom": True}

    def flaky(run_id, updates):
        if state["boom"] and any(e["active_run_id"] for e in updates.get("sessions", {}).values()):
            state["boom"] = False
            raise RuntimeError("process died after create_run, before recording")
        return real(run_id, updates)

    monkeypatch.setattr(env.repository, "update_run", flaky)
    with pytest.raises(RuntimeError):
        tick(env, rid)
    ((sid, _),) = env.repository.get_run(rid)["sessions"].items()
    assert len(runs_of(env, sid)) == 1  # the RunDoc exists ...
    assert env.repository.get_run(rid)["sessions"][sid]["active_run_id"] is None  # ... unrecorded
    assert len(env.repository.get_slots("anthropic")["holders"]) == 1
    tick(env, rid)  # the retry adopts the existing RunDoc by its deterministic id
    doc = env.repository.get_run(rid)
    assert len(runs_of(env, sid)) == 1 and len(env.run_queue.tasks) == 1  # no duplicate run/task
    assert doc["sessions"][sid]["active_run_id"] == runs_of(env, sid)[0].run_id
    assert len(env.repository.get_slots("anthropic")["holders"]) == 1  # the same slot, not two
    drive(env, [rid])
    assert env.repository.get_run(rid)["status"] == "done"
    assert env.repository.get_slots("anthropic")["holders"] == {}


def test_a_failed_create_releases_its_slot_and_is_retried(env, monkeypatch):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    real = sched.api_create_run
    calls = []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return real(*a, **k)

    monkeypatch.setattr(sched, "api_create_run", flaky)
    tick(env, rid)
    assert all_runs(env) == [] and env.repository.get_slots("anthropic")["holders"] == {}
    tick(env, rid)
    assert len(all_runs(env)) == 1


def test_sweep_drops_dead_holders_so_capacity_is_not_leaked(env):
    rid = create(env, ["one", "two", "three"], selection=SEL1, repeats=1)
    # holders left behind by an eval run that no longer exists, and by a finished one
    env.repository.claim_slot("anthropic", "ghost-1", "gone-eval-run", 2)
    env.repository.claim_slot("anthropic", "ghost-2", "gone-eval-run", 2)
    tick(env, rid)  # without the sweep both slots would be taken: nothing could start
    assert len(active_runs(env)) == 2
    holders = env.repository.get_slots("anthropic")["holders"]
    assert "ghost-1" not in holders and "ghost-2" not in holders and len(holders) == 2


def test_internal_error_gets_exactly_one_new_attempt_then_stays_failed(env):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    drive(env, [rid], outcome=lambda sid, run, n: ("failed", "internal_error"))
    doc = env.repository.get_run(rid)
    ((sid, entry),) = doc["sessions"].items()
    runs = runs_of(env, sid)
    assert len(runs) == 2 and runs[0].run_id != runs[1].run_id  # 1 + exactly one retry
    assert [(r["attempt"], r["status"], r["error"]) for r in entry["runs"]] == [
        (0, "failed", "internal_error"), (1, "failed", "internal_error")]
    assert (doc["status"], doc["failed_units"], doc["completed_units"], doc["done_units"]) == (
        "failed", 1, 1, 0)
    assert doc["cells_wait"][f"{sid}|miti|claude/claude-sonnet-5-5/low|0"]["internal_retries"] == 1
    assert env.repository.get_slots("anthropic")["holders"] == {}


def test_internal_error_retry_that_succeeds_counts_one_done_cell(env):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    drive(env, [rid], outcome=lambda sid, run, n: ("failed", "internal_error") if n == 1
          else ("done", None))
    doc = env.repository.get_run(rid)
    assert (doc["status"], doc["done_units"], doc["failed_units"], doc["completed_units"]) == (
        "done", 1, 0, 1)
    assert doc["usage"]["calls"] == 2  # the failed attempt's spend is kept


def test_internal_retries_follows_config(env):
    env.config = replace(env.config, internal_retries=0)
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    drive(env, [rid], outcome=lambda sid, run, n: ("failed", "internal_error"))
    assert len(all_runs(env)) == 1


@pytest.mark.parametrize("code", ["deadline_exceeded", "output_invalid", "run_failed"])  # overload: test_eval_resilience
def test_other_failure_codes_stay_failed_without_a_new_run(env, code):
    # upstream_unavailable / rate_limited are plain failures until Task 6 adds overload backoff
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    drive(env, [rid], outcome=lambda sid, run, n: ("failed", code))
    doc = env.repository.get_run(rid)
    assert len(all_runs(env)) == 1
    assert (doc["status"], doc["failed_units"]) == ("failed", 1)
    ((_, entry),) = doc["sessions"].items()
    assert entry["runs"][0]["error"] == code


def test_a_run_failed_by_a_code_version_change_is_not_retried(env):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    tick(env, rid)
    ((sid, run),) = active_runs(env)
    env.repo.update_run(UID, sid, run.run_id, {"code_version": "older-build"})
    finish(env, sid, run, "failed", "internal_error")  # the worker's drift failure is this code
    tick(env, rid)
    doc = env.repository.get_run(rid)
    assert len(all_runs(env)) == 1 and (doc["status"], doc["failed_units"]) == ("failed", 1)


def test_not_ready_session_is_retried_next_tick(env):
    a = create(env, ["one"], selection=SEL1, repeats=1)
    b = create(env, ["one"], selection=SEL1, repeats=1)  # same dataset session => same sid
    assert list(env.repository.get_run(a)["sessions"]) == list(env.repository.get_run(b)["sessions"])
    tick(env, a)
    ((sid, run),) = active_runs(env)
    tick(env, b)  # the session is busy: the repo refuses a second active run
    doc_b = env.repository.get_run(b)
    assert len(runs_of(env, sid)) == 1 and doc_b["sessions"][sid]["active_run_id"] is None
    assert doc_b["status"] == "running" and doc_b["tick_seq"] == 2  # not failed; chain goes on
    assert list(env.repository.get_slots("anthropic")["holders"]) == [run.run_id]  # released
    finish(env, sid, run)
    tick(env, b)
    assert len(runs_of(env, sid)) == 2  # b started once the session was free
    drive(env, [a, b])
    assert [env.repository.get_run(r)["status"] for r in (a, b)] == ["done", "done"]
    assert len(all_runs(env)) == 2


def test_two_engines_get_distinct_deterministic_run_ids(env):
    rid = create(env, ["one"], selection=SEL1, repeats=1, engines=("miti", "oneshot:miti"))
    doc = env.repository.get_run(rid)
    assert doc["total_units"] == 2
    drive(env, [rid])
    ((sid, entry),) = doc["sessions"].items()
    runs = runs_of(env, sid)
    assert sorted(r.eval.engine for r in runs) == ["miti", "oneshot:miti"]
    assert len({r.run_id for r in runs}) == 2
    assert env.repository.get_run(rid)["status"] == "done"


def test_config_drift_fails_the_cell_without_creating_a_run(env, monkeypatch):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    real = sched.eval_snapshot

    def changed(settings, preset, engine, combo):
        route, version = real(settings, preset, engine, combo)
        return {**route, "max_output_tokens": route["max_output_tokens"] + 1}, version

    monkeypatch.setattr(sched, "eval_snapshot", changed)
    tick(env, rid)
    doc = env.repository.get_run(rid)
    ((_, entry),) = doc["sessions"].items()
    assert all_runs(env) == [] and env.repository.get_slots("anthropic")["holders"] == {}
    assert entry["runs"][0]["error"] == "execution_config_changed"
    assert (doc["status"], doc["failed_units"], doc["completed_units"]) == ("failed", 1, 1)


def test_costs_priced_from_the_price_book_when_usage_reports_none(env):
    env.prices = PriceBook({"anthropic/claude-sonnet-5-5": {
        "input_usd_per_million": 1000000.0, "output_usd_per_million": 0.0}})
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    tick(env, rid)
    ((sid, run),) = active_runs(env)
    finish(env, sid, run, usage={"input_tokens": 3, "output_tokens": 1, "calls": 1,
                                 "cost_usd": None})
    tick(env, rid)
    doc = env.repository.get_run(rid)
    assert doc["cost_usd_est"] == pytest.approx(3.0) and doc["unpriced_units"] == 0
    assert doc["usage"]["cost_usd"] is None  # a missing reported cost stays unknown, as today


def test_cancel_requested_stops_new_runs_and_ends_the_chain(env):
    rid = create(env, ["one", "two"], selection=SEL1, repeats=2)
    tick(env, rid)
    assert len(active_runs(env)) == 2
    env.repository.cancel_run(rid)
    for sid, run in active_runs(env):
        finish(env, sid, run)
    tick(env, rid)
    assert len(all_runs(env)) == 2  # nothing new started after the request
    assert env.repository.get_run(rid)["status"] == "partial"  # Task 7 refines the details


def test_tick_endpoint_runs_a_tick_for_the_task_identity_only(env):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    c = client(services=env)
    assert c.post("/internal/tasks/tick", json={"eval_run_id": rid, "n": 1}).status_code == 401
    r = c.post("/internal/tasks/tick", headers=AUTH, json={"eval_run_id": rid, "n": 1})
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert len(all_runs(env)) == 1 and env.repository.get_run(rid)["tick_seq"] == 2
    for bad in ({}, {"eval_run_id": rid}, {"eval_run_id": rid, "n": "1"}, {"eval_run_id": "", "n": 1}):
        assert c.post("/internal/tasks/tick", headers=AUTH, json=bad).status_code == 422
    assert c.post("/internal/tasks/tick", headers=AUTH,
                  json={"eval_run_id": "unknown", "n": 1}).status_code == 200  # a no-op


def test_stale_tick_is_re_enqueued_from_get_but_a_fresh_chain_is_left_alone(env, monkeypatch):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    tick(env, rid)
    doc = env.repository.get_run(rid)
    now = datetime.fromisoformat(doc["last_tick_at"])
    tasks = len(env.queue.tasks)
    monkeypatch.setattr(sched, "_now", lambda: now + timedelta(seconds=30))
    assert sched.ensure_tick(env, rid, doc) is False and len(env.queue.tasks) == tasks
    later = now + timedelta(seconds=300)
    monkeypatch.setattr(sched, "_now", lambda: later)
    assert sched.ensure_tick(env, rid, doc) is True
    assert env.queue.tasks[-1]["payload"] == {"eval_run_id": rid, "n": doc["tick_seq"]}
    epoch = int(later.timestamp() // sched.STALE_TICK_S)
    assert f"{rid}-tick-{doc['tick_seq']}-r{epoch}" in env.queue._task_ids
    assert sched.ensure_tick(env, rid, doc) is True and len(env.queue.tasks) == tasks + 1  # deduped
    assert sched.ensure_tick(env, rid, {**doc, "status": "done"}) is False
    # the re-enqueued tick drives the run on
    monkeypatch.undo()
    assert run_tick(env, rid, doc["tick_seq"]) == "ran"


def test_get_run_detail_restarts_a_stalled_chain(env, monkeypatch):
    rid = create(env, ["one"], selection=SEL1, repeats=1)
    old = datetime.now(UTC) - timedelta(minutes=10)
    env.repository.update_run(rid, {"created_at": old.isoformat()})  # no tick ever ran
    tasks = len(env.queue.tasks)
    c = client(services=env)
    c.get(f"/v1/runs/{rid}", headers=AUTH)
    assert len(env.queue.tasks) == tasks + 1
    assert env.queue.tasks[-1]["payload"] == {"eval_run_id": rid, "n": 1}


def test_worst_case_group_doc_stays_under_the_firestore_limit(env):
    """499 cells x 8 attempts of refs (R4): the serialized doc is far below 1 MiB."""
    from onolys_eval_backend.eval_group import session_entry

    entry = session_entry("one", 0, "0" * 64)
    entry["runs"] = [
        {"run_id": "a" * 32, "combo_key": "claude/claude-sonnet-5-5/low", "engine": "oneshot:miti",
         "repeat": 0, "attempt": i % 8, "status": "failed", "error": "internal_error"}
        for i in range(499 * 8)
    ]
    assert len(json.dumps({"sessions": {"s" * 32: entry}})) < 1_000_000
