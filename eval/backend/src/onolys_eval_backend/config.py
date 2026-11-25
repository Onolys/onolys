"""Explicit deployment settings; eval always enforces the allowlist."""

from collections.abc import Mapping
from dataclasses import dataclass

from onolys_api.config import Settings
from onolys_engine_core.errors import ConfigError

# Pre-R14 names. The eval backend now uses the api's AUTH_PROJECT / CORS_ORIGINS plus
# EVAL_ALLOWED_EMAILS, and refuses to start if an old name is still set.
REMOVED_ENV = (
    "EVAL_AUTH",
    "EVAL_AUTH_PROJECT",
    "EVAL_CORS_ORIGINS",
)


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required")
    return value


def _positive_int(env: Mapping[str, str], name: str, default: int, *, minimum: int = 1) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer") from None
    if value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}")
    return value


@dataclass(frozen=True)
class EvalConfig:
    auth_project: str
    allowed_emails: frozenset[str]
    environment: str
    project: str
    datasets_bucket: str
    settings: Settings
    tasks_queue: str
    tasks_sa: str
    service_url: str
    task_audience: str
    prod_engine: str
    default_preset: str
    routes_file: str
    firestore_database: str = "staging"
    eval_owner_uid: str = "eval"
    max_per_provider: int = 2
    provider_fail_limit: int = 5
    overload_max_wait_s: int = 300
    internal_retries: int = 1

    @property
    def bucket(self) -> str:
        """Shim for the old unit engine/uploads (removed in 05 Task 10): the api AUDIO_BUCKET.

        EVAL_BUCKET no longer exists; the datasets bucket is `datasets_bucket`.
        """
        return self.settings.audio_bucket or self.datasets_bucket

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "EvalConfig":
        stale = [name for name in REMOVED_ENV if name in env]
        if stale:
            raise ConfigError(f"Removed settings, use AUTH_PROJECT/CORS_ORIGINS: {sorted(stale)}")
        if env.get("AUTH_MODE", "idp").strip().lower() != "idp":
            raise ConfigError("Eval requires AUTH_MODE=idp in every environment")
        emails = frozenset(
            e.strip().lower() for e in env.get("EVAL_ALLOWED_EMAILS", "").split(",") if e.strip()
        )
        if not emails:
            raise ConfigError("EVAL_ALLOWED_EMAILS must not be empty")
        auth_project = (env.get("AUTH_PROJECT") or env.get("GCP_PROJECT") or "").strip()
        if not auth_project:
            raise ConfigError("AUTH_PROJECT (or GCP_PROJECT) is required")
        service_url = _required(env, "SERVICE_URL").rstrip("/")
        # The eval backend composes the api's own settings; it only ever runs as the eval instance.
        settings = Settings.from_env(
            {
                "ENV": "staging",
                "FIRESTORE_DATABASE": "staging",
                "SERVICE_MODE": "worker",  # no voice relay here: VOICE_URL is not needed
                **env,
                "AUTH_PROJECT": auth_project,
            }
        )
        if not settings.eval_mode:
            raise ConfigError("EVAL_MODE=true is required: the eval backend refuses to start")
        return cls(
            auth_project=auth_project,
            allowed_emails=emails,
            environment=env.get("ENV", "staging").strip(),
            project=(env.get("GCP_PROJECT") or auth_project).strip(),
            datasets_bucket=_required(env, "DATASETS_BUCKET"),
            settings=settings,
            tasks_queue=_required(env, "TASKS_QUEUE"),
            tasks_sa=_required(env, "TASKS_SA"),
            service_url=service_url,
            task_audience=env.get("TASKS_OIDC_AUDIENCE", "").strip() or service_url,
            prod_engine=_required(env, "PROD_ENGINE"),
            default_preset=_required(env, "DEFAULT_PRESET"),
            routes_file=_required(env, "ROUTES_FILE"),
            eval_owner_uid=env.get("EVAL_OWNER_UID", "").strip() or cls.eval_owner_uid,
            max_per_provider=_positive_int(env, "EVAL_MAX_PER_PROVIDER", cls.max_per_provider),
            provider_fail_limit=_positive_int(
                env, "EVAL_PROVIDER_FAIL_LIMIT", cls.provider_fail_limit
            ),
            overload_max_wait_s=_positive_int(
                env, "EVAL_OVERLOAD_MAX_WAIT_S", cls.overload_max_wait_s, minimum=0
            ),
            internal_retries=_positive_int(
                env, "EVAL_INTERNAL_RETRIES", cls.internal_retries, minimum=0
            ),
        )
