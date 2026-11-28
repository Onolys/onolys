"""Line alignment, presence-based P/R/F1 and confusion per combo. Pure: no I/O, no clock.

Aligned lines = clinician turns of the session (already inside the coded span) that have a gold
`utterance_codes` row. Universe L = codes the dataset labels; codes outside L are masked on both
sides. Gold codes and report `item_id`s are the same ids (`COUNT_IDS`), so no renaming is needed.
A combo's codes on a turn = the set of `item_id`s with a counted instance there; an empty set is
"none" (only engines with line output). Each repeat is scored alone, repeats are averaged within a
session, sessions then count equally. Confusion counts are pooled (summed) over sessions after the
repeat mean, so matrix total + `multi` equals the aligned lines.
"""
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .gold_view import GoldProjection
from .projections import ParsedRun, TurnView

NO_LINE_OUTPUT = "no line-level output"
NONE = "none"
MISSING_HUMAN = "human"
_ANNOMI_NOTE = ("AnnoMI codes are per utterance and several annotators may disagree; gold takes "
                "the majority vote per utterance, so line labels are coarser than MITI coding.")
DATASET_NOTES = {"annomi": _ANNOMI_NOTE, "annosum-mi": _ANNOMI_NOTE}


@dataclass(frozen=True)
class LineSession:
    session_id: str
    human: GoldProjection
    turns: Sequence[TurnView]  # transcript turns inside the coded span
    runs: Mapping[str, Sequence[ParsedRun]]  # combo_key -> final-attempt done runs


@dataclass
class ComboLines:
    lane: str | None = None  # NO_LINE_OUTPUT for engines without line output
    sessions: int = 0
    repeats: int = 0  # max repeats over sessions
    aligned: int = 0
    per_code: dict[str, dict[str, float | None]] = field(default_factory=dict)  # code -> p/r/f1
    macro_f1: float | None = None
    line_accuracy: float | None = None
    confusion: dict[str, dict[str, float]] = field(default_factory=dict)  # human row -> col -> n
    multi: float = 0


@dataclass
class LineMetrics:
    missing: str | None = None  # "human": no human line labels
    codes_labeled: tuple[str, ...] = ()
    dataset_notes: list[str] = field(default_factory=list)
    combos: dict[str, ComboLines] = field(default_factory=dict)


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _aligned(s: LineSession, universe: frozenset[str]) -> list[tuple[str, frozenset[str]]]:
    gold = {row.turn_id: frozenset(row.codes) & universe for row in s.human.utterance_codes or ()}
    return [(t.id, gold[t.id]) for t in s.turns if t.is_clinician and t.id in gold]


def _label(codes: Collection[str]) -> str | None:
    """Single label (or NONE for the empty set); None when several labels (multi)."""
    if not codes:
        return NONE
    return next(iter(codes)) if len(codes) == 1 else None


def _score_repeat(aligned, run: ParsedRun, universe: frozenset[str], order: Sequence[str]):
    tp, fp, fn = dict.fromkeys(order, 0), dict.fromkeys(order, 0), dict.fromkeys(order, 0)
    confusion: dict[str, dict[str, int]] = {}
    multi = exact = 0
    for turn_id, gold in aligned:
        pred = run.turn_codes.get(turn_id, frozenset()) & universe
        exact += gold == pred
        for code in order:
            tp[code] += code in gold and code in pred
            fp[code] += code not in gold and code in pred
            fn[code] += code in gold and code not in pred
        row, col = _label(gold), _label(pred)
        if row is None or col is None:
            multi += 1
        else:
            confusion.setdefault(row, {}).setdefault(col, 0)
            confusion[row][col] += 1
    prf = {}
    for code in order:
        p = tp[code] / (tp[code] + fp[code]) if tp[code] + fp[code] else None
        r = tp[code] / (tp[code] + fn[code]) if tp[code] + fn[code] else None
        d = 2 * tp[code] + fp[code] + fn[code]
        prf[code] = {"p": p, "r": r, "f1": 2 * tp[code] / d if d else None}
    f1s = [v["f1"] for v in prf.values() if v["f1"] is not None]
    return {"prf": prf, "macro": _mean(f1s), "acc": exact / len(aligned) if aligned else None,
            "confusion": confusion, "multi": multi}


def _session_score(aligned, runs: Sequence[ParsedRun], universe, order):
    reps = [_score_repeat(aligned, r, universe, order) for r in runs]
    prf = {code: {k: _mean([x["prf"][code][k] for x in reps if x["prf"][code][k] is not None])
                  for k in ("p", "r", "f1")} for code in order}
    cells: dict[str, dict[str, float]] = {}
    for x in reps:
        for row, cols in x["confusion"].items():
            for col, n in cols.items():
                cells.setdefault(row, {})[col] = cells.get(row, {}).get(col, 0) + n / len(reps)
    return {"prf": prf, "macro": _mean([x["macro"] for x in reps if x["macro"] is not None]),
            "acc": _mean([x["acc"] for x in reps if x["acc"] is not None]),
            "confusion": cells, "multi": sum(x["multi"] for x in reps) / len(reps)}


def compute_line_metrics(sessions: Sequence[LineSession], combos: Sequence[str],
                         codes_labeled: Sequence[str], dataset_id: str | None = None) -> LineMetrics:
    """Line metrics over the requested `combos`; `codes_labeled` is the universe of coded labels."""
    out = LineMetrics(codes_labeled=tuple(codes_labeled))
    if dataset_id in DATASET_NOTES:
        out.dataset_notes.append(DATASET_NOTES[dataset_id])
    labeled = [s for s in sessions if s.human.utterance_codes is not None]
    if not labeled:
        out.missing = MISSING_HUMAN
        return out
    universe, order = frozenset(codes_labeled), tuple(codes_labeled)
    for combo in combos:
        cl = out.combos[combo] = ComboLines()
        runs_of = {s.session_id: [r for r in s.runs.get(combo, ()) if r.status == "ok"]
                   for s in labeled}
        if any(r.has_lines is False for rs in runs_of.values() for r in rs):
            cl.lane = NO_LINE_OUTPUT
            continue
        scored = [(s, _session_score(_aligned(s, universe), runs_of[s.session_id], universe, order))
                  for s in labeled if runs_of[s.session_id]]
        cl.sessions = len(scored)
        cl.repeats = max((len(runs_of[s.session_id]) for s, _ in scored), default=0)
        cl.aligned = sum(len(_aligned(s, universe)) for s, _ in scored)
        cl.per_code = {code: {k: _mean([x["prf"][code][k] for _, x in scored
                                        if x["prf"][code][k] is not None]) for k in ("p", "r", "f1")}
                       for code in order}
        cl.macro_f1 = _mean([x["macro"] for _, x in scored if x["macro"] is not None])
        cl.line_accuracy = _mean([x["acc"] for _, x in scored if x["acc"] is not None])
        cl.multi = sum(x["multi"] for _, x in scored)
        for _, x in scored:
            for row, cols in x["confusion"].items():
                for col, n in cols.items():
                    cl.confusion.setdefault(row, {})[col] = cl.confusion.get(row, {}).get(col, 0) + n
    return out


def turn_agreement(human_codes: Collection[str], runs: Sequence[ParsedRun], turn_id: str,
                   codes_labeled: Sequence[str]) -> dict[str, Any]:
    """Popup `agree k of r`: repeats whose masked code set on the turn equals the human's."""
    universe = frozenset(codes_labeled)
    gold = frozenset(human_codes) & universe
    k = sum((r.turn_codes.get(turn_id, frozenset()) & universe) == gold for r in runs)
    return {"k": k, "r": len(runs)}
