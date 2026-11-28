"""Pure More-analysis calculations and fixed, payload-grounded verdict clauses.

Inputs contain only final-attempt, completed run projections. Count error is the sum of
per-code repeat mean misses; sessions carry equal weight. Level agreement also averages
within session first. Repeat agreement counts (session, global) / (session, aligned line)
units with at least two successful repeats. No confidence intervals or composite score.
"""
from collections.abc import Collection, Mapping, Sequence
from itertools import combinations
from typing import Any

from onolys_miti.formula import label_for

from .._formulas import SUMMARY_REFERENCES, compute_summaries
from ..gold import COUNT_IDS, GLOBAL_IDS
from .line_metrics import LineSession
from .operations import SKIPPED_REASON
from .session_metrics import NOT_LABELED, SessionInput, compute_metrics

NEEDS_REPEATS = "needs at least two successful repeats"
NO_PAIRED = "no paired sessions"


def observed_range(values: Sequence[float]) -> dict[str, Any]:
    """The observed repeat values only, without statistical interpretation."""
    return {"min": min(values) if values else None, "max": max(values) if values else None,
            "n": len(values)}


def baseline() -> dict[str, Any]:
    return {"value": None, "n": 0, "na": {
        "reason": "needs a second human coder, not in this dataset"}}


def _share(values: Sequence[bool], reason: str) -> dict[str, Any]:
    return {"value": sum(values) / len(values) if values else None, "n": len(values),
            "agree": sum(values), "na": None if values else {"reason": reason}}


def _valid(cell: Mapping[str, Any], field: str) -> bool:
    return cell.get(field) is not None and cell.get("n", 0) > 0 and not cell.get("na")


def frontier(errors: Mapping[str, Mapping[str, Any]],
             operations: Mapping[str, Mapping[str, Any]], *, skipped_combos: Collection[str] = ()
             ) -> dict[str, Any]:
    """Pareto frontier of mean cost per run and Count error; ties remain on the frontier.

    Only points on the frontier are returned in `points`. `dominated` contains the other
    priced, comparable points, and `unpriced` lists valid errors without a price.
    """
    points, unpriced, unavailable = [], [], []
    for combo, error in errors.items():
        if combo in skipped_combos or not _valid(error, "off"):
            unavailable.append({"combo_key": combo, "n": 0, "na": {
                "reason": SKIPPED_REASON if combo in skipped_combos else
                (error.get("na") or {}).get("reason", NO_PAIRED)}})
            continue
        cost = operations.get(combo, {}).get("cost", {})
        point = {"combo_key": combo, "count_error": error["off"], "n": error["n"]}
        if not _valid(cost, "per_run_usd"):
            unpriced.append({**point, "cost_per_run_usd": None,
                             "na": cost.get("na") or {"reason": "no usage recorded"}})
        else:
            points.append({**point, "cost_per_run_usd": cost["per_run_usd"], "cost_n": cost["n"]})
    kept, dominated = [], []
    for p in points:
        dominated_by_other = any(
            q["cost_per_run_usd"] <= p["cost_per_run_usd"] and q["count_error"] <= p["count_error"]
            and (q["cost_per_run_usd"] < p["cost_per_run_usd"] or q["count_error"] < p["count_error"])
            for q in points)
        (dominated if dominated_by_other else kept).append(p)
    return {"points": kept, "dominated": dominated, "unpriced": unpriced, "unavailable": unavailable}


def _ok(s, combo):
    return [r for r in s.runs.get(combo, ()) if r.status == "ok"]


def interview_grid(sessions: Sequence[SessionInput], combos: Sequence[str], *,
                   skipped_combos: Collection[str] = ()) -> list[dict[str, Any]]:
    """One cell per interview/combo, retaining unavailable cells with their reason.

    Grid cells use each interview's labeled codes. Aggregate Count error uses the common
    label universe across the dataset, as in compute_metrics.
    """
    rows = []
    for s in sessions:
        cells = {}
        for combo in combos:
            runs = _ok(s, combo)
            reason = SKIPPED_REASON if combo in skipped_combos else (
                NOT_LABELED if not s.human.counts else "no completed runs" if not runs else None)
            errors = [sum(abs(r.counts[k] - v) for k, v in s.human.counts.items()
                          if k in COUNT_IDS) for r in runs] if reason is None else []
            cells[combo] = {"off": sum(errors) / len(errors) if errors else None,
                            "n": int(bool(errors)), "repeats": len(runs),
                            "codes_labeled": len(s.human.counts),
                            "observed": observed_range(errors),
                            "na": {"reason": reason} if reason else None}
        rows.append({"session_id": s.session_id, "cells": cells})
    return rows


def head_to_head(sessions: Sequence[SessionInput], combos: Sequence[str], *,
                 skipped_combos: Collection[str] = ()) -> list[dict[str, Any]]:
    """Pairwise shared cohort, one vote per session, with ties explicitly counted."""
    grid = interview_grid(sessions, combos, skipped_combos=skipped_combos)
    pairs = []
    for a, b in combinations(combos, 2):
        shared = [(row["cells"][a]["off"], row["cells"][b]["off"]) for row in grid
                  if _valid(row["cells"][a], "off") and _valid(row["cells"][b], "off")]
        pairs.append({"a": a, "b": b, "a_closer": sum(x < y for x, y in shared),
                      "b_closer": sum(y < x for x, y in shared),
                      "ties": sum(x == y for x, y in shared), "n": len(shared),
                      "na": None if shared else {"reason": NO_PAIRED}})
    return pairs


def length_series(grid: Sequence[Mapping[str, Any]], line_sessions: Sequence[LineSession]
                  ) -> list[dict[str, Any]]:
    """Coded-span length from saved transcript turns (all speakers), never estimated.

    Sessions without a saved coded-span transcript are omitted rather than given length 0.
    """
    lengths = {s.session_id: {"turns": len(s.turns),
                              "words": sum(len(t.text.split()) for t in s.turns)}
               for s in line_sessions}
    return [{"session_id": row["session_id"], "combo_key": combo, "off": cell["off"],
             **lengths[row["session_id"]], "n": cell["n"], "repeats": cell["repeats"]}
            for row in grid if row["session_id"] in lengths
            for combo, cell in row["cells"].items() if _valid(cell, "off")]


def _levels(sessions, combo):
    result = {}
    for metric, reference in SUMMARY_REFERENCES.items():
        shares, observed = [], []
        for s in sessions:
            gold_value = compute_summaries(s.human.counts, s.human.globals)[metric]
            gold_level = label_for(gold_value, reference)
            runs = _ok(s, combo)
            values = [compute_summaries(r.counts, r.globals)[metric] for r in runs]
            if gold_level is None or not values or any(v is None for v in values):
                continue
            shares.append(sum(label_for(v, reference) == gold_level for v in values) / len(values))
            observed.extend(values)
        result[metric] = {"value": sum(shares) / len(shares) if shares else None,
                          "n": len(shares), "observed": observed_range(observed),
                          "na": None if shares else {"reason": "no defined human and run summaries"}}
    return result


def _repeat_agreement(sessions, line_sessions, combo):
    globals_agree, lines_agree = [], []
    for s in sessions:
        runs = _ok(s, combo)
        if len(runs) >= 2:
            for key in GLOBAL_IDS:
                if all(key in r.globals for r in runs):
                    globals_agree.append(len({r.globals[key] for r in runs}) == 1)
    for s in line_sessions:
        runs = _ok(s, combo)
        if len(runs) < 2 or not all(r.has_lines for r in runs):
            continue
        labeled = {label.turn_id for label in s.human.utterance_codes or ()}
        universe = frozenset(s.human.counts)
        for t in s.turns:
            if t.is_clinician and t.id in labeled:
                codes = {r.turn_codes.get(t.id, frozenset()) & universe for r in runs}
                lines_agree.append(len(codes) == 1)
    return {"globals": _share(globals_agree, NEEDS_REPEATS),
            "lines": _share(lines_agree, NEEDS_REPEATS)}


def reliability(sessions: Sequence[SessionInput], combos: Sequence[str], *,
                line_sessions: Sequence[LineSession] = (),
                operations: Mapping[str, Mapping[str, Any]] | None = None,
                skipped_combos: Collection[str] = ()) -> dict[str, Any]:
    """Pack-level agreement is session-balanced; repeats agree by exact rating/code set."""
    result = {}
    for combo in combos:
        usable = [] if combo in skipped_combos else sessions
        usable_lines = [] if combo in skipped_combos else line_sessions
        result[combo] = {"levels": _levels(usable, combo),
                         "repeat_agreement": _repeat_agreement(usable, usable_lines, combo),
                         "na": {"reason": SKIPPED_REASON} if combo in skipped_combos else None,
                         **{k: v for k, v in (operations or {}).get(combo, {}).items()
                            if k in ("failures", "time")}}
    return result


def build_verdict(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Fixed Count-error clauses, only from payload['count_error'] and skipped_combos.

    No metric is inferred from other measurements, and an unavailable/skipped/empty cell
    can never win. Exact values and n are repeated unchanged in structured claims.
    """
    cells = payload.get("count_error", {})
    eligible = {c: v for c, v in cells.items() if c not in payload.get("skipped_combos", ())
                and _valid(v, "off")}
    if not eligible:
        return []
    low = min(v["off"] for v in eligible.values())
    winners = [(c, v) for c, v in eligible.items() if v["off"] == low]
    clauses = []
    for combo, cell in winners:
        n = cell["n"]
        prefix = "Lowest Count error" if len(winners) == 1 else "Tied lowest Count error"
        clauses.append({"text": f"{prefix}: {combo} ({cell['off']}; {n} "
                        f"{'session' if n == 1 else 'sessions'}).",
                        "claims": [{"metric": "count_error", "combo": combo,
                                    "value": cell["off"], "n": n}]})
    return clauses


def compute_analysis(sessions: Sequence[SessionInput], combos: Sequence[str],
                     operations: Mapping[str, Mapping[str, Any]], *,
                     line_sessions: Sequence[LineSession] = (), skipped_combos: Collection[str] = ()
                     ) -> dict[str, Any]:
    """JSON-ready analysis payload. Skipped providers are excluded before cohort selection."""
    active = [c for c in combos if c not in skipped_combos]
    errors = compute_metrics(sessions, active).cells["count_error"] if active else {}
    for combo in combos:
        if combo in skipped_combos:
            errors[combo] = {"off": None, "n": 0, "na": {"reason": SKIPPED_REASON}}
    grid = interview_grid(sessions, combos, skipped_combos=skipped_combos)
    payload = {"count_error": errors, "skipped_combos": sorted(skipped_combos),
               "frontier": frontier(errors, operations, skipped_combos=skipped_combos),
               "baseline": baseline(),
               "reliability": reliability(sessions, combos, operations=operations,
                   line_sessions=line_sessions, skipped_combos=skipped_combos),
               "head_to_head": head_to_head(sessions, combos, skipped_combos=skipped_combos),
               "grid": grid, "error_vs_length": length_series(grid, line_sessions)}
    payload["verdict"] = build_verdict(payload)
    return payload
