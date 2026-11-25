"""Explicit deployment settings; eval always enforces the allowlist."""

from collections.abc import Mapping
from dataclasses import dataclass

from onolys_engine_core.errors import ConfigError

# Pre-R14 names. The eval backend now uses the api's AUTH_PROJECT / CORS_ORIGINS plus
# EVAL_ALLOWED_EMAILS, and refuses to start if an old name is still set.
REMOVED_ENV = (
    "ADMIN_AUTH",
    "ADMIN_AUTH_PROJECT",
    "ADMIN_ALLOWED_EMAILS",
    "ADMIN_CORS_ORIGINS",
    "EVAL_AUTH",
    "EVAL_AUTH_PROJECT",
    "EVAL_CORS_ORIGINS",
)


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required")
    return value


@dataclass(frozen=True)
class EvalConfig:
    auth_project: str
    allowed_emails: frozenset[str]
    environment: str
    project: str
    bucket: str
    tasks_queue: str
    tasks_sa: str
    service_url: str
    task_audience: str
    prod_engine: str
    default_preset: str
    routes_file: str
    firestore_database: str = "staging"

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
        return cls(
            auth_project=auth_project,
            allowed_emails=emails,
            environment=env.get("ENV", "staging").strip(),
            project=(env.get("GCP_PROJECT") or auth_project).strip(),
            bucket=_required(env, "EVAL_BUCKET"),
            tasks_queue=_required(env, "TASKS_QUEUE"),
            tasks_sa=_required(env, "TASKS_SA"),
            service_url=service_url,
            task_audience=env.get("TASKS_OIDC_AUDIENCE", "").strip() or service_url,
            prod_engine=_required(env, "PROD_ENGINE"),
            default_preset=_required(env, "DEFAULT_PRESET"),
            routes_file=_required(env, "ROUTES_FILE"),
        )
