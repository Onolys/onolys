"""The only seam to the engines (PRD R6, D2, D20): `Stt`, `Evaluation`, and (SP10 R3) `Voice`.

`Stt` is the provider-neutral SP01 `SttAdapter` (`start`/`poll`); `Evaluation` wraps
`run_miti` (one call runs the whole `running` phase, asyncio inside). There are no
per-stage adapters. Fake implementations live in `fake.py`; real ones are SP09.
"""

from collections.abc import Callable
from typing import Any, Literal, Protocol

from onolys_miti.context import RunContext
from onolys_miti.errors import OnolysError
from onolys_miti.stt import AudioRef, SttParams
from onolys_miti.transcript import Transcript
from onolys_miti.voice import VoiceParams, VoiceSession
from pydantic import BaseModel, Field

Stage = Literal["paudit", "eaudit", "tips", "compare", "assemble"]
StageStatus = Literal["started", "done", "failed"]
ProgressCb = Callable[[Stage, StageStatus], None]


class AdapterError(OnolysError):
    """An engine call failed. `code` is a stable machine code; the caller maps it to a public
    error code (real mapping: SP09). Never carries transcript or rating text."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class EvaluationOutput(BaseModel):
    """SP03 `EvaluationOutput`: the report JSON (incl. its `run_info`) plus run artifacts."""

    report: dict[str, Any]
    artifacts: dict[str, Any] = Field(default_factory=dict)  # paudit, eaudit, tips


class Stt(Protocol):
    async def start(self, audio: AudioRef, params: SttParams) -> str:
        """Begin transcription once; return an opaque, JSON-serialisable handle."""
        ...

    async def poll(self, handle: str) -> Transcript | None:
        """Return the Transcript, or None while still running. Never re-submits."""
        ...


class Evaluation(Protocol):
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
    """Realtime voice seam (SP10 R3): the relay opens one provider session per connection.
    `params.provider` picks the core adapter; nothing else in the API names a provider."""

    async def open(self, params: VoiceParams) -> VoiceSession: ...
