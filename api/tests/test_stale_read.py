"""Lazy stale check: a session left in `transcribing` past its cap (+60 s) is failed when it is
read (GET /v1/sessions/{id}, the list), because the web app only reads the API on demand and
there is no cron. Fake clock via `app.state.clock`."""

from datetime import UTC, datetime, timedelta

import pytest

from onolys_api.app import create_app
from onolys_api.jobs.stale import STALE_MARGIN_S
from onolys_api.repo.fake import FakeRepo
from onolys_api.repo.models import RunDoc, SessionDoc, SessionStatusDoc, StepRecord
from onolys_api.storage.base import UPLOAD_URL_TTL_S

pytestmark = pytest.mark.unit
A = {"Authorization": "Bearer test:alice"}
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def repo(blobs):
    return FakeRepo(blobs)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def app(settings, blobs, repo, clock):
    a = create_app(settings, repo=repo, blobs=blobs)
    a.state.clock = clock
    return a


S1 = "0" * 31 + "1"  # path ids must be 32 hex chars


def seed(repo, sid=S1, state="transcribing", limit=600.0, at=T0, op="op-1"):
    steps = {"transcribe": StepRecord(status="pending", stt_operation=op, stt_started=at,
                                      stt_limit_s=limit)}  # fmt: skip
    repo.create_session(
        "alice", sid,
        SessionDoc(uid="alice", state=state, step="transcribe", steps=steps,
                   created_at=at, updated_at=at, stage_started_at=at),
        SessionStatusDoc(uid="alice", state=state, step="transcribe", progress=20, updated_at=at),
    )  # fmt: skip


async def get(client, sid=S1):
    return await client.get(f"/v1/sessions/{sid}", headers=A)


async def test_read_inside_the_cap_leaves_it_alone(client, repo, clock):
    seed(repo, limit=600)
    clock.now = T0 + timedelta(seconds=600 + STALE_MARGIN_S - 1)
    body = (await get(client)).json()
    assert body["status"] == "transcribing" and body["error"] is None


async def test_read_past_cap_plus_margin_fails_it(client, repo, clock):
    seed(repo, limit=600)
    clock.now = T0 + timedelta(seconds=600 + STALE_MARGIN_S + 1)
    body = (await get(client)).json()
    assert body["status"] == "failed"
    assert body["error"] == {"code": "deadline_exceeded"}  # LM-1: a lost task is retryable
    s, st = repo.get_session("alice", S1), repo.get_status("alice", S1)
    assert (s.state, s.steps["transcribe"].status) == ("failed", "failed")
    assert (st.state, st.error_code) == ("failed", "deadline_exceeded")  # the web listener


async def test_second_read_is_idempotent(client, repo, clock):
    seed(repo, limit=600)
    clock.now = T0 + timedelta(seconds=700)
    await get(client)
    writes = len(repo.status_writes)
    body = (await get(client)).json()
    assert body["status"] == "failed" and len(repo.status_writes) == writes


async def test_cap_comes_from_the_stored_limit(client, repo, clock):
    seed(repo, limit=300)  # a short recording
    clock.now = T0 + timedelta(seconds=300 + STALE_MARGIN_S + 1)
    assert (await get(client)).json()["status"] == "failed"


async def test_no_stored_limit_uses_the_settings_maximum(client, repo, clock):
    seed(repo, limit=None)
    clock.now = T0 + timedelta(seconds=1200 + STALE_MARGIN_S - 1)
    assert (await get(client)).json()["status"] == "transcribing"
    clock.now = T0 + timedelta(seconds=1200 + STALE_MARGIN_S + 1)
    assert (await get(client)).json()["status"] == "failed"


async def test_other_states_are_never_touched(client, repo, clock):
    seed(repo, "a" * 32, state="awaiting_input")
    seed(repo, "b" * 32, state="report_ready")
    clock.now = T0 + timedelta(hours=5)
    assert (await get(client, "a" * 32)).json()["status"] == "awaiting_input"
    assert (await get(client, "b" * 32)).json()["status"] == "report_ready"


async def test_stuck_validating_is_failed(client, repo, clock):
    seed(repo, state="validating")
    clock.now = T0 + timedelta(hours=1)
    body = (await get(client)).json()
    assert body["status"] == "failed" and body["error"] == {"code": "deadline_exceeded"}


async def test_stuck_running_is_failed_and_releases_the_slot(client, repo, clock):
    """A crashed worker leaves `running` + an unreleased run: fail it, hand the slot back (A1)."""
    seed(repo, state="running")
    repo.create_run("alice", S1, "r1", RunDoc(change_goal="", clinician_speaker="S1", language="en", transcript_sha256="test-hash", uid="alice", session_id=S1, run_id="r1",
                                                status="running", cap_date="2026-01-01"))  # fmt: skip
    clock.now = T0 + timedelta(hours=1)
    body = (await get(client)).json()
    assert body["status"] == "failed" and body["error"] == {"code": "deadline_exceeded"}
    run = repo.get_run("alice", S1, "r1")
    assert (run.status, run.released) == ("failed", True)


async def test_worker_crash_refunds_the_unit(client, repo, clock, monkeypatch):
    """Owner decision: a system failure (worker crash) refunds, even after the LLM started."""
    seed(repo, state="running")
    repo.create_run("alice", S1, "r1", RunDoc(change_goal="", clinician_speaker="S1", language="en", transcript_sha256="test-hash", uid="alice", session_id=S1, run_id="r1",
                                                status="running", cap_date="2026-01-01",
                                                llm_started=True))  # fmt: skip
    repo.add_usage("alice", "2026-01-01", runs=1)  # the unit the run spent
    clock.now = T0 + timedelta(hours=1)
    await get(client)
    run = repo.get_run("alice", S1, "r1")
    assert (run.released, run.unit_kept) == (True, False)  # refunded, in the failing transaction
    assert repo.get_usage("alice", "2026-01-01").runs == 0


async def test_later_writes_do_not_delay_the_stale_cutoff(client, repo, clock):
    """BH4: a rating/speaker write bumps `updated_at`, not the stage start."""
    seed(repo, state="running")
    clock.now = T0 + timedelta(minutes=30)
    repo.update_session("alice", S1, {"rating_submitted": True})  # bumps updated_at only
    clock.now = T0 + timedelta(hours=1)
    assert (await get(client)).json()["status"] == "failed"


async def test_a_poll_that_just_finished_wins_the_race(client, repo, clock, monkeypatch):
    """The read decides from an old snapshot; the transaction sees the session moved on."""
    seed(repo, limit=600)
    clock.now = T0 + timedelta(seconds=900)
    real = repo.fail_stale_session

    def racing(uid, sid, state, before, error, **kw):
        repo.update_session(uid, sid, {"state": "awaiting_input"},
                            status={"state": "awaiting_input"})  # fmt: skip
        return real(uid, sid, state, before, error, **kw)

    monkeypatch.setattr(repo, "fail_stale_session", racing)
    body = (await get(client)).json()
    assert body["status"] == "awaiting_input" and body["error"] is None


async def test_chain_that_never_started_is_failed_too(client, repo, clock):
    """validate moved it to transcribing, the transcribe task was dropped: no stt_started."""
    repo.create_session(
        "alice", S1,
        SessionDoc(uid="alice", state="transcribing", step="transcribe", created_at=T0,
                   updated_at=T0),
        SessionStatusDoc(uid="alice", state="transcribing", step="transcribe", updated_at=T0),
    )  # fmt: skip
    clock.now = T0 + timedelta(seconds=1200 + STALE_MARGIN_S + 1)
    body = (await get(client)).json()
    assert body["status"] == "failed" and body["error"] == {"code": "deadline_exceeded"}


async def test_list_fails_stale_items_too(client, repo, clock):
    seed(repo, "old", limit=600)
    seed(repo, "new", limit=600, at=T0 + timedelta(seconds=800))
    clock.now = T0 + timedelta(seconds=900)
    items = {i["id"]: i for i in (await client.get("/v1/sessions", headers=A)).json()["items"]}
    assert (items["old"]["status"], items["old"]["error_code"]) == (
        "failed",
        "deadline_exceeded",
    )
    assert items["new"]["status"] == "transcribing"
    assert repo.get_session("alice", "old").state == "failed"


# ---- FX8 / AR3 / D4: abandoned uploads become `upload_incomplete` (non-terminal) ----

UPLOAD_CUTOFF_S = UPLOAD_URL_TTL_S + STALE_MARGIN_S


@pytest.mark.parametrize("state", ["created", "uploading"])
async def test_abandoned_upload_becomes_upload_incomplete(client, repo, clock, state):
    seed(repo, state=state)
    clock.now = T0 + timedelta(seconds=UPLOAD_CUTOFF_S - 1)
    assert (await get(client)).json()["status"] == state
    clock.now = T0 + timedelta(seconds=UPLOAD_CUTOFF_S + 1)
    body = (await get(client)).json()
    assert (body["status"], body["error"]) == ("upload_incomplete", None)
    st = repo.get_status("alice", S1)
    assert (st.state, st.error_code) == ("upload_incomplete", None)  # the web listener
    items = (await client.get("/v1/sessions", headers=A)).json()["items"]
    assert items[0]["status"] == "upload_incomplete"


async def test_upload_incomplete_can_resume_and_complete(client, app, repo, clock):
    seed(repo, state="uploading")
    clock.now = T0 + timedelta(seconds=UPLOAD_CUTOFF_S + 1)
    assert (await get(client)).json()["status"] == "upload_incomplete"
    r = await client.post(f"/v1/sessions/{S1}/audio", json={"size_bytes": 1000,
                          "content_type": "audio/wav"}, headers=A)  # fmt: skip
    assert r.status_code == 200, r.text
    assert repo.get_session("alice", S1).state == "uploading"
    j = r.json()
    put = await client.put(j["upload_url"].removeprefix("http://localhost:8000"),
                           content=b"RIFF" + b"\0" * 40, headers=j["required_headers"])  # fmt: skip
    assert put.status_code == 200
    r = await client.post(f"/v1/sessions/{S1}/audio/complete", headers=A)
    assert (r.status_code, r.json()["session"]["status"]) == (202, "validating")


async def test_late_put_on_upload_incomplete_still_completes(client, repo, clock):
    """The slow upload finished after the cutoff: `complete` is accepted from `upload_incomplete`."""
    seed(repo, state="uploading")
    j = (await client.post(f"/v1/sessions/{S1}/audio", json={"size_bytes": 1000,
                           "content_type": "audio/wav"}, headers=A)).json()  # fmt: skip
    clock.now = T0 + timedelta(seconds=UPLOAD_CUTOFF_S + 1)
    repo.fail_stale_session("alice", S1, "uploading", clock.now, None, to="upload_incomplete")
    put = await client.put(j["upload_url"].removeprefix("http://localhost:8000"),
                           content=b"RIFF" + b"\0" * 40, headers=j["required_headers"])  # fmt: skip
    assert put.status_code == 200
    r = await client.post(f"/v1/sessions/{S1}/audio/complete", headers=A)
    assert r.status_code == 202
