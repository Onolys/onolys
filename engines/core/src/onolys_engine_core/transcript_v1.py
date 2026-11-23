"""Portable transcript.v1 contract; intentionally depends only on pydantic."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TranscriptTurnV1(BaseModel):
    """One turn, in the order it appears in the transcript."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"\S")
    speaker: str = Field(min_length=1, pattern=r"\S")
    role: str | None = Field(
        default=None, json_schema_extra={"enum": ["clinician", "client", None]}
    )
    text: str = Field(min_length=1, pattern=r"\S")
    start_ms: int | None = None
    end_ms: int | None = None

    @field_validator("role")
    @classmethod
    def valid_role(cls, value: str | None) -> str | None:
        if value is not None and value not in ("clinician", "client"):
            raise ValueError("role must be clinician, client, or null")
        return value

    @model_validator(mode="after")
    def ordered_times(self):
        if self.start_ms is not None and self.end_ms is not None and self.start_ms > self.end_ms:
            raise ValueError("start_ms must be less than or equal to end_ms")
        return self


class TranscriptV1(BaseModel):
    """The transcript shape shared by upload, transcription, and coding."""

    model_config = ConfigDict(extra="forbid")

    language: str | None = "en"
    duration_ms: int | None = None
    turns: list[TranscriptTurnV1]

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [turn.id for turn in self.turns]
        if len(ids) != len(set(ids)):
            raise ValueError("turn ids must be unique")
        return self
