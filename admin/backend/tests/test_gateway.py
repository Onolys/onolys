import pytest
from conftest import PROJECT
from fastapi.testclient import TestClient
from onolys_admin_auth import ConfigError, IdTokenVerifier

from onolys_admin_backend import create_app, parse_cors_origins

pytestmark = pytest.mark.unit

ORIGIN = "https://admin.example"
EVIL = "https://evil.example"
ENV_ON = {
    "ENV": "prod",
    "ADMIN_AUTH": "on",
    "GCP_PROJECT": PROJECT,
    "ADMIN_ALLOWED_EMAILS": "alice@example.com",
    "ADMIN_CORS_ORIGINS": ORIGIN,
}
ENV_LOCAL = {"ENV": "local", "ADMIN_AUTH": "off", "ADMIN_CORS_ORIGINS": ORIGIN}


@pytest.fixture
def secured(keys):
    verifier = IdTokenVerifier(PROJECT, fetch_certs=lambda: keys.certs)
    with TestClient(create_app(ENV_ON, verifier), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def local():
    with TestClient(create_app(ENV_LOCAL), raise_server_exceptions=False) as c:
        yield c


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# --- every route is gated ---
ROUTES = [
    ("GET", "/v1/me"),
    ("GET", "/healthz"),
    ("GET", "/nope"),
    ("GET", "/docs"),
    ("GET", "/openapi.json"),
    ("POST", "/v1/audit"),
    ("POST", "/v1/paudit/run"),
]


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_no_token_401(secured, method, path):
    r = secured.request(method, path)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_garbage_token_401(secured, method, path):
    assert secured.request(method, path, headers=auth("garbage")).status_code == 401


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_not_allowlisted_403(secured, keys, method, path):
    tok = keys.mint(email="mallory@example.com")
    assert secured.request(method, path, headers=auth(tok)).status_code == 403


def test_unverified_email_403(secured, keys):
    tok = keys.mint(email_verified=False)
    assert secured.get("/v1/me", headers=auth(tok)).status_code == 403


def test_allowlisted_me_200(secured, keys):
    r = secured.get("/v1/me", headers=auth(keys.mint()))
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_allowlist_case_insensitive(secured, keys):
    tok = keys.mint(email="Alice@Example.com")
    assert secured.get("/v1/me", headers=auth(tok)).status_code == 200


# --- only /v1/me exists: no eaudit/paudit routes ---
@pytest.mark.parametrize(
    ("method", "path"),
    [("POST", "/v1/audit"), ("GET", "/healthz"), ("POST", "/v1/paudit/run"), ("GET", "/docs")],
)
def test_legacy_routes_absent(secured, keys, method, path):
    assert secured.request(method, path, headers=auth(keys.mint())).status_code in (404, 405)


def test_no_engine_routes_registered(local):
    paths = {getattr(r, "path", "") for r in local.app.routes}
    assert "/v1/me" in paths
    assert not any("audit" in p for p in paths)


# --- CORS ---
PREFLIGHT = {
    "Access-Control-Request-Method": "GET",
    "Access-Control-Request-Headers": "authorization,content-type",
}


def test_preflight_allowed_origin_without_token(secured):
    r = secured.options("/v1/me", headers={"Origin": ORIGIN, **PREFLIGHT})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == ORIGIN
    allowed = {h.strip().lower() for h in r.headers["access-control-allow-headers"].split(",")}
    assert {"authorization", "content-type"} <= allowed
    assert "access-control-allow-credentials" not in r.headers


def test_preflight_disallowed_origin_rejected(secured):
    r = secured.options("/v1/me", headers={"Origin": EVIL, **PREFLIGHT})
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers


def test_preflight_disallowed_header_rejected(secured):
    h = {"Origin": ORIGIN, **PREFLIGHT, "Access-Control-Request-Headers": "x-evil"}
    assert secured.options("/v1/me", headers=h).status_code == 400


def test_cors_headers_on_401_for_allowed_origin_only(secured):
    ok = secured.get("/v1/me", headers={"Origin": ORIGIN})
    assert ok.status_code == 401 and ok.headers["access-control-allow-origin"] == ORIGIN
    bad = secured.get("/v1/me", headers={"Origin": EVIL})
    assert bad.status_code == 401 and "access-control-allow-origin" not in bad.headers


def test_cors_headers_on_success(secured, keys):
    r = secured.get("/v1/me", headers={**auth(keys.mint()), "Origin": ORIGIN})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == ORIGIN


# --- local mode ---
def test_local_me_ok(local):
    assert local.get("/v1/me").json() == {"status": "ok"}


# --- config ---
def test_cors_origin_parsing():
    assert parse_cors_origins(" https://a.example, https://b.example ,") == [
        "https://a.example",
        "https://b.example",
    ]
    assert parse_cors_origins("") == []
    for bad in ("*", "https://*.example.com", "null"):
        with pytest.raises(ConfigError):
            parse_cors_origins(bad)


def test_startup_fails_without_allowlist():
    env = {k: v for k, v in ENV_ON.items() if k != "ADMIN_ALLOWED_EMAILS"}
    with pytest.raises(ConfigError):
        create_app(env)


def test_auth_off_refused_outside_local():
    with pytest.raises(ConfigError):
        create_app({})
    with pytest.raises(ConfigError):
        create_app({"ADMIN_AUTH": "off"})
    with pytest.raises(ConfigError):
        create_app({**ENV_LOCAL, "ENV": "prod"})
