import logging
import time

import pytest
from conftest import KID, PROJECT
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from onolys_admin_auth import (
    AdminAuthConfig,
    AdminAuthMiddleware,
    ConfigError,
    IdTokenVerifier,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def make_client(keys):
    def make(emails="alice@example.com,Bob@Example.com", **kw):
        cfg = AdminAuthConfig(
            enabled=True,
            project=PROJECT,
            allowed_emails=frozenset(e.strip().lower() for e in emails.split(",")),
        )
        app = Starlette(routes=[Route("/x", lambda r: PlainTextResponse("ok"), methods=["GET"])])
        verifier = IdTokenVerifier(PROJECT, fetch_certs=lambda: keys.certs)
        wrapped = AdminAuthMiddleware(app, cfg, verifier)
        wrapped = CORSMiddleware(
            wrapped,
            allow_origins=["https://admin.example"],
            allow_headers=["authorization", "content-type"],
            allow_methods=["GET", "POST"],
        )
        return TestClient(wrapped)

    return make


def get(client, token=None, raw=None):
    h = {}
    if raw is not None:
        h["Authorization"] = raw
    elif token:
        h["Authorization"] = f"Bearer {token}"
    return client.get("/x", headers=h)


def err(resp, status, code):
    assert resp.status_code == status
    assert resp.json()["error"]["code"] == code
    assert set(resp.json()["error"]) == {"code", "message"}


def test_ok(make_client, keys):
    assert get(make_client(), keys.mint()).status_code == 200


def test_missing_token(make_client):
    err(get(make_client()), 401, "unauthenticated")


def test_non_bearer_scheme(make_client):
    err(get(make_client(), raw="Basic abc"), 401, "unauthenticated")


def test_malformed_token(make_client):
    err(get(make_client(), "not.a.jwt"), 401, "unauthenticated")


def test_expired(make_client, keys):
    t = keys.mint(exp=int(time.time()) - 3600, iat=int(time.time()) - 7200)
    err(get(make_client(), t), 401, "unauthenticated")


def test_wrong_audience(make_client, keys):
    err(get(make_client(), keys.mint(aud="other")), 401, "unauthenticated")


def test_wrong_issuer(make_client, keys):
    t = keys.mint(iss="https://securetoken.google.com/other")
    err(get(make_client(), t), 401, "unauthenticated")


def test_bad_signature(make_client, keys):
    other = type(keys)()
    err(get(make_client(), other.mint()), 401, "unauthenticated")
    assert KID in keys.certs


def test_unverified_email(make_client, keys):
    err(get(make_client(), keys.mint(email_verified=False)), 403, "email_unverified")


def test_missing_email_claim(make_client, keys):
    err(get(make_client(), keys.mint(email=None)), 403, "email_unverified")


def test_not_listed(make_client, keys):
    err(get(make_client(), keys.mint(email="eve@example.com")), 403, "not_allowlisted")


def test_mixed_case_allowed(make_client, keys):
    assert get(make_client(), keys.mint(email="BOB@example.COM")).status_code == 200
    assert get(make_client(), keys.mint(email="ALICE@Example.com")).status_code == 200


def test_preflight_bypasses_auth(make_client):
    r = make_client().options(
        "/x",
        headers={
            "Origin": "https://admin.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "https://admin.example"


def test_no_token_or_email_in_logs(make_client, keys, caplog):
    caplog.set_level(logging.DEBUG)
    client = make_client()
    good = keys.mint()
    bad = keys.mint(email="secret.eve@example.com")
    get(client, good)
    get(client, bad)
    get(client, keys.mint(email_verified=False))
    get(client, "garbage.token.value")
    get(client, keys.mint(aud="other"))
    text = "\n".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
    for secret in (good, bad, "garbage.token.value", "secret.eve", "alice@example.com"):
        assert secret not in text


def test_upstream_cert_failure_is_503(keys):
    def boom():
        raise RuntimeError("net")

    cfg = AdminAuthConfig(True, PROJECT, frozenset({"alice@example.com"}))
    app = Starlette(routes=[Route("/x", lambda r: PlainTextResponse("ok"))])
    c = TestClient(AdminAuthMiddleware(app, cfg, IdTokenVerifier(PROJECT, fetch_certs=boom)))
    err(get(c, keys.mint()), 503, "upstream_unavailable")


def test_disabled_passes_through():
    app = Starlette(routes=[Route("/x", lambda r: PlainTextResponse("ok"))])
    c = TestClient(AdminAuthMiddleware(app, AdminAuthConfig(enabled=False)))
    assert get(c).status_code == 200


# --- startup config ---
ON = {"ENV": "prod", "ADMIN_AUTH": "on", "GCP_PROJECT": PROJECT}


def test_empty_allowlist_fails_startup():
    for v in ("", " , ,"):
        with pytest.raises(ConfigError, match="ALLOWED_EMAILS"):
            AdminAuthConfig.from_env({**ON, "ADMIN_ALLOWED_EMAILS": v})
    with pytest.raises(ConfigError):
        AdminAuthConfig.from_env(ON)


def test_middleware_refuses_empty_allowlist():
    with pytest.raises(ValueError):
        AdminAuthMiddleware(None, AdminAuthConfig(True, PROJECT, frozenset()))


def test_off_refused_outside_local_test():
    for env in ("staging", "prod"):
        with pytest.raises(ConfigError, match="local or test"):
            AdminAuthConfig.from_env({"ENV": env, "ADMIN_AUTH": "off"})


def test_off_allowed_local_test_and_default():
    for env in ("local", "test"):
        assert not AdminAuthConfig.from_env({"ENV": env, "ADMIN_AUTH": "off"}).enabled
    assert not AdminAuthConfig.from_env({"ENV": "local"}).enabled
    assert not AdminAuthConfig.from_env({"ENV": "test"}).enabled


def test_unset_or_empty_env_is_non_local_auth_on():
    for env in ({}, {"ENV": ""}, {"ENV": "  "}):
        with pytest.raises(ConfigError, match="ALLOWED_EMAILS"):
            AdminAuthConfig.from_env(env)
        c = AdminAuthConfig.from_env(
            {**env, "GCP_PROJECT": PROJECT, "ADMIN_ALLOWED_EMAILS": "a@x.com"}
        )
        assert c.enabled


def test_unset_env_with_auth_off_refused():
    for env in ({}, {"ENV": ""}):
        with pytest.raises(ConfigError, match="local or test"):
            AdminAuthConfig.from_env({**env, "ADMIN_AUTH": "off"})


def test_default_on_outside_local():
    with pytest.raises(ConfigError):
        AdminAuthConfig.from_env({"ENV": "prod"})


def test_on_parses_allowlist_lowercased():
    c = AdminAuthConfig.from_env({**ON, "ADMIN_ALLOWED_EMAILS": " A@x.com, b@X.com "})
    assert c.allowed_emails == {"a@x.com", "b@x.com"}


def test_invalid_mode():
    with pytest.raises(ConfigError):
        AdminAuthConfig.from_env({"ADMIN_AUTH": "maybe"})


def test_unknown_key_refresh_is_bounded_and_rotation_recovers(keys):
    from google.auth import jwt

    from onolys_admin_auth import InvalidToken, UpstreamUnavailable

    now = [0.0]
    calls = []
    certs = {}

    def fetch():
        calls.append(now[0])
        return dict(certs)

    verifier = IdTokenVerifier(PROJECT, fetch_certs=fetch, clock=lambda: now[0])
    # An empty upstream response is unavailable, never a usable cache entry.
    with pytest.raises(UpstreamUnavailable):
        verifier.verify(keys.mint())
    with pytest.raises(UpstreamUnavailable):
        verifier.verify(keys.mint())
    assert len(calls) == 1
    certs.update(keys.certs)
    now[0] = 31
    assert verifier.verify(keys.mint())["email"] == "alice@example.com"
    # Publish the local signing key under its next ordinary rotation ID.
    claims = verifier.verify(keys.mint())
    rotated = jwt.encode(keys.signer, claims, key_id="next").decode()
    certs["next"] = certs[KID]
    for _ in range(3):
        with pytest.raises(InvalidToken):
            verifier.verify(rotated)
    assert len(calls) == 2
    now[0] = 62
    assert verifier.verify(rotated)["email_verified"] is True
    assert len(calls) == 3


def test_refresh_failure_is_cooled_down_and_does_not_serve_expired_keys(keys):
    from onolys_admin_auth import UpstreamUnavailable

    now = [0.0]
    calls = []

    def fetch():
        calls.append(now[0])
        if len(calls) > 1:
            raise RuntimeError("temporarily unavailable")
        return keys.certs

    verifier = IdTokenVerifier(PROJECT, fetch_certs=fetch, ttl_s=60, clock=lambda: now[0])
    verifier.verify(keys.mint())
    now[0] = 61
    for _ in range(3):
        with pytest.raises(UpstreamUnavailable):
            verifier.verify(keys.mint())
    assert len(calls) == 2


def test_admin_verification_runs_outside_event_loop():
    import asyncio
    import threading

    async def exercise():
        loop_thread = threading.get_ident()

        class Verifier:
            def verify(self, token):
                assert threading.get_ident() != loop_thread
                return {"email": "alice@example.com", "email_verified": True}

        async def app(scope, receive, send):
            pass

        middleware = AdminAuthMiddleware(
            app, AdminAuthConfig(True, PROJECT, frozenset({"alice@example.com"})), Verifier()
        )
        await middleware(
            {"type": "http", "method": "GET", "headers": [(b"authorization", b"Bearer valid")]},
            None,
            None,
        )

    asyncio.run(exercise())


def test_concurrent_cold_cache_fetches_once(keys):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    entered = threading.Event()
    release = threading.Event()
    calls = []

    def fetch():
        calls.append(1)
        entered.set()
        assert release.wait(timeout=1)
        return keys.certs

    verifier = IdTokenVerifier(PROJECT, fetch_certs=fetch)
    token = keys.mint()
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(verifier.verify, token)
        try:
            assert entered.wait(timeout=1)
            others = [pool.submit(verifier.verify, token) for _ in range(2)]
        finally:
            release.set()
        assert first.result(timeout=1)["email_verified"] is True
        assert all(f.result(timeout=1)["email_verified"] is True for f in others)
    assert len(calls) == 1


def test_cache_wait_is_bounded():
    from onolys_admin_auth import UpstreamUnavailable
    from onolys_admin_auth.verifier import CertificateCache

    cache = CertificateCache(lambda: {"current": "cert"}, lock_timeout_s=0)
    with cache._lock, pytest.raises(UpstreamUnavailable):
        cache.get("current")
