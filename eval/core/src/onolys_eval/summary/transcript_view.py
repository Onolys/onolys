"""Transcript projection for the Line view.

Pure. Only the saved TranscriptDoc's turns inside the run's pinned `coded_span`, with
`is_clinician`. No storage pointers, no audio refs, no invented fields. A transcript whose
`sha256` differs from `RunDoc.transcript_sha256` raises `TranscriptChanged` (the API maps it to
409 `transcript_changed`).
"""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from onolys_engine_core.spans import apply_coded_span
from onolys_engine_core.transcript_v1 import TranscriptV1


class TranscriptChanged(Exception):
    """The stored transcript no longer matches the run's `transcript_sha256`."""


@dataclass(frozen=True)
class TurnView:
    id: str
    speaker: str
    is_clinician: bool
    text: str
    start_ms: int | None
    end_ms: int | None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "speaker": self.speaker, "is_clinician": self.is_clinician,
                "text": self.text, "start_ms": self.start_ms, "end_ms": self.end_ms}


def project_transcript(run_doc: Mapping[str, Any], transcript_doc: Mapping[str, Any]
                       ) -> tuple[TurnView, ...]:
    if transcript_doc.get("sha256") != run_doc.get("transcript_sha256"):
        raise TranscriptChanged(run_doc.get("transcript_sha256"))
    transcript = TranscriptV1.model_validate(transcript_doc["transcript"])
    chosen = apply_coded_span(transcript, run_doc.get("coded_span")).turns
    clinician = run_doc.get("clinician_speaker")
    return tuple(TurnView(id=t.id, speaker=t.speaker, is_clinician=t.speaker == clinician,
                          text=t.text, start_ms=t.start_ms, end_ms=t.end_ms)
                 for t in chosen)
