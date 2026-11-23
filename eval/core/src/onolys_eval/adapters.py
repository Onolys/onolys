"""Engine-specific projection into the engine-independent scoring boundary."""
from collections.abc import Mapping
from typing import Annotated, Any

from onolys_miti.report import Report
from pydantic import Field

from ._contracts import Contract
from .gold import CountId, Counts, GlobalId, Globals
from .metrics import Scores


def miti_lean_scores(report: Report | Mapping[str, Any]) -> Scores:
    """Project a full lean report to its authorable counts and global ratings.

    Counts use ``behaviours[].onolys_count.mean`` (possibly fractional across
    runs); globals use the representative ``globals[].onolys.score``. Engine
    summaries, scorecard, evidence and metadata do not enter scoring. Tips are
    authorable but have no numeric metric, so they are also excluded. Metrics
    recompute summaries from these values using the shared pack formulas.

    Missing fields/items, duplicate IDs, unknown IDs and invalid numeric values
    raise rather than silently defaulting or rounding.
    """
    data = report.model_dump() if isinstance(report, Report) else report
    counts = {}
    for entry in data["behaviours"]:
        key = entry["item_id"]
        if key in counts:
            raise ValueError(f"duplicate behaviour item_id: {key}")
        counts[key] = entry["onolys_count"]["mean"]
    globals_ = {}
    for entry in data["globals"]:
        key = entry["item_id"]
        if key in globals_:
            raise ValueError(f"duplicate global item_id: {key}")
        globals_[key] = entry["onolys"]["score"]
    return Scores(counts=counts, globals=globals_)


class _OneshotTip(Contract):
    rank: Annotated[int, Field(ge=1)]
    item_id: CountId | GlobalId
    observation: str
    alternative: str
    why_it_matters: str


class _OneshotOutput(Contract):
    # Keep the engine-independent boundary strict without importing the engine.
    counts: Counts
    globals: Globals
    tips: list[_OneshotTip]


def oneshot_scores(output: Mapping[str, Any]) -> Scores:
    """Validate the one-shot MITI subset and project it to comparable scores.

    All ten counts must be nonnegative integers and all four globals must be
    integer ratings from 1 to 5. Tips are required and validated but have no
    numeric metric. Missing, extra or invalid fields raise ``ValidationError``;
    no values are defaulted, coerced or rounded. The shared metrics recompute
    summaries from counts/globals, just as for lean reports and gold.
    """
    data = _OneshotOutput.model_validate(output)
    return Scores(counts=data.counts, globals=data.globals)
