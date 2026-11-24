"""03-failure-policy R8/R11 (AC7, AC11): a file-check failure is an UPLOAD failure (nothing
left but a data-free status stub); any later failure keeps the user's data."""

import re
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from audio_helpers import MAGIC, A, StubTools, tiny_wav
from test_validate import OK, run_validate

from onolys_api.audio import ProbeResult
from onolys_api.jobs.delete import delete_session_data
from onolys_api.jobs.queue import TaskPayload
from onolys_api.jobs.worker import HandlerSpec, PermanentError
from onolys_api.repo.base import NotFoundError
from onolys_api.repo.fake import FakeRepo
from onolys_api.storage.base import MAX_UPLOAD_BYTES

pytestmark = pytest.mark.unit
INFRA = Path(__file__).resolve().parents[2] / "infra/modules/environment/main.tf"


@pytest.fixture
def repo(blobs):
    return FakeRepo(blobs)


# (case id, bytes, tools, size override, expected code)
CASES = {
    "audio_too_large": (MAGIC["wav"], StubTools(probe=OK), None, "audio_too_large"),
    "unsupported_audio": (b"not audio at all" * 4, StubTools(probe=OK), None, "unsupported_audio"),
    "audio_unreadable": (MAGIC["wav"], StubTools(probe_error=True), None, "audio_unreadable"),
    "audio_too_long": (
        MAGIC["wav"], StubTools(probe=ProbeResult(duration_s=21 * 60.0, audio_streams=1)),
        None, "audio_too_long",
    ),
}  # fmt: skip


def assert_discarded(repo, blobs, sid, code):
    with pytest.raises(NotFoundError):
        repo.get_session("alice", sid)
    assert repo.paths(sid) == [f"session_status/{sid}"]  # no session doc, no subcollections
    assert blobs.list_keys(f"uploads/alice/{sid}/") == []
    assert blobs.list_keys(f"alice/{sid}/") == []
    st = repo.get_status("alice", sid)
    assert (st.state, st.error_code) == ("upload_failed", code)
    left = (st.expire_at - st.updated_at).total_seconds()
    assert abs(left - timedelta(days=7).total_seconds()) < 5
    stored = repo._docs[f"session_status/{sid}"]  # no user data, no progress, no step
    assert {k for k, v in stored.items() if v not in (None, 0, False)} == {
        "uid", "state", "error_code", "updated_at", "expire_at",
    }  # fmt: skip


@pytest.mark.parametrize("name", list(CASES))
async def test_file_check_failure_discards_session_and_keeps_only_a_stub(
    settings, repo, blobs, name
):
    data, tools, size, code = CASES[name]
    before = repo.get_usage("alice", "2026-01-01")
    if code == "audio_too_large":  # the staged object is over the limit (never uploaded for real)
        real_size = blobs.size
        blobs.size = lambda k: MAX_UPLOAD_BYTES + 1 if k.startswith("uploads/") else real_size(k)  # type: ignore[method-assign]
    app, sid = await run_validate(settings, repo, blobs, data, tools, size=size)
    assert_discarded(repo, blobs, sid, code)
    assert repo.get_usage("alice", "2026-01-01") == before  # nothing counted
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get(f"/v1/sessions/{sid}", headers=A)).status_code == 404
        listed = (await c.get("/v1/sessions", headers=A)).json()
        assert sid not in [s["id"] for s in listed["items"]]
    # upload-failed stubs are not retryable
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.post(f"/v1/sessions/{sid}/retry", headers=A)).status_code == 404


async def test_discard_removes_recordings_and_runs_too(repo):
    from onolys_api.repo.models import RecordingDoc, RunDoc, SessionDoc, SessionStatusDoc

    repo.create_session("alice", "s1", SessionDoc(uid="alice"), SessionStatusDoc(uid="alice"))
    repo.add_recording("alice", "s1", "original", RecordingDoc(gcs_uri="gs://b/x"))
    repo.create_run("alice", "s1", "r1", RunDoc(uid="alice", session_id="s1", run_id="r1"))
    repo.discard_failed_upload("alice", "s1", "audio_unreadable")
    assert repo.paths("s1") == ["session_status/s1"]
    with pytest.raises(NotFoundError):
        repo.discard_failed_upload("alice", "s1", "audio_unreadable") or repo.get_session(
            "alice", "s1"
        )


async def test_validated_upload_that_fails_transcription_keeps_everything(settings, repo, blobs):
    import httpx as _h

    from onolys_api.app import create_app

    app = create_app(settings, repo=repo, blobs=blobs, audio_tools=StubTools(probe=OK))

    def boom(ctx):
        raise PermanentError("transcription_failed")

    app.state.runner._registry["transcribe"] = HandlerSpec(boom, step="transcribe")
    calls: list[str] = []
    real = blobs.delete_prefix
    blobs.delete_prefix = lambda p: (calls.append(p), real(p))[1]  # type: ignore[method-assign]
    async with _h.AsyncClient(transport=_h.ASGITransport(app=app), base_url="http://t") as c:
        sid = (await c.post("/v1/sessions", json={}, headers=A)).json()["session"]["id"]
        up = (
            await c.post(
                f"/v1/sessions/{sid}/audio",
                json={"content_type": "audio/wav", "size_bytes": len(tiny_wav())},
                headers=A,
            )
        ).json()
        blobs.put_bytes(f"uploads/alice/{sid}/{up['upload_id']}", tiny_wav())
        await c.post(f"/v1/sessions/{sid}/audio/complete", headers=A)
    app.state.queue.drain()
    s = repo.get_session("alice", sid)
    assert (s.state, s.error.code, s.error.step) == ("failed", "transcription_failed", "transcribe")
    assert blobs.exists(f"alice/{sid}/audio/original.wav")
    assert blobs.exists(f"alice/{sid}/audio/canonical.flac")
    assert len(repo.list_recordings("alice", sid)) == 1
    # only the successful-validation staging cleanup ran: no purge of audio after the failure
    assert all(p.startswith("uploads/") for p in calls), calls


async def test_transient_validate_error_keeps_data(settings, repo, blobs):
    """A non-file-check failure of validate (internal) deletes nothing and is a normal failure."""
    app, sid = await run_validate(settings, repo, blobs, tiny_wav(), StubTools(probe=OK))
    repo.update_session("alice", sid, {"steps.validate.status": "pending", "state": "validating"})

    def fn(ctx):
        raise PermanentError("internal_error")

    app.state.runner._registry["validate"] = HandlerSpec(fn, step="validate")
    app.state.runner.handle(TaskPayload(kind="validate", uid="alice", sid=sid))
    assert repo.get_session("alice", sid).state == "failed"
    assert blobs.exists(f"alice/{sid}/audio/original.wav")


async def test_successful_validation_still_removes_staged_object(settings, repo, blobs):
    _, sid = await run_validate(settings, repo, blobs, tiny_wav(), StubTools(probe=OK))
    assert blobs.list_keys(f"uploads/alice/{sid}/") == []
    assert repo.get_session("alice", sid).state == "transcribing"


async def test_delete_still_sweeps_everything(settings, repo, blobs):
    _, sid = await run_validate(settings, repo, blobs, tiny_wav(), StubTools(probe=OK))
    assert delete_session_data(repo, blobs, "alice", sid) is True
    assert blobs.list_keys(f"alice/{sid}/") == [] and repo.paths(sid) == []


def test_status_stub_expiry_is_a_firestore_ttl_policy():
    tf = INFRA.read_text()
    m = re.search(
        r'resource "google_firestore_field" "[^"]+" \{[^}]*collection\s*=\s*"session_status"'
        r'[^}]*field\s*=\s*"expire_at"[^}]*ttl_config \{\}',
        tf,
    )
    assert m, "session_status.expire_at needs a TTL policy"
