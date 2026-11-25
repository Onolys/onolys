"""Transcript projection for the Line view (SP06 R4).

Pure. Only the saved TranscriptDoc's turns inside the run's pinned `coded_span`, with
`is_clinician`. No storage pointers, no audio refs, no invented fields. A transcript whose
`sha256` differs from `RunDoc.transcript_sha256` raises `TranscriptChanged` (the API maps it to
409 `transcript_changed`).
"""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


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
    turns = transcript_doc["transcript"]["turns"]
    span = run_doc.get("coded_span")
    if span is None:
        chosen = list(turns)
    elif "start_turn" in span:  # zero-based, half-open [start_turn, end_turn)
        chosen = list(turns[span["start_turn"]:span["end_turn"]])
    else:  # time span: turns that start inside [start_ms, end_ms)
        chosen = [t for t in turns
                  if t.get("start_ms") is not None
                  and span["start_ms"] <= t["start_ms"] < span["end_ms"]]
    clinician = run_doc.get("clinician_speaker")
    return tuple(TurnView(id=t["id"], speaker=t["speaker"], is_clinician=t["speaker"] == clinician,
                          text=t["text"], start_ms=t.get("start_ms"), end_ms=t.get("end_ms"))
                 for t in chosen)
