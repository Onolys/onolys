"""Transcript types (PRD R5). STT interface types live in onolys_miti.stt."""

from pydantic import BaseModel

from onolys_miti.transcript_v1 import TranscriptTurnV1 as Turn  # noqa: F401
from onolys_miti.transcript_v1 import TranscriptV1 as Transcript  # noqa: F401


class Span(BaseModel):
    """Code-point offsets into the turn text (ADR 0002)."""

    turn_id: str
    start: int
    end: int
