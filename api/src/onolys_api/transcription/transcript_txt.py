"""Parse label-prefixed UTF-8 text into transcript.v1 without inferring speakers."""

import re

from onolys_engine import TranscriptV1

from onolys_api.transcription.transcript_input import (
    TranscriptInputError,
    validate_transcript_input,
)

_LABEL = re.compile(r"^([^:\r\n]{1,40}):[ \t]*(.*)$")
_ROLES = {"T": "clinician", "C": "client"}
# Role-style labels accepted even when they occur once.
_KNOWN = {
    "T", "C", "TH", "CL", "THERAPIST", "CLIENT", "CLINICIAN", "COUNSELOR", "COUNSELLOR",
    "INTERVIEWER", "INTERVIEWEE", "PATIENT", "PARTICIPANT", "SPEAKER", "DOCTOR", "DR",
    "PROVIDER", "PT",
}
_TIMESTAMP = re.compile(
    r"^\s*\[?\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?\]?[ \t]+(?=[^:\r\n]{1,40}:)"
)
# A plausible label: starts with a letter, at most four short words, no sentence punctuation.
_NAME = re.compile(r"^[^\W\d_][\w.'-]*(?: [\w.'-]+){0,3}$")


def _candidate(line: str) -> tuple[str, str] | None:
    """Return (label, text) when the line has a plausible label shape, else None."""
    line = _TIMESTAMP.sub("", line, count=1)
    match = _LABEL.fullmatch(line)
    if not match:
        return None
    label = match.group(1).strip()
    if not label or not _NAME.fullmatch(label):
        return None
    return label, match.group(2)


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
    lines = [line for line in source.split("\n") if line.strip()]
    candidates = [_candidate(line) for line in lines]
    counts: dict[str, int] = {}
    for found in candidates:
        if found:
            key = found[0].casefold()
            counts[key] = counts.get(key, 0) + 1
    sole = len(counts) == 1
    # With no role-style or repeated label to anchor on (e.g. "Pat: ...\nSam: ..."), a name that
    # appears once is still a speaker if it is one of the first two labels in the file; any later
    # one-off "word:" line stays a continuation. Labels are used as written, never invented.
    anchored = any(k.upper() in _KNOWN or n >= 2 for k, n in counts.items())
    opening = set(list(counts)[:2])

    def accepted(found: tuple[str, str] | None) -> bool:
        if not found:
            return False
        label = found[0]
        if label.upper() in _KNOWN or counts[label.casefold()] >= 2 or sole:
            return True
        return not anchored and label.casefold() in opening

    for line, found in zip(lines, candidates, strict=True):
        if accepted(found):
            label, rest = found
            canonical = label.upper()
            speaker = canonical if canonical in _ROLES else label
            turns.append({
                "id": f"t{len(turns) + 1}",
                "speaker": speaker,
                "role": _ROLES.get(canonical),
                "text": rest.strip(),
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
