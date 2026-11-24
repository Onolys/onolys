"""Task 7: `/v1/auth/email/*` routes (R1, R10, D5, D6; AC1-AC7)."""

import json
import logging

import httpx
import pytest
from test_auth import KID, PROJECT, PUB, bearer, mint

from onolys_api.adapters.base import AdapterError, AuthAccount
from onolys_api.adapters.fake import FakeAuthLinks, FakeEmailSender
from onolys_api.app import create_app
from onolys_api.auth.idtoken import IdTokenVerifier
from onolys_api.config import Settings
from onolys_api.email.rate import MemoryRateStore
from onolys_api.repo.fake import FakeRepo

pytestmark = pytest.mark.unit

BASE = "https://onolys-app-staging.web.app"
EMAIL = "phi.person@example.org"
VERIFY = "/v1/auth/email/verification"
RESET = "/v1/auth/email/password-reset"


def accounts():
    return {
        "u1": AuthAccount(email=EMAIL, email_verified=False),
        "u2": AuthAccount(email="done@example.org", email_verified=True),
        "u3": AuthAccount(email="off@example.org", disabled=True),
    }


class Env:
    def __init__(self, blobs, sender=None, links=None):
        self.sender = sender or FakeEmailSender()
        self.links = links or FakeAuthLinks(accounts())
        settings = Settings(
            env="staging", service_mode="api", auth_mode="idp", auth_project=PROJECT,
            app_base_url=BASE, uid_hmac_key="k", adapters="stub",
        )  # fmt: skip
        self.app = create_app(
            settings,
            repo=FakeRepo(blobs),
            blobs=blobs,
            token_verifier=IdTokenVerifier(PROJECT, fetch_certs=lambda: {KID: PUB}),
            email_sender=self.sender,
            auth_links=self.links,
            email_rate_store=MemoryRateStore(),
        )

    def client(self):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://t",
        )


@pytest.fixture
def env(blobs):
    return Env(blobs)


async def test_verify_sends_to_account_address_with_configured_host(env):  # AC1, AC3
    async with env.client() as c:
        r = await c.post(
            VERIFY,
            json={"next": "/sessions"},
            headers={**bearer(mint(verified=False)), "Host": "evil.test",
                     "Origin": "https://evil.test", "X-Forwarded-Host": "evil.test"},
        )  # fmt: skip
    assert r.status_code == 202 and r.json() == {}
    [m] = env.sender.messages
    assert m["to"] == EMAIL
    assert f"{BASE}/auth/action?mode=verifyEmail&oobCode=" in m["text"]
    assert "evil.test" not in m["text"] + m["html"]


async def test_reset_sends_reset_mode(env):  # AC1
    async with env.client() as c:
        r = await c.post(RESET, json={"email": EMAIL})
    assert r.status_code == 202 and r.json() == {}
    [m] = env.sender.messages
    assert m["to"] == EMAIL and f"{BASE}/auth/action?mode=resetPassword" in m["text"]


async def test_reset_identical_for_known_unknown_disabled_limited_and_errors(blobs):  # AC2
    env = Env(blobs)
    async with env.client() as c:
        known = await c.post(RESET, json={"email": EMAIL})
        limited = await c.post(RESET, json={"email": EMAIL})
        unknown = await c.post(RESET, json={"email": "nobody@example.org"})
        disabled = await c.post(RESET, json={"email": "off@example.org"})
    outs = [known, limited, unknown, disabled]
    assert {(r.status_code, r.text) for r in outs} == {(202, "{}")}
    assert [m["to"] for m in env.sender.messages] == [EMAIL]  # unknown/disabled/limited: nothing

    class Boom(FakeAuthLinks):
        def password_reset(self, email):
            raise AdapterError("auth_links_failed")

    env2 = Env(blobs, links=Boom(accounts()))
    async with env2.client() as c:
        r = await c.post(RESET, json={"email": EMAIL})
    assert (r.status_code, r.text) == (202, "{}") and env2.sender.messages == []


async def test_reset_send_failure_after_202_is_only_logged(blobs, caplog):
    class Down(FakeEmailSender):
        def send(self, *a):
            e = AdapterError("email_send_failed")
            e.provider_status = 500
            raise e

    env = Env(blobs, sender=Down())
    with caplog.at_level(logging.INFO):
        async with env.client() as c:
            r = await c.post(RESET, json={"email": EMAIL})
    assert (r.status_code, r.text) == (202, "{}")
    lines = [json.loads(x.getMessage()) for x in caplog.records if x.name == "onolys_api.events"]
    ev = [d for d in lines if d["message"] == "auth_email"]
    assert ev[0]["outcome"] == "send_failed" and ev[0]["provider_status"] == 500


async def test_verify_auth_matrix_and_already_verified(env):  # AC4
    async with env.client() as c:
        assert (await c.post(VERIFY, json={})).status_code == 401
        r = await c.post(VERIFY, json={}, headers={"X-API-Key": "onolys_x_y"})
        assert r.status_code == 403
        r = await c.post(VERIFY, json={}, headers=bearer(mint("u2", verified=True)))
        assert (r.status_code, r.json()) == (202, {})
        assert env.sender.messages == []
        r = await c.post(VERIFY, json={}, headers=bearer(mint("u1", verified=False)))
        assert r.status_code == 202
    assert len(env.sender.messages) == 1


async def test_verify_second_within_minute_429_and_send_failure_503(blobs):  # AC5
    env = Env(blobs)
    async with env.client() as c:
        h = bearer(mint(verified=False))
        assert (await c.post(VERIFY, json={}, headers=h)).status_code == 202
        r = await c.post(VERIFY, json={}, headers=h)
    assert r.status_code == 429 and r.json()["details"][0]["code"] == "rate_limited"
    assert len(env.sender.messages) == 1

    class Down(FakeEmailSender):
        def send(self, *a):
            raise AdapterError("email_send_failed")

    env2 = Env(blobs, sender=Down())
    async with env2.client() as c:
        r = await c.post(VERIFY, json={}, headers=bearer(mint(verified=False)))
    assert r.status_code == 503
    assert r.json()["details"] == [
        {"code": "email_unavailable", "message": "Email is temporarily unavailable."}
    ]


async def test_logs_never_contain_email_link_or_code(blobs, caplog):  # AC6
    env = Env(blobs)
    with caplog.at_level(logging.DEBUG):
        async with env.client() as c:
            await c.post(VERIFY, json={}, headers=bearer(mint(verified=False)))
            await c.post(VERIFY, json={}, headers=bearer(mint(verified=False)))  # 429
            await c.post(RESET, json={"email": EMAIL})
            await c.post(RESET, json={"email": "nobody@example.org"})
    ours = "\n".join(
        r.getMessage() for r in caplog.records if r.name.split(".")[0] not in {"httpx", "httpcore"}
    )
    assert "auth_email" in ours
    for secret in (EMAIL, "nobody@example.org", "oobCode", "fake-verify", "fake-reset",
                   "/auth/action", BASE):  # fmt: skip
        assert secret not in ours
    reset_lines = [
        json.loads(x.getMessage()) for x in caplog.records
        if x.name == "onolys_api.events" and '"email_kind": "reset"' in x.getMessage()
    ]  # fmt: skip
    assert reset_lines and all("uid_hash" not in d for d in reset_lines)


async def test_app_serves_without_resend_key_and_verify_503(blobs):  # AC7
    settings = Settings(
        env="staging", service_mode="api", auth_mode="idp", auth_project=PROJECT,
        app_base_url=BASE, uid_hmac_key="k", adapters="real", resend_api_key="",
    )  # fmt: skip
    app = create_app(
        settings,
        repo=FakeRepo(blobs),
        blobs=blobs,
        token_verifier=IdTokenVerifier(PROJECT, fetch_certs=lambda: {KID: PUB}),
        auth_links=FakeAuthLinks(accounts()),
        email_rate_store=MemoryRateStore(),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as c:
        assert (await c.get("/v1/healthz")).status_code == 200
        r = await c.post(VERIFY, json={}, headers=bearer(mint(verified=False)))
        assert r.status_code == 503
        assert r.json()["details"][0]["code"] == "email_unavailable"
        r = await c.post(RESET, json={"email": EMAIL})
        assert (r.status_code, r.text) == (202, "{}")


async def test_already_verified_consumes_no_rate_slot(env):  # AC4, R1
    env.links.accounts["u1"] = AuthAccount(email=EMAIL, email_verified=True)
    async with env.client() as c:
        h = bearer(mint("u1", verified=True))
        for _ in range(3):
            assert (await c.post(VERIFY, json={}, headers=h)).status_code == 202
        assert env.sender.messages == []
        env.links.accounts["u1"] = AuthAccount(email=EMAIL, email_verified=False)
        r = await c.post(VERIFY, json={}, headers=h)
    assert r.status_code == 202 and len(env.sender.messages) == 1  # not 429


async def test_reset_ip_bucket_ignores_spoofed_forwarded_prefix(blobs):
    env = Env(blobs)
    async with env.client() as c:
        for i in range(20):
            xff = f"10.0.0.{i}, 203.0.113.9, 130.211.0.1"
            assert (await c.post(RESET, json={"email": f"x{i}@example.org"},
                                 headers={"X-Forwarded-For": xff})).status_code == 202  # fmt: skip
        r = await c.post(RESET, json={"email": EMAIL},
                         headers={"X-Forwarded-For": "10.9.9.9, 203.0.113.9, 130.211.0.1"})  # fmt: skip
    assert r.status_code == 202 and env.sender.messages == []  # 21st from the same real IP


@pytest.mark.parametrize("mode", ["worker", "voice"])
async def test_worker_and_voice_start_without_app_base_url(blobs, mode):
    settings = Settings.from_env({"ENV": "staging", "SERVICE_MODE": mode, "UID_HMAC_KEY": "k",
                                  "ADAPTERS": "stub", "AUTH_MODE": "idp", "AUTH_PROJECT": PROJECT,
                                  "WORKER_URL": "https://w.run.app", "TASKS_SA": "t@p.iam"})  # fmt: skip
    app = create_app(settings, repo=FakeRepo(blobs), blobs=blobs,
                     token_verifier=IdTokenVerifier(PROJECT, fetch_certs=lambda: {KID: PUB}))  # fmt: skip
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as c:
        assert (await c.get("/v1/healthz")).status_code == 200


async def test_api_starts_without_app_base_url_verify_503_reset_logged(blobs, caplog):
    settings = Settings.from_env({"ENV": "staging", "SERVICE_MODE": "api", "UID_HMAC_KEY": "k",
                                  "ADAPTERS": "stub", "AUTH_MODE": "idp", "AUTH_PROJECT": PROJECT})  # fmt: skip
    sender = FakeEmailSender()
    app = create_app(settings, repo=FakeRepo(blobs), blobs=blobs,
                     token_verifier=IdTokenVerifier(PROJECT, fetch_certs=lambda: {KID: PUB}),
                     auth_links=FakeAuthLinks(accounts()), email_sender=sender,
                     email_rate_store=MemoryRateStore())  # fmt: skip
    with caplog.at_level(logging.INFO):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
        ) as c:
            assert (await c.get("/v1/healthz")).status_code == 200
            r = await c.post(VERIFY, json={}, headers=bearer(mint(verified=False)))
            assert r.status_code == 503
            assert r.json()["details"][0]["code"] == "email_unavailable"
            r = await c.post(RESET, json={"email": EMAIL})
            assert (r.status_code, r.text) == (202, "{}")
    assert sender.messages == []
    outs = [json.loads(x.getMessage()).get("outcome") for x in caplog.records
            if x.name == "onolys_api.events" and '"email_kind": "reset"' in x.getMessage()]  # fmt: skip
    assert "unconfigured" in outs
