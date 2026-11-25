"""Session-balanced counts, globals, cohorts and heatmap cells (SP06 R5). Pure: no I/O, no clock.

One counting rule: per session and combo, the miss is the mean over that combo's repeats of
|repeat value - human| (repeat values are never averaged first); sessions then count equally.
R:Q, %CR and the other pack summaries are computed per repeat (`compare` / `compute_summaries`),
then missed against the human's. A repeat with an undefined ratio (division by zero) makes that
session n/a for that combo and metric; it is reported in `excluded`, never counted as 0.

Inputs are already filtered: per combo, only the final-attempt `done` runs (Task 5's job).
Floats are not rounded here.
"""
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .._formulas import SUMMARY_FORMULAS
from ..gold import COUNT_IDS, GLOBAL_IDS
from ..metrics import PartialScores, compare
from .gold_view import GoldProjection
from .run_report import ParsedRun

COUNT_TOLERANCE = 0.6  # lines, inclusive
GLOBAL_TOLERANCE = 0.4  # points, inclusive
COUNT_ERROR = "count_error"

NOT_LABELED = "not labeled in this dataset"
NEEDS_GLOBALS = "needs cct, sst, partnership, empathy"
NO_QUESTIONS = "no Questions in this session"
NO_REFLECTIONS = "no reflections in this session"
NO_PAIRED = "no paired sessions"
NO_RUNS = "no completed runs"

_NEEDS = {key: frozenset(re.findall(r"[a-z_]+", expr)) for key, expr in SUMMARY_FORMULAS}
_GLOBAL_DERIVED = ("technical", "relational")
_UNDEFINED_REASON = {"reflection_question_ratio": NO_QUESTIONS, "pct_cr": NO_REFLECTIONS}
METRICS = (*COUNT_IDS, *GLOBAL_IDS, *_NEEDS)


def kind(metric: str) -> str:
    """count | global | ratio | total (lines-scaled count sum)."""
    if metric in COUNT_IDS:
        return "count"
    if metric in GLOBAL_IDS or metric in _GLOBAL_DERIVED:
        return "global"
    return "ratio" if metric in _UNDEFINED_REASON else "total"


def _tolerance(metric: str) -> float | None:
    k = kind(metric)
    return COUNT_TOLERANCE if k in ("count", "total") else GLOBAL_TOLERANCE if k == "global" else None


@dataclass(frozen=True)
class SessionInput:
    session_id: str
    human: GoldProjection
    runs: Mapping[str, Sequence[ParsedRun]]  # combo_key -> final-attempt done runs (repeats)


@dataclass
class Metrics:
    cells: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)  # metric -> combo -> cell
    cohorts: dict[str, dict[str, int]] = field(default_factory=dict)  # metric -> {paired, of}
    human: dict[str, dict[str, Any]] = field(default_factory=dict)  # metric -> {min, max, n}
    excluded: list[dict[str, Any]] = field(default_factory=list)  # {session_id, combo_key, metric, reason}


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _labeled(human: GoldProjection, metric: str) -> bool:
    if metric in COUNT_IDS:
        return metric in human.counts
    if metric in GLOBAL_IDS:
        return metric in human.globals
    return all(k in human.counts or k in human.globals for k in _NEEDS[metric])


def _na_reason(metric: str) -> str:
    return NEEDS_GLOBALS if metric in _GLOBAL_DERIVED else NOT_LABELED


def _na_cell(reason: str, of: int = 0, repeats: int = 0) -> dict[str, Any]:
    return {"value": None, "off": None, "bias": None, "n": 0, "of": of, "repeats": repeats,
            "within_tolerance": None, "best": False, "na": {"reason": reason}}


def _rows(cmp: Mapping[str, Any], metric: str) -> Mapping[str, Any]:
    section = "counts" if metric in COUNT_IDS else "globals" if metric in GLOBAL_IDS else "summaries"
    return cmp[section][metric]


def _bucket(abs_diff: float) -> str:
    return "same" if abs_diff == 0 else "off1" if abs_diff <= 1 else "off2plus"


def _mark_best(row: Mapping[str, dict[str, Any]]) -> None:
    offs = [c["off"] for c in row.values() if c["off"] is not None]
    if offs:
        low = min(offs)
        for c in row.values():
            c["best"] = c["off"] == low


def compute_metrics(sessions: Sequence[SessionInput], combos: Sequence[str]) -> Metrics:
    """Session-balanced metrics over the requested `combos` (cohort is computed over that set)."""
    out = Metrics()
    # comparisons[session][combo] -> one `compare` result per repeat
    comparisons: dict[str, dict[str, list]] = {}
    for s in sessions:
        human = PartialScores(counts=dict(s.human.counts), globals=dict(s.human.globals) or None)
        comparisons[s.session_id] = {
            c: [compare(human, PartialScores(counts=dict(r.counts), globals=dict(r.globals)))
                for r in s.runs.get(c, ()) if r.status == "ok"]
            for c in combos}
    sess = {s.session_id: s for s in sessions}
    paired_ids = [sid for sid in sess if all(comparisons[sid][c] for c in combos)]

    for metric in METRICS:
        labeled = [sid for sid in sess if _labeled(sess[sid].human, metric)]
        # a human value that is undefined (e.g. human Question 0) cannot be missed against
        defined = []
        undefined = False
        for sid in labeled:
            if sid not in paired_ids:
                continue
            cmps = [c for combo in combos for c in comparisons[sid][combo]]
            if _rows(cmps[0], metric)["gold"] is None:
                out.excluded.append({"session_id": sid, "combo_key": None, "metric": metric,
                                     "reason": _UNDEFINED_REASON.get(metric, NOT_LABELED)})
                undefined = True
                continue
            invalid_combos = [combo for combo in combos
                              if any(_rows(c, metric)["diff"] is None
                                     for c in comparisons[sid][combo])]
            for combo in invalid_combos:
                out.excluded.append({"session_id": sid, "combo_key": combo, "metric": metric,
                                     "reason": _UNDEFINED_REASON.get(metric, NOT_LABELED)})
            if invalid_combos:
                undefined = True
                continue
            defined.append(sid)
        out.cohorts[metric] = {"paired": len(defined), "of": len(labeled)}
        human_vals = [_rows(comparisons[sid][combos[0]][0], metric)["gold"] for sid in defined] \
            if combos and defined else []
        out.human[metric] = {"min": min(human_vals) if human_vals else None,
                             "max": max(human_vals) if human_vals else None, "n": len(human_vals)}
        row = {}
        for combo in combos:
            if not labeled:
                row[combo] = _na_cell(_na_reason(metric))
                continue
            if not defined:
                reason = (_UNDEFINED_REASON.get(metric, NOT_LABELED) if undefined
                          else NO_PAIRED if paired_ids else NO_RUNS)
                row[combo] = _na_cell(reason, of=len(labeled))
                continue
            row[combo] = _cell(metric, combo, defined, comparisons, labeled)
        _mark_best(row)
        out.cells[metric] = row

    out.cells[COUNT_ERROR] = _count_error(sess, combos, comparisons, paired_ids)
    return out


def _cell(metric, combo, defined, comparisons, labeled) -> dict[str, Any]:
    misses, biases, means, repeat_values, shares = [], [], [], [], []
    repeats = 0
    for sid in defined:
        rows = [_rows(c, metric) for c in comparisons[sid][combo]]
        repeats = max(repeats, len(rows))
        misses.append(_mean([r["abs_diff"] for r in rows]))
        biases.append(_mean([r["diff"] for r in rows]))
        means.append(_mean([r["ours"] for r in rows]))
        repeat_values += [r["ours"] for r in rows]
        if metric in GLOBAL_IDS:
            shares.append({b: sum(_bucket(r["abs_diff"]) == b for r in rows) / len(rows)
                           for b in ("same", "off1", "off2plus")})
    if not misses:
        return _na_cell(_UNDEFINED_REASON.get(metric, NO_PAIRED), of=len(labeled))
    off, tol = _mean(misses), _tolerance(metric)
    cell = {"value": None if kind(metric) == "global" else _mean(means), "off": off,
            "bias": _mean(biases), "n": len(misses), "of": len(labeled), "repeats": repeats,
            "within_tolerance": None if tol is None else off <= tol, "best": False, "na": None,
            "observed": {"min": min(repeat_values), "max": max(repeat_values),
                         "n": len(repeat_values)}}
    if shares:
        buckets = {b: _mean([s[b] for s in shares]) for b in ("same", "off1", "off2plus")}
        cell["buckets"] = buckets
        cell["within_1"] = buckets["same"] + buckets["off1"]
    return cell


def _count_error(sess, combos, comparisons, paired_ids) -> dict[str, dict[str, Any]]:
    """Sum over labeled codes of the per-code session miss, averaged over cohort sessions."""
    with_labels = [sid for sid in sess if sess[sid].human.counts]
    codes = [c for c in COUNT_IDS if with_labels and all(c in sess[sid].human.counts for sid in with_labels)]
    cohort = [sid for sid in with_labels if sid in paired_ids]
    if not codes:
        row = {c: _na_cell(NOT_LABELED) for c in combos}
        for cell in row.values():
            cell["codes_labeled"] = 0
        return row
    row = {}
    for combo in combos:
        if not cohort:
            cell = _na_cell(NO_PAIRED if paired_ids else NO_RUNS, of=len(with_labels))
        else:
            per_session, signed = [], []
            for sid in cohort:
                cmps = comparisons[sid][combo]
                per_session.append(sum(_mean([c["counts"][k]["abs_diff"] for c in cmps]) for k in codes))
                signed.append(sum(_mean([c["counts"][k]["diff"] for c in cmps]) for k in codes))
            cell = {"value": None, "off": _mean(per_session), "bias": _mean(signed), "n": len(cohort),
                    "of": len(with_labels), "repeats": max(len(comparisons[s][combo]) for s in cohort),
                    "within_tolerance": None, "best": False, "na": None}
        cell["codes_labeled"] = len(codes)
        cell["codes_total"] = len(COUNT_IDS)
        row[combo] = cell
    _mark_best(row)
    return row
