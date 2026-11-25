"""Settings from the SP06 env-var interface (see ../.env.example)."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from onolys_engine_core.errors import ConfigError

ENVS = ("local", "test", "staging", "prod")
SERVICE_MODES = ("api", "worker", "combined", "voice")
ADAPTER_KINDS = ("stub", "real")
AUTH_MODES = ("fake", "idp")
LOCAL_ENVS = ("local", "test")
# Keep in sync with the web action handler and docs/reference/web-email-actions.md.
APP_HOSTS = frozenset({
    "app.onolys.com", "onolys-app.web.app", "onolys-app-staging.web.app",
    "onolys-staging-app.web.app",
})


def _validate_app_base_url(value: str, env: str) -> None:
    try:
        parts = urlsplit(value)
        port = parts.port  # malformed or out-of-range ports raise ValueError
        origin_only = (
            bool(value)
            and not any(c.isspace() or ord(c) < 32 or c == "\\" for c in value)
            and parts.username is None
            and parts.password is None
            and not parts.path
            and "?" not in value
            and "#" not in value
        )
        allowed = (
            parts.scheme == "https" and parts.hostname in APP_HOSTS and port in (None, 443)
        ) or (env in LOCAL_ENVS and parts.scheme == "http" and parts.hostname == "localhost")
        if origin_only and allowed:
            return
    except ValueError:
        pass
    raise ConfigError(
        "APP_BASE_URL must be an HTTPS origin on a known app host "
        "(http://localhost:<port> is allowed for local or test)"
    )


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


def _strict_bool(e: Mapping[str, str], name: str, default: bool) -> bool:
    raw = e.get(name)
    if raw is None:
        return default
    if raw == "true":
        return True
    if raw == "false":
        return False
    raise ConfigError(f"{name} must be true or false")


# user-visible retries of a transient failure (03-failure-policy R4): the one source, no env
MAX_SESSION_RETRIES = 3


@dataclass(frozen=True)
class Settings:
    env: str = "test"
    service_mode: str = "combined"
    pr_preview: bool = False  # staging-only combined mode with stub providers
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
    eval_mode: bool = False  # EVAL_MODE: the one switch for everything eval (04-eval-run-path R6)
    # Presets beyond the default that users may pick (FX43): empty in prod unless the owner opts in
    extra_presets: tuple[str, ...] = ()
    git_sha: str = "dev"
    revision: str = ""  # Cloud Run `K_REVISION`
    stt_cap_factor: float = 3.0  # STT poll cap = factor x audio duration ...
    stt_cap_min_s: float = 300.0  # ... but never under this
    stt_time_limit_s: float = 1200.0  # ... and never over this (the old flat limit)
    voice_url: str = "ws://localhost:8081"  # voice relay base (no path); `wss://` outside local
    ai_max_seconds: int = 600  # hard cap on one interview
    ai_warn_seconds: int = 480  # client warns the user at this elapsed time
    ai_min_seconds: int = 300  # shortest recording worth sending to the audit
    ai_tolerance_seconds: int = 30  # only the interview ceiling: AI_MAX_SECONDS + this
    # relay/upload mismatch: tolerated up to max(this, pct of relay)
    ai_mismatch_min_seconds: int = 60
    ai_mismatch_pct: int = 15
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
    # Explicit construction supports local tests; from_env leaves it empty when unset (emails 503).
    app_base_url: str = "http://localhost:5173"
    email_from: str = "Onolys <no-reply@onolys.com>"
    resend_api_key: str = ""
    client_ip_trusted_hops: int = 1  # X-Forwarded-For hops to skip from the right (infra.md)
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
            pr_preview=_bool(e, "PR_PREVIEW", cls.pr_preview),
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
            eval_mode=_strict_bool(e, "EVAL_MODE", cls.eval_mode),
            extra_presets=tuple(
                p.strip() for p in e.get("ENABLED_EXTRA_PRESETS", "").split(",") if p.strip()
            ),
            git_sha=e.get("GIT_SHA", "dev"),
            revision=e.get("K_REVISION", ""),
            voice_url=e.get("VOICE_URL", cls.voice_url if local else ""),
            ai_max_seconds=_int(e, "AI_MAX_SECONDS", cls.ai_max_seconds),
            ai_warn_seconds=_int(e, "AI_WARN_SECONDS", cls.ai_warn_seconds),
            ai_min_seconds=_int(e, "AI_MIN_SECONDS", cls.ai_min_seconds),
            ai_tolerance_seconds=_int(e, "AI_TOLERANCE_SECONDS", cls.ai_tolerance_seconds),
            ai_mismatch_min_seconds=_int(
                e, "AI_MISMATCH_MIN_SECONDS", cls.ai_mismatch_min_seconds
            ),
            ai_mismatch_pct=_int(e, "AI_MISMATCH_PCT", cls.ai_mismatch_pct),
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
            app_base_url=e.get("APP_BASE_URL", ""),
            client_ip_trusted_hops=_int(e, "CLIENT_IP_TRUSTED_HOPS", cls.client_ip_trusted_hops),
            email_from=e.get("EMAIL_FROM", cls.email_from),
            resend_api_key=e.get("RESEND_API_KEY", ""),
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
        if self.pr_preview and not (
            self.env == "staging"
            and self.service_mode == "combined"
            and self.adapters == "stub"
            and self.firestore_database == "staging"
        ):
            raise ConfigError(
                "PR_PREVIEW requires ENV=staging, SERVICE_MODE=combined, "
                "ADAPTERS=stub and FIRESTORE_DATABASE=staging"
            )
        if self.auth_mode == "fake" and self.env not in LOCAL_ENVS:
            raise ConfigError("AUTH_MODE=fake is only allowed when ENV is local or test")
        if self.env not in LOCAL_ENVS and not self.uid_hmac_key:
            raise ConfigError("UID_HMAC_KEY is required when ENV is staging or prod")
        if self.client_ip_trusted_hops < 0:
            raise ConfigError("CLIENT_IP_TRUSTED_HOPS must be >= 0")
        if self.app_base_url:  # unset is allowed: auth-email endpoints then answer 503
            _validate_app_base_url(self.app_base_url, self.env)
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
            ("AI_MISMATCH_MIN_SECONDS", self.ai_mismatch_min_seconds),
            ("AI_MISMATCH_PCT", self.ai_mismatch_pct),
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

        if self.env not in LOCAL_ENVS:
            if self.service_mode == "combined" and not self.pr_preview:
                raise ConfigError(
                    "SERVICE_MODE=combined requires local/test or an explicit staging PR_PREVIEW"
                )
            if self.adapters == "real" or self.pr_preview:
                required = ["GCP_PROJECT", "REGION", "AUTH_PROJECT"]
                if self.service_mode in ("api", "worker"):
                    required += ["AUDIO_BUCKET", "TASKS_QUEUE", "TASKS_SA", "WORKER_URL"]
                if self.service_mode == "api" or self.pr_preview:
                    required += ["VOICE_URL"]
                if self.pr_preview:
                    required += ["AUDIO_BUCKET"]
                for name in required:
                    if not getattr(self, name.lower()).strip():
                        raise ConfigError(f"{name} is required for deployed {self.service_mode}")
