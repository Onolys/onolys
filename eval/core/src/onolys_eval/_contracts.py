"""Shared strict metadata fields for dataset and gold contracts."""
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


Identifier = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
Nonempty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
HttpURL = Annotated[str, StringConstraints(pattern=r"^https?://[^\s/]+(?:/[^\s]*)?$")]
NonnegativeInt = Annotated[int, Field(ge=0)]


class TimeSpan(Contract):
    start_ms: NonnegativeInt
    end_ms: NonnegativeInt

    @model_validator(mode="after")
    def ordered(self):
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must follow start_ms")
        return self


class TurnSpan(Contract):
    """Zero-based half-open transcript turn range [start_turn, end_turn)."""
    start_turn: NonnegativeInt
    end_turn: NonnegativeInt

    @model_validator(mode="after")
    def ordered(self):
        if self.end_turn <= self.start_turn:
            raise ValueError("end_turn must follow start_turn")
        return self


CodedSpan = TimeSpan | TurnSpan | None
