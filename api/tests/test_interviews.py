"""SP10 Task 4: interview API, state table, SP11 seam (R5, D11-D14, D16, AC3, AC6)."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from onolys_core.errors import ConfigError

from onolys_api.adapters import Adapters, build_adapters
from onolys_api.adapters.fake import FakeVoice
from onolys_api.app import create_app
from onolys_api.config import Settings
from onolys_api.jobs import caps
from onolys_api.jobs.interviews import settle_interview
from onolys_api.repo.fake import FakeRepo
from onolys_api.repo.models import InterviewDoc
from onolys_api.storage.fake import FakeBlobStore

pytestmark = pytest.mark.unit
A = {"Authorization": "Bearer test:alice"}
B = {"Authorization": "Bearer test:bob"}
SCENARIO = "sample-drinking-ambivalent"
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


class SpyRepo(FakeRepo):
    """FakeRepo + a call log shared by the SP11 seam, to prove ordering and refunds."""

    def __init__(self, blobs):
        super().__init__(blobs)
        self.calls: list[tuple] = []

    def reserve_usage(self, uid, kind, date, defaults, max_active):
        self.calls.append(("reserve", uid, kind, date))
        return super().reserve_usage(uid, kind, date, defaults, max_active)

    def release_usage(self, uid, kind, date, refund):
        self.calls.append(("release", uid, kind, date, refund))
        return super().release_usage(uid, kind, date, refund)

    def create_interview_reserved(self, uid, iid, doc, defaults, max_active):
        out = super().create_interview_reserved(uid, iid, doc, defaults, max_active)
        if out == "ok":
            self.calls.append(("create", uid))
        return out


@pytest.fixture
def repo(tmp_path):
    return SpyRepo(FakeBlobStore(tmp_path / "b"))


@pytest.fixture
def app(tmp_path, repo):
    a = create_app(
        Settings(
            env="test",
            auth_mode="fake",
            service_mode="combined",
            ai_cap_day=2,
            voice_url="wss://voice.example",
        ),
        repo=repo,
        blobs=FakeBlobStore(tmp_path / "b2"),
    )
    a.state.clock = lambda: NOW
    return a


@pytest.fixture
async def api(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as c:
        yield c


def usage(repo, uid="alice"):
    return repo.get_usage_doc(uid, "2026-11-21").interviews


async def create(api, headers=A, **body):
    return await api.post("/v1/interviews", headers=headers, json={"scenario_id": SCENARIO, **body})


def set_duration(repo, iid, seconds, uid="alice"):
    repo.update_interview(uid, iid, {"duration_s": seconds})


async def test_requires_auth(api):
    assert (await api.post("/v1/interviews", json={"scenario_id": SCENARIO})).status_code == 401
    assert (await api.get("/v1/interviews/x")).status_code == 401
    assert (await api.post("/v1/interviews/x/end")).status_code == 401


async def test_create_reserves_first_then_creates_doc(api, repo):
    r = await create(api)
    assert r.status_code == 201
    b = r.json()
    assert [c[0] for c in repo.calls] == ["reserve", "create"]
    assert repo.calls[0][2:] == ("interview", "2026-11-21")
    assert b["state"] == "created" and b["voice"] == "Kore"  # the scenario's default voice
    assert b["voice_url"] == f"wss://voice.example/v1/voice/{b['interview_id']}"
    assert b["limits"] == {"max_s": 600, "warn_s": 480}
    assert set(b["scenario"]) == {"id", "title", "difficulty", "summary", "language", "voice"}
    assert usage(repo) == 1
    doc = repo.get_interview("alice", b["interview_id"])
    assert (doc.uid, doc.scenario_id, doc.state, doc.reservation_date) == (
        "alice", SCENARIO, "created", "2026-11-21",
    )  # fmt: skip


async def test_voice_choice_validated_server_side(api, repo):
    ok = await create(api, voice="Puck")
    assert ok.status_code == 201 and ok.json()["voice"] == "Puck"
    bad = await create(api, voice="NotAVoice")
    assert bad.status_code == 422 and bad.json()["details"][0]["code"] == "invalid_parameters"
    unknown = await create(api, scenario_id="nope")
    assert unknown.status_code == 422
    assert usage(repo) == 1  # rejected requests reserved nothing


async def test_response_leaks_no_persona_text(api):
    text = (await create(api)).text
    for hidden in ("hidden_info", "response_rules", "persona", "opening_line", "system_prompt"):
        assert hidden not in text


class _FailingQueue:
    def enqueue(self, *a, **k):
        raise RuntimeError("queue down")


async def test_failed_create_releases_with_refund(api, repo, app):
    app.state.queue = _FailingQueue()
    r = await create(api)
    assert r.status_code == 500
    assert [c[0] for c in repo.calls] == ["reserve", "create", "release"]
    assert repo.calls[-1][-1] is True  # refund
    assert usage(repo) == 0


async def test_cap_reached_passes_through_and_creates_nothing(api, repo):
    for _ in range(2):  # day cap is 2; 300 s each so lazy abandon keeps them counted
        r = await create(api)
        assert r.status_code == 201
        set_duration(repo, r.json()["interview_id"], 300)
    r = await create(api)
    assert r.status_code == 429
    d = r.json()["details"][0]
    assert d["code"] == "interview_cap_reached" and d["period"] == "day"
    assert len([c for c in repo.calls if c[0] == "create"]) == 2  # none for the refused call
    assert usage(repo) == 2


async def test_get_returns_state_and_elapsed(api, repo):
    iid = (await create(api)).json()["interview_id"]
    repo.update_interview("alice", iid, {"state": "live", "duration_s": 42.5})
    b = (await api.get(f"/v1/interviews/{iid}", headers=A)).json()
    assert (b["state"], b["duration_s"], b["interview_id"]) == ("live", 42.5, iid)


async def test_foreign_user_gets_404_everywhere(api, repo):
    iid = (await create(api)).json()["interview_id"]
    for call in (
        api.get(f"/v1/interviews/{iid}", headers=B),
        api.post(f"/v1/interviews/{iid}/end", headers=B, json={}),
        api.post("/v1/interviews/" + "0" * 32 + "/end", headers=B, json={}),
    ):
        r = await call
        assert r.status_code == 404 and r.json()["details"][0]["code"] == "not_found"
    assert repo.get_interview("alice", iid).state == "created"  # untouched


async def test_end_short_refunds_once_and_is_idempotent(api, repo):
    iid = (await create(api)).json()["interview_id"]
    set_duration(repo, iid, 29)
    for _ in range(3):
        r = await api.post(f"/v1/interviews/{iid}/end", headers=A, json={})
        assert r.status_code == 200 and r.json()["state"] == "ended"
    assert [c[-1] for c in repo.calls if c[0] == "release"] == [True]
    assert usage(repo) == 0


async def test_end_long_keeps_the_unit_no_refund(api, repo):
    iid = (await create(api)).json()["interview_id"]
    set_duration(repo, iid, 30)  # exactly the threshold counts
    await api.post(f"/v1/interviews/{iid}/end", headers=A)  # no body at all
    await api.post(f"/v1/interviews/{iid}/end", headers=A)
    assert [c[-1] for c in repo.calls if c[0] == "release"] == [False]
    assert usage(repo) == 1


async def test_discard_abandons_and_end_after_discard_changes_nothing(api, repo):
    iid = (await create(api)).json()["interview_id"]
    r = await api.post(f"/v1/interviews/{iid}/end", headers=A, json={"discard": True})
    assert r.json()["state"] == "abandoned"
    again = await api.post(f"/v1/interviews/{iid}/end", headers=A, json={"discard": False})
    assert again.json()["state"] == "abandoned"
    again = await api.post(f"/v1/interviews/{iid}/end", headers=A, json={"discard": True})
    assert again.json()["state"] == "abandoned"
    assert len([c for c in repo.calls if c[0] == "release"]) == 1
    assert usage(repo) == 0  # never recorded -> under 30 s -> refunded


async def test_lazy_abandon_refund_rule(api, repo):
    short = (await create(api)).json()["interview_id"]  # duration None -> refund
    assert (await create(api)).status_code == 201
    assert repo.get_interview("alice", short).state == "abandoned"
    assert usage(repo) == 1  # short refunded, new one counted
    long_ = [d for d in repo.list_open_interviews("alice")][0]
    repo.update_interview("alice", long_.id, {"state": "live", "duration_s": 200})
    assert (await create(api)).status_code == 201
    assert repo.get_interview("alice", long_.id).state == "abandoned"
    assert usage(repo) == 2  # 200 s stays counted


async def test_lazy_abandon_does_not_touch_other_users_or_settled(api, repo):
    bob = (await create(api, headers=B)).json()["interview_id"]
    mine = (await create(api)).json()["interview_id"]
    await api.post(f"/v1/interviews/{mine}/end", headers=A)
    releases = len([c for c in repo.calls if c[0] == "release"])
    assert (await create(api)).status_code == 201
    assert repo.get_interview("bob", bob).state == "created"
    assert len([c for c in repo.calls if c[0] == "release"]) == releases  # nothing re-released


@pytest.mark.parametrize(
    "start,to_end,expect",
    [
        ("created", "ended", "ended"), ("live", "ended", "ended"),
        ("created", "abandoned", "abandoned"), ("live", "abandoned", "abandoned"),
        ("ended", "abandoned", "ended"), ("abandoned", "ended", "abandoned"),
        ("uploaded", "ended", "uploaded"), ("uploaded", "abandoned", "uploaded"),
    ],
)  # fmt: skip
def test_state_table(repo, start, to_end, expect):
    s = Settings(env="test")
    repo.create_interview(
        "alice", "i1",
        InterviewDoc(uid="alice", scenario_id=SCENARIO, voice="Kore", state=start,
                     reservation_date="2026-11-21"),
    )  # fmt: skip
    got = settle_interview(repo, s, "alice", "i1", to_end, NOW)
    assert got.state == expect
    released = len([c for c in repo.calls if c[0] == "release"])
    assert released == (1 if start in ("created", "live") else 0)


def test_refund_hits_the_reservation_day_after_rollover(repo):
    s = Settings(env="test", ai_cap_day=5)
    r = caps.reserve(repo, s, "alice", "interview", NOW)
    repo.create_interview(
        "alice", "i1",
        InterviewDoc(uid="alice", scenario_id=SCENARIO, voice="Kore", reservation_date=r.date),
    )  # fmt: skip
    settle_interview(repo, s, "alice", "i1", "abandoned", NOW + timedelta(days=1))
    assert repo.get_usage_doc("alice", "2026-11-21").interviews == 0


def test_adapters_wiring_stub_and_real():
    assert isinstance(build_adapters(Settings(env="test", adapters="stub")).voice, FakeVoice)
    real = build_adapters(Settings(env="test", adapters="real"))
    assert type(real.voice).__name__ == "RealVoice"
    assert isinstance(Adapters(stt=None, evaluation=None).voice, FakeVoice)


async def test_real_voice_registry_routes_by_provider_and_rejects_unknown():
    from onolys_core.voice import VoiceParams
    from onolys_core.voice.fixture import FixtureVoice

    from onolys_api.adapters.real import RealVoice

    fx = FixtureVoice()
    rv = RealVoice({"fixture": lambda: fx})
    await rv.open(VoiceParams(provider="fixture", model="m", voice="Kore"))
    assert len(fx.opened) == 1
    with pytest.raises(ConfigError):
        await rv.open(VoiceParams(provider="other", model="m", voice="Kore"))


async def test_fake_voice_records_open():
    from onolys_core.voice import VoiceParams

    fv = FakeVoice()
    sess = await fv.open(VoiceParams(provider="anything", model="m", voice="Kore"))
    await sess.close()
    assert [p.voice for p in fv.opened] == ["Kore"]


def test_settings_ai_and_voice_url():
    s = Settings.from_env({"ENV": "local"})
    assert (s.ai_max_seconds, s.ai_warn_seconds, s.ai_min_seconds) == (600, 480, 300)
    assert (s.ai_tolerance_seconds, s.ai_abandon_count_seconds) == (30, 30)
    assert (s.ai_reconnect_seconds, s.ai_mic_gate, s.voice_url) == (
        60,
        False,
        "ws://localhost:8081",
    )
    t = Settings.from_env({"ENV": "prod", "UID_HMAC_KEY": "k", "VOICE_URL": "wss://v.x", "AI_MIC_GATE": "true",
                           "AI_MAX_SECONDS": "300", "AI_WARN_SECONDS": "200"})  # fmt: skip
    assert (t.voice_url, t.ai_mic_gate, t.ai_max_seconds) == ("wss://v.x", True, 300)
    for bad in (
        {"ENV": "prod", "VOICE_URL": "ws://insecure"},
        {"VOICE_URL": "wss://x/"},
        {"AI_MIC_GATE": "maybe"},
        {"AI_MAX_SECONDS": "x"},
        {"AI_WARN_SECONDS": "600"},
        {"AI_ABANDON_COUNT_SECONDS": "-1"},
    ):
        with pytest.raises(ConfigError):
            Settings.from_env(bad)


async def test_short_interview_refunds_are_capped_per_day(api, repo):
    """A9: only the first 3 short (<30 s) interviews of a user per day get the unit back."""
    for i in range(5):
        iid = (await create(api)).json()["interview_id"]
        assert (await api.post(f"/v1/interviews/{iid}/end", headers=A)).status_code == 200
        assert repo.get_interview("alice", iid).refunded is (i < 3)
        assert usage(repo) == max(0, i + 1 - 3)  # 4th and 5th stay counted


async def test_second_create_while_one_is_open_is_a_conflict_not_a_second_unit(api, repo):
    # a still-open interview is abandoned by the next create; a racing create must not reserve
    first = await create(api)
    assert first.status_code == 201
    repo.update_interview("alice", first.json()["interview_id"], {"state": "live"})
    from onolys_api.repo.limits import LimitDefaults

    doc = InterviewDoc(
        uid="alice", scenario_id=SCENARIO, voice="Kore", reservation_date="2026-11-21"
    )
    out = repo.create_interview_reserved("alice", "b" * 32, doc, LimitDefaults(10, 5), 2)
    assert out == "open_exists"
    assert usage(repo) == 1
