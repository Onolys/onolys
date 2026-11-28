"""Provider-neutral STT interface types, upload parsers and the STT adapters.

`SttRun` (the provenance model the report carries) is defined by the engine; re-exported here.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from onolys_engine_core.transcript_v1 import TranscriptV1
from onolys_miti.run_info import SttRun
from pydantic import BaseModel


class SttParams(BaseModel):
    provider: str
    model: str
    language: str = "auto"  # BCP-47 or "auto"
    diarization: bool = True
    speakers_min: int = 2
    speakers_max: int = 2
    options: dict = {}  # provider-only fields
    max_audio_s: float = 1200.0  # longest audio per call (Chirp 3 batch: 20 min)


class AudioRef(BaseModel):
    uri: str
    local_path_fn: Callable[[], Path] | None = None
    mime: str
    duration_ms: int | None = None


class Word(BaseModel):
    text: str
    start_ms: int
    end_ms: int | None  # None when the provider gave no valid end; never guessed
    speaker: str | None = None


class SttCompletion(BaseModel):
    """Completed STT result: portable transcript and separate provider provenance."""

    transcript: TranscriptV1
    run: SttRun


class SttAdapter(Protocol):
    async def start(self, audio: AudioRef, params: SttParams) -> str:
        """Begin transcription; return an opaque, JSON-serialisable handle."""
        ...

    async def poll(self, handle: str) -> SttCompletion | None:
        """Return the completion, or None while still running."""
        ...
