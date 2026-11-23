"""The portable transcript contract and its generated schema."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from onolys_miti.transcript_v1 import TranscriptV1

pytestmark = pytest.mark.unit


def turn(**changes):
    return {"id": "t1", "speaker": "T", "text": "Synthetic example.", **changes}


def test_valid_transcript_preserves_text_and_array_order():
    payload = {
        "language": "en",
        "duration_ms": 2000,
        "turns": [
            turn(id="second", role="clinician", start_ms=0, end_ms=1000, text="  Example.  "),
            turn(id="first", speaker="C", role="client", start_ms=1000, end_ms=2000),
        ],
    }
    transcript = TranscriptV1.model_validate(payload)
    assert transcript.model_dump() == payload


@pytest.mark.parametrize("value", ["", " ", "\t\n"])
@pytest.mark.parametrize("field", ["id", "speaker", "text"])
def test_nonblank_required_strings(field, value):
    with pytest.raises(ValidationError):
        TranscriptV1(turns=[turn(**{field: value})])


def test_duplicate_ids_are_invalid():
    with pytest.raises(ValidationError, match="unique"):
        TranscriptV1(turns=[turn(), turn(speaker="C")])


@pytest.mark.parametrize("role", ["therapist", "Clinician", "", "client\n"])
def test_invalid_role(role):
    with pytest.raises(ValidationError, match="role"):
        TranscriptV1(turns=[turn(role=role)])


@pytest.mark.parametrize("supplied", [{}, {"role": None}])
def test_role_can_be_missing_or_null(supplied):
    transcript = TranscriptV1(turns=[turn(**supplied)])
    assert transcript.turns[0].role is None
    assert transcript.language == "en"
    assert transcript.duration_ms is None
    assert transcript.turns[0].start_ms is None
    assert transcript.turns[0].end_ms is None


def test_start_after_end_is_invalid():
    with pytest.raises(ValidationError, match="start_ms"):
        TranscriptV1(turns=[turn(start_ms=10, end_ms=9)])


@pytest.mark.parametrize("times", [{"start_ms": 10}, {"end_ms": 10}, {"start_ms": 10, "end_ms": 10}])
def test_optional_times_and_equal_boundaries(times):
    assert len(TranscriptV1(turns=[turn(**times)]).turns) == 1


@pytest.mark.parametrize("payload", [{"stt_run": {}}, {"turns": [turn(language="en")]}])
def test_provenance_and_per_turn_language_are_not_v1(payload):
    with pytest.raises(ValidationError, match="extra_forbidden"):
        TranscriptV1.model_validate({"turns": [turn()], **payload})


def test_generated_schema_does_not_drift():
    path = Path(__file__).parents[1] / "src/onolys_miti/data/transcript.v1.schema.json"
    generated = json.dumps(TranscriptV1.model_json_schema(), indent=2, ensure_ascii=False) + "\n"
    assert path.read_text(encoding="utf-8") == generated


def test_schema_enforces_portable_constraints():
    validator = Draft202012Validator(TranscriptV1.model_json_schema())
    validator.check_schema(validator.schema)
    validator.validate({"turns": [turn(role=None)]})
    for field, value in [("id", ""), ("speaker", " "), ("text", "\t"), ("role", "client\n")]:
        assert list(validator.iter_errors({"turns": [turn(**{field: value})]}))
