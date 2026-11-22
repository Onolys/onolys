"""MITI 4.2.1 coding engine.

Public surface for the API: `run_miti` and its types, plus the llm, stt, voice, transcript and
error types the API imports. Everything else is importable from its submodule."""

from onolys_miti.context import RunContext
from onolys_miti.errors import ConfigError, InputError, OnolysError
from onolys_miti.llm import (
    LiteLLMClient,
    LLMConfig,
    LLMError,
    LLMUnavailable,
    MetricsCollector,
    StubClient,
)
from onolys_miti.llm.routes import resolve_preset
from onolys_miti.run import (
    AllRunsFailed,
    Artifacts,
    MitiOutput,
    ProgressCb,
    Stage,
    StageStatus,
    run_miti,
)
from onolys_miti.run_info import RunInfo
from onolys_miti.stt import AudioRef, SttParams, SttRun, Word
from onolys_miti.stt.google_chirp import GoogleChirp3, SttProviderError
from onolys_miti.transcript import Transcript, Turn
from onolys_miti.voice import VoiceParams, VoiceSession

__all__ = [
    "AllRunsFailed",
    "Artifacts",
    "AudioRef",
    "ConfigError",
    "GoogleChirp3",
    "InputError",
    "LLMConfig",
    "LLMError",
    "LLMUnavailable",
    "LiteLLMClient",
    "MetricsCollector",
    "MitiOutput",
    "OnolysError",
    "ProgressCb",
    "RunContext",
    "RunInfo",
    "Stage",
    "StageStatus",
    "StubClient",
    "SttParams",
    "SttProviderError",
    "SttRun",
    "Transcript",
    "Turn",
    "VoiceParams",
    "VoiceSession",
    "Word",
    "resolve_preset",
    "run_miti",
]
