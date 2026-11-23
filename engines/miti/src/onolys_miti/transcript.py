"""MITI quote spans measured in code-point offsets (ADR 0002)."""

from pydantic import BaseModel


class Span(BaseModel):
    """Code-point offsets into the turn text (ADR 0002)."""

    turn_id: str
    start: int
    end: int
