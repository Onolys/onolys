"""Shared transcript names for engine and transport consumers."""

from onolys_engine.transcript_v1 import TranscriptTurnV1, TranscriptV1

Turn = TranscriptTurnV1
Transcript = TranscriptV1

__all__ = ["Transcript", "TranscriptTurnV1", "TranscriptV1", "Turn"]
