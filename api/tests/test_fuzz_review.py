"""Property / fuzz tests from the full-app review (docs/agent_files/review-full-app-20261121).

They assert the CORRECT behaviour. Known bugs are `xfail(strict=True)` tagged with their finding id
(A# = static review, F# = fuzz review), so they flip to a failure (XPASS) once fixed: then drop the
marker. Runs on the in-memory FakeRepo and, when FIRESTORE_EMULATOR_HOST is set, on Firestore.
"""

import os
import uuid

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from onolys_api.app import create_app
from onolys_api.config import Settings
from onolys_api.repo.fake import FakeRepo
from onolys_api.storage.fake import FakeBlobStore

pytestmark = pytest.mark.integration
HAS_EMULATOR = bool(os.environ.get("FIRESTORE_EMULATOR_HOST"))
HSET = settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
ALICE = {"Authorization": "Bearer test:alice"}
BOB = {"Authorization": "Bearer test:bob"}


def _make_api(kind, tmp_path):
    """Generator: (sync httpx client, kind) bound to a fresh app on the chosen repo."""
    blobs = FakeBlobStore(tmp_path / "blobs")
    if kind == "fake":
        repo = FakeRepo(blobs)
    else:
        if not HAS_EMULATOR:
            pytest.skip("FIRESTORE_EMULATOR_HOST not set")
        from google.auth.credentials import AnonymousCredentials
        from google.cloud import firestore

        from onolys_api.repo.firestore import FirestoreRepo

        repo = FirestoreRepo(
            firestore.Client(project="demo-onolys", credentials=AnonymousCredentials()), blobs
        )
    app = create_app(
        Settings(
            env="test",
            service_mode="combined",
            auth_mode="fake",
            git_sha="x",
            cors_origins=("https://app.onolys.com",),
        ),
        repo=repo,
        blobs=blobs,
    )
    from starlette.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as c:
        c.kind = kind  # type: ignore[attr-defined]
        yield c


# "firestore" in the param id makes conftest auto-add the `firestore` marker (emulator CI job).
FS_PARAM = pytest.param("firestore", marks=[pytest.mark.integration, pytest.mark.firestore])


@pytest.fixture(params=["fake", FS_PARAM])
def api(request, tmp_path):
    yield from _make_api(request.param, tmp_path)


@pytest.fixture
def fake_api(tmp_path):
    """In-memory repo only (fast, xdist-safe, never builds a Firestore client)."""
    yield from _make_api("fake", tmp_path)


@pytest.fixture(params=[FS_PARAM])
def fs_api(request, tmp_path):
    """Firestore emulator only (the emulator job is serial: keep these few)."""
    yield from _make_api("firestore", tmp_path)


def _uid() -> dict:
    return {"Authorization": f"Bearer test:u{uuid.uuid4().hex[:12]}"}


def known_bug(request, reason: str):
    """Mark this test as a known bug (strict xfail: an unexpected pass fails, so fixes surface)."""
    request.applymarker(pytest.mark.xfail(strict=True, reason=reason))


# ---- unvalidated path ids and cursors must never 500 ------------------------------

ID_ROUTES = [
    ("get", "/v1/sessions/{x}"),
    ("delete", "/v1/sessions/{x}"),
    ("get", "/v1/sessions/{x}/transcript"),
    ("get", "/v1/sessions/{x}/speakers"),
    ("get", "/v1/sessions/{x}/runs"),
    ("get", "/v1/sessions/{x}/rating"),
    ("get", "/v1/sessions/{x}/reports"),
    ("get", "/v1/sessions/{x}/audio"),
    ("get", "/v1/runs/{x}"),
    ("get", "/v1/interviews/{x}"),
]
WEIRD_IDS = [".", "%2e", "é" * 40, "0" * 5000, "\x00"]
# Reserved doc ids and over-long ids used to reach Firestore -> InvalidArgument -> 500.
FS_BAD_IDS = {"__x__", "%2e"}


def _seg(x: str) -> str:
    from urllib.parse import quote

    return x if "%" in x else quote(x, safe="")


@pytest.mark.parametrize("x", WEIRD_IDS)
@pytest.mark.parametrize(("method", "tpl"), ID_ROUTES[:2] + ID_ROUTES[-4:])
def test_weird_path_ids_never_5xx(fake_api, method, tpl, x):
    r = fake_api.request(method, tpl.format(x=_seg(x)), headers=_uid())
    assert r.status_code < 500, (r.status_code, x)


@pytest.mark.parametrize("x", sorted(FS_BAD_IDS | {"0" * 5000}))
@pytest.mark.parametrize(("method", "tpl"), ID_ROUTES[:6] + ID_ROUTES[-2:])
def test_weird_path_ids_never_5xx_firestore(fs_api, method, tpl, x):
    r = fs_api.request(method, tpl.format(x=_seg(x)), headers=_uid())
    assert r.status_code < 500, (r.status_code, x)


@pytest.mark.parametrize("path", ["/v1/sessions/{x}", "/v1/runs/{x}", "/v1/interviews/{x}"])
@HSET
@given(
    x=st.text(alphabet=st.characters(blacklist_categories=("Cs", "Cc")), max_size=60).filter(
        lambda v: "%" not in v and not (v.startswith("__") and v.endswith("__")) and set(v) != {"."}
    )
)
def test_random_path_ids_are_404_not_5xx(fake_api, path, x):
    api = fake_api
    r = api.get(path.format(x=_seg(x)), headers=_uid())
    assert r.status_code < 500, (r.status_code, x)


@pytest.mark.parametrize("c", ["a/b", "__x__", ".", "é", "%", "=" * 9, "e30", "!!!!"])
def test_list_cursor_never_5xx(api, c):
    r = api.get("/v1/sessions", params={"cursor": c}, headers=_uid())
    assert r.status_code < 500, (r.status_code, c)


@HSET
@given(limit=st.integers(min_value=-5, max_value=500))
def test_list_limit_never_5xx(fake_api, limit):
    api = fake_api
    r = api.get("/v1/sessions", params={"limit": limit}, headers=_uid())
    assert r.status_code in (200, 422)


# ---- create params: n_runs / preset / language / title ----------------------------------------

bodies = st.fixed_dictionaries(
    {},
    optional={
        "language": st.one_of(st.text(max_size=20), st.sampled_from(["auto", "en", "zz", "en-US"])),
        "n_runs": st.one_of(st.integers(-3, 9), st.text(max_size=3), st.none(), st.floats()),
        "preset": st.one_of(
            st.none(), st.text(max_size=70), st.sampled_from(["claude", "default"])
        ),
        "title": st.one_of(st.none(), st.text(max_size=210)),
        "interview_id": st.one_of(st.none(), st.text(max_size=105)),
    },
)


@HSET
@given(body=bodies)
def test_create_session_body_never_5xx(fake_api, body):
    api = fake_api
    try:
        r = api.post("/v1/sessions", json=body, headers=_uid())
    except ValueError:  # NaN/inf not JSON-serialisable client side
        return
    assert r.status_code < 500, (r.status_code, body, r.text)


def test_create_session_rejects_non_public_preset(api):
    r = api.post("/v1/sessions", json={"preset": "claude"}, headers=_uid())
    assert r.status_code == 422


@pytest.mark.parametrize("lang", ["zz", "xx-YY", "qqq"])
def test_create_session_rejects_unknown_language(api, lang):
    r = api.post("/v1/sessions", json={"language": lang}, headers=_uid())
    assert r.status_code == 422


@pytest.mark.parametrize("lang", ["auto", "en", "en-US", "ja-JP", "fr", "es-419", "fil"])
def test_create_session_accepts_supported_languages(api, lang):
    r = api.post("/v1/sessions", json={"language": lang}, headers=_uid())
    assert r.status_code == 202, r.text


def test_garbage_body_is_documented_422(api):
    r = api.post(
        "/v1/sessions", content=b"\xff", headers={**_uid(), "content-type": "application/json"}
    )
    assert r.status_code == 422


# ---- rating PUT bodies ------------------------------------------------------------------------

json_vals = st.recursive(
    st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=20)),
    lambda c: st.one_of(
        st.lists(c, max_size=3), st.dictionaries(st.text(max_size=8), c, max_size=4)
    ),
    max_leaves=12,
)


@HSET
@given(body=json_vals)
def test_rating_put_arbitrary_body_never_5xx(fake_api, body):
    api = fake_api
    h = _uid()
    sid = api.post("/v1/sessions", json={}, headers=h).json()["session"]["id"]
    r = api.put(f"/v1/sessions/{sid}/rating", json=body, headers=h)
    assert r.status_code < 500, (r.status_code, body, r.text)


@HSET
@given(body=json_vals)
def test_speakers_confirm_arbitrary_body_never_5xx(fake_api, body):
    api = fake_api
    h = _uid()
    sid = api.post("/v1/sessions", json={}, headers=h).json()["session"]["id"]
    r = api.post(f"/v1/sessions/{sid}/speakers/confirm", json=body, headers=h)
    assert r.status_code < 500, (r.status_code, body, r.text)


# ---- idempotency keys -------------------------------------------------------------------------

keys = st.one_of(
    st.text(min_size=0, max_size=260), st.sampled_from(["k", "é" * 100, " ", "a" * 200, "a" * 201])
)


@HSET
@given(key=keys)
def test_idempotency_key_never_5xx_and_replays(fake_api, key):
    api = fake_api
    try:
        h = {**_uid(), "Idempotency-Key": key}
        r1 = api.post("/v1/sessions", json={}, headers=h)
    except (UnicodeEncodeError, ValueError):
        return  # header not representable on the wire
    assert r1.status_code < 500, (r1.status_code, key)
    if r1.status_code == 202:
        r2 = api.post("/v1/sessions", json={}, headers=h)
        assert r2.status_code == 202
        assert r2.json()["session"]["id"] == r1.json()["session"]["id"]


def test_idempotent_replay_after_delete_does_not_return_deleted_session(request, api):
    h = {**_uid(), "Idempotency-Key": "k-del"}
    sid = api.post("/v1/sessions", json={}, headers=h).json()["session"]["id"]
    assert api.delete(f"/v1/sessions/{sid}", headers=h).status_code in (200, 202, 204)
    r = api.post("/v1/sessions", json={}, headers=h)
    assert r.status_code != 202 or r.json()["session"]["id"] != sid


# ---- concurrency / races ----------------------------------------------------------------------


def _concurrently(api, calls):
    """Fire all calls at once through the ASGI app (sync routes run in the threadpool)."""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=len(calls)) as ex:
        return list(ex.map(lambda f: f(), calls))


@pytest.mark.flaky
def test_concurrent_same_idempotency_key_creates_one_session(fs_api):
    api = fs_api
    h = {**_uid(), "Idempotency-Key": "race-1"}
    rs = _concurrently(api, [lambda: api.post("/v1/sessions", json={}, headers=h)] * 8)
    assert all(r.status_code < 500 for r in rs), [r.status_code for r in rs]
    ok_ids = {r.json()["session"]["id"] for r in rs if r.status_code == 202}
    losers = [r.status_code for r in rs if r.status_code != 202]
    assert len(ok_ids) == 1 and not losers, (len(ok_ids), losers)


@pytest.mark.flaky
def test_concurrent_api_key_create_leaves_single_active_key(fs_api):
    api = fs_api
    h = _uid()
    rs = _concurrently(api, [lambda: api.post("/v1/api-key", headers=h)] * 6)
    assert all(r.status_code == 201 for r in rs), [r.status_code for r in rs]
    secrets = [r.json()["api_key"] for r in rs]
    api.delete("/v1/api-key", headers=h)
    live = [s for s in secrets if api.get("/v1/usage", headers={"X-API-Key": s}).status_code == 200]
    assert live == [], f"{len(live)} key(s) still valid after DELETE"


def test_session_create_is_free_and_uncapped(fake_api):
    """Creating a session costs nothing and has no cap; only POST /runs
    (and starting an AI interview) uses a unit."""
    api = fake_api
    h = _uid()
    rs = _concurrently(api, [lambda: api.post("/v1/sessions", json={}, headers=h)] * 20)
    assert all(r.status_code == 202 for r in rs), [r.status_code for r in rs]
    usage = api.get("/v1/usage", headers=h).json()
    assert usage["eval"]["day"]["used"] == 0 and usage["interview"]["day"]["used"] == 0


# ---- response headers -------------------------------------------------------------------------


def test_phi_responses_are_no_store(request, api):
    h = _uid()
    sid = api.post("/v1/sessions", json={}, headers=h).json()["session"]["id"]
    r = api.get(f"/v1/sessions/{sid}/speakers", headers=h)
    assert "no-store" in r.headers["cache-control"]
