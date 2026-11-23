"""Typed, versioned engine output (PRD R3). `data/miti-result.schema.json` is generated
from these models (`python -m onolys_miti.result --write`); a test keeps the two in sync.

Protocol-agnostic: item ids, codes and summary ids are free strings defined by the pack."""

import json
import sys
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_serializer,
    model_validator,
)

from onolys_miti.run_info import RunInfo

SCHEMA_VERSION = "0.0.1"

# Engine-defined warning codes; packs may define more (any `[a-z][a-z0-9_]*` string).
WARNING_CODES = (
    "short_session",
    "quote_not_found",
    "overlap",
    "insufficient_evidence",
    "capped",
    "coded_window",
    "unknown_speaker",
    "language_not_validated",
    "run_failed",
)

WarningCode = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
Offset = Annotated[int, Field(ge=0)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ResultWarning(_Model):
    code: WarningCode = Field(
        json_schema_extra={"examples": list(WARNING_CODES)},
        description="Engine code (see WARNING_CODES) or a pack-defined code.",
    )
    severity: Literal["info", "warning"] = "warning"
    item_id: str | None = None
    detail: str | None = None


class ProtocolBlock(_Model):
    id: str
    version: str
    pack_hash: str
    pack_format: str


class CodedSpan(_Model):
    """Exactly one half-open time (milliseconds) or zero-based turn range."""

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={
        "oneOf": [
            {"required": ["start_ms", "end_ms"], "properties": {
                "start_ms": {"type": "integer"}, "end_ms": {"type": "integer"},
                "start_turn": {"type": "null"}, "end_turn": {"type": "null"}}},
            {"required": ["start_turn", "end_turn"], "properties": {
                "start_turn": {"type": "integer"}, "end_turn": {"type": "integer"},
                "start_ms": {"type": "null"}, "end_ms": {"type": "null"}}},
        ],
    })
    start_ms: Offset | None = None
    end_ms: Offset | None = None
    start_turn: Offset | None = None
    end_turn: Offset | None = None

    @model_serializer(mode="wrap")
    def _serialize(self, handler):
        return {key: value for key, value in handler(self).items() if value is not None}

    @model_validator(mode="after")
    def _range(self):
        time = self.start_ms is not None and self.end_ms is not None
        turns = self.start_turn is not None and self.end_turn is not None
        if time and self.start_turn is None and self.end_turn is None:
            start, end = self.start_ms, self.end_ms
        elif turns and self.start_ms is None and self.end_ms is None:
            start, end = self.start_turn, self.end_turn
        else:
            raise ValueError("supply exactly one complete time or turn range")
        if start >= end:
            raise ValueError("range start must be less than end")
        return self


class Instance(_Model):
    """One coded utterance. Offsets are code points into the turn's text."""

    id: str
    volley_id: str
    turn_id: str
    start: Offset
    end: Offset
    start_ms: int | None = None
    end_ms: int | None = None
    quote: str
    code: str | None
    counted: bool
    uncounted_reason: str | None = None
    rationale: str

    @model_validator(mode="after")
    def _check(self):
        if self.end < self.start:
            raise ValueError("end < start")
        if self.uncounted_reason is not None and self.counted:
            raise ValueError("uncounted_reason set on a counted instance")
        return self


class Evidence(_Model):
    turn_id: str
    start: Offset
    end: Offset
    quote: str

    @model_validator(mode="after")
    def _check(self):
        if self.end < self.start:
            raise ValueError("end < start")
        return self


class GlobalScore(_Model):
    score: int
    source: Literal["model", "default", "capped"]
    raw_score: int
    reason: str
    evidence: list[Evidence]


class Reference(_Model):
    fair: float
    good: float


class Summary(_Model):
    value: float | None
    label: Literal["below_fair", "fair", "good"] | None
    reference: Reference | None


class RunResult(_Model):
    run_index: Annotated[int, Field(ge=0)]
    instances: list[Instance]
    counts: dict[str, Annotated[int, Field(ge=0)]]
    globals: dict[str, GlobalScore]
    summaries: dict[str, Summary]
    warnings: list[ResultWarning]


class Stat(_Model):
    mean: float
    min: float
    max: float
    values: list[float]


class SummaryStat(_Model):
    mean: float | None
    min: float | None
    max: float | None
    values: list[float | None]
    label: Literal["below_fair", "fair", "good"] | None = None
    reference: Reference | None = None


class Aggregate(_Model):
    counts: dict[str, Stat]
    globals: dict[str, Stat]
    summaries: dict[str, SummaryStat]
    representative_run: Annotated[
        int, Field(ge=0, description="`run_index` of the run closest to the mean vector.")
    ]


class MitiResult(_Model):
    schema_version: Literal["0.0.1"]
    request_id: str | None = None
    protocol: ProtocolBlock
    language: str
    change_goal: str | None = None
    coded_span: CodedSpan | None = None
    subject_speaker: str
    n_runs: Annotated[int, Field(ge=1)]
    results: Annotated[list[RunResult], Field(min_length=1)]
    aggregate: Aggregate
    warnings: list[ResultWarning]
    run_info: RunInfo

    @model_validator(mode="after")
    def _check(self):
        if self.aggregate.representative_run not in {r.run_index for r in self.results}:
            raise ValueError("representative_run is not a run_index in results")
        return self


def result_schema() -> dict[str, Any]:
    schema = MitiResult.model_json_schema(mode="validation")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "MitiResult",
        **schema,
    }


def schema_text() -> str:
    return json.dumps(result_schema(), indent=2) + "\n"


def schema_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "miti-result.schema.json"


if __name__ == "__main__":
    if "--write" in sys.argv:
        schema_path().write_text(schema_text())
    else:
        sys.stdout.write(schema_text())
