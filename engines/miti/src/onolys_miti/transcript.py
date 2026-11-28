"""MITI quote spans measured in code-point offsets."""

from pydantic import BaseModel


class Span(BaseModel):
    """Code-point offsets into the turn text."""

    turn_id: str
    start: int
    end: int
