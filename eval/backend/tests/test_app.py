"""Auth boundary tests exercise the actual ASGI middleware, without cloud access."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from onolys_api.auth.idtoken import EmailNotVerified, InvalidToken
from onolys_api.errors import ApiError
from onolys_engine_core.errors import ConfigError

from onolys_eval_backend import create_app
from onolys_eval_backend.config import EvalConfig

ENV = {
    "ENV": "staging",
    "FIRESTORE_DATABASE": "staging",
    "GCP_PROJECT": "onolys-test",
    "EVAL_ALLOWED_EMAILS": "Alice@Example.com",
    "CORS_ORIGINS": "https://eval.example",
    "DATASETS_BUCKET": "datasets-test",
    "AUDIO_BUCKET": "audio-eval-test",
    "EVAL_MODE": "true",
    "REGION": "europe-west1",
    "WORKER_URL": "https://worker.example",
    "UID_HMAC_KEY": "test-hmac-key",
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
    """Fake of both verifiers: `verify` (task OIDC) and the prod `verify_claims` (user ID token)."""

    def __init__(self, claims):
        self.claims = claims

    def verify(self, token):
        if token != "valid":
            raise InvalidToken
        return self.claims

    def verify_claims(self, token):
        claims = self.verify(token)
        if claims.get("email_verified") is not True:
            raise EmailNotVerified  # the prod verifier checks this itself
        return claims


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
    assert response.json()["error"]["code"] == "not_allowlisted"


def test_unverified_email_is_403():
    response = client(claims={"email": "alice@example.com", "email_verified": False}).get(
        "/v1/me", headers=AUTH
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "email_unverified"


def test_invalid_token_is_401():
    response = client().get("/v1/me", headers={"Authorization": "Bearer bad"})
    assert response.status_code == 401


def test_cert_outage_is_503():
    class Down:
        def verify_claims(self, token):
            raise ApiError.of(503, "upstream_unavailable", "x")

    app = create_app(ENV, verifier=Down(), task_verifier=Verifier(TASK_CLAIMS))
    assert TestClient(app).get("/v1/me", headers=AUTH).status_code == 503


def test_email_is_matched_case_insensitively_and_recorded():
    seen = []
    app = create_app(
        ENV,
        verifier=Verifier({"email": " ALICE@example.com ", "email_verified": True}),
        task_verifier=Verifier(TASK_CLAIMS),
    )

    @app.get("/v1/whoami")
    async def whoami(request: __import__("fastapi").Request):
        seen.append(request.state.user_email)
        return {}

    assert TestClient(app).get("/v1/whoami", headers=AUTH).status_code == 200
    assert seen == ["alice@example.com"]


def test_allowed_me_and_health():
    with client() as c:
        assert c.get("/v1/me", headers=AUTH).json() == {"status": "ok"}
        assert c.get("/healthz", headers=AUTH).json() == {"status": "ok"}


@pytest.mark.parametrize(
    "env",
    [
        {"EVAL_ALLOWED_EMAILS": ""},
        {"EVAL_ALLOWED_EMAILS": " , "},
        {"AUTH_MODE": "fake"},
        {"ENV": "local", "AUTH_MODE": "fake"},
        {"EVAL_AUTH": "on"},
        {"GCP_PROJECT": "", "AUTH_PROJECT": ""},
    ],
)
def test_unsafe_auth_config_fails_at_creation(env):
    with pytest.raises(ConfigError):
        create_app({**ENV, **env})


def test_auth_is_always_on_even_locally():
    app = create_app({**ENV, "ENV": "local"}, verifier=Verifier({}))
    assert TestClient(app).get("/v1/me").status_code == 401
    assert app.state.config.allowed_emails == frozenset({"alice@example.com"})


def test_auth_project_falls_back_to_gcp_project():
    assert create_app(ENV).state.config.auth_project == "onolys-test"
    assert create_app({**ENV, "AUTH_PROJECT": "idp-proj"}).state.config.auth_project == "idp-proj"


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
    response = client(task_claims=claims).post("/internal/tasks/tick", headers=AUTH)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_internal_invalid_token():
    assert (
        client().post("/internal/tasks/tick", headers={"Authorization": "Bearer bad"}).status_code
        == 401
    )


@pytest.mark.parametrize("route,status", [("tick", 422), ("delete", 422), ("transcribe", 422)])
def test_task_identity_passes_without_allowlist_membership(route, status):
    assert client().post(f"/internal/tasks/{route}", headers=AUTH).status_code == status


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
        for path in ("/v1/me", "/internal/tasks/tick"):
            response = c.get(path, headers={"Origin": "https://eval.example"})
            assert response.status_code == 401
            assert response.headers["access-control-allow-origin"] == "https://eval.example"


@pytest.mark.parametrize("origin", ["*", "https://*.example", "null"])
def test_unsafe_cors_rejected(origin):
    with pytest.raises(ConfigError):
        create_app({**ENV, "CORS_ORIGINS": origin})


def test_config_and_injected_services():
    services = object()
    app = create_app(ENV, services=services)
    config = app.state.config
    assert isinstance(config, EvalConfig)
    assert config.datasets_bucket == ENV["DATASETS_BUCKET"]
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
        "DATASETS_BUCKET",
        "TASKS_QUEUE",
        "TASKS_SA",
        "SERVICE_URL",
        "FIRESTORE_DATABASE",
        "DEFAULT_PRESET",
        "ROUTES_FILE",
    ],
)
def test_missing_required_config_fails(field):
    with pytest.raises(ConfigError):
        create_app({**ENV, field: " "})


@pytest.fixture(scope="module")
def task_keys():
    import time

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from google.auth import crypt, jwt

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signer = crypt.RSASigner.from_string(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        "current",
    )
    cert = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )

    def mint(kid="current", **overrides):
        now = int(time.time())
        return jwt.encode(
            signer, {**TASK_CLAIMS, "iat": now, "exp": now + 600, **overrides}, key_id=kid
        ).decode()

    return mint, cert


def test_task_verifier_caches_refreshes_and_retains_google_validation(task_keys):
    import json
    from types import SimpleNamespace

    from onolys_eval_backend.auth import TaskOidcVerifier

    mint, cert = task_keys
    calls = []
    now = [0.0]
    certs = {"current": cert}

    def request(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(status=200, data=json.dumps(certs).encode())

    verifier = TaskOidcVerifier(ENV["SERVICE_URL"], request=request, clock=lambda: now[0])
    for _ in range(3):
        assert verifier.verify(mint())["email"] == ENV["TASKS_SA"]
    assert len(calls) == 1
    assert calls[0][1] == {"method": "GET", "timeout": 5}
    certs["next"] = cert
    now[0] = 31
    assert verifier.verify(mint("next"))["email_verified"] is True
    assert len(calls) == 2
    for overrides in ({"aud": "another-service"}, {"iss": "another-issuer"}, {"iat": 1, "exp": 2}):
        with pytest.raises(InvalidToken):
            verifier.verify(mint(**overrides))


def test_task_verifier_upstream_failure_is_not_an_auth_bypass(task_keys):
    from google.auth.exceptions import TransportError

    from onolys_eval_backend.auth import TaskOidcVerifier, UpstreamUnavailable

    calls = []

    def unavailable(*args, **kwargs):
        calls.append(1)
        raise TransportError("certificate service unavailable")

    verifier = TaskOidcVerifier(ENV["SERVICE_URL"], request=unavailable, clock=lambda: 0)
    for _ in range(3):
        with pytest.raises(UpstreamUnavailable):
            verifier.verify(task_keys[0]())
    assert len(calls) == 1

    class Unavailable:
        def verify(self, token):
            raise UpstreamUnavailable

    with TestClient(create_app(ENV, task_verifier=Unavailable())) as c:
        assert c.post("/internal/tasks/tick", headers=AUTH).status_code == 503


def test_task_verification_runs_outside_event_loop():
    import asyncio
    import threading

    from onolys_eval_backend.auth import EvalAuthMiddleware

    async def exercise():
        loop_thread = threading.get_ident()
        reached = []

        class Verifier:
            def verify(self, token):
                assert threading.get_ident() != loop_thread
                return TASK_CLAIMS

        async def app(scope, receive, send):
            reached.append(True)

        middleware = EvalAuthMiddleware(app, EvalConfig.from_env(ENV), task_verifier=Verifier())
        await middleware(
            {
                "type": "http",
                "path": "/internal/tasks/tick",
                "headers": [(b"authorization", b"Bearer valid")],
            },
            None,
            None,
        )
        assert reached == [True]

    asyncio.run(exercise())


def test_explicit_task_audience_configuration():
    app = create_app({**ENV, "TASKS_OIDC_AUDIENCE": "https://explicit-audience.example"})
    assert app.state.config.task_audience == "https://explicit-audience.example"


def test_allowlist_middleware_refuses_empty_set():
    from onolys_eval_backend.allowlist import AllowlistMiddleware

    with pytest.raises(ValueError):
        AllowlistMiddleware(lambda *a: None, Verifier({}), frozenset())


def test_eval_config_defaults_and_overrides():
    config = EvalConfig.from_env(ENV)
    assert (config.eval_owner_uid, config.max_per_provider, config.provider_fail_limit) == (
        "eval", 2, 5
    )
    assert (config.overload_max_wait_s, config.internal_retries) == (300, 1)
    assert config.settings.eval_mode is True
    assert config.audio_bucket == ENV["AUDIO_BUCKET"]  # uploads only; datasets_bucket is separate
    over = EvalConfig.from_env(
        {
            **ENV,
            "EVAL_OWNER_UID": "owner-x",
            "EVAL_MAX_PER_PROVIDER": "3",
            "EVAL_PROVIDER_FAIL_LIMIT": "2",
            "EVAL_OVERLOAD_MAX_WAIT_S": "60",
            "EVAL_INTERNAL_RETRIES": "0",
        }
    )
    assert (over.eval_owner_uid, over.max_per_provider, over.provider_fail_limit) == (
        "owner-x", 3, 2
    )
    assert (over.overload_max_wait_s, over.internal_retries) == (60, 0)


def test_audio_bucket_fails_closed_without_falling_back_to_datasets():
    config = EvalConfig.from_env(ENV)
    config = replace(config, settings=replace(config.settings, audio_bucket=""))
    assert config.datasets_bucket
    with pytest.raises(ConfigError):
        _ = config.audio_bucket


@pytest.mark.parametrize("name", ["EVAL_MAX_PER_PROVIDER", "EVAL_PROVIDER_FAIL_LIMIT"])
@pytest.mark.parametrize("bad", ["0", "x"])
def test_eval_config_bad_numbers_fail(name, bad):
    with pytest.raises(ConfigError):
        EvalConfig.from_env({**ENV, name: bad})


@pytest.mark.parametrize("value", [None, "false"])
def test_refuses_to_start_unless_eval_mode(value):
    env = {k: v for k, v in ENV.items() if k != "EVAL_MODE"}
    if value is not None:
        env["EVAL_MODE"] = value
    with pytest.raises(ConfigError, match="EVAL_MODE"):
        EvalConfig.from_env(env)
    with pytest.raises(ConfigError, match="EVAL_MODE"):
        create_app(env)


def test_services_compose_api_pieces_and_ensure_owner_once():
    from onolys_api.jobs.queue import InMemoryQueue
    from onolys_api.repo.fake import FakeRepo
    from onolys_api.storage.fake import FakeBlobStore

    from onolys_eval_backend.services import EvalServices

    blobs = FakeBlobStore()
    repo = FakeRepo(blobs)
    calls = []
    real = repo.ensure_user
    repo.ensure_user = lambda uid: calls.append(uid) or real(uid)
    queue = InMemoryQueue()
    services = EvalServices(
        EvalConfig.from_env({**ENV, "EVAL_OWNER_UID": "owner-x"}),
        blobs=blobs, repo=repo, run_queue=queue,
    )
    assert services.settings.eval_mode is True
    assert services.blobs is blobs and services.run_queue is queue
    assert services.repo is repo and services.repo is repo and services.repo is repo
    assert calls == ["owner-x"]
