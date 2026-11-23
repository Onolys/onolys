"""Core selection uses SP1 half-open turn/time semantics without MITI imports."""

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
