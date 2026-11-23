"""Real `Stt` adapter (SP09 R1, D5): a registry over the SP01 core STT adapters.

The provider is data: the worker passes the session's stored `stt.provider` in `SttParams`, and
this module looks the core adapter up by that key. There is no `if provider == ...` in worker
code. A new STT provider is one core adapter plus one `DEFAULT_REGISTRY` line (and its
`stt_providers.yaml` entry).

`poll(handle)` carries no provider, so `start` wraps the core handle as
`{"provider", "handle"}` JSON; `stt_operation` stores that string and `poll` routes on it.
The completion carries transcript.v1 and separate STT provenance unchanged.

`RealEvaluation` (SP09 R2, D5) is the single call into `onolys_miti.run_miti`; it names no model
or provider: routes come from the run's preset (`resolve_preset`, unknown preset -> `InputError`).
It passes no pack, rating or coded span; `seed` (the session id) lets the engine pick the span.

An unknown provider raises core `ConfigError` (an `OnolysError`): `error_map.to_public` maps it
to `internal_error`, not retryable, and the worker logs the class, never the message.
"""

import json
import time
from collections.abc import Callable, Mapping
from typing import Any

from onolys_miti.context import RunContext
from onolys_miti.errors import ConfigError
from onolys_miti.llm import LiteLLMClient, LLMConfig, MetricsCollector
from onolys_miti.llm.routes import resolve_preset
from onolys_miti.stt import AudioRef, SttAdapter, SttCompletion, SttParams
from onolys_miti.stt.fixture import FixtureStt
from onolys_miti.stt.google_chirp import GoogleChirp3
from onolys_miti.transcript import Transcript
from onolys_miti.voice import VoiceAdapter, VoiceParams, VoiceSession
from onolys_miti.voice.fixture import FixtureVoice
from onolys_miti.voice.gemini_live_vertex import GeminiLiveVertex

from onolys_api.adapters.base import EvaluationOutput, ProgressCb

SttFactory = Callable[[], SttAdapter]

# provider key (stored on the session from stt_providers.yaml) -> core adapter factory.
# `google` is the value the packaged stt_providers.yaml writes for its Chirp 3 entry.
DEFAULT_REGISTRY: dict[str, SttFactory] = {
    "google_chirp": GoogleChirp3,
    "google": GoogleChirp3,
    "fixture": lambda: FixtureStt({}),
}


class RealStt:
    """Implements `adapters.base.Stt`."""

    def __init__(self, registry: Mapping[str, SttFactory] | None = None) -> None:
        self._registry = dict(DEFAULT_REGISTRY if registry is None else registry)
        self._cache: dict[str, SttAdapter] = {}

    def _adapter(self, provider: str) -> SttAdapter:
        if provider not in self._cache:
            factory = self._registry.get(provider)
            if factory is None:
                raise ConfigError("unknown STT provider")
            self._cache[provider] = factory()
        return self._cache[provider]

    async def start(self, audio: AudioRef, params: SttParams) -> str:
        handle = await self._adapter(params.provider).start(audio, params)
        return json.dumps({"provider": params.provider, "handle": handle})

    async def poll(self, handle: str) -> SttCompletion | None:
        try:
            wrapped = json.loads(handle)
            provider, inner = wrapped["provider"], wrapped["handle"]
        except (ValueError, KeyError, TypeError):
            raise ConfigError("bad STT handle") from None
        return await self._adapter(provider).poll(inner)


VoiceFactory = Callable[[], VoiceAdapter]

# `provider` value of voice_providers.yaml -> core voice adapter factory.
VOICE_REGISTRY: dict[str, VoiceFactory] = {
    "gemini_live_vertex": GeminiLiveVertex,
    "fixture": FixtureVoice,
}


class RealVoice:
    """Implements `adapters.base.Voice`: a registry over the core voice adapters."""

    def __init__(self, registry: Mapping[str, VoiceFactory] | None = None) -> None:
        self._registry = dict(VOICE_REGISTRY if registry is None else registry)
        self._cache: dict[str, VoiceAdapter] = {}

    async def open(self, params: VoiceParams) -> VoiceSession:
        if params.provider not in self._cache:
            factory = self._registry.get(params.provider)
            if factory is None:
                raise ConfigError("unknown voice provider")
            self._cache[params.provider] = factory()
        return await self._cache[params.provider].open(params)


RUN_DEADLINE_S = 8 * 60  # the whole evaluation; a shorter ctx.deadline (task budget) wins
_ENGINE_PARAMS = ("change_goal", "seed", "language", "n_runs", "preset", "code_version", "stt_run")


def _llm_from_routes(routes: dict) -> Any:
    return LiteLLMClient(LLMConfig(routes=routes))


class RealEvaluation:
    """Implements `adapters.base.Evaluation`: one `run_miti` call, nothing else."""

    def __init__(
        self,
        run_miti: Callable[..., Any] | None = None,
        llm_factory: Callable[[dict], Any] = _llm_from_routes,
    ) -> None:
        self._run_miti = run_miti
        self._llm_factory = llm_factory

    async def run(
        self,
        ctx: RunContext,
        transcript: Transcript,
        speaker_map: dict[str, str],
        params: dict[str, Any],
        progress_cb: ProgressCb | None = None,
    ) -> EvaluationOutput:
        run_miti = self._run_miti
        if run_miti is None:
            from onolys_miti import run_miti
        routes, _ = resolve_preset(params.get("preset"))  # unknown preset: InputError
        deadline = time.monotonic() + RUN_DEADLINE_S
        if ctx.deadline is not None:
            deadline = min(deadline, ctx.deadline)
        rctx = RunContext(
            llm=self._llm_factory(routes),
            metrics=MetricsCollector(),
            request_id=ctx.request_id,
            deadline=deadline,
        )
        engine_params = {k: params.get(k) for k in _ENGINE_PARAMS if k != "stt_run" or k in params}
        out = await run_miti(rctx, transcript, speaker_map, engine_params, progress_cb)
        return EvaluationOutput(
            report=json.loads(out.report.model_dump_json()),
            artifacts=json.loads(out.artifacts.model_dump_json()),
        )
