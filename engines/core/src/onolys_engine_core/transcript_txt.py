"""Parse label-prefixed UTF-8 text into transcript.v1 without inferring speakers."""

import re

from onolys_engine_core.transcript_input import TranscriptInputError, validate_transcript_input
from onolys_engine_core.transcript_v1 import TranscriptV1

_LABEL = re.compile(r"^([^:\r\n]{1,40}):[ \t]*(.*)$")
_ROLES = {"T": "clinician", "C": "client"}


def parse_transcript_txt(source: str | bytes) -> TranscriptV1:
    """Label lines start turns; all other nonblank lines continue the last turn."""
    if isinstance(source, bytes):
        try:
            source = source.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise TranscriptInputError(
                "transcript_invalid", "The transcript must be UTF-8 text.", "$", "invalid"
            ) from None
    source = source.removeprefix("\ufeff").replace("\r\n", "\n")
    turns: list[dict] = []
    for line in source.split("\n"):
        if not line.strip():
            continue
        match = _LABEL.fullmatch(line)
        if match and match.group(1).strip():
            label = match.group(1).strip()
            canonical = label.upper()
            speaker = canonical if canonical in _ROLES else label
            turns.append({
                "id": f"t{len(turns) + 1}",
                "speaker": speaker,
                "role": _ROLES.get(canonical),
                "text": match.group(2).strip(),
            })
        elif turns:
            turns[-1]["text"] += "\n" + line.strip()
        else:
            raise TranscriptInputError(
                "transcript_invalid",
                "The transcript must begin with a speaker label followed by a colon.",
                "$",
                "invalid",
            )
    return validate_transcript_input({"turns": turns})
