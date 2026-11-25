"""EvalConfig must start with exactly the env the deployed Cloud Run service gets."""

import re
from pathlib import Path

import pytest
from onolys_engine_core.errors import ConfigError

from onolys_eval_backend.config import EvalConfig

SERVICES_TF = Path(__file__).parents[3] / "infra/modules/environment/services.tf"

# Dummy values; anything not listed gets "1". ENV is local.runtime_env of `module "eval"`.
VALUES = {
    "ENV": "staging",
    "FIRESTORE_DATABASE": "eval",
    "GCP_PROJECT": "onolys-test",
    "REGION": "europe-west1",
    "AUTH_PROJECT": "onolys-test",
    "AUDIO_BUCKET": "audio-eval",
    "ADAPTERS": "real",
    "TASKS_QUEUE": "projects/p/locations/europe-west1/queues/eval-runs",
    "TASKS_SA": "tasks@onolys-test.iam.gserviceaccount.com",
    "WORKER_URL": "https://worker.example",
    "EVAL_MODE": "true",
    "AI_MAX_SECONDS": "600",
    "AI_WARN_SECONDS": "60",
    "AI_MIC_GATE": "true",
    "UID_HMAC_KEY": "hmac",
    "BLOB_SIGNER_EMAIL": "api@onolys-test.iam.gserviceaccount.com",
    "CORS_ORIGINS": "https://eval.example",
    "SERVICE_URL": "https://eval-backend.example",
    "TASKS_OIDC_AUDIENCE": "https://eval-backend.example",
    "DATASETS_BUCKET": "datasets",
    "EVAL_OWNER_UID": "eval",
    "EVAL_ALLOWED_EMAILS": "a@example.com",
    "ROUTES_FILE": "config/staging/routes.yaml",
    "DEFAULT_PRESET": "configured-prod",
}


def _terraform_env_names() -> set[str]:
    """Env var names the terraform eval-backend service sets (derived so it cannot drift)."""
    text = SERVICES_TF.read_text()
    block = text.split('resource "google_cloud_run_v2_service" "eval_backend"', 1)[1]
    block = block.split("\n}\n", 1)[0]
    names = set(re.findall(r'\bname\s*=\s*"([A-Z][A-Z0-9_]+)"', block))
    # The dynamic env blocks pull in the shared locals.
    for local in ("platform_env", "routes_env", "interview_env"):
        if f"local.{local}" in block or local == "interview_env":
            body = text.split(f"  {local} = ", 1)[1].split("\n  ]", 1)[0]
            names |= set(re.findall(r'\{ name = "([A-Z][A-Z0-9_]+)"', body))
    return names


def _deployed_env() -> dict[str, str]:
    names = _terraform_env_names() | {"EVAL_MODE"}  # EVAL_MODE: platform_env, eval_mode=true
    assert {"SERVICE_MODE", "FIRESTORE_DATABASE", "ENV", "EVAL_ALLOWED_EMAILS"} <= names
    # The service really sets SERVICE_MODE=api; keep that exact value.
    return {n: VALUES.get(n, "1") for n in names} | {"SERVICE_MODE": "api"}


def test_starts_with_exact_terraform_env() -> None:
    env = _deployed_env()
    assert "VOICE_URL" not in env  # the eval backend service has no voice relay
    assert "PROD_ENGINE" not in env  # not set by terraform: falls back to the api default
    config = EvalConfig.from_env(env)
    assert config.settings.eval_mode is True
    assert config.firestore_database == "eval"
    assert config.settings.firestore_database == "eval"


@pytest.mark.parametrize("name", ["FIRESTORE_DATABASE", "ENV"])
def test_missing_database_or_env_fails_closed(name: str) -> None:
    env = _deployed_env()
    del env[name]
    with pytest.raises(ConfigError, match=name):
        EvalConfig.from_env(env)
