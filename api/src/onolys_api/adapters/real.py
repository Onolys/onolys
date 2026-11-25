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
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import parse_qs, urlsplit

from onolys_engine_core.context import RunContext
from onolys_engine_core.errors import ConfigError
from onolys_engine_core.llm import LiteLLMClient, LLMConfig, MetricsCollector
from onolys_engine_core.llm.routes import resolve_preset
from onolys_engine_core.registry import EngineRegistry
from onolys_engine_core.transcript import Transcript
from onolys_engine_core.validated_run import run_validated
from onolys_miti.stt import AudioRef, SttAdapter, SttCompletion, SttParams
from onolys_miti.stt.fixture import FixtureStt
from onolys_miti.stt.google_chirp import GoogleChirp3
from onolys_miti.voice import VoiceAdapter, VoiceParams, VoiceSession
from onolys_miti.voice.fixture import FixtureVoice
from onolys_miti.voice.gemini_live_vertex import GeminiLiveVertex

from onolys_api.adapters.base import AdapterError, AuthAccount, EvaluationOutput, ProgressCb
from onolys_api.config import Settings
from onolys_api.engines import build_engine_registry, override_routes, resolve_engine

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
    "config",
)


def _llm_from_routes(routes: dict) -> Any:
    return LiteLLMClient(LLMConfig(routes=routes))


class RealEvaluation:
    """Implements `adapters.base.Evaluation` through the configured engine registry."""

    # Trusted adapter contract: the job must not validate this result a second time.
    validates_output = True

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
        engine_id = override = None
        if self._settings.eval_mode:  # engine/route_override exist only for eval runs
            engine_id, override = params.get("engine"), params.get("route_override")
        if engine_id:
            engine = resolve_engine(self._settings, engine_id, self._registry)
        else:
            engine = self._registry.get(self._settings.prod_engine)
        routes, _ = resolve_preset(params.get("preset"))  # unknown preset: InputError
        if override:
            routes = override_routes(self._settings, routes, override)
        deadline = time.monotonic() + RUN_DEADLINE_S
        if ctx.deadline is not None:
            deadline = min(deadline, ctx.deadline)
        if ctx.metrics is None:
            ctx.metrics = MetricsCollector()
        rctx = RunContext(
            llm=self._llm_factory(routes),
            metrics=ctx.metrics,
            request_id=ctx.request_id,
            deadline=deadline,
        )
        engine_params = {
            k: params.get(k)
            for k in _ENGINE_PARAMS
            if k not in ("stt_run", "config") or k in params
        }
        if engine_id and engine_id.startswith("oneshot:"):
            engine_params["config"] = engine_id.split(":", 1)[1]
        engine_params["speaker_map"] = dict(speaker_map)
        out = await run_validated(engine, rctx, transcript, engine_params, progress_cb)
        payload = out.model_dump(mode="json")
        return EvaluationOutput(
            report=payload["output"], artifacts=payload["artifacts"] or {},
            run_info=payload["run_info"],
        )


class UnconfiguredEmailSender:
    def send(self, to: str, subject: str, html: str, text: str) -> None:
        raise AdapterError("email_unconfigured")


class ResendEmailSender:
    """One bounded request, without retries or provider error text."""

    def __init__(self, api_key: str, sender: str) -> None:
        self._api_key = api_key
        self._sender = sender

    def send(self, to: str, subject: str, html: str, text: str) -> None:
        import requests

        try:
            response = requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "from": self._sender,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                    "text": text,
                },
                timeout=5,
                allow_redirects=False,
            )
        except requests.RequestException:
            raise AdapterError("email_send_failed") from None
        if not 200 <= response.status_code < 300:
            error = AdapterError("email_send_failed")
            error.provider_status = response.status_code
            raise error


_FIREBASE_INIT_LOCK = threading.Lock()


class FirebaseAuthLinks:
    """Lazy Admin SDK access. Only action codes and trusted account data escape."""

    def __init__(self, project: str, app_base_url: str, *, auth_sdk=None) -> None:
        self._project = project
        self._base_url = app_base_url
        self._sdk = auth_sdk
        self._app = None

    def _auth(self):
        if self._sdk is not None:
            return self._sdk
        import firebase_admin
        from firebase_admin import auth

        name = f"onolys-auth-email-{self._project}"
        with _FIREBASE_INIT_LOCK:
            try:
                self._app = firebase_admin.get_app(name)
            except ValueError:
                self._app = firebase_admin.initialize_app(
                    options={"projectId": self._project}, name=name
                )
        self._sdk = auth
        return auth

    def get_user(self, uid: str) -> AuthAccount:
        try:
            sdk = self._auth()
            user = sdk.get_user(uid, **self._app_kwargs())
            if not isinstance(user.email, str) or not user.email:
                raise AdapterError("auth_links_failed")
            return AuthAccount(user.email, user.email_verified, user.disabled)
        except Exception:
            raise AdapterError("auth_links_failed") from None

    def _app_kwargs(self) -> dict:
        return {"app": self._app} if self._app is not None else {}

    def _generate(self, email: str, kind: str) -> str | None:
        try:
            sdk = self._auth()
            settings = sdk.ActionCodeSettings(url=self._base_url)
            generate = (
                sdk.generate_email_verification_link
                if kind == "verify"
                else sdk.generate_password_reset_link
            )
            link = generate(email, action_code_settings=settings, **self._app_kwargs())
            codes = parse_qs(urlsplit(link).query).get("oobCode", [])
            if len(codes) != 1 or not codes[0]:
                raise AdapterError("auth_links_failed")
            return codes[0]
        except Exception as exc:
            ineligible = tuple(  # no such account / disabled: nothing to send, not an error
                c for n in ("UserNotFoundError", "EmailNotFoundError", "UserDisabledError")
                if isinstance(c := getattr(self._sdk, n, None), type)
            )
            if kind == "reset" and ineligible and isinstance(exc, ineligible):
                return None
            raise AdapterError("auth_links_failed") from None

    def verification(self, uid: str) -> str:
        user = self.get_user(uid)
        code = self._generate(user.email, "verify")
        assert code is not None
        return code

    def password_reset(self, email: str) -> str | None:
        return self._generate(email, "reset")
