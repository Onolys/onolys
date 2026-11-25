"""Run selection, cost, time, coverage, excluded runs and status gating (SP06 R1, R6, R10).

Pure: no I/O, no clock. Inputs are `EvalRunSource.cells` dicts and the grouping doc. Only the
highest `attempt` per (session, combo, repeat) counts; earlier attempts feed only the time
footnote (`retried_runs`). Only `done` and parseable runs are compared; everything else is
reported in `excluded` / `coverage`, never imputed and never 0.
"""
from collections.abc import Collection, Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from .run_report import ParsedRun
from .session_metrics import Metrics, _mark_best, _na_cell
from .source import PriceLookup

SKIPPED_REASON = "skipped: provider unavailable"
NOT_FINISHED = "not_finished"
NO_COMPLETED_RUNS = "no_completed_runs"
_UNFINISHED = frozenset({"queued", "running", "deleting"})
_NOT_STARTED = frozenset({"queued", "running", None})

CellKey = tuple[str, str, int]  # (session_id, combo_key, repeat)


def _key(c: Mapping[str, Any]) -> CellKey:
    return (c["sid"], c["combo_key"], c["repeat"])


def final_attempts(cells: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Highest attempt per (sid, combo_key, repeat); first-seen cell order kept."""
    best: dict[CellKey, Mapping[str, Any]] = {}
    for c in cells:
        k = _key(c)
        if k not in best or c["attempt"] > best[k]["attempt"]:
            best[k] = c
    return [dict(c) for c in best.values()]


def done_cells(final: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(c) for c in final if c["status"] == "done"]


def split_parsed(pairs: Iterable[tuple[Mapping[str, Any], ParsedRun]]
                 ) -> tuple[dict[str, dict[str, list[ParsedRun]]], set[CellKey]]:
    """(done cell, parsed run) pairs -> {sid: {combo_key: [ok runs]}} and the unparseable keys."""
    runs: dict[str, dict[str, list[ParsedRun]]] = {}
    bad: set[CellKey] = set()
    for c, parsed in pairs:
        if parsed.status != "ok":
            bad.add(_key(c))
            continue
        runs.setdefault(c["sid"], {}).setdefault(c["combo_key"], []).append(parsed)
    return runs, bad


def _seconds(c: Mapping[str, Any]) -> float | None:
    if not c.get("started") or not c.get("ended"):
        return None
    return (datetime.fromisoformat(c["ended"]) - datetime.fromisoformat(c["started"])).total_seconds()


def _error_code(c: Mapping[str, Any]) -> str:
    err = c.get("error")
    return (err.get("code") if isinstance(err, Mapping) else None) or "unknown"


def operational(cells: Sequence[Mapping[str, Any]], combos: Sequence[Mapping[str, Any]],
                prices: PriceLookup, unparseable: Collection[CellKey] = ()
                ) -> dict[str, dict[str, Any]]:
    """Per combo `{time, cost, failures}` from ALL attempts' cells (final attempts are picked here).

    time: mean `ended - started` over final done/failed runs with both set; `retried_runs` counts
    (session, repeat) cells that needed more than one attempt. cost: sum over final done/failed
    runs that have usage; one unpriced run makes it n/a "no price for <model>". failures: final
    failed runs by error code plus unparseable done runs; skipped runs are not failures."""
    attempts: dict[CellKey, int] = {}
    for c in cells:
        attempts[_key(c)] = attempts.get(_key(c), 0) + 1
    final = final_attempts(cells)
    out: dict[str, dict[str, Any]] = {}
    for combo in combos:
        ck, model = combo["combo_key"], combo["litellm_id"]
        mine = [c for c in final if c["combo_key"] == ck and c["status"] in ("done", "failed")]
        secs = [s for s in map(_seconds, mine) if s is not None]
        costs = [prices.estimate(c["run_info"]["usage"], model).cost_usd
                 for c in mine if (c.get("run_info") or {}).get("usage") is not None]
        if None in costs:
            cost: dict[str, Any] = {"total_usd": None, "per_run_usd": None, "n": len(costs),
                                    "na": {"reason": f"no price for {model}"}}
        elif costs:
            cost = {"total_usd": sum(costs), "per_run_usd": sum(costs) / len(costs),
                    "n": len(costs), "na": None}
        else:
            cost = {"total_usd": None, "per_run_usd": None, "n": 0, "na": {"reason": "no usage recorded"}}
        codes: dict[str, int] = {}
        for c in mine:
            code = _error_code(c) if c["status"] == "failed" else (
                "unparseable" if _key(c) in unparseable else None)
            if code:
                codes[code] = codes.get(code, 0) + 1
        out[ck] = {
            "time": {"mean_seconds": sum(secs) / len(secs) if secs else None, "n": len(secs),
                     "retried_runs": sum(1 for c in final if c["combo_key"] == ck
                                         and attempts[_key(c)] > 1)},
            "cost": cost,
            "failures": [{"code": k, "count": codes[k]} for k in sorted(codes)]}
    return out


def _reason(c: Mapping[str, Any], unparseable: Collection[CellKey]) -> str | None:
    status = c["status"]
    if status == "done":
        return "unparseable" if _key(c) in unparseable else None
    if status == "failed":
        return f"failed:{_error_code(c)}"
    if status == "cancelled":
        return "cancelled"
    if status == "skipped":
        return "provider_unavailable"
    return "not_started" if status in _NOT_STARTED else f"failed:{status}"


def excluded(final: Iterable[Mapping[str, Any]], unparseable: Collection[CellKey] = ()
             ) -> list[dict[str, Any]]:
    """Final-attempt cells not compared: {session_id, combo_key, repeat, reason}."""
    out = []
    for c in final:
        reason = _reason(c, unparseable)
        if reason:
            out.append({"session_id": c["sid"], "combo_key": c["combo_key"], "repeat": c["repeat"],
                        "reason": reason})
    return out


def coverage(eval_run: Mapping[str, Any], final: Sequence[Mapping[str, Any]],
             unparseable: Collection[CellKey] = ()) -> dict[str, Any]:
    return {
        "eval_status": eval_run["status"],
        "cancelled_at": eval_run.get("cancelled_at"),
        "runs_done": sum(1 for c in final if c["status"] == "done" and _key(c) not in unparseable),
        "runs_total": len(final),
        "runs_skipped": sum(1 for c in final if c["status"] == "skipped"),
        "skipped_providers": [{"provider": p["provider"], "after_failures": p["after_failures"]}
                              for p in eval_run.get("provider_skips") or []]}


def skipped_combo_keys(eval_run: Mapping[str, Any]) -> set[str]:
    """Combos whose provider was skipped by the breaker."""
    providers = {p["provider"] for p in eval_run.get("provider_skips") or []}
    return {c["combo_key"] for c in eval_run.get("combos", []) if c["provider"] in providers}


def mark_skipped(metrics: Metrics, combo_keys: Iterable[str]) -> Metrics:
    """Set every metric cell of the skipped combos to n/a (never 0), in place; recompute `best`."""
    keys = list(combo_keys)
    for row in metrics.cells.values():
        for ck in keys:
            row[ck] = _na_cell(SKIPPED_REASON)
        _mark_best(row)
    return metrics


def gate(eval_run: Mapping[str, Any], cells: Sequence[Mapping[str, Any]]) -> str | None:
    """None = compare (200); else the 409 code: `not_finished` or `no_completed_runs`."""
    if eval_run["status"] in _UNFINISHED:
        return NOT_FINISHED
    if not any(c["status"] == "done" for c in final_attempts(cells)):
        return NO_COMPLETED_RUNS
    return None
