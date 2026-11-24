"""Pure scoring of engine-independent authorable values, reused by all adapters.

Differences are ours minus gold. Aggregates give each session equal weight per
key, excluding pairs where either side is null; ``n`` counts valid pairs. All
returned comparisons and aggregates contain only JSON-native values.
"""
from collections.abc import Iterable, Mapping
from typing import Annotated, Literal, TypedDict

from pydantic import Field

from ._contracts import Contract
from ._formulas import SUMMARY_FORMULAS, compute_summaries
from .gold import (
    COUNT_IDS,
    GLOBAL_IDS,
    CountId,
    GlobalId,
    Globals,
    Gold,
    Number,
    QualityLabel,
)

# Gold counts remain strict integers; lean multi-run reports expose count means.
ScoreCount = Annotated[int | float, Field(ge=0, allow_inf_nan=False)]
ScoreCounts = Annotated[dict[CountId, ScoreCount], Field(min_length=10, max_length=10)]


class Scores(Contract):
    """Adapter boundary: complete counts/globals and optional supplied summaries.

    Summaries are accepted for adapter convenience but recomputed for comparison
    from the authorable counts/globals; engine-computed values never affect scores.
    """

    counts: ScoreCounts
    globals: Globals
    summaries: dict[str, Number | None] = Field(default_factory=dict)


class PartialScores(Contract):
    """Possibly partial human labels; missing or null entries are "not labeled".

    Gold counts/globals may omit keys or hold nulls; those fields are skipped in
    comparisons and aggregates rather than treated as zero.
    """

    counts: dict[CountId, ScoreCount | None] = Field(default_factory=dict)
    globals: dict[GlobalId, Annotated[int, Field(ge=1, le=5)] | None] | None = None
    summaries: dict[str, Number | None] = Field(default_factory=dict)  # ignored; recomputed
    quality_label: QualityLabel | None = None


def gold_scores(gold: Gold) -> PartialScores:
    """Project a gold file to its comparable (possibly partial) labels."""
    return PartialScores(counts=dict(gold.counts), globals=gold.globals,
                         quality_label=gold.quality_label)


class Difference(TypedDict):
    gold: float | int | None
    ours: float | int | None
    diff: float | int | None
    abs_diff: float | int | None


class SessionComparison(TypedDict):
    schema: Literal["compare.v1"]
    quality_label: QualityLabel | None
    counts: dict[str, Difference]
    globals: dict[str, Difference]
    summaries: dict[str, Difference]
    notes: list[str]


class ErrorMetrics(TypedDict):
    mae: float | None
    mean_bias: float | None
    n: int


class WithinOne(TypedDict):
    n: int
    total: int
    fraction: float | None


class GlobalMetrics(ErrorMetrics):
    within_1: WithinOne


class Aggregate(TypedDict):
    n: int
    counts: dict[str, ErrorMetrics]
    globals: dict[str, GlobalMetrics]
    summaries: dict[str, ErrorMetrics]


def _differences(gold: Mapping[str, float | int | None],
                 ours: Mapping[str, float | int | None]) -> dict[str, Difference]:
    rows = {}
    for key, reference in gold.items():
        value = ours.get(key)
        diff = None if reference is None or value is None else value - reference
        rows[key] = Difference(gold=reference, ours=value, diff=diff,
                               abs_diff=None if diff is None else abs(diff))
    return rows


def _complete(values: Mapping[str, float | int | None] | None,
              ids: tuple[str, ...]) -> dict[str, float | int | None]:
    return {key: (values or {}).get(key) for key in ids}


def compare(gold: Scores | PartialScores, ours: Scores | PartialScores) -> SessionComparison:
    """Compare two adapters' values, recomputing all summaries with the same pack.

    Only fields present (non-null) on both sides yield a difference; others keep
    their value(s) but a null diff, so they drop out of every aggregate.
    """
    gold_counts, gold_globals = _complete(gold.counts, COUNT_IDS), _complete(gold.globals, GLOBAL_IDS)
    our_counts, our_globals = _complete(ours.counts, COUNT_IDS), _complete(ours.globals, GLOBAL_IDS)
    return SessionComparison(
        schema="compare.v1",
        quality_label=getattr(gold, "quality_label", None),
        counts=_differences(gold_counts, our_counts),
        globals=_differences(gold_globals, our_globals),
        summaries=_differences(compute_summaries(gold_counts, gold_globals),
                               compute_summaries(our_counts, our_globals)),
        notes=[
            ("Gold uses one consensus coder; measured agreement is limited by this reference "
             "and does not establish inter-rater reliability or official MITI validation."),
            ("Rule mismatch: engine volley rules and CASAA row coding can produce different "
             "counts even when the same words are identified."),
        ],
    )


def _errors(rows: Iterable[Difference]) -> ErrorMetrics:
    diffs = [row["diff"] for row in rows if row["diff"] is not None]
    n = len(diffs)
    return ErrorMetrics(mae=sum(abs(diff) for diff in diffs) / n if n else None,
                        mean_bias=sum(diffs) / n if n else None, n=n)


def aggregate(comparisons: Iterable[SessionComparison]) -> Aggregate:
    """Aggregate comparisons per key; empty inputs retain stable keys with n=0."""
    sessions = list(comparisons)
    counts = {key: _errors(session["counts"][key] for session in sessions)
              for key in COUNT_IDS}
    summaries = {key: _errors(session["summaries"][key] for session in sessions)
                 for key, _ in SUMMARY_FORMULAS}
    globals_ = {}
    for key in GLOBAL_IDS:
        rows = [session["globals"][key] for session in sessions]
        errors = _errors(rows)
        within = sum(row["abs_diff"] <= 1 for row in rows if row["abs_diff"] is not None)
        globals_[key] = GlobalMetrics(
            **errors, within_1=WithinOne(n=within, total=errors["n"],
                                        fraction=within / errors["n"] if errors["n"] else None))
    return Aggregate(n=len(sessions), counts=counts, globals=globals_, summaries=summaries)
