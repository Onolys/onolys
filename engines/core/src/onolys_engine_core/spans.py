"""Pure transcript selection shared by engines; indices and times are half-open."""

from collections.abc import Sequence

from .errors import InvalidCodedSpan, SessionTooLong
from .transcript_v1 import TranscriptTurnV1, TranscriptV1

_FIELDS = {"start_ms", "end_ms", "start_turn", "end_turn"}


def apply_coded_span(transcript: TranscriptV1, span: dict | None) -> TranscriptV1:
    """Keep whole turns in a turn slice or overlapping a millisecond range.

    SP1 retains turns without a start timestamp alongside selected timed turns. Missing
    end timestamps fall back to start timestamps. Metadata and source turns stay intact.
    """
    if span is None:
        return transcript.model_copy(update={"turns": list(transcript.turns)})
    if not isinstance(span, dict) or span.keys() - _FIELDS:
        raise InvalidCodedSpan("invalid_coded_span: supply a time or turn range")
    bounds = {key: value for key, value in span.items() if value is not None}
    if bounds.keys() == {"start_turn", "end_turn"}:
        start, end = bounds["start_turn"], bounds["end_turn"]
        timed = False
    elif bounds.keys() == {"start_ms", "end_ms"}:
        start, end = bounds["start_ms"], bounds["end_ms"]
        timed = True
    else:
        raise InvalidCodedSpan("invalid_coded_span: supply exactly one complete range")
    if type(start) is not int or type(end) is not int or not 0 <= start < end:
        raise InvalidCodedSpan("invalid_coded_span: bounds must be ordered nonnegative integers")
    if not timed:
        if end > len(transcript.turns):
            raise InvalidCodedSpan("invalid_coded_span: turn range exceeds transcript length")
        selected = transcript.turns[start:end]
    else:
        if not any(turn.start_ms is not None for turn in transcript.turns):
            raise InvalidCodedSpan("invalid_coded_span: time spans require turn timestamps")
        selected = []
        for turn in transcript.turns:
            turn_start = turn.start_ms
            turn_end = turn.end_ms if turn.end_ms is not None else turn_start
            if turn_start is None or (turn_start < end and turn_end > start):
                selected.append(turn)
        if not selected:
            raise InvalidCodedSpan("invalid_coded_span: time range selects no turns")
    return transcript.model_copy(update={"turns": selected})


def selected_duration_ms(
    source: TranscriptV1, turns: Sequence[TranscriptTurnV1], span: dict | None,
) -> int | None:
    """Measure a validated selection; the source header describes only a whole session."""
    if span and span.get("start_ms") is not None:
        return span["end_ms"] - span["start_ms"]
    ends = [
        turn.end_ms if turn.end_ms is not None else turn.start_ms
        for turn in turns
        if turn.end_ms is not None or turn.start_ms is not None
    ]
    if span:
        starts = [turn.start_ms for turn in turns if turn.start_ms is not None]
        return max(ends) - min(starts) if ends and starts else None
    return max(ends) if ends else source.duration_ms


def validate_portion_limits(
    turns: Sequence[TranscriptTurnV1],
    duration_ms: int | None,
    *,
    max_duration_ms: int | None = 25 * 60_000,
    max_words: int = 6000,
) -> None:
    """Reject an oversized coded portion without inspecting or changing source metadata.

    Callers with configurable duration checks may disable this duration cap and retain
    their existing warning/error policy. Word counts always use selected turns only.
    """
    if sum(len(turn.text.split()) for turn in turns) > max_words:
        raise SessionTooLong(
            f"session_too_long: coded portion exceeds {max_words} words; "
            "supply a narrower coded_span"
        )
    if max_duration_ms is not None and duration_ms is not None and duration_ms > max_duration_ms:
        raise SessionTooLong(
            "session_too_long: coded portion exceeds the duration limit; "
            "supply a narrower coded_span"
        )
