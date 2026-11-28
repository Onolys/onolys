"""Core selection uses half-open turn/time semantics without MITI imports."""

import pytest

from onolys_engine_core.errors import InvalidCodedSpan
from onolys_engine_core.transcript_v1 import TranscriptV1


def transcript():
    return TranscriptV1.model_validate(
        {
            "language": "en",
            "duration_ms": 4000,
            "turns": [
                {"id": "a", "speaker": "T", "text": "first", "start_ms": 0, "end_ms": 1000},
                {"id": "b", "speaker": "C", "text": "second", "start_ms": 1000, "end_ms": 2000},
                {"id": "c", "speaker": "T", "text": "third", "start_ms": 2000, "end_ms": 3000},
            ],
        }
    )


def apply(transcript, span):
    from onolys_engine_core.spans import apply_coded_span

    return apply_coded_span(transcript, span)


def test_full_default_and_turn_boundaries_preserve_metadata_and_source():
    tx = transcript()
    assert apply(tx, None) == tx
    selected = apply(tx, {"start_turn": 1, "end_turn": 3})
    assert [t.id for t in selected.turns] == ["b", "c"]
    assert selected.language == tx.language and selected.duration_ms == tx.duration_ms
    assert len(tx.turns) == 3


def test_time_overlap_is_half_open():
    tx = transcript()
    assert [t.id for t in apply(tx, {"start_ms": 1000, "end_ms": 2000}).turns] == ["b"]
    assert [t.id for t in apply(tx, {"start_ms": 999, "end_ms": 1001}).turns] == ["a", "b"]


def test_partial_timestamps_follow_sp1():
    tx = transcript()
    tx.turns[0].start_ms = None
    tx.turns[1].end_ms = None
    # Untimed-start turns stay; start-only turns act as points with strict overlap.
    assert [t.id for t in apply(tx, {"start_ms": 900, "end_ms": 1100}).turns] == ["a", "b"]
    assert [t.id for t in apply(tx, {"start_ms": 1000, "end_ms": 2500}).turns] == ["a", "c"]


@pytest.mark.parametrize(
    "span",
    [
        {},
        {"start_turn": 1},
        {"start_turn": 0, "end_turn": 4},
        {"start_turn": -1, "end_turn": 2},
        {"start_turn": 2, "end_turn": 2},
        {"start_turn": 2, "end_turn": 1},
        {"start_turn": True, "end_turn": 2},
        {"start_turn": "0", "end_turn": 2},
        {"start_turn": 0.0, "end_turn": 2},
        {"start_ms": 0, "end_ms": 1000, "end_turn": 1},
        {"start_ms": 0, "end_ms": 1000, "extra": 1},
        {"start_ms": -1, "end_ms": 1000},
        {"start_ms": 0, "end_ms": False},
        {"start_ms": 3000, "end_ms": 4000},
        [],
        "bad",
    ],
)
def test_invalid_spans_raise_typed_input_error(span):
    with pytest.raises(InvalidCodedSpan, match="invalid_coded_span"):
        apply(transcript(), span)


def test_time_span_requires_some_start_timestamps():
    tx = transcript()
    for turn in tx.turns:
        turn.start_ms = None
    with pytest.raises(InvalidCodedSpan, match="timestamps"):
        apply(tx, {"start_ms": 0, "end_ms": 1000})


def test_empty_transcript_supports_whole_but_rejects_explicit():
    tx = TranscriptV1(turns=[])
    assert apply(tx, None) == tx
    with pytest.raises(InvalidCodedSpan):
        apply(tx, {"start_turn": 0, "end_turn": 1})


@pytest.mark.parametrize("span,expected", [
    (None, 3000),
    ({"start_turn": 1, "end_turn": 3}, 2000),
    ({"start_ms": 1100, "end_ms": 2100}, 1000),
])
def test_selected_duration_uses_span_semantics(span, expected):
    from onolys_engine_core.spans import selected_duration_ms

    tx = transcript()
    original = tx.model_dump()
    selected = apply(tx, span)
    assert selected_duration_ms(tx, selected.turns, span) == expected
    assert tx.model_dump() == original


def test_untimed_selected_duration_never_inherits_whole_header():
    from onolys_engine_core.spans import selected_duration_ms

    tx = transcript()
    for turn in tx.turns:
        turn.start_ms = turn.end_ms = None
    assert selected_duration_ms(tx, tx.turns, None) == 4000
    assert selected_duration_ms(tx, tx.turns[1:], {"start_turn": 1, "end_turn": 3}) is None


def test_partial_timing_duration_uses_maximum_end_and_minimum_start():
    from onolys_engine_core.spans import selected_duration_ms

    tx = transcript()
    tx.turns[0].end_ms = None
    tx.turns[1].start_ms = None
    span = {"start_turn": 0, "end_turn": 3}
    assert selected_duration_ms(tx, list(reversed(tx.turns)), span) == 3000


@pytest.mark.parametrize("words,duration,allowed", [
    (6000, 1_500_000, True),
    (6001, 1_500_000, False),
    (6000, 1_500_001, False),
])
def test_selected_portion_limits_are_inclusive(words, duration, allowed):
    from onolys_engine_core.errors import SessionTooLong
    from onolys_engine_core.spans import validate_portion_limits

    tx = TranscriptV1.model_validate({"turns": [
        {"id": "a", "speaker": "T", "text": "word\t\n" * words},
    ]})
    if allowed:
        validate_portion_limits(tx.turns, duration)
    else:
        with pytest.raises(SessionTooLong, match="narrower coded_span"):
            validate_portion_limits(tx.turns, duration)
