"""Reusable gold.v1 contract with engine item IDs and pack-computed summaries."""
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    StringConstraints,
    field_validator,
    model_serializer,
    model_validator,
)

from ._contracts import (
    CodedSpan,
    Contract,
    HttpURL,
    Identifier,
    Nonempty,
    NonnegativeInt,
)
from ._formulas import compute_summaries

CountId = Literal[
    "gi", "persuade", "persuade_permission", "question", "sr", "cr", "affirm",
    "seek_collab", "emphasize_autonomy", "confront",
]
GlobalId = Literal["cct", "sst", "partnership", "empathy"]
COUNT_IDS = tuple(CountId.__args__)
GLOBAL_IDS = tuple(GlobalId.__args__)
Counts = Annotated[dict[CountId, NonnegativeInt], Field(min_length=10, max_length=10)]
Globals = Annotated[dict[GlobalId, Annotated[int, Field(ge=1, le=5)]],
                    Field(min_length=4, max_length=4)]
# Partial human labels: a missing or null entry means "not labeled", never zero.
PartialCounts = Annotated[dict[CountId, NonnegativeInt | None], Field(max_length=10)]
PartialGlobals = Annotated[
    dict[GlobalId, Annotated[int, Field(ge=1, le=5)] | None], Field(max_length=4)]
Number = Annotated[float, Field(allow_inf_nan=False)]
QualityLabel = Literal["high", "low"]


class Summaries(Contract):
    """Pack summaries; null when undefined or when an input is not labeled."""
    technical: Number | None = None
    relational: Number | None = None
    pct_cr: Number | None = None
    reflection_question_ratio: Number | None = None
    total_mia: Number | None = None
    total_mina: Number | None = None


class GoldSource(Contract):
    # Optional for datasets without coded/uncoded PDFs (e.g. public annotated corpora).
    coded_url: HttpURL | None = None
    uncoded_url: HttpURL | None = None
    retrieved_at: str
    # Hash of the coded source file: the source of truth for the parsed reference.
    sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")] | None = None

    @field_validator("retrieved_at")
    @classmethod
    def timestamp_has_timezone(cls, value):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("retrieved_at must include a timezone")
        return value


class UtteranceCodes(Contract):
    turn_id: Nonempty
    codes: list[CountId]
    note: str | None = None


class ParseInfo(Contract):
    method: Literal["auto", "auto+override"]
    warnings: list[str]


class Gold(Contract):
    schema_version: Literal["gold.v1"] = Field(alias="schema")
    dataset_id: Identifier
    session_id: Identifier
    source: GoldSource
    coded_span: CodedSpan
    counts: PartialCounts = Field(default_factory=dict)
    globals: PartialGlobals | None = None
    summaries: Summaries | None = None
    utterance_codes: list[UtteranceCodes] | None = None
    parse: ParseInfo
    quality_label: QualityLabel | None = None
    label_source: str | None = None
    label_scheme: str | None = None

    @model_serializer(mode="wrap")
    def _omit_unset_label_metadata(self, handler: SerializerFunctionWrapHandler):
        # Keep full-gold dumps (and their hashes) identical to pre-partial files.
        data = handler(self)
        for key in ("quality_label", "label_source", "label_scheme"):
            if data.get(key) is None:
                data.pop(key, None)
        return data

    @model_validator(mode="after")
    def summaries_match_scores(self):
        if self.summaries is not None:
            present_counts = {k: v for k, v in self.counts.items() if v is not None}
            present_globals = {k: v for k, v in (self.globals or {}).items() if v is not None}
            if self.summaries.model_dump() != compute_summaries(present_counts, present_globals):
                raise ValueError(
                    "summaries must equal the engine pack formulas for the labeled counts/globals")
        if self.utterance_codes is not None:
            ids = [row.turn_id for row in self.utterance_codes]
            if len(ids) != len(set(ids)):
                raise ValueError("utterance_codes turn_id must be unique")
        return self


def load_gold(path: str | Path) -> Gold:
    """Load a gold JSON file with structural and formula consistency checks."""
    return Gold.model_validate_json(Path(path).read_text())
