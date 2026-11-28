"""The only seam to the engines: `Stt`, `Evaluation`, and `Voice`.

`Stt` is the provider-neutral engine `SttAdapter` (`start`/`poll`); `Evaluation` wraps
the configured engine (one call runs the whole `running` phase, asyncio inside). There are no
per-stage adapters. Fake implementations live in `fake.py`; real ones live in `real.py`.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from onolys_engine_core.context import RunContext
from onolys_engine_core.errors import OnolysError
from onolys_engine_core.transcript import Transcript
from onolys_miti.run import ProgressCb, Stage, StageStatus
from pydantic import BaseModel, Field

from onolys_api.transcription import AudioRef, SttCompletion, SttParams
from onolys_api.voice import VoiceParams, VoiceSession

__all__ = [
    "AuthAccount",
    "AuthLinks",
    "AdapterError",
    "EmailSender",
    "Evaluation",
    "EvaluationOutput",
    "ProgressCb",
    "Stage",
    "StageStatus",
    "Stt",
    "Voice",
]


class AdapterError(OnolysError):
    """An engine call failed. `code` is a stable machine code; the caller maps it to a public
    error code (the real mapping is in `error_map.py`). Never carries transcript or rating text."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class EvaluationOutput(BaseModel):
    """The evaluation engine's `EvaluationOutput`: the report JSON (incl. its `run_info`) plus
    run artifacts."""

    report: dict[str, Any]
    run_info: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)  # code, tips


class Stt(Protocol):
    async def start(self, audio: AudioRef, params: SttParams) -> str:
        """Begin transcription once; return an opaque, JSON-serialisable handle."""
        ...

    async def poll(self, handle: str) -> SttCompletion | None:
        """Return the completion, or None while still running. Never re-submits."""
        ...


class Evaluation(Protocol):
    """Evaluation seam. Trusted implementations may declare class-level
    ``validates_output = True`` only when their public run uses run_validated;
    the job bridges all other implementations through the shared wrapper.
    """

    async def run(
        self,
        ctx: RunContext,
        transcript: Transcript,
        speaker_map: dict[str, str],
        params: dict[str, Any],
        progress_cb: ProgressCb | None = None,
    ) -> EvaluationOutput:
        """`speaker_map = {"subject": <transcript speaker label>}`. `params` =
        {change_goal, seed, language, n_runs, preset, code_version}.
        Raises AdapterError when the run fails (coding failure)."""
        ...


class Voice(Protocol):
    """Realtime voice seam: the relay opens one provider session per connection.
    `params.provider` picks the core adapter; nothing else in the API names a provider."""

    async def open(self, params: VoiceParams) -> VoiceSession: ...


class EmailSender(Protocol):
    """Transactional email delivery; failures contain safe codes only."""

    def send(
        self, to: str, subject: str, html: str, text: str, idempotency_key: str | None = None
    ) -> None: ...


@dataclass(frozen=True)
class AuthAccount:
    email: str
    email_verified: bool = False
    disabled: bool = False


class AuthLinks(Protocol):
    """Trusted account lookup and action codes; SDK links never leave this boundary."""

    def get_user(self, uid: str) -> AuthAccount: ...
    def verification(self, uid: str) -> str: ...
    def password_reset(self, email: str) -> str | None: ...
