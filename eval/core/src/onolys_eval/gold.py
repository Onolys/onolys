"""Reusable gold.v1 contract with engine item IDs and pack-computed summaries."""
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

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
Number = Annotated[float, Field(allow_inf_nan=False)]


class Summaries(Contract):
    technical: Number
    relational: Number
    pct_cr: Number | None
    reflection_question_ratio: Number | None
    total_mia: Number
    total_mina: Number


class GoldSource(Contract):
    coded_url: HttpURL
    uncoded_url: HttpURL
    retrieved_at: str
    # Hash of the coded PDF: the source of truth for the parsed reference.
    sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]

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
    counts: Counts
    globals: Globals
    summaries: Summaries
    utterance_codes: list[UtteranceCodes] | None = None
    parse: ParseInfo

    @model_validator(mode="after")
    def summaries_match_scores(self):
        if self.summaries.model_dump() != compute_summaries(self.counts, self.globals):
            raise ValueError("summaries must equal the engine pack formulas for counts/globals")
        if self.utterance_codes is not None:
            ids = [row.turn_id for row in self.utterance_codes]
            if len(ids) != len(set(ids)):
                raise ValueError("utterance_codes turn_id must be unique")
        return self


def load_gold(path: str | Path) -> Gold:
    """Load a gold JSON file with structural and formula consistency checks."""
    return Gold.model_validate_json(Path(path).read_text())
