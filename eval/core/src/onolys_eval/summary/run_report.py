"""Engine-keyed parsing of one saved ReportDoc into a typed run projection (SP06 R2).

Pure: no I/O, no clock. Parsing is keyed by `RunDoc.eval.engine`, never by sniffing the report
shape. A run that cannot be read exactly is `unparseable` with a reason code (fail closed): a
fractional count, a null global score, an unknown engine or a schema mismatch. Nothing is rounded
or defaulted. Only what the report holds is passed through (counts, globals, global reason and
evidence, counted instances); tips are ignored. Instance rationale is kept apart from the
instance (`rationales`) because it feeds the reasoning/popup views only; a rationale withheld
for tone stays `""`.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from ..adapters import miti_lean_scores, oneshot_scores

REASON_UNKNOWN_ENGINE = "unknown_engine"
REASON_SCHEMA = "schema_mismatch"
REASON_NON_INTEGER_COUNT = "non_integer_count"
REASON_NULL_GLOBAL = "null_global"


@dataclass(frozen=True)
class Evidence:
    turn_id: str
    quote: str


@dataclass(frozen=True)
class GlobalReason:
    reason: str
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class Instance:
    """One counted instance; `code` is the owning behaviour `item_id`. `ref` indexes
    `ParsedRun.rationales`."""
    ref: int
    code: str
    turn_id: str
    quote: str


@dataclass(frozen=True)
class ParsedRun:
    engine: str
    status: str  # "ok" | "unparseable"
    reason: str | None
    counts: Mapping[str, int] = field(default_factory=dict)
    globals: Mapping[str, int] = field(default_factory=dict)
    global_reasons: Mapping[str, GlobalReason] = field(default_factory=dict)
    instances: tuple[Instance, ...] = ()
    rationales: Mapping[int, str] = field(default_factory=dict)  # ref -> rationale ("" = withheld)
    turn_codes: Mapping[str, frozenset[str]] = field(default_factory=dict)
    has_lines: bool = False


def _unparseable(engine: str, reason: str) -> ParsedRun:
    return ParsedRun(engine=engine, status="unparseable", reason=reason)


def _exact_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def parse_report(engine: str, report_doc: Mapping[str, Any]) -> ParsedRun:
    """Parse a ReportDoc (`{"report": {...}}`) for the given `RunDoc.eval.engine`."""
    try:
        body = report_doc["report"]
        if engine == "miti":
            return _parse_miti(engine, body)
        if engine.startswith("oneshot:"):
            return _parse_oneshot(engine, body)
    except (KeyError, TypeError, ValueError, AttributeError, ValidationError):
        return _unparseable(engine, REASON_SCHEMA)
    return _unparseable(engine, REASON_UNKNOWN_ENGINE)


def _scores(engine: str, scores) -> tuple[dict[str, int], dict[str, int]] | ParsedRun:
    counts = {}
    for key, value in scores.counts.items():
        exact = _exact_int(value)
        if exact is None or exact < 0:
            return _unparseable(engine, REASON_NON_INTEGER_COUNT)
        counts[key] = exact
    globals_ = {}
    for key, value in scores.globals.items():
        if value is None:
            return _unparseable(engine, REASON_NULL_GLOBAL)
        exact = _exact_int(value)
        if exact is None or not 1 <= exact <= 5:
            return _unparseable(engine, REASON_SCHEMA)
        globals_[key] = exact
    return counts, globals_


def _parse_oneshot(engine: str, body: Mapping[str, Any]) -> ParsedRun:
    # oneshot_scores validates strictly; a null global fails validation, so detect it first to
    # give the precise reason.
    if isinstance(body, Mapping) and isinstance(body.get("globals"), Mapping) \
            and any(v is None for v in body["globals"].values()):
        return _unparseable(engine, REASON_NULL_GLOBAL)
    scores = oneshot_scores(body)
    parsed = _scores(engine, scores)
    if isinstance(parsed, ParsedRun):
        return parsed
    counts, globals_ = parsed
    return ParsedRun(engine=engine, status="ok", reason=None, counts=counts, globals=globals_)


def _parse_miti(engine: str, body: Mapping[str, Any]) -> ParsedRun:
    if any(g["onolys"]["score"] is None for g in body["globals"]):
        return _unparseable(engine, REASON_NULL_GLOBAL)
    scores = miti_lean_scores(body)
    parsed = _scores(engine, scores)
    if isinstance(parsed, ParsedRun):
        return parsed
    counts, globals_ = parsed
    reasons = {}
    for entry in body["globals"]:
        onolys = entry["onolys"]
        reasons[entry["item_id"]] = GlobalReason(
            reason=str(onolys.get("reason") or ""),
            evidence=tuple(Evidence(turn_id=e["turn_id"], quote=e["quote"])
                           for e in onolys.get("evidence") or ()))
    instances: list[Instance] = []
    rationales: dict[int, str] = {}
    turn_codes: dict[str, set[str]] = {}
    for behaviour in body["behaviours"]:
        code = behaviour["item_id"]
        for inst in behaviour.get("instances") or ():
            ref = len(instances)
            instances.append(Instance(ref=ref, code=code, turn_id=inst["turn_id"],
                                      quote=inst["quote"]))
            rationales[ref] = inst.get("rationale") or ""
            turn_codes.setdefault(inst["turn_id"], set()).add(code)
    return ParsedRun(
        engine=engine, status="ok", reason=None, counts=counts, globals=globals_,
        global_reasons=reasons, instances=tuple(instances), rationales=rationales,
        turn_codes={k: frozenset(v) for k, v in turn_codes.items()}, has_lines=True)
