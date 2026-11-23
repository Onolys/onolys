"""Real `Stt` adapter (SP09 R1, D5): a registry over the SP01 core STT adapters.

The provider is data: the worker passes the session's stored `stt.provider` in `SttParams`, and
this module looks the core adapter up by that key. There is no `if provider == ...` in worker
code. A new STT provider is one core adapter plus one `DEFAULT_REGISTRY` line (and its
`stt_providers.yaml` entry).

`poll(handle)` carries no provider, so `start` wraps the core handle as
`{"provider", "handle"}` JSON; `stt_operation` stores that string and `poll` routes on it.
The completion carries transcript.v1 and separate STT provenance unchanged.

`RealEvaluation` calls the configured registry engine once; it names no model
or provider: routes come from the run's preset (`resolve_preset`, unknown preset -> `InputError`).
It forwards the caller span and seed, without a pack or rating card.

An unknown provider raises core `ConfigError` (an `OnolysError`): `error_map.to_public` maps it
to `internal_error`, not retryable, and the worker logs the class, never the message.
"""

import json
import time
from collections.abc import Callable, Mapping
from typing import Any

from onolys_engine_core.context import RunContext
from onolys_engine_core.errors import ConfigError
from onolys_engine_core.llm import LiteLLMClient, LLMConfig, MetricsCollector
from onolys_engine_core.llm.routes import resolve_preset
from onolys_engine_core.registry import EngineRegistry
from onolys_engine_core.transcript import Transcript
from onolys_miti.stt import AudioRef, SttAdapter, SttCompletion, SttParams
from onolys_miti.stt.fixture import FixtureStt
from onolys_miti.stt.google_chirp import GoogleChirp3
from onolys_miti.voice import VoiceAdapter, VoiceParams, VoiceSession
from onolys_miti.voice.fixture import FixtureVoice
from onolys_miti.voice.gemini_live_vertex import GeminiLiveVertex

from onolys_api.adapters.base import EvaluationOutput, ProgressCb
from onolys_api.config import Settings
from onolys_api.engines import build_engine_registry

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
_ENGINE_PARAMS = (
    "change_goal", "seed", "language", "n_runs", "preset", "code_version", "stt_run", "coded_span",
)


def _llm_from_routes(routes: dict) -> Any:
    return LiteLLMClient(LLMConfig(routes=routes))


class RealEvaluation:
    """Implements `adapters.base.Evaluation` through the configured engine registry."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        registry: EngineRegistry | None = None,
        llm_factory: Callable[[dict], Any] = _llm_from_routes,
    ) -> None:
        self._settings = settings or Settings()
        self._registry = registry if registry is not None else build_engine_registry(self._settings)
        self._llm_factory = llm_factory

    async def run(
        self,
        ctx: RunContext,
        transcript: Transcript,
        speaker_map: dict[str, str],
        params: dict[str, Any],
        progress_cb: ProgressCb | None = None,
    ) -> EvaluationOutput:
        engine = self._registry.get(self._settings.prod_engine)
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
        engine_params["speaker_map"] = dict(speaker_map)
        out = await engine.run(rctx, transcript, engine_params, progress_cb)
        payload = out.model_dump(mode="json")
        return EvaluationOutput(report=payload["output"], artifacts=payload["artifacts"] or {})
