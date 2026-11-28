"""Synthetic upload input examples and limit boundaries."""

import pytest
from onolys_engine import TranscriptV1

from onolys_api.transcription.transcript_input import (
    TranscriptInputError,
    validate_transcript_input,
)
from onolys_api.transcription.transcript_txt import parse_transcript_txt

pytestmark = pytest.mark.unit
WORDS = " ".join(["example"] * 50)


def payload(count=1, speakers=1, text=WORDS):
    return {"turns": [
        {"id": f"t{i + 1}", "speaker": f"S{i % speakers}", "text": text}
        for i in range(count)
    ]}


def assert_error(call, code, field, issue):
    with pytest.raises(TranscriptInputError) as caught:
        call()
    assert (caught.value.code, caught.value.field, caught.value.issue) == (code, field, issue)
    assert caught.value.message


def test_text_roles_names_and_ids():
    source = f"t: {WORDS}\nc: Example answer.\nAlex: Another answer.\nAlex: More."
    transcript = parse_transcript_txt(source)
    assert isinstance(transcript, TranscriptV1)
    assert [(t.id, t.speaker, t.role) for t in transcript.turns] == [
        ("t1", "T", "clinician"), ("t2", "C", "client"), ("t3", "Alex", None), ("t4", "Alex", None)
    ]
    assert all(t.start_ms is None and t.end_ms is None for t in transcript.turns)


@pytest.mark.parametrize("as_bytes", [False, True])
def test_multiline_bom_crlf_and_blank_lines(as_bytes):
    source = f"\ufeffT: {WORDS}\r\n\r\ncontinued here\r\nC: reply\r\n"
    transcript = parse_transcript_txt(source.encode("utf-8") if as_bytes else source)
    assert transcript.turns[0].text == f"{WORDS}\ncontinued here"
    assert transcript.turns[1].text == "reply"


@pytest.mark.parametrize("label", ["A", "A" * 40])
def test_label_length_boundaries(label):
    assert parse_transcript_txt(f"{label}: {WORDS}").turns[0].speaker == label


@pytest.mark.parametrize("source", ["orphan\nT: example", ": missing label", f"{'A' * 41}: text"])
def test_leading_nonlabel_is_invalid(source):
    assert_error(lambda: parse_transcript_txt(source), "transcript_invalid", "$", "invalid")


def test_nonlabel_after_turn_is_continuation():
    source = f"T: {WORDS}\n{'A' * 41}: continuation\n: continuation"
    assert parse_transcript_txt(source).turns[0].text == source[3:]


def test_empty_labeled_turn_is_invalid():
    assert_error(lambda: parse_transcript_txt(f"T: \nC: {WORDS}"),
                 "transcript_invalid", "turns/0/text", "required")


def test_invalid_utf8_does_not_expose_input():
    assert_error(lambda: parse_transcript_txt(b"private\xff"),
                 "transcript_invalid", "$", "invalid")
    with pytest.raises(TranscriptInputError) as caught:
        parse_transcript_txt(b"private\xff")
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("source", ["", "\ufeff\r\n \n", "T: short example"])
def test_empty_or_short_text_uses_empty_transcript(source):
    assert_error(lambda: parse_transcript_txt(source), "empty_transcript", "turns", "required")


@pytest.mark.parametrize("count", [4999, 5000])
def test_turn_count_limit_allows_boundary(count):
    assert len(validate_transcript_input(payload(count, text="example")).turns) == count


def test_turn_count_over_limit():
    assert_error(lambda: validate_transcript_input(payload(5001, text="example")),
                 "transcript_invalid", "turns", "too_large")


@pytest.mark.parametrize("length", [19999, 20000])
def test_character_limit_allows_boundary(length):
    text = WORDS + "x" * (length - len(WORDS))
    assert len(validate_transcript_input(payload(text=text)).turns[0].text) == length


def test_character_over_limit():
    assert_error(lambda: validate_transcript_input(payload(text=WORDS + "x" * (20001 - len(WORDS)))),
                 "transcript_invalid", "turns/0/text", "too_long")


@pytest.mark.parametrize("speakers", [7, 8])
def test_speaker_limit_allows_boundary(speakers):
    assert len(validate_transcript_input(payload(speakers, speakers)).turns) == speakers


def test_speakers_over_limit():
    assert_error(lambda: validate_transcript_input(payload(9, 9)),
                 "transcript_invalid", "turns", "too_large")


@pytest.mark.parametrize("count", [0, 49])
def test_word_count_below_minimum(count):
    data = payload(text=" ".join(["example"] * count)) if count else {"turns": []}
    assert_error(lambda: validate_transcript_input(data), "empty_transcript", "turns", "required")


@pytest.mark.parametrize("count", [50, 51])
def test_word_count_at_or_above_minimum(count):
    assert validate_transcript_input(payload(text="\t".join(["example"] * count)))


def test_model_input_uses_same_limits():
    data = TranscriptV1.model_validate(payload(text="example"))
    assert_error(lambda: validate_transcript_input(data), "empty_transcript", "turns", "required")


@pytest.mark.parametrize(("data", "field", "issue"), [
    ({}, "turns", "required"),
    ({"turns": "private"}, "turns", "invalid_type"),
    (payload(text=" "), "turns/0/text", "required"),
    ({"turns": [{"id": "t1", "speaker": "T"}]}, "turns/0/text", "required"),
    ({**payload(), "private": "secret"}, "$", "unknown_key"),
])
def test_malformed_json_has_safe_field_and_issue(data, field, issue):
    assert_error(lambda: validate_transcript_input(data), "transcript_invalid", field, issue)


def test_txt_uses_same_limits():
    assert_error(lambda: parse_transcript_txt(f"T: {WORDS + 'x' * 20000}"),
                 "transcript_invalid", "turns/0/text", "too_long")
