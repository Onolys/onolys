"""Settings from the SP06 env-var interface (see ../.env.example)."""

import os
from collections.abc import Mapping
from dataclasses import dataclass

from onolys_engine_core.errors import ConfigError

ENVS = ("local", "test", "staging", "prod")
SERVICE_MODES = ("api", "worker", "combined", "voice")
ADAPTER_KINDS = ("stub", "real")
AUTH_MODES = ("fake", "idp")
LOCAL_ENVS = ("local", "test")


def _int(e: Mapping[str, str], name: str, default: int) -> int:
    try:
        return int(e.get(name, default))
    except ValueError:
        raise ConfigError(f"{name} must be an integer") from None


def _float(e: Mapping[str, str], name: str, default: float) -> float:
    try:
        return float(e.get(name, default))
    except ValueError:
        raise ConfigError(f"{name} must be a number") from None


def _bool(e: Mapping[str, str], name: str, default: bool) -> bool:
    raw = e.get(name)
    if raw is None:
        return default
    if raw.strip().lower() in ("1", "true", "yes", "on"):
        return True
    if raw.strip().lower() in ("0", "false", "no", "off", ""):
        return False
    raise ConfigError(f"{name} must be true or false")


@dataclass(frozen=True)
class Settings:
    env: str = "test"
    service_mode: str = "combined"
    auth_mode: str = "fake"
    adapters: str = "stub"
    gcp_project: str = ""
    region: str = ""
    firestore_database: str = "(default)"
    auth_project: str = ""
    audio_bucket: str = ""
    cors_origins: tuple[str, ...] = ()
    eval_cap_day: int = 10
    ai_cap_day: int = 5
    max_active_runs: int = 1
    tasks_queue: str = ""
    tasks_sa: str = ""
    worker_url: str = ""
    routes_file: str = ""
    default_preset: str = ""
    prod_engine: str = "miti"
    # Presets beyond the default that users may pick (FX43): empty in prod unless the owner opts in
    extra_presets: tuple[str, ...] = ()
    git_sha: str = "dev"
    stt_cap_factor: float = 3.0  # STT poll cap = factor x audio duration ...
    stt_cap_min_s: float = 300.0  # ... but never under this
    stt_time_limit_s: float = 1200.0  # ... and never over this (the old flat limit)
    voice_url: str = "ws://localhost:8081"  # voice relay base (no path); `wss://` outside local
    ai_max_seconds: int = 600  # hard cap on one interview
    ai_warn_seconds: int = 480  # client warns the user at this elapsed time
    ai_min_seconds: int = 300  # shortest recording worth sending to the audit
    ai_tolerance_seconds: int = 30
    ai_abandon_count_seconds: int = 30  # ended/abandoned under this: the usage unit is refunded
    ai_refunds_per_day: int = 3  # at most this many such refunds per user per UTC day (A9)
    ai_reconnect_seconds: int = 60  # relay waits this long for a dropped client
    ai_mic_gate: bool = False
    # relay abuse caps (A21): one client audio frame, bytes per second of audio (PCM16 16 kHz is
    # 32000 B/s, so the default tolerates 4x real time for buffered bursts), and how many times
    # one interview may (re)connect before it is ended.
    ai_max_frame_bytes: int = 65536
    ai_max_audio_bytes_per_s: int = 128000
    ai_max_connects: int = 30
    uid_hmac_key: str = ""  # keys the `uid_hash` log field (Secret Manager `uid-hmac-key-{env}`)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        e = os.environ if environ is None else environ
        env = e.get("ENV")
        if not env:  # never default to local: that means fake auth and no /tasks OIDC (A8)
            raise ConfigError(f"ENV is required ({'|'.join(ENVS)})")
        local = env in LOCAL_ENVS
        if local and e.get("K_SERVICE"):  # Cloud Run sets K_SERVICE
            raise ConfigError("ENV=local|test is not allowed on Cloud Run (K_SERVICE is set)")
        active_raw = e.get("MAX_ACTIVE_RUNS", str(cls.max_active_runs))
        try:
            max_active = int(active_raw)
        except ValueError:
            raise ConfigError("MAX_ACTIVE_RUNS must be an integer") from None
        s = cls(
            env=env,
            stt_cap_factor=_float(e, "STT_CAP_FACTOR", cls.stt_cap_factor),
            stt_cap_min_s=_float(e, "STT_CAP_MIN_S", cls.stt_cap_min_s),
            stt_time_limit_s=_float(e, "STT_TIME_LIMIT_S", cls.stt_time_limit_s),
            service_mode=e.get("SERVICE_MODE", "combined" if local else "api"),
            auth_mode=e.get("AUTH_MODE", "fake" if local else "idp"),
            adapters=e.get("ADAPTERS", "stub" if local else "real"),
            gcp_project=e.get("GCP_PROJECT", ""),
            region=e.get("REGION", ""),
            firestore_database=e.get("FIRESTORE_DATABASE", "(default)"),
            auth_project=e.get("AUTH_PROJECT", ""),
            audio_bucket=e.get("AUDIO_BUCKET", ""),
            cors_origins=tuple(
                o.strip() for o in e.get("CORS_ORIGINS", "").split(",") if o.strip()
            ),
            eval_cap_day=_int(e, "EVAL_CAP_DAY", cls.eval_cap_day),
            ai_cap_day=_int(e, "AI_CAP_DAY", cls.ai_cap_day),
            max_active_runs=max_active,
            tasks_queue=e.get("TASKS_QUEUE", ""),
            tasks_sa=e.get("TASKS_SA", ""),
            worker_url=e.get("WORKER_URL", ""),
            routes_file=e.get("ROUTES_FILE", ""),
            default_preset=e.get("DEFAULT_PRESET", ""),
            prod_engine=e.get("PROD_ENGINE", cls.prod_engine),
            extra_presets=tuple(
                p.strip() for p in e.get("ENABLED_EXTRA_PRESETS", "").split(",") if p.strip()
            ),
            git_sha=e.get("GIT_SHA", "dev"),
            voice_url=e.get("VOICE_URL", cls.voice_url if local else ""),
            ai_max_seconds=_int(e, "AI_MAX_SECONDS", cls.ai_max_seconds),
            ai_warn_seconds=_int(e, "AI_WARN_SECONDS", cls.ai_warn_seconds),
            ai_min_seconds=_int(e, "AI_MIN_SECONDS", cls.ai_min_seconds),
            ai_tolerance_seconds=_int(e, "AI_TOLERANCE_SECONDS", cls.ai_tolerance_seconds),
            ai_abandon_count_seconds=_int(
                e, "AI_ABANDON_COUNT_SECONDS", cls.ai_abandon_count_seconds
            ),
            ai_refunds_per_day=_int(e, "AI_REFUNDS_PER_DAY", cls.ai_refunds_per_day),
            ai_reconnect_seconds=_int(e, "AI_RECONNECT_SECONDS", cls.ai_reconnect_seconds),
            ai_mic_gate=_bool(e, "AI_MIC_GATE", cls.ai_mic_gate),
            ai_max_frame_bytes=_int(e, "AI_MAX_FRAME_BYTES", cls.ai_max_frame_bytes),
            ai_max_audio_bytes_per_s=_int(
                e, "AI_MAX_AUDIO_BYTES_PER_S", cls.ai_max_audio_bytes_per_s
            ),
            ai_max_connects=_int(e, "AI_MAX_CONNECTS", cls.ai_max_connects),
            uid_hmac_key=e.get("UID_HMAC_KEY", ""),
        )
        s.validate()
        return s

    def validate(self) -> None:
        for name, value, allowed in (
            ("ENV", self.env, ENVS),
            ("SERVICE_MODE", self.service_mode, SERVICE_MODES),
            ("ADAPTERS", self.adapters, ADAPTER_KINDS),
            ("AUTH_MODE", self.auth_mode, AUTH_MODES),
        ):
            if value not in allowed:
                raise ConfigError(f"{name} must be one of {', '.join(allowed)}")
        if self.auth_mode == "fake" and self.env not in LOCAL_ENVS:
            raise ConfigError("AUTH_MODE=fake is only allowed when ENV is local or test")
        if self.env not in LOCAL_ENVS and not self.uid_hmac_key:
            raise ConfigError("UID_HMAC_KEY is required when ENV is staging or prod")
        for kind, day in (("EVAL", self.eval_cap_day), ("AI", self.ai_cap_day)):
            if day < 0:
                raise ConfigError(f"{kind}_CAP_DAY must be >= 0")
        if self.max_active_runs < 0:
            raise ConfigError("MAX_ACTIVE_RUNS must be >= 0")
        if self.stt_cap_factor <= 0 or self.stt_cap_min_s <= 0:
            raise ConfigError("STT_CAP_FACTOR and STT_CAP_MIN_S must be > 0")
        if self.stt_time_limit_s < self.stt_cap_min_s:
            raise ConfigError("STT_TIME_LIMIT_S must be >= STT_CAP_MIN_S")
        for name, v in (
            ("AI_MAX_SECONDS", self.ai_max_seconds),
            ("AI_WARN_SECONDS", self.ai_warn_seconds),
            ("AI_MIN_SECONDS", self.ai_min_seconds),
            ("AI_TOLERANCE_SECONDS", self.ai_tolerance_seconds),
            ("AI_ABANDON_COUNT_SECONDS", self.ai_abandon_count_seconds),
            ("AI_REFUNDS_PER_DAY", self.ai_refunds_per_day),
            ("AI_RECONNECT_SECONDS", self.ai_reconnect_seconds),
        ):
            if v < 0:
                raise ConfigError(f"{name} must be >= 0")
        for name, v in (
            ("AI_MAX_FRAME_BYTES", self.ai_max_frame_bytes),
            ("AI_MAX_AUDIO_BYTES_PER_S", self.ai_max_audio_bytes_per_s),
            ("AI_MAX_CONNECTS", self.ai_max_connects),
        ):
            if v <= 0:
                raise ConfigError(f"{name} must be > 0")
        if self.ai_max_seconds <= 0 or self.ai_warn_seconds >= self.ai_max_seconds:
            raise ConfigError("AI_WARN_SECONDS must be < AI_MAX_SECONDS (> 0)")
        if self.voice_url:
            scheme = ("ws://", "wss://") if self.env in LOCAL_ENVS else ("wss://",)
            if not self.voice_url.startswith(scheme) or self.voice_url.endswith("/"):
                raise ConfigError("VOICE_URL must be a wss:// base URL without a trailing slash")
