"""Deterministic no-rating compare helpers and explanation templates (PRD R3). No model call:
summary formulas come from `pack.yaml > summaries` (through `formula.evaluate`), the headline
from `report.yaml`. There is no clinician value here, so every diff is `not_rated` (or
`no_onolys_value` when Onolys has none)."""

from collections.abc import Sequence

from onolys_miti.report import (
    Diff,
    Explanation,
    Instance,
    Line,
    SummaryEntry,
    SummaryReference,
    SummaryValue,
    Warning,
)
from onolys_miti.result import MitiResult, SummaryStat
from onolys_miti.tone import ToneRules

# Engine templates (neutral wording; linted against the banned list by a unit test). The rated
# templates stay in the list so `engine:compare_templates` hashes the same as before.
HEADLINE_AGREE = "Onolys agrees"
HEADLINE_NEUTRAL = "Onolys's reading"
SCORED = "Onolys scored {o}; you scored {c}."
COUNTED = "Onolys counted {o}; you counted {c}."
SCORED_ONLY = "Onolys scored {o}."
COUNTED_ONLY = "Onolys counted {o}."
NO_VALUE = "Onolys has no value for this item; you recorded {c}."
NOTE_BOTH = "Both values use the same formula. Reference levels, not pass marks."
NOTE_ONOLYS = "Onolys values only. Reference levels, not pass marks."
# Appended to the method limits: the report is Onolys's reading, not an official coding.
METHOD_LIMIT = "This is Onolys's reading of the session, not an official coding."


def template_strings() -> list[str]:
    return [HEADLINE_AGREE, HEADLINE_NEUTRAL, SCORED, COUNTED, SCORED_ONLY, COUNTED_ONLY,
            NO_VALUE, NOTE_BOTH, NOTE_ONOLYS, METHOD_LIMIT]


def not_rated_diff(onolys: float | None) -> Diff:
    """Diff of one item with no clinician rating: `not_rated`, or `no_onolys_value`."""
    status = "no_onolys_value" if onolys is None else "not_rated"
    return Diff(signed=None, abs=None, direction=None, status=status)


def onolys_summaries(summaries: Sequence[dict], onolys: dict[str, SummaryStat]
                     ) -> list[SummaryEntry]:
    """Summary rows with Onolys values only (`clinician` is null). `summaries` is the
    definition's `summaries` list."""
    out = []
    for s in summaries:
        ref = s.get("reference")
        o = onolys[s["id"]]
        out.append(SummaryEntry(
            id=s["id"], label=s["label"], clinician=None,
            onolys=SummaryValue(value=o.mean, label=o.label),
            reference=SummaryReference(fair=ref["fair"], good=ref["good"]) if ref else None,
            note=NOTE_ONOLYS))
    return out


def representative_instances(result: MitiResult, code: str) -> list[Instance]:
    """Counted instances of `code` from the representative run (all of them; the UI shows the
    first `max_instances_shown`)."""
    idx = result.aggregate.representative_run
    run = next(r for r in result.results if r.run_index == idx)
    return [Instance(id=i.id, turn_id=i.turn_id, start=i.start, end=i.end, quote=i.quote,
                     rationale=i.rationale)
            for i in run.instances if i.counted and i.code == code]


def _num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.2f}".rstrip("0").rstrip(".")


def _line(x: Line) -> Line:
    return Line(turn_id=x.turn_id, start=x.start, end=x.end, quote=x.quote)


def explain(*, item_id: str, kind: str, diff: Diff, onolys_value: float | None,
            reason: str | None, onolys_lines: Sequence[Line], rules: ToneRules,
            ) -> tuple[Explanation, list[Warning]]:
    """Template explanation for an item with no clinician rating. A model reason that fails the
    tone lint is withheld and `reason_withheld_tone` is returned; evidence lines are kept."""
    warnings: list[Warning] = []
    body: list[str] = []
    if diff.status != "no_onolys_value":
        body.append((COUNTED_ONLY if kind == "count" else SCORED_ONLY).format(
            o=_num(onolys_value)))
    if reason:
        if rules.lint(reason):
            warnings.append(Warning(code="reason_withheld_tone", item_id=item_id))
        else:
            body.append(reason)
    return Explanation(headline=HEADLINE_NEUTRAL, body=body,
                       onolys_lines=[_line(x) for x in onolys_lines],
                       clinician_support_lines=[]), warnings


__all__ = ["METHOD_LIMIT", "explain", "not_rated_diff", "onolys_summaries",
           "representative_instances", "template_strings"]
