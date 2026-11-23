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
from .gold import COUNT_IDS, GLOBAL_IDS, CountId, Globals, Number

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


class Difference(TypedDict):
    gold: float | int | None
    ours: float | int | None
    diff: float | int | None
    abs_diff: float | int | None


class SessionComparison(TypedDict):
    schema: Literal["compare.v1"]
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
        value = ours[key]
        diff = None if reference is None or value is None else value - reference
        rows[key] = Difference(gold=reference, ours=value, diff=diff,
                               abs_diff=None if diff is None else abs(diff))
    return rows


def compare(gold: Scores, ours: Scores) -> SessionComparison:
    """Compare two adapters' values, recomputing all summaries with the same pack."""
    return SessionComparison(
        schema="compare.v1",
        counts=_differences(gold.counts, ours.counts),
        globals=_differences(gold.globals, ours.globals),
        summaries=_differences(compute_summaries(gold.counts, gold.globals),
                               compute_summaries(ours.counts, ours.globals)),
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
