"""Server hardening: language choice, cursors, stale uploads and more. Fake repo, fake clocks."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from onolys_api.app import create_app
from onolys_api.auth import deps
from onolys_api.jobs.sweep import run_sweep
from onolys_api.repo.fake import FakeRepo
from onolys_api.repo.models import (
    InterviewDoc,
    ReportDoc,
    SessionDoc,
    SessionError,
    SessionStatusDoc,
)

pytestmark = pytest.mark.unit
UID = "alice"
A = {"Authorization": f"Bearer test:{UID}"}
SCENARIO = "sample-drinking-ambivalent"
WORDS = " ".join(["word"] * 30)
TXT = f"Therapist: {WORDS}\nClient: {WORDS}"
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def repo(blobs):
    return FakeRepo(blobs)


@pytest.fixture
async def api(settings, repo, blobs):
    app = create_app(settings, repo=repo, blobs=blobs)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as c:
        c.app = app  # type: ignore[attr-defined]
        yield c


def interview(repo, iid="a1b2c3d4" + "0" * 24, state="ended", **kw):
    repo.create_interview(
        UID, iid,
        InterviewDoc(uid=UID, scenario_id=SCENARIO, voice="Kore", state=state,
                     reservation_date="2026-11-21", **kw),
    )  # fmt: skip
    return iid


async def put_txt(api, sid, body=TXT):
    return await api.put(
        f"/v1/sessions/{sid}/transcript", content=body,
        headers={**A, "Content-Type": "text/plain"},
    )


async def new_session(api, **body):
    r = await api.post("/v1/sessions", headers=A, json=body)
    assert r.status_code == 202, r.text
    return r.json()["session"]["id"]


# ---- speaker confirm refused once the report is ready ----


async def test_confirm_speakers_refused_in_report_ready(api, repo):
    sid = await new_session(api)
    assert (await put_txt(api, sid)).status_code == 202
    repo.update_session(UID, sid, {"state": "report_ready", "clinician_speaker": "Therapist"})
    r = await api.post(
        f"/v1/sessions/{sid}/speakers/confirm", headers=A,
        json={"clinician_speaker": "Client"},
    )
    assert r.status_code == 409 and r.json()["details"][0]["code"] == "invalid_state"
    assert repo.get_session(UID, sid).clinician_speaker == "Therapist"


# ---- transcript keeps the session language ----


async def test_transcript_without_language_keeps_the_session_language(api, repo):
    sid = await new_session(api, language="de")
    assert (await put_txt(api, sid)).status_code == 202
    assert repo.get_session(UID, sid).language == "de"


async def test_transcript_without_language_and_auto_session_falls_back_to_en(api, repo):
    sid = await new_session(api)  # language "auto"
    assert (await put_txt(api, sid)).status_code == 202
    assert repo.get_session(UID, sid).language == "en"


# ---- transcript upload refused for interview sessions ----


async def test_transcript_put_refused_for_interview_session(api, repo):
    iid = interview(repo)
    sid = await new_session(api, interview_id=iid)
    r = await put_txt(api, sid)
    assert r.status_code == 409
    s = repo.get_session(UID, sid)
    assert s.state == "created" and not s.transcript_ready


# ---- transcript-only session start time ----


async def test_transcript_only_session_gets_started_at_and_excludes_input_wait(api, repo):
    sid = await new_session(api)
    assert repo.get_status(UID, sid).started_at is None
    assert (await put_txt(api, sid)).status_code == 202
    st = repo.get_status(UID, sid)
    assert st.state == "awaiting_input" and st.started_at is not None
    assert st.waited_ms == 0


# ---- server ----


async def test_relinking_an_interview_in_upload_phase_returns_the_same_session(api, repo):
    iid = interview(repo)
    first = await api.post("/v1/sessions", headers=A, json={"interview_id": iid})
    again = await api.post("/v1/sessions", headers=A, json={"interview_id": iid})
    assert first.status_code == 202 and again.status_code == 202, again.text
    assert again.json()["session"]["id"] == first.json()["session"]["id"]
    assert len(repo.list_sessions(UID).items) == 1


async def test_relinking_after_the_session_left_upload_phase_stays_a_conflict(api, repo):
    iid = interview(repo)
    sid = (await api.post("/v1/sessions", headers=A, json={"interview_id": iid})).json()[
        "session"
    ]["id"]
    repo.update_session(UID, sid, {"state": "running"})
    r = await api.post("/v1/sessions", headers=A, json={"interview_id": iid})
    assert r.status_code == 409 and r.json()["details"][0]["code"] == "conflict"


# ---- end idempotency ----


async def test_second_end_returns_the_same_success(api, repo):
    iid = interview(repo, state="live")
    a = await api.post(f"/v1/interviews/{iid}/end", headers=A, json={"discard": False})
    b = await api.post(f"/v1/interviews/{iid}/end", headers=A, json={"discard": False})
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json() and b.json()["state"] == "ended"


# ---- idempotent replay ignores volatile client info ----


async def test_idempotent_replay_ignores_volatile_client_info(api, repo):
    h = {**A, "Idempotency-Key": "k1"}
    a = await api.post("/v1/sessions", headers=h, json={"client": {"web_version": "1.0"}})
    b = await api.post("/v1/sessions", headers=h, json={"client": {"web_version": "2.0"}})
    assert b.status_code == 202, b.text
    assert b.headers["Idempotent-Replayed"] == "true" and a.json() == b.json()
    c = await api.post("/v1/sessions", headers=h, json={"title": "other"})
    assert c.status_code == 409  # a real body change still conflicts


# ---- report version is bounded ----


@pytest.mark.parametrize("version", ["99999999999999999999999", "9223372036854775808", "0", "-1"])
async def test_report_version_is_bounded(api, repo, version):
    sid = await new_session(api)
    r = await api.get(f"/v1/sessions/{sid}/reports/{version}", headers=A)
    assert r.status_code == 422, r.text


# ---- last-used write failure is tolerated ----


async def test_last_used_write_failure_does_not_fail_the_request(api, repo, monkeypatch):
    from onolys_api.auth.keys import new_key
    from onolys_api.repo.models import ApiKeyDoc

    key_id, full, digest = new_key()
    repo.create_api_key(UID, key_id, ApiKeyDoc(uid=UID, hash=digest))

    def boom(*a, **kw):
        raise RuntimeError("firestore down")

    monkeypatch.setattr(repo, "mark_api_key_used", boom)
    r = await api.get("/v1/sessions", headers={"X-API-Key": full})
    assert r.status_code == 200, r.text


# ---- upload limits survive a bad default preset ----


async def test_upload_limits_survives_a_bad_default_preset(api, monkeypatch):
    def boom(*a, **kw):
        raise ValueError("bad preset")

    monkeypatch.setattr(api.app.state.presets, "resolve", boom)  # type: ignore[attr-defined]
    r = await api.get("/v1/upload-limits", headers=A)
    assert r.status_code == 200 and r.json()["max_bytes"] > 0


async def test_retry_task_name_uses_the_stored_retry_count_not_a_stale_read(
    api, repo, monkeypatch
):
    from onolys_api.jobs.queue import TaskPayload, task_name

    sent: list[TaskPayload] = []

    class Q:
        def enqueue(self, payload, delay_s=0.0):
            sent.append(payload)

    api.app.state.queue = Q()  # type: ignore[attr-defined]
    sid = await new_session(api)
    repo.update_session(
        UID, sid,
        {"state": "failed", "step": "transcribe", "retry_count": 2,
         "error": SessionError(code="upstream_unavailable", step="transcribe",
                               kind="transient").model_dump()},
        status={"state": "failed"},
    )  # fmt: skip
    real = repo.get_session
    calls = {"n": 0}

    def stale_first(uid, s):
        doc = real(uid, s)
        calls["n"] += 1
        if calls["n"] == 1:
            doc = doc.model_copy(update={"retry_count": 0})  # a stale snapshot
        return doc

    monkeypatch.setattr(repo, "get_session", stale_first)
    r = await api.post(f"/v1/sessions/{sid}/retry", headers=A)
    assert r.status_code == 202, r.text
    assert sent and sent[0].retry == 3 and task_name(sent[0]).endswith("-r3")


async def test_sweep_does_not_starve_behind_a_session_that_keeps_failing_deletion(
    repo, blobs, settings
):
    old = T0 - timedelta(days=1)
    for n in range(3):
        repo.create_session(
            UID, f"s{n}",
            SessionDoc(uid=UID, state="deleting", created_at=old, updated_at=old,
                       stage_started_at=old + timedelta(seconds=n)),
            SessionStatusDoc(uid=UID, state="deleting", updated_at=old),
        )  # fmt: skip
    import onolys_api.jobs.sweep as sweep

    real = sweep.delete_session_data

    def flaky(repo_, blobs_, uid, sid, *a, **kw):
        if sid == "s0":
            raise RuntimeError("stuck")
        return real(repo_, blobs_, uid, sid, *a, **kw)

    sweep.delete_session_data = flaky
    try:
        for _ in range(2):  # batch of 1: the stuck head must not block the others forever
            run_sweep(repo, blobs, settings, T0, batch=1)
    finally:
        sweep.delete_session_data = real
    remaining = {s.id for s in repo.list_sessions_stuck("deleting", T0, 10)}
    assert "s1" not in remaining, remaining
    assert deps.LAST_USED_EVERY  # keep the import used
    assert ReportDoc
