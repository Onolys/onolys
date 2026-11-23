"""Auth boundary tests exercise the actual ASGI middleware, without cloud access."""

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from onolys_admin_auth import ConfigError, InvalidToken

from onolys_eval_backend import create_app
from onolys_eval_backend.config import EvalConfig

ENV = {
    "ENV": "staging",
    "GCP_PROJECT": "onolys-test",
    "ADMIN_AUTH": "on",
    "ADMIN_ALLOWED_EMAILS": "alice@example.com",
    "ADMIN_CORS_ORIGINS": "https://eval.example",
    "EVAL_BUCKET": "eval-test",
    "TASKS_QUEUE": "projects/test/locations/europe-west1/queues/eval-runs",
    "TASKS_SA": "tasks@onolys-test.iam.gserviceaccount.com",
    "SERVICE_URL": "https://eval-backend.example",
    "PROD_ENGINE": "miti",
    "DEFAULT_PRESET": "configured-prod",
    "ROUTES_FILE": "/config/routes.yaml",
}
TASK_CLAIMS = {
    "iss": "https://accounts.google.com",
    "aud": ENV["SERVICE_URL"],
    "email": ENV["TASKS_SA"],
    "email_verified": True,
}


class Verifier:
    def __init__(self, claims):
        self.claims = claims

    def verify(self, token):
        if token != "valid":
            raise InvalidToken
        return self.claims


def client(*, claims=None, task_claims=None, **kwargs):
    return TestClient(
        create_app(
            ENV,
            verifier=Verifier(claims or {"email": "alice@example.com", "email_verified": True}),
            task_verifier=Verifier(TASK_CLAIMS if task_claims is None else task_claims),
            **kwargs,
        )
    )


AUTH = {"Authorization": "Bearer valid"}


@pytest.mark.parametrize("path", ["/v1/me", "/healthz", "/v1/missing", "/docs"])
def test_anonymous_is_401(path):
    assert client().get(path).status_code == 401


def test_non_allowlisted_is_403():
    response = client(claims={"email": "outsider@example.com", "email_verified": True}).get(
        "/v1/me", headers=AUTH
    )
    assert response.status_code == 403
    assert response.json()["error"]["message"] == "Not allowed."


def test_allowed_me_and_health():
    with client() as c:
        assert c.get("/v1/me", headers=AUTH).json() == {"status": "ok"}
        assert c.get("/healthz", headers=AUTH).json() == {"status": "ok"}


@pytest.mark.parametrize(
    "env",
    [{"ADMIN_ALLOWED_EMAILS": ""}, {"ADMIN_AUTH": "off"}, {"ENV": "local", "ADMIN_AUTH": "off"}],
)
def test_unsafe_auth_config_fails_at_creation(env):
    with pytest.raises(ConfigError):
        create_app({**ENV, **env})


def test_auth_defaults_on_even_locally():
    env = {k: v for k, v in ENV.items() if k != "ADMIN_AUTH"}
    assert create_app({**env, "ENV": "local"}).state.config.auth.enabled is True


@pytest.mark.parametrize("route", ["unit", "transcribe", "unknown"])
def test_internal_requires_token_even_with_cloudtasks_headers(route):
    response = client().post(
        f"/internal/tasks/{route}", headers={"X-CloudTasks-TaskName": "trusted-looking"}
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "claims",
    [
        {**TASK_CLAIMS, "iss": "https://evil.example"},
        {**TASK_CLAIMS, "aud": "another-service"},
        {**TASK_CLAIMS, "email": "other@test.iam.gserviceaccount.com"},
        {**TASK_CLAIMS, "email_verified": False},
        {**TASK_CLAIMS, "email_verified": "true"},
        {"email": "alice@example.com", "email_verified": True},
    ],
)
def test_internal_checks_all_identity_claims(claims):
    assert client(task_claims=claims).post("/internal/tasks/unit", headers=AUTH).status_code == 403


def test_internal_invalid_token():
    assert (
        client().post("/internal/tasks/unit", headers={"Authorization": "Bearer bad"}).status_code
        == 401
    )


@pytest.mark.parametrize("route", ["unit", "transcribe"])
def test_task_identity_passes_without_allowlist_membership(route):
    assert client().post(f"/internal/tasks/{route}", headers=AUTH).status_code == 501


def test_task_identity_cannot_access_public_api():
    assert client(claims=TASK_CLAIMS).get("/v1/me", headers=AUTH).status_code == 403


def test_internal_prefix_cannot_bypass_public_auth():
    assert client().get("/internal/tasks-spoof").status_code == 401


def test_cors_outermost_for_preflight_and_denials():
    with client() as c:
        response = c.options(
            "/v1/me",
            headers={
                "Origin": "https://eval.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert response.status_code == 200
        for path in ("/v1/me", "/internal/tasks/unit"):
            response = c.get(path, headers={"Origin": "https://eval.example"})
            assert response.status_code == 401
            assert response.headers["access-control-allow-origin"] == "https://eval.example"


@pytest.mark.parametrize("origin", ["*", "https://*.example", "null"])
def test_unsafe_cors_rejected(origin):
    with pytest.raises(ConfigError):
        create_app({**ENV, "ADMIN_CORS_ORIGINS": origin})


def test_config_and_injected_services():
    services = object()
    app = create_app(ENV, services=services)
    config = app.state.config
    assert isinstance(config, EvalConfig)
    assert config.bucket == ENV["EVAL_BUCKET"]
    assert config.tasks_queue == ENV["TASKS_QUEUE"]
    assert config.tasks_sa == ENV["TASKS_SA"]
    assert config.task_audience == ENV["SERVICE_URL"]
    assert config.service_url == ENV["SERVICE_URL"]
    assert config.prod_engine == "miti"
    assert config.default_preset == "configured-prod"
    assert config.routes_file == "/config/routes.yaml"
    assert config.firestore_database == "staging"
    assert app.state.services is services


@pytest.mark.parametrize(
    "field",
    [
        "EVAL_BUCKET",
        "TASKS_QUEUE",
        "TASKS_SA",
        "SERVICE_URL",
        "PROD_ENGINE",
        "DEFAULT_PRESET",
        "ROUTES_FILE",
    ],
)
def test_missing_required_config_fails(field):
    with pytest.raises(ConfigError):
        create_app({**ENV, field: " "})


def test_no_api_imports_in_backend():
    root = Path(__file__).parents[1] / "src"
    for source in root.rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text())):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            assert not any(
                name == "onolys_api" or name.startswith("onolys_api.") for name in names
            ), source


def test_task_verifier_uses_google_oauth_verification_with_exact_audience(monkeypatch):
    from onolys_eval_backend.auth import TaskOidcVerifier, id_token

    seen = {}

    def verify(token, request, audience):
        seen.update(token=token, request=request, audience=audience)
        return TASK_CLAIMS

    monkeypatch.setattr(id_token, "verify_oauth2_token", verify)
    verifier = TaskOidcVerifier(ENV["SERVICE_URL"])
    assert verifier.verify("signed-token") == TASK_CLAIMS
    assert seen == {
        "token": "signed-token",
        "request": verifier.request,
        "audience": ENV["SERVICE_URL"],
    }


def test_task_verifier_rejects_google_verification_failure(monkeypatch):
    from onolys_eval_backend.auth import TaskOidcVerifier, id_token

    def reject(*args, **kwargs):
        raise ValueError("invalid signature / expired token")

    monkeypatch.setattr(id_token, "verify_oauth2_token", reject)
    with pytest.raises(InvalidToken):
        TaskOidcVerifier(ENV["SERVICE_URL"]).verify("bad")


def test_task_verifier_upstream_failure_is_not_an_auth_bypass(monkeypatch):
    from google.auth.exceptions import TransportError
    from onolys_admin_auth import UpstreamUnavailable

    from onolys_eval_backend.auth import TaskOidcVerifier, id_token

    def unavailable(*args, **kwargs):
        raise TransportError("certificate service unavailable")

    monkeypatch.setattr(id_token, "verify_oauth2_token", unavailable)
    with pytest.raises(UpstreamUnavailable):
        TaskOidcVerifier(ENV["SERVICE_URL"]).verify("token")

    class Unavailable:
        def verify(self, token):
            raise UpstreamUnavailable

    with TestClient(create_app(ENV, task_verifier=Unavailable())) as c:
        assert c.post("/internal/tasks/unit", headers=AUTH).status_code == 503


def test_explicit_task_audience_configuration():
    app = create_app({**ENV, "TASKS_OIDC_AUDIENCE": "https://explicit-audience.example"})
    assert app.state.config.task_audience == "https://explicit-audience.example"
