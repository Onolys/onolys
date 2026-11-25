"""R1 / AC4: ID tokens, API keys, /v1/api-key, fake-auth guard. No network."""

import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.security import HTTPAuthorizationCredentials
from google.auth import _helpers, crypt, jwt
from onolys_engine_core.errors import ConfigError

from onolys_api.app import create_app
from onolys_api.auth import deps
from onolys_api.auth.deps import Authenticator
from onolys_api.auth.idtoken import IdTokenVerifier, InvalidToken
from onolys_api.auth.keys import hash_secret, new_key, parse_key
from onolys_api.config import Settings
from onolys_api.errors import ApiError
from onolys_api.repo.fake import FakeRepo
from onolys_api.repo.models import ApiKeyDoc

PROJECT = "onolys-test"
KID = "k1"


def _keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return priv.decode(), pub.decode()


PRIV, PUB = _keypair()
OTHER_PRIV, _ = _keypair()


def mint(
    uid="u1",
    *,
    verified=True,
    aud=PROJECT,
    iss=None,
    exp_in=3600,
    priv=PRIV,
    kid=KID,
    iat_in=-5,
    now=None,
):
    now = int(time.time()) if now is None else now
    claims = {
        "sub": uid,
        "aud": aud,
        "iss": iss or f"https://securetoken.google.com/{PROJECT}",
        "iat": now + iat_in,
        "exp": now + exp_in,
        "email_verified": verified,
    }
    return jwt.encode(crypt.RSASigner.from_string(priv, kid), claims, header={"kid": kid}).decode()


@pytest.fixture
def idp_settings():
    return Settings(env="staging", service_mode="api", auth_mode="idp", auth_project=PROJECT)


@pytest.fixture
def repo(blobs):
    return FakeRepo(blobs)


@pytest.fixture
async def idp_client(idp_settings, repo, blobs):
    verifier = IdTokenVerifier(PROJECT, fetch_certs=lambda: {KID: PUB})
    app = create_app(idp_settings, repo=repo, blobs=blobs, token_verifier=verifier)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as c:
        yield c


def bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


def assert_401(r):
    assert r.status_code == 401
    assert r.json()["details"][0]["code"] == "unauthenticated"


# ---- ID tokens ----


async def test_valid_token_resolves_uid_and_creates_user(idp_client, repo):
    assert repo.get_user("u1") is None
    r = await idp_client.get("/v1/api-key", headers=bearer(mint("u1")))
    assert r.status_code == 200
    assert repo.get_user("u1") is not None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"exp_in": -3600},  # expired
        {"aud": "other-project"},
        {"iss": "https://securetoken.google.com/other"},
        {"priv": OTHER_PRIV},  # bad signature
        {"kid": "unknown"},
    ],
)
async def test_bad_tokens_are_401(idp_client, kwargs):
    assert_401(await idp_client.get("/v1/api-key", headers=bearer(mint(**kwargs))))


async def test_unverified_email_is_403_email_unverified_not_401(idp_client):
    """A14: a valid token whose email is unverified is told so (403), distinct from bad creds."""
    r = await idp_client.get("/v1/api-key", headers=bearer(mint(verified=False)))
    assert r.status_code == 403
    assert r.json()["details"][0]["code"] == "email_unverified"


@pytest.mark.parametrize("uid", ["a" * 128, "a-b_C9"])
def test_sub_accepted(uid):
    v = IdTokenVerifier(PROJECT, fetch_certs=lambda: {KID: PUB})
    assert v.verify(mint(uid)) == uid


def test_verify_claims_returns_full_claims():
    v = IdTokenVerifier(PROJECT, fetch_certs=lambda: {KID: PUB})
    claims = v.verify_claims(mint("u9"))
    assert claims["sub"] == "u9" and claims["email_verified"] is True
    assert claims["aud"] == PROJECT


def test_verify_claims_unverified_email_raises_unless_allowed():
    from onolys_api.auth.idtoken import EmailNotVerified

    v = IdTokenVerifier(PROJECT, fetch_certs=lambda: {KID: PUB})
    with pytest.raises(EmailNotVerified):
        v.verify_claims(mint(verified=False))
    assert v.verify_claims(mint(verified=False), allow_unverified=True)["sub"] == "u1"


@pytest.mark.parametrize(
    "kwargs",
    [{"aud": "other"}, {"iss": "https://evil"}, {"exp_in": -60}, {"priv": OTHER_PRIV}, {"uid": ""}],
)
def test_verify_claims_rejects_bad_tokens(kwargs):
    v = IdTokenVerifier(PROJECT, fetch_certs=lambda: {KID: PUB})
    with pytest.raises(InvalidToken):
        v.verify_claims(mint(**kwargs))


def test_verify_claims_garbage_is_invalid():
    v = IdTokenVerifier(PROJECT, fetch_certs=lambda: {KID: PUB})
    with pytest.raises(InvalidToken):
        v.verify_claims("not-a-jwt")


@pytest.mark.parametrize("uid", ["a" * 129, "", "a/b", 123, None, ["x"]])
def test_sub_rejected(uid):
    v = IdTokenVerifier(PROJECT, fetch_certs=lambda: {KID: PUB})
    with pytest.raises(InvalidToken):
        v.verify(mint(uid))


@pytest.mark.parametrize(
    "kwargs, ok",
    [
        ({"exp_in": -9}, True),  # just expired, inside the 10s skew
        ({"exp_in": -11}, False),
        ({"iat_in": 9}, True),  # issued slightly in the future
        ({"iat_in": 11}, False),
    ],
)
def test_clock_skew_window(kwargs, ok, monkeypatch):
    # Freeze the clock the JWT library reads, and mint against the same instant, so the
    # +-9/+-11s boundary cannot straddle a real second tick (FX53).
    frozen = datetime(2026, 1, 1, 12, 0, 0)
    monkeypatch.setattr(_helpers, "utcnow", lambda: frozen)
    now = _helpers.datetime_to_secs(frozen)
    v = IdTokenVerifier(PROJECT, fetch_certs=lambda: {KID: PUB})
    if ok:
        assert v.verify(mint("u1", now=now, **kwargs)) == "u1"
    else:
        with pytest.raises(InvalidToken):
            v.verify(mint("u1", now=now, **kwargs))


async def test_garbage_and_missing_credentials_are_401(idp_client):
    assert_401(await idp_client.get("/v1/api-key", headers=bearer("not-a-jwt")))
    assert_401(await idp_client.get("/v1/api-key"))
    assert_401(await idp_client.get("/v1/api-key", headers=bearer("test:u1")))  # no fake in idp


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _verifier(certs, clock, **kw):
    calls = []

    def fetch():
        calls.append(1)
        if isinstance(certs, Exception):
            raise certs
        return dict(certs)

    return IdTokenVerifier(PROJECT, fetch_certs=fetch, clock=clock, **kw), calls


async def test_cert_rotation_refetches_once():
    clock, certs = _Clock(), {"old": "x"}
    v, calls = _verifier(certs, clock)
    assert v._get_certs() == {"old": "x"}
    certs.clear()
    certs[KID] = PUB
    clock.t += 61  # past the min refresh interval
    assert v.verify(mint("u9")) == "u9"
    assert len(calls) == 2
    assert v.verify(mint("u9")) == "u9"  # kid now cached: no further fetch
    assert len(calls) == 2


async def test_unknown_kid_flood_fetches_once_then_is_negative_cached():
    clock, calls_certs = _Clock(), {KID: PUB}
    v, calls = _verifier(calls_certs, clock)
    assert v.verify(mint("u1")) == "u1"
    assert len(calls) == 1
    clock.t += 61
    for i in range(5):  # 5 distinct unknown kids, then repeats of the first
        with pytest.raises(InvalidToken):
            v.verify(mint(kid=f"junk{i}"))
    assert len(calls) == 2  # one refresh, the rest inside min interval
    clock.t += 61  # past the min interval, repeat kid is still negative-cached
    with pytest.raises(InvalidToken):
        v.verify(mint(kid="junk0"))
    assert len(calls) == 2
    assert v.verify(mint("u1")) == "u1"  # legit callers unaffected


async def test_failed_refresh_serves_stale_certs():
    clock, certs = _Clock(), {KID: PUB}
    v, calls = _verifier(certs, clock)
    assert v.verify(mint("u1")) == "u1"
    v._fetch = lambda: (_ for _ in ()).throw(OSError("down"))
    clock.t += 3601  # TTL expired, fetch fails: keep serving the old certs
    assert v.verify(mint("u1")) == "u1"
    with pytest.raises(InvalidToken):  # unknown kid while upstream is down: 401, not 503
        v.verify(mint(kid="nope"))


async def test_cert_ttl_boundary_and_no_refetch_within_ttl():
    clock, certs = _Clock(), {KID: PUB}
    v, calls = _verifier(certs, clock, ttl_s=100)
    v._get_certs()
    clock.t += 100  # exactly the ttl: still fresh
    v._get_certs()
    assert len(calls) == 1
    clock.t += 0.5  # just past
    v._get_certs()
    assert len(calls) == 2
    v._get_certs()  # default force=False: cached
    assert len(calls) == 2


async def test_forced_refresh_respects_min_interval_boundary():
    clock, certs = _Clock(), {KID: PUB}
    v, calls = _verifier(certs, clock, min_refresh_s=60)
    v._get_certs()
    clock.t += 59.9
    v._get_certs(force=True)
    assert len(calls) == 1
    clock.t += 0.1  # exactly min interval
    v._get_certs(force=True)
    assert len(calls) == 2


async def test_cert_fetch_failure_is_503(repo, blobs, idp_settings):
    def boom():
        raise OSError("down")

    app = create_app(
        idp_settings, repo=repo, blobs=blobs, token_verifier=IdTokenVerifier(PROJECT, boom)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as c:
        r = await c.get("/v1/api-key", headers=bearer(mint()))
    assert r.status_code == 503


# ---- fake auth ----


async def test_fake_auth_accepts_test_uid(client):
    r = await client.get("/v1/api-key", headers=bearer("test:alice"))
    assert r.status_code == 200 and r.json() == {
        "active": False,
        "key_id": None,
        "created": None,
        "last_used_at": None,
    }


@pytest.mark.parametrize("tok", ["alice", "test:", "test:a/b", "other:alice"])
async def test_fake_auth_rejects_malformed(client, tok):
    assert_401(await client.get("/v1/api-key", headers=bearer(tok)))


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_fake_auth_refused_outside_local_test(env, blobs):
    s = Settings(env=env, service_mode="api", auth_mode="fake")  # bypasses from_env validation
    with pytest.raises(ConfigError):
        create_app(s, repo=FakeRepo(blobs), blobs=blobs)
    with pytest.raises(ConfigError):
        Settings.from_env(
            {"APP_BASE_URL": "https://app.onolys.com", "ENV": env, "AUTH_MODE": "fake"}
        )


def test_idp_requires_project(blobs):
    s = Settings(env="staging", service_mode="api", auth_mode="idp")
    with pytest.raises(ConfigError):
        create_app(s, repo=FakeRepo(blobs), blobs=blobs)


# ---- API keys ----


def test_key_format_and_hash():
    key_id, full, digest = new_key()
    parsed = parse_key(full)
    assert parsed is not None and parsed[0] == key_id
    assert digest == hash_secret(parsed[1]) and digest != parsed[1] and digest not in full
    assert parse_key("onolys_zz_short") is None


async def test_api_key_lifecycle(client, app):
    repo = app.state.repo
    h = bearer("test:alice")
    created = (await client.post("/v1/api-key", headers=h)).json()
    key = created["api_key"]
    assert key.startswith(f"onolys_{created['key_id']}_")
    secret = parse_key(key)[1]

    stored = repo.active_api_key("alice")
    assert stored.hash != secret and stored.hash == hash_secret(secret)
    assert secret not in repr(stored.to_store())

    info = (await client.get("/v1/api-key", headers=h)).json()
    assert info["active"] and info["key_id"] == created["key_id"] and "api_key" not in info

    # key authenticates as the same uid, and records last_used_at
    # (a key cannot reach /api-key, so use a second token user to prove uid mapping below)
    assert repo.get_api_key(created["key_id"]).last_used_at is None
    r = await client.get("/v1/api-key", headers={"X-API-Key": key})
    assert r.status_code == 403  # authenticated, but token-only route
    assert repo.get_api_key(created["key_id"]).last_used_at is not None


async def test_api_key_refused_on_key_management(client):
    key = (await client.post("/v1/api-key", headers=bearer("test:alice"))).json()["api_key"]
    for method in ("GET", "POST", "DELETE"):
        r = await client.request(method, "/v1/api-key", headers={"X-API-Key": key})
        assert r.status_code == 403
        assert r.json()["details"][0]["code"] == "forbidden"
    # and nothing was revoked or replaced
    assert (await client.get("/v1/api-key", headers=bearer("test:alice"))).json()["active"]


async def test_regenerate_invalidates_old_key(client, app):
    repo = app.state.repo
    h = bearer("test:alice")
    old = (await client.post("/v1/api-key", headers=h)).json()
    new = (await client.post("/v1/api-key", headers=h)).json()
    assert old["key_id"] != new["key_id"]
    auth = app.state.auth
    assert auth.authenticate(None, new["api_key"]).uid == "alice"
    from onolys_api.errors import ApiError

    with pytest.raises(ApiError) as e:
        auth.authenticate(None, old["api_key"])
    assert e.value.status == 401 and e.value.details[0]["code"] == "unauthenticated"
    assert repo.get_api_key(old["key_id"]).revoked_at is not None


async def test_revoked_key_is_401_over_http(client, app):
    h = bearer("test:alice")
    key = (await client.post("/v1/api-key", headers=h)).json()["api_key"]
    assert (await client.delete("/v1/api-key", headers=h)).status_code == 204
    assert (await client.delete("/v1/api-key", headers=h)).status_code == 204  # idempotent
    assert not (await client.get("/v1/api-key", headers=h)).json()["active"]
    r = await client.get("/v1/api-key", headers={"X-API-Key": key})
    assert_401(r)


@pytest.mark.parametrize(
    "bad",
    [
        "garbage",
        "onolys_0123456789abcdef_" + "A" * 43,  # unknown id
    ],
)
async def test_bad_or_unknown_key_is_401(client, bad):
    assert_401(await client.get("/v1/api-key", headers={"X-API-Key": bad}))


async def test_wrong_secret_is_401(client):
    created = (await client.post("/v1/api-key", headers=bearer("test:alice"))).json()
    forged = f"onolys_{created['key_id']}_" + "B" * 43
    assert_401(await client.get("/v1/api-key", headers={"X-API-Key": forged}))


async def test_key_maps_to_owner_uid(client, app):
    ka = (await client.post("/v1/api-key", headers=bearer("test:alice"))).json()["api_key"]
    kb = (await client.post("/v1/api-key", headers=bearer("test:bob"))).json()["api_key"]
    assert app.state.auth.authenticate(None, ka).uid == "alice"
    user = app.state.auth.authenticate(None, kb)
    assert (user.uid, user.auth_kind) == ("bob", "api_key")


async def test_healthz_needs_no_auth(client):
    assert (await client.get("/v1/healthz")).status_code == 200


# ---- Authenticator internals (mutation survivors M5-M7) ----


def _idp(auth_project="", gcp_project="", verifier=None):
    s = Settings(
        env="staging", service_mode="api", auth_mode="idp",
        auth_project=auth_project, gcp_project=gcp_project,
    )  # fmt: skip
    return Authenticator(s, FakeRepo(None), verifier)


def test_idp_project_falls_back_to_gcp_project():
    assert _idp(gcp_project="gp")._verifier._project == "gp"
    assert _idp(auth_project="ap", gcp_project="gp")._verifier._project == "ap"


def test_idp_without_any_project_is_a_config_error():
    with pytest.raises(ConfigError):
        _idp()
    _idp(verifier=IdTokenVerifier(PROJECT, lambda: {}))  # injected verifier needs no project


def _key(client_repo, secret="S" * 43, kid="0123456789abcdef", **doc):
    client_repo.create_api_key(
        "alice", kid, ApiKeyDoc(uid="alice", hash=hash_secret(secret), **doc)
    )
    return f"onolys_{kid}_{secret}"


async def test_unknown_key_still_compares_against_a_64_char_dummy(client, app, monkeypatch):
    seen = []
    real = deps.secret_matches
    monkeypatch.setattr(deps, "secret_matches", lambda s, h: seen.append(h) or real(s, h))
    with pytest.raises(ApiError):
        app.state.auth.authenticate(None, "onolys_0123456789abcdef_" + "A" * 43)
    assert seen == ["0" * 64]


async def test_last_used_throttle_boundary(client, app, monkeypatch):
    repo = app.state.auth._repo
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    key = _key(repo, last_used_at=t0)
    now = [t0 + timedelta(seconds=59)]

    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return now[0]

    monkeypatch.setattr(deps, "datetime", FakeDT)
    app.state.auth.authenticate(None, key)
    assert repo.get_api_key("0123456789abcdef").last_used_at == t0  # inside the minute
    now[0] = t0 + deps.LAST_USED_EVERY  # exactly the interval: written
    app.state.auth.authenticate(None, key)
    assert repo.get_api_key("0123456789abcdef").last_used_at == now[0]


async def test_seen_set_is_cleared_only_when_full(client, app, monkeypatch):
    monkeypatch.setattr(deps, "_SEEN_CAP", 3)
    a = app.state.auth
    for uid in ("u1", "u2", "u3"):
        a.authenticate(f"test:{uid}", None)
    assert a._seen == {"u1", "u2", "u3"}  # at the cap but not over: kept
    a.authenticate("test:u4", None)
    assert a._seen == {"u4"}  # full: evicted, then the new uid recorded


async def test_current_user_records_auth_kind(client, app):
    repo = app.state.auth._repo
    key = _key(repo)
    for tok, key_hdr, kind in (("test:alice", None, "token"), (None, key, "api_key")):
        req = SimpleNamespace(app=app, state=SimpleNamespace(auth_kind=None))
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok) if tok else None
        user = deps.current_user(req, creds, key_hdr)
        assert (user.auth_kind, req.state.auth_kind) == (kind, kind)
