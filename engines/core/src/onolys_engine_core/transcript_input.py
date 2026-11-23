"""Validation shared by JSON and plain-text transcript uploads.

Upload constraints deliberately live outside the portable v1 schema: internal callers
can represent short transcripts, while uploaded sessions need enough speech to code.
"""

from pydantic import ValidationError

from onolys_engine_core.transcript_v1 import TranscriptV1

MAX_TURNS = 5_000
MAX_TURN_CHARS = 20_000
MAX_SPEAKERS = 8
MIN_WORDS = 50


class TranscriptInputError(ValueError):
    """Transport-independent upload error, with no transcript content in its details."""

    def __init__(self, code: str, message: str, field: str, issue: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.issue = issue


def _invalid(field: str, issue: str, message: str) -> TranscriptInputError:
    return TranscriptInputError("transcript_invalid", message, field, issue)


def _schema_error(error: ValidationError) -> TranscriptInputError:
    first = error.errors(include_input=False, include_context=False)[0]
    kind = first["type"]
    # An extra key is arbitrary user text. Report its known parent rather than echoing it.
    location = first["loc"][:-1] if kind == "extra_forbidden" else first["loc"]
    field = "/".join(str(part) for part in location) or "$"
    if kind in ("missing", "string_too_short", "string_pattern_mismatch"):
        issue = "required"
    elif kind == "extra_forbidden":
        issue = "unknown_key"
    elif kind.endswith("_type"):
        issue = "invalid_type"
    else:
        issue = "invalid"
    return _invalid(field, issue, "The transcript does not match transcript.v1.")


def validate_transcript_input(value: object) -> TranscriptV1:
    """Validate uploaded v1 data and enforce limits for either upload format.

    Body byte limits belong to the HTTP layer, before decoding. Coded-span duration
    and word caps belong to the engine after span selection, not to upload validation.
    """
    try:
        transcript = TranscriptV1.model_validate(value)
    except ValidationError as error:
        raise _schema_error(error) from None

    if len(transcript.turns) > MAX_TURNS:
        raise _invalid("turns", "too_large", "The transcript may contain at most 5,000 turns.")
    speakers = set()
    words = 0
    for index, turn in enumerate(transcript.turns):
        if len(turn.text) > MAX_TURN_CHARS:
            raise _invalid(
                f"turns/{index}/text", "too_long", "A turn may contain at most 20,000 characters."
            )
        speakers.add(turn.speaker)
        words += len(turn.text.split())
    if len(speakers) > MAX_SPEAKERS:
        raise _invalid("turns", "too_large", "The transcript may contain at most 8 speakers.")
    if words < MIN_WORDS:
        raise TranscriptInputError(
            "empty_transcript",
            "The transcript must contain at least 50 words.",
            "turns",
            "required",
        )
    return transcript


def inferred_clinician_speaker(transcript: TranscriptV1) -> str | None:
    """Resolve fully supplied roles; partial roles still require the speaker gate.

    Transport-independent so the transcript module can move to core. Multiple
    clinician labels are rejected even when other turns have missing roles.
    """
    clinicians = {turn.speaker for turn in transcript.turns if turn.role == "clinician"}
    if len(clinicians) > 1:
        raise _invalid(
            "turns", "invalid", "The transcript may identify only one clinician speaker."
        )
    if not clinicians or any(turn.role is None for turn in transcript.turns):
        return None
    return next(iter(clinicians))
