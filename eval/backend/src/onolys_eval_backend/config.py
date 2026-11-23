"""Explicit deployment settings; eval never permits disabling allowlist auth."""

from collections.abc import Mapping
from dataclasses import dataclass

from onolys_admin_auth import AdminAuthConfig, ConfigError


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required")
    return value


@dataclass(frozen=True)
class EvalConfig:
    auth: AdminAuthConfig
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
        if env.get("ADMIN_AUTH", "on").strip().lower() != "on":
            raise ConfigError("Eval requires ADMIN_AUTH=on in every environment")
        auth = AdminAuthConfig.from_env({**env, "ADMIN_AUTH": "on"})
        service_url = _required(env, "SERVICE_URL").rstrip("/")
        return cls(
            auth=auth,
            environment=env.get("ENV", "staging").strip(),
            project=(env.get("GCP_PROJECT") or auth.project).strip(),
            bucket=_required(env, "EVAL_BUCKET"),
            tasks_queue=_required(env, "TASKS_QUEUE"),
            tasks_sa=_required(env, "TASKS_SA"),
            service_url=service_url,
            task_audience=env.get("TASKS_OIDC_AUDIENCE", "").strip() or service_url,
            prod_engine=_required(env, "PROD_ENGINE"),
            default_preset=_required(env, "DEFAULT_PRESET"),
            routes_file=_required(env, "ROUTES_FILE"),
        )
