"""Automatic coded span (PRD R7): the engine, never the caller, picks what is coded."""

import hashlib
import math
import random
from dataclasses import dataclass, field
from typing import Literal

from onolys_miti.result import CodedSpan, ResultWarning
from onolys_miti.run_info import SpanInfo
from onolys_miti.transcript import Transcript

MAX_CODED_S = 1200  # longest stretch coded: 20 minutes


@dataclass(frozen=True)
class SpanChoice:
    coded_span: CodedSpan | None  # None = whole session
    mode: Literal["whole", "random_window"]
    duration_s: int | None  # None when the transcript has no timestamps
    seed: str
    warnings: list[ResultWarning] = field(default_factory=list)

    def info(self) -> SpanInfo:
        return SpanInfo(mode=self.mode, duration_s=self.duration_s, seed=self.seed)


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


def select_coded_span(transcript: Transcript, seed: str) -> SpanChoice:
    dur = duration_s(transcript)
    if dur is None:
        w = ResultWarning(code="span_ignored", detail="transcript has no timestamps")
        return SpanChoice(None, "whole", None, seed, [w])
    if dur <= MAX_CODED_S:
        return SpanChoice(None, "whole", dur, seed)
    from_s = math.floor(_rng(seed).uniform(0, dur - MAX_CODED_S))
    to_s = from_s + MAX_CODED_S
    w = ResultWarning(
        code="coded_window",
        severity="info",
        detail=f"coded {_mmss(from_s)}-{_mmss(to_s)} of a {_mmss(dur)} session",
    )
    return SpanChoice(CodedSpan(from_s=from_s, to_s=to_s), "random_window", dur, seed, [w])
