"""Server-driven tick scheduler for eval runs (05 R6): the browser is never needed.

`POST /internal/tasks/tick {eval_run_id, n}` runs one scheduling round for one eval run:

1. enqueue tick n+1 BEFORE any work (a crash cannot end the chain), then atomically lease
   the group and advance `tick_seq`; competing ticks queue a durable lease-recovery timer;
   every snapshot write and RunDoc admission is fenced by the lease token;
2. fold terminal RunDocs of active sessions into the group doc, release their provider slots;
3. classify failures (`internal_error` -> one retry; everything else stays failed);
4. fill every idle session in order with its next cell: transactional `eval_slots/{provider}`
   claim (cap from config), drift check, `create_run(is_eval=True)` with a deterministic id;
5. all cells terminal -> roll the status up; later ticks are no-ops.

Task 6 (R6b-R6d): overload `waiting` + provider cooldown, per-cell isolation (`_isolated`),
provider breaker (`_record_outcome`). Cancel (R7): `_cancel_cells`.
"""

import hashlib
import logging
import math
import random
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from functools import partial
from types import SimpleNamespace
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from onolys_api.engines import eval_snapshot
from onolys_api.errors import ApiError
from onolys_api.repo.base import NotFoundError
from onolys_api.repo.models import EvalRunInfo
from onolys_api.routes.runs import EvalDisabled
from onolys_api.routes.runs import RunRequest as ApiRunRequest
from onolys_api.routes.runs import create_run as api_create_run
from onolys_engine_core.errors import ConfigError, InputError

from onolys_eval_backend.matrix import combo_key

router = APIRouter()
logger = logging.getLogger(__name__)

TICK_LEASE_S = 120  # recovery may fence a paused owner; every state/start write checks its token
TICK_DELAY_S = 10
STALE_TICK_S = 60  # GET re-enqueues a tick when none has run for this long while active
ACTIVE = {"queued", "running"}
RUN_TERMINAL = {"done", "failed"}  # RunStatus values of a finished RunDoc
# Provider capacity codes: the cell goes `waiting` behind a provider cooldown (R6b).
OVERLOAD_CODES = {"upstream_unavailable", "rate_limited"}
OVERLOAD_BASE_S, OVERLOAD_CAP_S, OVERLOAD_MAX_RETRIES = 15, 120, 6
HANDLER_ERROR_LIMIT = 3  # consecutive handler errors on one cell before it fails (R6c)
ZERO_USAGE = {"input_tokens": 0, "output_tokens": 0, "calls": 0, "cost_usd": 0.0}


class TickOwnershipLost(Exception):
    """A recovered tick fenced this handler; it must stop without touching any more state."""


class _AdmittedRepo:
    """Delegate normal API reads, but gate its actual RunDoc transaction on this tick."""

    def __init__(self, repo, repository, eval_run_id, owner):
        self.repo, self.repository = repo, repository
        self.eval_run_id, self.owner = eval_run_id, owner

    def __getattr__(self, name):
        return getattr(self.repo, name)

    def start_run(self, *args, **kwargs):
        return self.repository.admit_start(
            self.repo, self.eval_run_id, self.owner, *args, **kwargs,
        )


def _now() -> datetime:
    """Tests replace this (fake clock)."""
    return datetime.now(UTC)


def _jitter() -> float:
    """Tests replace this (deterministic jitter in 0.5-1.0)."""
    return random.uniform(0.5, 1.0)


def plan_cells(doc: dict) -> list[dict]:
    """Per-session plan, the same for every session: engine, combo (combo-major), repeat."""
    return [
        {"engine": engine, "combo": dict(combo), "combo_key": combo_key(combo), "repeat": repeat}
        for engine in doc["engines"]
        if engine != "human"
        for combo in doc["combos"]
        for repeat in range(doc["repeats"])
    ]


def cell_key(sid: str, cell: dict) -> str:
    return f"{sid}|{cell['engine']}|{cell['combo_key']}|{cell['repeat']}"


def run_id_for(eval_run_id: str, sid: str, cell: dict, attempt: int) -> str:
    """Deterministic: a crash between creating a RunDoc and recording it is recovered."""
    raw = f"{eval_run_id}|{sid}|{cell['engine']}|{cell['combo_key']}|{cell['repeat']}|{attempt}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def provider_of(doc: dict, cell: dict) -> str:
    """First segment of the cell's resolved `litellm_id` (`<provider>/<tier>`)."""
    return doc["saved_config"]["resolved_combos"][cell["combo_key"]]["litellm_id"].split("/")[0]


def _cell_refs(entry: dict, cell: dict) -> list[dict]:
    return [
        r for r in entry["runs"]
        if r["combo_key"] == cell["combo_key"] and r["repeat"] == cell["repeat"]
        and r.get("engine") == cell["engine"]
    ]


def classify_failure(services, doc: dict, run, wait: dict) -> str:
    """What a failed RunDoc becomes: "retry" (new attempt, no delay), "wait" or "failed" (final).

    `internal_error` gets `EVAL_INTERNAL_RETRIES` new attempts, unless the run was made by an
    older build (`code_version` differs: a deploy failed it, the worker maps that to
    `internal_error` too). `OVERLOAD_CODES` -> "wait" (provider cooldown) while fewer than 6
    re-tries are used and the total wait stays within `EVAL_OVERLOAD_MAX_WAIT_S`; the chosen delay
    is left in `wait["next_delay_s"]`. Every other code, `deadline_exceeded` included, is failed."""
    code = run.error
    if (
        code == "internal_error"
        and run.code_version == services.config.settings.git_sha
        and wait.get("internal_retries", 0) < services.config.internal_retries
    ):
        return "retry"
    if code in OVERLOAD_CODES:
        k = wait.get("overload_retries", 0)
        if k < OVERLOAD_MAX_RETRIES:
            delay = min(OVERLOAD_CAP_S, OVERLOAD_BASE_S * 2**k) * _jitter()
            if wait.get("overload_waited_s", 0) + delay <= services.config.overload_max_wait_s:
                wait["next_delay_s"] = delay
                return "wait"
    return "failed"


def _parse(stamp: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(stamp) if stamp else None
    except ValueError:
        return None


def _cell_blocked(services, doc: dict, key: str, provider: str) -> bool:
    """Provider skipped by the breaker, cooling down (any eval run), or the cell is backing off."""
    if provider in doc.get("provider_skips", {}):
        return True
    now = _now()
    for until in (
        services.repository.get_slots(provider).get("cooldown_until"),
        doc["cells_wait"].get(key, {}).get("next_try_at"),
    ):
        stamp = _parse(until)
        if stamp and now < stamp:
            return True
    return False


def _advance(entry: dict, cells: list[dict]) -> None:
    """Step the cursor over cells the breaker skipped; the session is done past the last cell."""
    skipped = set(entry.get("skipped_idx", []))
    while entry["cursor"] in skipped:
        entry["cursor"] += 1
    if entry["cursor"] >= len(cells):
        entry["state"] = "done"


def _record_outcome(services, doc: dict, cells: list[dict], provider: str, outcome: str) -> None:
    """Provider breaker (R6d): only FINAL `failed` counts, `done` resets, anything else (cancelled,
    skipped, waiting) neither counts nor resets. At the limit, every not-started cell of the
    provider in this eval run is skipped (`provider_unavailable`); in-flight runs are kept."""
    if outcome not in ("done", "failed") or provider in doc.setdefault("provider_skips", {}):
        return
    counts = doc.setdefault("consecutive_failures", {})
    if outcome == "done":
        counts[provider] = 0
        return
    counts[provider] = counts.get(provider, 0) + 1
    if counts[provider] < services.config.provider_fail_limit:
        return
    skipped_cells = 0
    for sid, entry in doc["sessions"].items():
        start = entry["cursor"] + (1 if entry["active_run_id"] else 0)
        for idx in range(start, len(cells)):
            cell = cells[idx]
            if provider_of(doc, cell) != provider or idx in entry.get("skipped_idx", []):
                continue
            entry.setdefault("skipped_idx", []).append(idx)
            entry["runs"].append({
                "run_id": None, "combo_key": cell["combo_key"], "engine": cell["engine"],
                "repeat": cell["repeat"], "attempt": len(_cell_refs(entry, cell)),
                "status": "skipped", "error": "provider_unavailable",
            })
            doc["cells_wait"].pop(cell_key(sid, cell), None)
            skipped_cells += 1
        if not entry["active_run_id"]:
            _advance(entry, cells)
    doc["skipped_units"] += skipped_cells
    doc["provider_skips"][provider] = {
        "skipped_at": _now().isoformat(), "after_failures": counts[provider],
        "skipped_cells": skipped_cells,
    }


def _fail_cell(doc: dict, entry: dict, cell: dict, cells: list[dict], code: str) -> None:
    """Fail only this cell with `code` (scheduler_error); it never touches the breaker."""
    ref = next((r for r in entry["runs"] if r["run_id"] == entry["active_run_id"]), None) \
        if entry["active_run_id"] else None
    if ref is None:
        ref = {"run_id": None, "combo_key": cell["combo_key"], "engine": cell["engine"],
               "repeat": cell["repeat"], "attempt": len(_cell_refs(entry, cell))}
        entry["runs"].append(ref)
    ref.update(status="failed", error=code)
    entry["active_run_id"] = None
    entry["state"] = "pending"
    entry["cursor"] += 1
    doc["completed_units"] += 1
    doc["failed_units"] += 1
    _advance(entry, cells)


def _isolated(
    services, doc: dict, sid: str, cells: list[dict], handler, *,
    clear_errors=True, preserve_active=False,
):
    """Run one cell's handler (R6c): an unexpected exception is logged (cell key, no payload),
    its partial changes are rolled back, and after 3 consecutive errors only that cell fails.
    Uncertain active-run reads retain their ref/slot until an actual outcome can be read.
    """
    entry = doc["sessions"][sid]
    cell = cells[entry["cursor"]]
    key = cell_key(sid, cell)
    backup = deepcopy({k: doc[k] for k in _STATE_KEYS if k in doc})
    try:
        result = handler()
    except (EvalDisabled, TickOwnershipLost):
        raise
    except Exception as error:
        doc.update(backup)
        logger.exception("tick_cell_error", extra={"cell": key})
        wait = doc["cells_wait"].setdefault(key, {"internal_retries": 0})
        wait["handler_errors"] = wait.get("handler_errors", 0) + 1
        entry = doc["sessions"][sid]
        can_fail = (
            not preserve_active or not entry["active_run_id"] or isinstance(error, NotFoundError)
        )
        if wait["handler_errors"] >= HANDLER_ERROR_LIMIT and can_fail:
            _fail_cell(doc, entry, cell, cells, "scheduler_error")
        return None
    if clear_errors and key in doc["cells_wait"]:
        doc["cells_wait"][key].pop("handler_errors", None)
    return result


def _add_usage(total: dict, usage: dict | None) -> dict:
    usage = usage or {}
    keys = ("input_tokens", "output_tokens", "calls")
    out = {k: total.get(k, 0) + (usage.get(k) or 0) for k in keys}
    old, new = total.get("cost_usd"), usage.get("cost_usd")
    out["cost_usd"] = old + new if old is not None and new is not None else None
    return out


def _cost(services, run, litellm_id: str) -> tuple[float, bool]:
    usage = (run.run_info or {}).get("usage") or {}
    try:
        estimate = services.prices.estimate(usage, litellm_id)
    except Exception:  # missing or broken price data must never block accounting
        return (usage.get("cost_usd") or 0.0), usage.get("cost_usd") is None
    return (estimate.cost_usd or 0.0), estimate.cost_usd is None


def _start_cooldown(services, wait: dict, provider: str) -> None:
    """Record the backoff on the cell and as a provider cooldown on `eval_slots/{provider}`."""
    delay = wait.pop("next_delay_s")
    until = _now() + timedelta(seconds=delay)
    wait["overload_waited_s"] = wait.get("overload_waited_s", 0) + delay
    wait["overload_retries"] = wait.get("overload_retries", 0) + 1
    wait["next_try_at"] = until.isoformat()
    slots = services.repository.get_slots(provider)
    current = _parse(slots.get("cooldown_until"))
    services.repository.update_slot(provider, {
        "overload_streak": slots.get("overload_streak", 0) + 1,
        "cooldown_until": max(until, current).isoformat() if current else until.isoformat(),
    })


def _clear_cooldown(services, provider: str) -> None:
    """A success on the provider resets the streak and the cooldown."""
    slots = services.repository.get_slots(provider)
    if slots.get("cooldown_until") or slots.get("overload_streak"):
        services.repository.update_slot(provider, {"overload_streak": 0, "cooldown_until": None})


def _fold_session(services, doc: dict, sid: str, cells: list[dict], run=None) -> None:
    """Fold a terminal active RunDoc into the doc. Its slot is dropped by `sweep_slots`."""
    entry = doc["sessions"][sid]
    run_id = entry["active_run_id"]
    uid = services.config.eval_owner_uid
    if run is None:
        runs = services.repo.get_runs(uid, sid, [run_id])
        run = runs[0] if runs else None
    if run is None or run.status not in RUN_TERMINAL:
        return
    cell = cells[entry["cursor"]]
    provider = provider_of(doc, cell)
    ref = next(r for r in entry["runs"] if r["run_id"] == run_id)
    key = cell_key(sid, cell)
    wait = doc["cells_wait"].setdefault(key, {"internal_retries": 0})
    outcome = "done" if run.status == "done" else classify_failure(services, doc, run, wait)
    ref["status"] = "waiting" if outcome == "wait" else run.status
    if run.error:
        ref["error"] = run.error
    cost, unpriced = _cost(services, run, doc["saved_config"]["resolved_combos"][
        cell["combo_key"]]["litellm_id"])
    doc["usage"] = _add_usage(doc["usage"], (run.run_info or {}).get("usage"))
    doc["cost_usd_est"] = doc.get("cost_usd_est", 0) + cost
    doc["unpriced_units"] = doc.get("unpriced_units", 0) + int(unpriced)
    entry["active_run_id"] = None
    entry["state"] = "pending"
    if outcome == "retry":
        wait["internal_retries"] = wait.get("internal_retries", 0) + 1
    elif outcome == "wait":
        _start_cooldown(services, wait, provider)
        entry["state"] = "waiting"
    else:
        entry["cursor"] += 1
        doc["completed_units"] += 1
        doc["done_units"] += int(outcome == "done")
        doc["failed_units"] += int(outcome == "failed")
        if outcome == "done":
            _clear_cooldown(services, provider)
        _record_outcome(services, doc, cells, provider, outcome)
        _advance(entry, cells)


def _drifted(services, doc: dict, cell: dict) -> tuple[bool, dict | None, str | None]:
    """Recompute the worker's own snapshot and compare with what was saved at creation."""
    try:
        route, version = eval_snapshot(
            services.config.settings, doc["base_preset"], cell["engine"], cell["combo"]
        )
    except (ConfigError, InputError, ValueError, KeyError):
        return True, None, None
    saved = doc["saved_config"]["resolved_combos"].get(cell["combo_key"])
    expected_version = doc["engine_versions"].get(cell["engine"])
    return route != saved or version != expected_version, route, version


def _create(services, doc, eval_run_id, sid, cell, run_id, route, version) -> str:
    """Create the eval RunDoc. Returns "created", "exists" or "not_ready"."""
    config = services.config
    uid = config.eval_owner_uid
    if services.repo.get_runs(uid, sid, [run_id]):
        return "exists"  # created by a tick that crashed before recording it
    spec = EvalRunInfo(
        eval_run_id=eval_run_id, combo_key=cell["combo_key"], repeat=cell["repeat"],
        engine=cell["engine"], route_override=dict(cell["combo"]), resolved_route=route,
        engine_version=version,
    )
    state = SimpleNamespace(
        repo=_AdmittedRepo(services.repo, services.repository, eval_run_id, doc["_tick_owner"]),
        settings=config.settings, queue=services.run_queue, presets=None
    )
    body = {}
    if services.repo.get_session(uid, sid).preset != doc["base_preset"]:
        from onolys_api.presets import PresetResolver

        state.presets = PresetResolver(config.settings)
        body["preset"] = doc["base_preset"]
    try:
        api_create_run(
            SimpleNamespace(state=state), uid, sid, ApiRunRequest(**body),
            is_eval=True, eval_spec=spec, run_id=run_id,
        )
    except ApiError as error:
        code = error.details[0]["code"] if error.details else None
        if code == "invalid_state":
            return "not_ready"  # session busy (another eval run uses it): retry next tick
        if code == "conflict":
            return "exists"
        # The API may have created and then compensated the RunDoc after queue failure.
        # Adopt it (and fold its actual outcome next tick), keeping the claimed slot/ref.
        if services.repo.get_runs(uid, sid, [run_id]):
            return "exists"
        raise
    except Exception:
        if services.repo.get_runs(uid, sid, [run_id]):
            return "exists"
        raise
    return "created"


def _fill_session(services, doc: dict, eval_run_id: str, sid: str, cells: list[dict]) -> bool:
    """Start the session's next cell if its provider has a free slot. True if a run was recorded."""
    entry = doc["sessions"][sid]
    cell = cells[entry["cursor"]]
    provider = provider_of(doc, cell)
    if _cell_blocked(services, doc, cell_key(sid, cell), provider):
        return False
    attempt = len(_cell_refs(entry, cell))
    run_id = run_id_for(eval_run_id, sid, cell, attempt)
    drifted, route, version = _drifted(services, doc, cell)
    if drifted:
        entry["runs"].append({
            "run_id": None, "combo_key": cell["combo_key"], "engine": cell["engine"],
            "repeat": cell["repeat"], "attempt": attempt, "status": "failed",
            "error": "execution_config_changed",
        })
        entry["cursor"] += 1
        entry["state"] = "pending"
        _advance(entry, cells)
        doc["completed_units"] += 1
        doc["failed_units"] += 1
        return True
    repository = services.repository
    owner = doc["_tick_owner"]
    release = partial(
        repository.release_slot, provider, run_id, eval_run_id=eval_run_id, owner=owner,
    )
    if not repository.claim_slot(
        provider, run_id, eval_run_id, services.config.max_per_provider, owner=owner,
    ):
        return False  # provider is full: this cell waits (it is not skipped), retried next tick
    try:
        outcome = _create(services, doc, eval_run_id, sid, cell, run_id, route, version)
    except Exception:
        release()
        raise  # unexpected errors belong to _isolated and its bounded handler-error budget
    if outcome == "not_ready":
        release()
        return False
    _record_started(entry, cell, run_id, attempt)
    return True


def _record_started(entry, cell, run_id, attempt):
    entry["runs"].append({
        "run_id": run_id, "combo_key": cell["combo_key"], "engine": cell["engine"],
        "repeat": cell["repeat"], "attempt": attempt, "status": "running",
    })
    entry["active_run_id"] = run_id
    entry["state"] = "running"


def _inspect_session(services, eval_run_id, doc, sid, cells):
    """Read once and adopt creation-before-save crashes before cancellation marks cells.

    The new token fences late starts by the old owner. A missing parent/run can fail this
    cell after bounded isolation; an uncertain read must preserve a known active run/slot.
    """
    entry = doc["sessions"][sid]
    cell = cells[entry["cursor"]]
    attempt = len(_cell_refs(entry, cell))
    run_id = entry["active_run_id"] or run_id_for(eval_run_id, sid, cell, attempt)
    runs = services.repo.get_runs(services.config.eval_owner_uid, sid, [run_id])
    if not runs:
        if entry["active_run_id"]:
            raise NotFoundError()
        return None
    if not entry["active_run_id"]:
        _record_started(entry, cell, run_id, attempt)
    return runs[0]


def _holder_dead(services, owner_doc: dict | None, run_id: str) -> bool:
    """A slot holder is dead when its eval run is gone or over, or its RunDoc is terminal."""
    if owner_doc is None or owner_doc.get("status") not in ACTIVE:
        return True
    for sid, entry in owner_doc["sessions"].items():
        for ref in entry["runs"]:
            if ref["run_id"] != run_id:
                continue
            if ref["status"] in RUN_TERMINAL:
                return True
            if sid in owner_doc.get("_unreadable_sessions", set()):
                return False  # unknown outcome: preserve this valid active ref and capacity
            checked = owner_doc.get("_checked_runs", {})
            if run_id in checked:
                return checked[run_id].status in RUN_TERMINAL
            runs = services.repo.get_runs(services.config.eval_owner_uid, sid, [run_id])
            return bool(runs) and runs[0].status in RUN_TERMINAL
    return False  # claimed but not recorded yet: its eval run's next tick resolves it


def sweep_slots(services, doc: dict, eval_run_id: str) -> None:
    """Crash recovery: drop holders whose RunDoc is terminal or whose eval run is gone/over."""
    repository = services.repository
    for provider in sorted({provider_of(doc, c) for c in plan_cells(doc)}):
        for run_id, owner in repository.get_slots(provider).get("holders", {}).items():
            try:
                owner_doc = doc if owner == eval_run_id else repository.get_run(owner)
                dead = _holder_dead(services, owner_doc, run_id)
            except NotFoundError:
                dead = True  # the owning session was removed: no RunDoc can still be active
            except Exception:
                logger.exception("tick_slot_lookup_error", extra={"run_id": run_id})
                continue  # one unreadable holder must not stop unrelated providers/sessions
            if dead:
                repository.release_slot(provider, run_id)


def _rollup(doc: dict) -> None:
    if doc["completed_units"] + doc["skipped_units"] + doc["cancelled_units"] < doc["total_units"]:
        return
    # Public counters include the auto-completed Human gold refs. Status describes AI work.
    human = len(doc["sessions"]) if "human" in doc["engines"] else 0
    done = doc["done_units"] - human
    if doc.get("cancel_requested"):
        doc["status"] = "partial" if done else "cancelled"
    elif done == doc["total_units"] - human:
        doc["status"] = "done"
    elif done:
        doc["status"] = "partial"
    elif doc["cancelled_units"] and not doc["skipped_units"] and not doc["failed_units"]:
        doc["status"] = "cancelled"  # R7: no run done, even if in-flight ones failed
    else:
        doc["status"] = "failed"
    doc["finished_at"] = _now().isoformat()


def _cancel_cells(doc: dict, cells: list[dict]) -> None:
    """R7: every cell not started, `waiting` included, becomes `cancelled`; skipped cells stay
    skipped; the in-flight run (if any) finishes and is kept. Cancelled cells are added to
    `skipped_idx` so the cursor steps over them, and never reach `_record_outcome` (breaker).
    Idempotent: a second pass finds nothing left to mark."""
    for sid, entry in doc["sessions"].items():
        if sid in doc.get("_unreadable_sessions", set()):
            continue  # recovery could not establish whether this cell already started
        gone = set(entry.setdefault("skipped_idx", []))
        start = entry["cursor"] + (1 if entry["active_run_id"] else 0)
        for idx in range(start, len(cells)):
            if idx in gone:
                continue
            cell = cells[idx]
            identity = (cell["engine"], cell["combo_key"], cell["repeat"])
            waiting = next((r for r in entry["runs"] if r["status"] == "waiting"
                            and (r["engine"], r["combo_key"], r["repeat"]) == identity), None)
            if waiting is not None:
                waiting.update(status="cancelled", error="cancelled")
            else:
                entry["runs"].append({
                    "run_id": None, "combo_key": cell["combo_key"], "engine": cell["engine"],
                    "repeat": cell["repeat"], "attempt": len(_cell_refs(entry, cell)),
                    "status": "cancelled", "error": "cancelled",
                })
            entry["skipped_idx"].append(idx)
            doc["cells_wait"].pop(cell_key(sid, cell), None)
            doc["cancelled_units"] += 1
        if not entry["active_run_id"]:
            if entry["state"] == "waiting":
                entry["state"] = "pending"
            _advance(entry, cells)


_STATE_KEYS = (
    "sessions", "cells_wait", "usage", "cost_usd_est", "unpriced_units", "completed_units",
    "done_units", "failed_units", "cancelled_units", "skipped_units", "status",
    "consecutive_failures", "provider_skips",
)


def _save(services, eval_run_id: str, doc: dict) -> None:
    updates = {k: doc[k] for k in _STATE_KEYS if k in doc}
    if "finished_at" in doc:
        updates["finished_at"] = doc["finished_at"]
    if not services.repository.save_tick(eval_run_id, doc["_tick_owner"], updates):
        raise TickOwnershipLost()


def _defer_busy_tick(services, eval_run_id, doc):
    """Durably continue past the queue's two-attempt budget before acknowledging busy work.

    One named timer per live owner fires after its lease, even if that owner dies. If a
    successor arrives before its predecessor claimed ownership, use a short timed probe.
    Recovery resolves the CURRENT sequence on delivery, avoiding an already-consumed task id.
    """
    now = _now()
    lease = _parse(doc.get("tick_lease_until"))
    if doc.get("tick_owner") and lease and lease > now:
        delay = math.ceil((lease - now).total_seconds()) + 1
        suffix = doc["tick_owner"]
    else:
        delay = TICK_DELAY_S
        suffix = str(int(now.timestamp() * 1_000_000))
    services.queue.enqueue(
        "tick", {"eval_run_id": eval_run_id, "n": doc["tick_seq"],
                 "recover": True, "resume_key": suffix},
        delay_seconds=delay, task_id=f"{eval_run_id}-tick-recover-{suffix}",
    )
    return "busy"


def run_tick(services, eval_run_id: str, n: int, *, continuation_key: str | None = None) -> str:
    """One round; busy delivery queues a durable timer beyond the current owner's lease."""
    repository = services.repository
    doc = repository.get_run(eval_run_id)
    if doc is None or doc.get("status") not in ACTIVE:
        return "noop"
    if doc.get("tick_seq") != n:
        # Its predecessor enqueues first and may not yet have advanced the sequence.
        if n == doc.get("tick_seq", 0) + 1:
            return _defer_busy_tick(services, eval_run_id, doc)
        return "noop"
    lease_until = _parse(doc.get("tick_lease_until"))
    if doc.get("tick_owner") and lease_until and lease_until > _now():
        return _defer_busy_tick(services, eval_run_id, doc)
    # Recovery needs a distinct successor name: its normal name may already be consumed.
    suffix = f"-resume-{continuation_key}" if continuation_key else ""
    # Queue first: enqueue failure leaves both sequence and ownership untouched.
    services.queue.enqueue(
        "tick", {"eval_run_id": eval_run_id, "n": n + 1}, delay_seconds=TICK_DELAY_S,
        task_id=f"{eval_run_id}-tick-{n + 1}{suffix}",
    )
    owner = uuid4().hex
    now = _now()
    claimed = repository.claim_tick(
        eval_run_id, n, now.isoformat(), owner, (now + timedelta(seconds=TICK_LEASE_S)).isoformat(),
    )
    if claimed != "claimed":
        if claimed == "busy":
            return _defer_busy_tick(services, eval_run_id, repository.get_run(eval_run_id) or doc)
        return claimed
    doc = repository.get_run(eval_run_id)
    doc["_tick_owner"] = owner
    try:
        _run_owned_tick(services, eval_run_id, doc)
    except TickOwnershipLost:
        return "noop"
    finally:
        repository.release_tick(eval_run_id, owner)
    return "ran"


def _cancel_latest(services, eval_run_id, doc, cells):
    latest = services.repository.get_run(eval_run_id) or {}
    if latest.get("tick_owner") != doc["_tick_owner"]:
        raise TickOwnershipLost()
    if latest.get("cancel_requested"):
        doc["cancel_requested"] = True
        doc["cancelled_at"] = latest.get("cancelled_at")
        _cancel_cells(doc, cells)
        return True
    return False


def _run_owned_tick(services, eval_run_id, doc):
    cells = plan_cells(doc)
    if doc["status"] == "queued":
        doc["status"] = "running"

    # Inspect each cell in isolation before sorting terminal outcomes by ended time. Failed
    # lookups skip all later handling of that session this tick (one error budget increment).
    terminal = []
    unreadable = doc["_unreadable_sessions"] = set()
    checked = doc["_checked_runs"] = {}
    for sid in doc["sessions"]:
        entry = doc["sessions"][sid]
        if entry["cursor"] >= len(cells):
            continue
        result = []
        _isolated(
            services, doc, sid, cells,
            lambda sid=sid, result=result: result.append(
                _inspect_session(services, eval_run_id, doc, sid, cells)
            ),
            clear_errors=False, preserve_active=True,
        )
        if not result:
            unreadable.add(sid)
            continue
        run = result[0]
        if run is not None:
            checked[run.run_id] = run
            if run.status in RUN_TERMINAL:
                terminal.append((run.ended or _now(), sid, run))
            else:
                cell = cells[doc["sessions"][sid]["cursor"]]
                doc["cells_wait"].get(cell_key(sid, cell), {}).pop("handler_errors", None)
    for _, sid, run in sorted(terminal, key=lambda item: (item[0], item[1])):  # by `ended`
        fold = partial(_fold_session, services, doc, sid, cells, run)
        _isolated(services, doc, sid, cells, fold)
    _save(services, eval_run_id, doc)
    sweep_slots(services, doc, eval_run_id)

    # (4) re-read cancellation before every admission; the RunDoc transaction also checks it.
    for sid in sorted(doc["sessions"], key=lambda sid: doc["sessions"][sid]["order"]):
        if _cancel_latest(services, eval_run_id, doc, cells):
            break
        entry = doc["sessions"][sid]
        if sid in unreadable or entry["active_run_id"] or entry["cursor"] >= len(cells):
            continue
        fill = partial(_fill_session, services, doc, eval_run_id, sid, cells)
        if _isolated(services, doc, sid, cells, fill):
            _save(services, eval_run_id, doc)
    _cancel_latest(services, eval_run_id, doc, cells)
    # (5) everything terminal -> roll up; the chain ends because later ticks are no-ops
    if doc["status"] in ACTIVE:
        _rollup(doc)
    _save(services, eval_run_id, doc)
    if doc["status"] not in ACTIVE:
        sweep_slots(services, doc, eval_run_id)


def ensure_tick(services, eval_run_id: str, doc: dict) -> bool:
    """Safety net for `GET /v1/runs/{id}`: re-enqueue the current tick if the chain stalled."""
    if doc.get("status") not in ACTIVE or "tick_seq" not in doc:  # legacy docs have no chain
        return False
    last = doc.get("last_tick_at") or doc.get("created_at")
    try:
        age = (_now() - datetime.fromisoformat(last)).total_seconds()
    except (TypeError, ValueError):
        return False
    if age < STALE_TICK_S:
        return False
    epoch = int(_now().timestamp() // STALE_TICK_S)
    services.queue.enqueue(
        "tick", {"eval_run_id": eval_run_id, "n": doc["tick_seq"]},
        task_id=f"{eval_run_id}-tick-{doc['tick_seq']}-r{epoch}",
    )
    return True


@router.post("/internal/tasks/tick")
def tick_task(request: Request, body: dict):
    eval_run_id, n = body.get("eval_run_id"), body.get("n")
    if not isinstance(eval_run_id, str) or not eval_run_id or not isinstance(n, int) or n < 1:
        raise HTTPException(422, "An eval run id and tick number are required.")
    services = request.app.state.services
    if body.get("recover") is True:
        doc = services.repository.get_run(eval_run_id)
        if doc is None or doc.get("status") not in ACTIVE:
            return {"status": "ok"}
        n = doc["tick_seq"]
    run_tick(
        services, eval_run_id, n,
        continuation_key=body.get("resume_key") if body.get("recover") is True else None,
    )  # busy work has queued its own durable recovery timer
    return {"status": "ok"}
