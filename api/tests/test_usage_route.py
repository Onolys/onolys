"""GET /v1/usage: eval + interview x UTC day, used/cap/resets_at (SP11 R8, D3, AC7)."""

from datetime import UTC, datetime

import httpx
import pytest

from onolys_api.app import create_app
from onolys_api.config import Settings
from onolys_api.repo.fake import FakeRepo
from onolys_api.storage.fake import FakeBlobStore

A = {"Authorization": "Bearer test:alice"}


@pytest.fixture
def repo(tmp_path):
    return FakeRepo(FakeBlobStore(tmp_path / "b"))


@pytest.fixture
async def api(tmp_path, repo):
    app = create_app(
        Settings(
            env="test",
            auth_mode="fake",
            service_mode="combined",
            eval_cap_day=20,
            ai_cap_day=4,
        ),
        repo=repo,
        blobs=FakeBlobStore(tmp_path / "b2"),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as c:
        yield c


def seed(repo, uid, key, **fields):
    d = repo._get(f"usage/{uid}_{key}") or {}
    repo._put(f"usage/{uid}_{key}", {**d, **fields})


def today():
    return datetime.now(UTC).strftime("%Y-%m-%d")


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


async def test_requires_auth(api):
    assert (await api.get("/v1/usage")).status_code == 401


async def test_shape_defaults_and_resets(api):
    r = await api.get("/v1/usage", headers=A)
    assert r.status_code == 200
    b = r.json()
    assert set(b) == {"eval", "interview"}
    for kind in b.values():
        assert set(kind) == {"day"}  # no monthly period
        for p in kind.values():
            assert set(p) == {"used", "cap", "resets_at"} and p["used"] == 0
    assert b["eval"]["day"]["cap"] == 20 and b["interview"]["day"]["cap"] == 4
    now = datetime.now(UTC)
    for kind in b.values():
        d = ts(kind["day"]["resets_at"])
        assert now < d and (d.hour, d.minute, d.second) == (0, 0, 0)


async def test_used_counts_both_kinds(api, repo):
    seed(repo, "alice", today(), runs=3, interviews=2)
    b = (await api.get("/v1/usage", headers=A)).json()
    assert (b["eval"]["day"]["used"], b["interview"]["day"]["used"]) == (3, 2)


async def test_overrides_reflected(api, repo):
    repo._put(
        "users/alice",
        {"limits": {"eval": {"day": 9}, "interview": {"month": 12}}},
    )
    b = (await api.get("/v1/usage", headers=A)).json()
    assert b["eval"]["day"]["cap"] == 9
    assert b["interview"]["day"]["cap"] == 4  # a stale `month` override is ignored


async def test_used_above_cap_after_lowered_override(api, repo):
    seed(repo, "alice", today(), runs=8, interviews=3)
    repo._put("users/alice", {"limits": {"eval": {"day": 2}, "interview": {"day": 1}}})
    b = (await api.get("/v1/usage", headers=A)).json()
    assert b["eval"]["day"]["used"] == 8 > b["eval"]["day"]["cap"] == 2
    assert b["interview"]["day"]["used"] == 3 > b["interview"]["day"]["cap"] == 1


async def test_per_user_isolation(api, repo):
    seed(repo, "bob", today(), runs=4, interviews=2)
    repo._put("users/bob", {"limits": {"eval": {"day": 1}}})
    b = (await api.get("/v1/usage", headers=A)).json()
    assert b["eval"]["day"] == {**b["eval"]["day"], "used": 0, "cap": 20}
    assert b["interview"]["day"]["used"] == 0


@pytest.mark.parametrize(
    "raw", [{"limits": "oops"}, {"limits": [1]}, {"limits": 5}]
)
async def test_malformed_user_limits_never_500_and_use_defaults(api, repo, raw):
    repo._put("users/alice", raw)
    r = await api.get("/v1/usage", headers=A)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["eval"]["day"]["cap"] == 20 and b["interview"]["day"]["cap"] == 4
    assert repo.ensure_user("alice") is not None  # every route's ensure_user survives it
