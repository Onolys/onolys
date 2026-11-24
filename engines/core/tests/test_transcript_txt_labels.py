"""Never invent speakers from stray 'word:' lines (B6)."""

import random

import pytest

from onolys_engine_core.transcript_txt import parse_transcript_txt

pytestmark = pytest.mark.unit
WORDS = " ".join(["example"] * 30)


def speakers(source):
    return [t.speaker for t in parse_transcript_txt(source).turns]


def test_timestamp_note_is_continuation_not_speaker_10():
    source = f"T: {WORDS}\n10:32 note: x\nC: {WORDS}\nT: {WORDS}"
    assert speakers(source) == ["T", "C", "T"]
    assert "10:32 note: x" in parse_transcript_txt(source).turns[0].text


def test_leading_timestamp_before_label_is_stripped():
    source = f"[00:01:02] T: {WORDS}\n10:32 C: {WORDS}"
    turns = parse_transcript_txt(source).turns
    assert [(t.speaker, t.start_ms) for t in turns] == [("T", None), ("C", None)]


def test_wrapped_line_with_colon_is_continuation():
    source = f"T: {WORDS}\nthe reason: it was late\nC: ok {WORDS}\nT: bye"
    assert speakers(source) == ["T", "C", "T"]


def test_singleton_unknown_label_among_known_is_not_a_speaker():
    source = f"T: {WORDS}\nSummary: wrapped\nC: {WORDS}"
    assert speakers(source) == ["T", "C"]


def test_repeated_name_labels_are_speakers():
    source = f"Alex: {WORDS}\nSam: {WORDS}\nAlex: more\nSam: more"
    assert speakers(source) == ["Alex", "Sam", "Alex", "Sam"]


def test_never_invents_speakers_property():
    rng = random.Random(1234)
    noise = ["note: x", "10:32 memo: y", "Re: thing", "see: this", "12:05 wait: no", "a, b: c"]
    for _ in range(200):
        labels = rng.sample(["T", "C", "Therapist", "Client"], 2)
        lines, pool = [], list(noise)
        for i in range(rng.randint(2, 8)):
            lines.append(f"{labels[i % 2]}: {WORDS}")
            if pool and rng.random() < 0.6:
                lines.append(pool.pop(rng.randrange(len(pool))))
        got = set(speakers("\n".join(lines)))
        assert got <= {lab.upper() if lab in "TC" else lab for lab in labels}


def test_two_distinct_named_speakers_each_once_are_speakers():
    assert speakers(f"Pat: {WORDS}\nSam: {WORDS}") == ["Pat", "Sam"]


def test_stray_colon_line_after_two_unanchored_names_is_continuation():
    source = f"Pat: {WORDS}\nSam: {WORDS}\nnote: wrapped"
    assert speakers(source) == ["Pat", "Sam"]
