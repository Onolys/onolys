"""Whole-session default, caller-selected spans, and an optional seeded window helper."""

import hashlib
import math
import random
from dataclasses import dataclass, field
from typing import Any, Literal

from onolys_engine_core.errors import InvalidCodedSpan
from onolys_engine_core.transcript import Transcript
from pydantic import ValidationError

from onolys_miti.result import CodedSpan, ResultWarning
from onolys_miti.run_info import SpanInfo

MAX_CODED_S = 1200  # optional default_window length: 20 minutes


@dataclass(frozen=True)
class SpanChoice:
    coded_span: CodedSpan | None  # None = whole session
    mode: Literal["whole", "explicit", "random_window"]
    duration_s: int | None  # None when the transcript has no timestamps
    seed: str
    warnings: list[ResultWarning] = field(default_factory=list)

    def info(self) -> SpanInfo:
        bounds = self.coded_span.model_dump(exclude_none=True) if self.coded_span else {}
        return SpanInfo(mode=self.mode, duration_s=self.duration_s, seed=self.seed, **bounds)


def duration_s(transcript: Transcript) -> int | None:
    """Max over turns of `end_ms` (fallback `start_ms`), whole seconds (ceil); None if no turn
    has a timestamp."""
    ends = [
        t.end_ms if t.end_ms is not None else t.start_ms
        for t in transcript.turns
        if t.end_ms is not None or t.start_ms is not None
    ]
    return math.ceil(max(ends) / 1000) if ends else None


def _rng(seed: str) -> random.Random:
    # sha256, not hash(): reproducible across processes.
    return random.Random(int.from_bytes(hashlib.sha256(seed.encode()).digest(), "big"))


def _mmss(s: int) -> str:
    return f"{s // 60}:{s % 60:02d}"


def select_coded_span(
    transcript: Transcript, seed: str, coded_span: CodedSpan | dict[str, Any] | None = None
) -> SpanChoice:
    """Choose the whole transcript unless the caller supplies an explicit valid range."""
    dur = duration_s(transcript)
    if coded_span is None:
        return SpanChoice(None, "whole", dur, seed)
    try:
        span = CodedSpan.model_validate(coded_span)
    except ValidationError as exc:
        raise InvalidCodedSpan(f"invalid_coded_span: {exc}") from exc
    if span.start_turn is not None:
        if span.end_turn > len(transcript.turns):
            raise InvalidCodedSpan("invalid_coded_span: turn range exceeds transcript length")
    elif not any(t.start_ms is not None for t in transcript.turns):
        raise InvalidCodedSpan("invalid_coded_span: time spans require turn timestamps")
    return SpanChoice(span, "explicit", dur, seed)


def default_window(transcript: Transcript, seed: str) -> SpanChoice:
    """Opt-in reproducible 20-minute window; never applied automatically by run_miti."""
    dur = duration_s(transcript)
    if dur is None:
        return SpanChoice(None, "whole", None, seed)
    if dur <= MAX_CODED_S:
        return SpanChoice(None, "whole", dur, seed)
    from_s = math.floor(_rng(seed).uniform(0, dur - MAX_CODED_S))
    to_s = from_s + MAX_CODED_S
    w = ResultWarning(
        code="coded_window",
        severity="info",
        detail=f"coded {_mmss(from_s)}-{_mmss(to_s)} of a {_mmss(dur)} session",
    )
    span = CodedSpan(start_ms=from_s * 1000, end_ms=to_s * 1000)
    return SpanChoice(span, "random_window", dur, seed, [w])
