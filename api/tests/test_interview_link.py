"""SP10 Task 7: session link + validate rules for AI interviews (R6, R7, D10, AC7, AC8)."""

import dataclasses

import httpx
import pytest
from audio_helpers import MAGIC, A, StubTools

from onolys_api.app import create_app
from onolys_api.audio import ProbeResult
from onolys_api.jobs import caps
from onolys_api.repo.base import NotFoundError
from onolys_api.repo.fake import FakeRepo
from onolys_api.repo.models import InterviewDoc

pytestmark = pytest.mark.unit
SCENARIO = "sample-drinking-ambivalent"
GOAL = "Cut back to drinking only on weekends"


@pytest.fixture
def repo(blobs):
    return FakeRepo(blobs)


def make_app(settings, repo, blobs, tools=None):
    return create_app(settings, repo=repo, blobs=blobs, audio_tools=tools or StubTools())


@pytest.fixture
async def api(settings, repo, blobs):
    app = make_app(settings, repo, blobs)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as c:
        yield c


def interview(repo, iid="iv1", uid="alice", state="ended", **kw):
    repo.create_interview(
        uid,
        iid,
        InterviewDoc(
            uid=uid, scenario_id=SCENARIO, voice="Kore", state=state,
            reservation_date="2026-11-21", **kw,
        ),
    )  # fmt: skip
    return iid


async def link(api, iid, headers=A, **extra):
    return await api.post("/v1/sessions", headers=headers, json={"interview_id": iid, **extra})


async def test_links_ended_interview_and_prefills_everything(api, repo):
    iid = interview(repo)
    r = await link(api, iid)
    assert r.status_code == 202
    sid = r.json()["session"]["id"]
    s = repo.get_session("alice", sid)
    assert (s.interview_id, s.language, s.title) == (
        iid,
        "en-US",
        "Evening drinking, unsure it's a problem",
    )
    assert repo.get_interview("alice", iid).session_id == sid
    assert repo.get_interview("alice", iid).state == "ended"  # `uploaded` only on audio/complete
    detail = (await api.get(f"/v1/sessions/{sid}", headers=A)).json()
    assert detail["interview_id"] == iid
    # the draft is returned by GET rating, with no final
    g = (await api.get(f"/v1/sessions/{sid}/rating", headers=A)).json()
    assert g["final"] is None and g["draft"]["card"] == {"change_goal": GOAL}


async def test_refunded_interview_cannot_be_linked(api, repo):
    iid = interview(repo, refunded=True)
    r = await link(api, iid)
    assert r.status_code == 409 and r.json()["details"][0]["code"] == "invalid_state"
    assert repo.get_interview("alice", iid).session_id is None


async def test_list_tags_interview_sessions(api, repo):
    iid = interview(repo)
    sid = (await link(api, iid)).json()["session"]["id"]
    plain = (await api.post("/v1/sessions", headers=A, json={})).json()["session"]["id"]
    items = {i["id"]: i for i in (await api.get("/v1/sessions", headers=A)).json()["items"]}
    assert items[sid]["interview_id"] == iid and items[plain]["interview_id"] is None


async def test_explicit_title_wins_over_default(api, repo):
    iid = interview(repo)
    sid = (await link(api, iid, title="My own")).json()["session"]["id"]
    assert repo.get_session("alice", sid).title == "My own"


async def test_no_rating_run_still_allowed(api, repo):
    iid = interview(repo)
    sid = (await link(api, iid)).json()["session"]["id"]
    r = await api.put(
        f"/v1/sessions/{sid}/rating",
        headers=A,
        json={"final": True, "no_rating": True, "card": {"change_goal": GOAL}},
    )
    assert r.status_code == 202 and r.json()["no_rating"] is True
    assert repo.get_session("alice", sid).has_rating is False


@pytest.mark.parametrize("state", ["created", "live", "abandoned", "uploaded"])
async def test_non_ended_interview_is_409_invalid_state(api, repo, state):
    iid = interview(repo, state=state)
    r = await link(api, iid)
    assert r.status_code == 409 and r.json()["details"][0]["code"] == "invalid_state"
    assert repo.get_interview("alice", iid).session_id is None
    assert repo.list_sessions("alice").items == []


async def test_foreign_or_unknown_interview_is_404_and_untouched(api, repo):
    iid = interview(repo, uid="bob")
    for target in (iid, "nope"):
        r = await link(api, target)
        assert r.status_code == 404 and r.json()["details"][0]["code"] == "not_found"
    assert repo.get_interview("bob", iid).session_id is None


async def test_already_linked_is_409_conflict(api, repo):
    iid = interview(repo)
    first = await link(api, iid)
    assert first.status_code == 202
    second = await link(api, iid)
    assert second.status_code == 409 and second.json()["details"][0]["code"] == "conflict"
    assert len(repo.list_sessions("alice").items) == 1


async def test_link_is_atomic_under_a_race(repo):
    import threading

    from onolys_api.repo.models import RatingDraftDoc, SessionDoc, SessionStatusDoc

    iid = interview(repo)
    out: list[str] = []

    def go(n):
        out.append(
            repo.create_session_for_interview(
                "alice", iid, f"s{n}", SessionDoc(uid="alice", interview_id=iid),
                SessionStatusDoc(uid="alice"), RatingDraftDoc(card={}),
            )
        )  # fmt: skip

    ts = [threading.Thread(target=go, args=(n,)) for n in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(out) == ["already_linked"] * 5 + ["linked"]
    assert len(repo.list_sessions("alice").items) == 1


async def test_idempotent_replay_returns_same_session(api, repo):
    iid = interview(repo)
    h = {**A, "Idempotency-Key": "k1"}
    a = await link(api, iid, headers=h)
    b = await link(api, iid, headers=h)
    assert b.headers["Idempotent-Replayed"] == "true" and a.json() == b.json()


async def test_plain_session_has_no_interview_and_no_draft(api, repo):
    sid = (await api.post("/v1/sessions", headers=A, json={})).json()["session"]["id"]
    assert repo.get_session("alice", sid).interview_id is None
    assert (await api.get(f"/v1/sessions/{sid}/rating", headers=A)).json()["draft"] is None


# ---- validate rules (R7, AC7, AC8) ----


async def upload(settings, repo, blobs, seconds, iid=None):
    tools = StubTools(probe=ProbeResult(duration_s=seconds, audio_streams=1))
    app = make_app(settings, repo, blobs, tools)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as c:
        body = {"interview_id": iid} if iid else {}
        sid = (await c.post("/v1/sessions", json=body, headers=A)).json()["session"]["id"]
        data = MAGIC["wav"]
        up = (
            await c.post(
                f"/v1/sessions/{sid}/audio",
                json={"content_type": "audio/wav", "size_bytes": len(data)},
                headers=A,
            )
        ).json()
        blobs.put_bytes(f"uploads/alice/{sid}/{up['upload_id']}", data)
        assert (await c.post(f"/v1/sessions/{sid}/audio/complete", headers=A)).status_code == 202
    app.state.runner._registry.pop("transcribe")
    app.state.queue.drain()
    return sid


async def test_640s_interview_fails_interview_too_long(settings, repo, blobs):
    iid = interview(repo)
    sid = await upload(settings, repo, blobs, 640.0, iid)
    with pytest.raises(NotFoundError):  # an upload failure leaves no session (SP03 R11)
        repo.get_session("alice", sid)
    assert repo.get_status("alice", sid).error_code == "interview_too_long"
    assert blobs.list_keys(f"alice/{sid}/") == []


async def test_630s_interview_passes_the_tolerance_edge(settings, repo, blobs):
    sid = await upload(settings, repo, blobs, 630.0, interview(repo))
    s = repo.get_session("alice", sid)
    assert s.state == "transcribing" and s.warnings == []


async def test_640s_plain_upload_is_unchanged(settings, repo, blobs):
    sid = await upload(settings, repo, blobs, 640.0)
    s = repo.get_session("alice", sid)
    assert s.state == "transcribing" and s.warnings == []


async def test_250s_interview_warns_short_interview_not_short_recording(settings, repo, blobs):
    sid = await upload(settings, repo, blobs, 250.0, interview(repo))
    s = repo.get_session("alice", sid)
    assert s.state == "transcribing" and s.warnings == ["short_interview"]


async def test_400s_interview_has_no_warning(settings, repo, blobs):
    sid = await upload(settings, repo, blobs, 400.0, interview(repo))
    assert repo.get_session("alice", sid).warnings == []  # above AI_MIN, no short_recording


async def test_250s_plain_upload_still_short_recording(settings, repo, blobs):
    sid = await upload(settings, repo, blobs, 250.0)
    assert repo.get_session("alice", sid).warnings == ["short_recording"]


async def test_audio_complete_marks_interview_uploaded(settings, repo, blobs):
    iid = interview(repo)
    await upload(settings, repo, blobs, 400.0, iid)
    assert repo.get_interview("alice", iid).state == "uploaded"


async def test_failed_validation_unlinks_the_interview_so_the_unit_can_relink(
    settings, repo, blobs
):
    iid = interview(repo)
    await upload(settings, repo, blobs, 640.0, iid)
    iv = repo.get_interview("alice", iid)  # M-4: back to `ended`, unlinked (not lost)
    assert (iv.state, iv.session_id) == ("ended", None)


# ---- 03-failure-policy R9: a relay/upload mismatch beyond max(60 s, 15 %) is OUR error ----


@pytest.mark.parametrize(
    ("relay_s", "upload_s"),
    [(300.0, 310.0), (300.0, 331.0), (600.0, 689.0), (180.0, 240.0), (None, 310.0)],
)
async def test_linked_upload_within_the_threshold_proceeds(settings, repo, blobs, relay_s, upload_s):
    # a long relay is capped at AI_MAX_SECONDS (600): raise the ceiling so only the match rule decides
    settings = dataclasses.replace(settings, ai_max_seconds=700)
    iid = interview(repo, duration_s=relay_s)
    sid = await upload(settings, repo, blobs, upload_s, iid)
    s = repo.get_session("alice", sid)
    assert s.state == "transcribing"


@pytest.mark.parametrize(("relay_s", "upload_s"), [(600.0, 691.0), (180.0, 241.0), (120.0, 600.0)])
async def test_linked_upload_beyond_the_threshold_stops_as_our_error(
    settings, repo, blobs, relay_s, upload_s
):
    settings = dataclasses.replace(settings, ai_max_seconds=700)
    iid = interview(repo, duration_s=relay_s)
    sid = await upload(settings, repo, blobs, upload_s, iid)
    s, st = repo.get_session("alice", sid), repo.get_status("alice", sid)
    assert s.state == "failed" and s.warnings == []
    assert (s.error.code, s.error.kind, s.error.counted) == ("internal_error", "permanent_internal", False)
    assert (st.error_code, st.error_kind, st.counted, st.retries_left) == (
        "internal_error", "permanent_internal", False, 0,
    )  # fmt: skip
    assert blobs.list_keys(f"alice/{sid}/audio/")  # data kept (the audio passed validation)
    assert repo.get_usage("alice", caps.utc_date()).runs == 0
    assert (repo.get_user("alice") is None) or repo.get_user("alice").active_runs == 0
