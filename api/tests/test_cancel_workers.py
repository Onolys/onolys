"""04-cancel Task 5: workers stop on cancel (R5, D4, D9).

`alive.ensure_active` raises `Cancelled` on a `cancelled` session (purging nothing); the runner
answers 200 `cancelled` and never writes `failed` over `cancelled`; data is kept.
"""

from datetime import UTC, datetime, timedelta

import pytest
from audio_helpers import A, StubTools, tiny_wav
from test_run import env  # noqa: F401  (fixture)
from test_transcribe import UID, Env, fixture_stt, make_env  # noqa: F401  (fixture)
from test_validate import OK, DeletingTools

from onolys_api.app import create_app
from onolys_api.config import Settings
from onolys_api.jobs import caps
from onolys_api.jobs.alive import ensure_active
from onolys_api.jobs.queue import InMemoryQueue, TaskPayload
from onolys_api.jobs.stale import settle_if_stale
from onolys_api.jobs.worker import Cancelled, HandlerSpec, PermanentError, TaskRunner
from onolys_api.repo.base import NotFoundError
from onolys_api.repo.fake import FakeRepo
from onolys_api.repo.limits import LimitDefaults
from onolys_api.repo.models import SessionDoc, SessionStatusDoc

pytestmark = pytest.mark.integration
D = LimitDefaults(eval_day=10, interview_day=5)
SID = "s1"


def cancel(repo, uid, sid):
    return repo.cancel_session(uid, sid, caps.utc_date(), D)


# ---- ensure_active / runner ----


def _unit_repo(blobs, state="validating"):
    repo = FakeRepo(blobs)
    now = datetime.now(UTC)
    repo.create_session(
        UID, SID, SessionDoc(uid=UID, state=state, created_at=now, updated_at=now),
        SessionStatusDoc(uid=UID, state=state, updated_at=now),
    )  # fmt: skip
    return repo


def test_ensure_active_raises_cancelled_and_purges_nothing(blobs):
    repo = _unit_repo(blobs)
    blobs.put_bytes(f"{UID}/{SID}/audio/original.wav", b"x")
    blobs.put_bytes(f"uploads/{UID}/{SID}/u1", b"y")
    cancel(repo, UID, SID)
    with pytest.raises(Cancelled):
        ensure_active(repo, blobs, UID, SID)
    assert blobs.exists(f"{UID}/{SID}/audio/original.wav") and blobs.exists(
        f"uploads/{UID}/{SID}/u1"
    )


def test_ensure_active_deleting_still_purges(blobs):
    repo = _unit_repo(blobs)
    blobs.put_bytes(f"{UID}/{SID}/audio/original.wav", b"x")
    repo.update_session(UID, SID, {"state": "deleting"})
    with pytest.raises(NotFoundError):
        ensure_active(repo, blobs, UID, SID)
    assert not blobs.exists(f"{UID}/{SID}/audio/original.wav")


def test_ensure_active_live_session_is_silent(blobs):
    ensure_active(_unit_repo(blobs), blobs, UID, SID)


def _runner(repo, fn):
    runner = TaskRunner(repo, InMemoryQueue())
    runner.register("validate", HandlerSpec(fn, step="validate"))
    return runner


P = TaskPayload(kind="validate", uid=UID, sid=SID)


def test_runner_cancelled_is_200_cancelled_with_no_failure(blobs):
    repo = _unit_repo(blobs)

    def fn(ctx):
        cancel(repo, UID, SID)
        raise Cancelled()

    r = _runner(repo, fn).handle(P)
    assert (r.status_code, r.outcome) == (200, "cancelled")
    s = repo.get_session(UID, SID)
    assert s.state == "cancelled" and s.error is None and s.steps["validate"].status != "failed"


def test_backstop_catch_all_answers_cancelled_not_failed(blobs):
    repo = _unit_repo(blobs)

    def fn(ctx):  # e.g. `advance` raising invalid_state after a cancel
        cancel(repo, UID, SID)
        raise RuntimeError("boom")

    r = _runner(repo, fn).handle(P, retry_count=2)
    assert (r.status_code, r.outcome) == (200, "cancelled")
    s = repo.get_session(UID, SID)
    assert s.state == "cancelled" and s.error is None and s.steps["validate"].status != "failed"
    assert repo.get_status(UID, SID).state == "cancelled"


def test_fail_never_overwrites_cancelled(blobs):
    repo = _unit_repo(blobs)

    def fn(ctx):
        cancel(repo, UID, SID)
        raise PermanentError("transcription_failed")

    r = _runner(repo, fn).handle(P)
    assert r.status_code == 200
    s = repo.get_session(UID, SID)
    assert s.state == "cancelled" and s.error is None and s.steps["validate"].status != "failed"
    assert repo.get_status(UID, SID).state == "cancelled"


def test_stale_check_ignores_cancelled(blobs):
    repo = _unit_repo(blobs, state="transcribing")
    cancel(repo, UID, SID)
    s = repo.get_session(UID, SID)
    old = s.model_copy(update={"stage_started_at": datetime(2020, 1, 1, tzinfo=UTC)})
    out = settle_if_stale(repo, old, datetime.now(UTC) + timedelta(days=2), Settings())
    assert out.state == "cancelled" and out.error is None


# ---- validate ----


async def _staged(settings, repo, blobs, tools):
    """A session with its upload complete and `validate` queued, not yet delivered."""
    import httpx

    app = create_app(settings, repo=repo, blobs=blobs, audio_tools=tools)
    data = tiny_wav()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as c:
        sid = (await c.post("/v1/sessions", json={}, headers=A)).json()["session"]["id"]
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
    return app, sid


async def test_late_validate_noops_and_keeps_the_upload(settings, blobs):
    repo = FakeRepo(blobs)
    app, sid = await _staged(settings, repo, blobs, StubTools(probe=OK))
    cancel(repo, "alice", sid)
    app.state.queue.drain()
    s = repo.get_session("alice", sid)
    assert s.state == "cancelled" and s.error is None
    assert s.steps["validate"].status != "failed"
    assert len(blobs.list_keys(f"uploads/alice/{sid}/")) == 1  # data kept
    assert repo.list_recordings("alice", sid) == []


async def test_cancel_mid_validate_stops_and_keeps_blobs(settings, blobs):
    repo = FakeRepo(blobs)
    holder = {}
    tools = DeletingTools(lambda: cancel(repo, "alice", holder["sid"]), probe=OK)
    app, sid = await _staged(settings, repo, blobs, tools)
    holder["sid"] = sid
    app.state.queue.drain()
    s = repo.get_session("alice", sid)
    assert s.state == "cancelled" and s.error is None
    assert s.steps["validate"].status != "failed"
    assert repo.get_status("alice", sid).state == "cancelled"
    assert blobs.list_keys(f"uploads/alice/{sid}/")  # staged upload not purged
    assert f"{sid}-transcribe" not in app.state.queue.seen  # nothing handed on


async def test_cancel_mid_validate_then_failing_file_check_keeps_everything(settings, blobs):
    """Cancel lands while ffprobe runs, then the probe fails: no purge, no stub over cancelled."""
    repo = FakeRepo(blobs)
    holder = {}

    class CancellingBadProbe(StubTools):
        def probe(self, path, fmt=None):
            cancel(repo, "alice", holder["sid"])
            return super().probe(path, fmt)

    tools = CancellingBadProbe(probe_error=True)
    app, sid = await _staged(settings, repo, blobs, tools)
    holder["sid"] = sid
    app.state.queue.drain()
    s = repo.get_session("alice", sid)  # the session doc survives
    assert s.state == "cancelled" and s.error is None
    assert repo.get_status("alice", sid).state == "cancelled"  # no upload_failed stub
    assert blobs.list_keys(f"uploads/alice/{sid}/")  # audio kept


async def test_cancel_after_blob_writes_in_validate_keeps_them(settings, blobs, monkeypatch):
    """Cancel lands right after the original is moved: ensure_active stops, nothing purged."""
    repo = FakeRepo(blobs)
    app, sid = await _staged(settings, repo, blobs, StubTools(probe=OK))
    real = blobs.delete_prefix

    def cancelling(prefix):
        real(prefix)
        if prefix.startswith("uploads/"):
            cancel(repo, "alice", sid)

    monkeypatch.setattr(blobs, "delete_prefix", cancelling)
    app.state.queue.drain()
    s = repo.get_session("alice", sid)
    assert s.state == "cancelled" and s.error is None
    assert blobs.exists(f"alice/{sid}/audio/original.wav")
    assert blobs.exists(f"alice/{sid}/audio/canonical.flac")
    assert f"{sid}-transcribe" not in app.state.queue.seen


# ---- transcribe / poll ----


def test_late_transcribe_noops_with_cancelled(make_env):  # noqa: F811
    tenv = make_env()
    cancel(tenv.repo, UID, SID)
    r = tenv.start()
    assert (r.status_code, r.outcome) == (200, "cancelled")
    assert tenv.stt.submits == 0 and tenv.queue.pending == []
    assert tenv.session.state == "cancelled" and tenv.session.error is None


def test_cancel_during_stt_start_enqueues_no_poll(make_env):  # noqa: F811
    tenv = make_env()
    orig = tenv.stt.start

    async def start(audio, params):
        handle = await orig(audio, params)
        cancel(tenv.repo, UID, SID)
        return handle

    tenv.stt.start = start
    r = tenv.start()
    assert (r.status_code, r.outcome) == (200, "cancelled")
    assert tenv.queue.pending == []
    assert tenv.session.state == "cancelled" and tenv.session.error is None


def test_late_poll_noops_with_cancelled(make_env):  # noqa: F811
    tenv = make_env()
    tenv.start()
    cancel(tenv.repo, UID, SID)
    r = tenv.poll(1)
    assert (r.status_code, r.outcome) == (200, "cancelled")
    assert tenv.queue.pending == [] or all(p.n == 1 for p in tenv.queue.pending)
    assert tenv.session.state == "cancelled" and tenv.hook_calls == []


def test_cancel_mid_poll_discards_the_result_and_keeps_state(make_env):  # noqa: F811
    tenv = make_env()
    tenv.start()
    tenv.queue.pending.clear()
    orig = tenv.stt.poll

    async def poll(handle):
        out = await orig(handle)
        cancel(tenv.repo, UID, SID)  # lands while the provider answers
        return out

    tenv.stt.poll = poll
    tenv.clock.advance(60)
    r = tenv.poll(1)
    assert (r.status_code, r.outcome) == (200, "cancelled")
    s = tenv.session
    assert s.state == "cancelled" and s.error is None
    assert s.steps["transcribe"].status != "failed" and s.steps["transcribe"].stt_operation
    with pytest.raises(NotFoundError):
        tenv.repo.get_transcript(UID, SID, "current")
    assert tenv.hook_calls == []


def test_backstop_when_advance_loses_the_race(make_env, monkeypatch):  # noqa: F811
    """Cancel lands between the last check and `advance`: invalid_state -> 200 cancelled."""
    from onolys_api.jobs import transcribe as tr

    tenv = make_env()
    tenv.start()
    tenv.queue.pending.clear()
    real = tr.advance

    def racing(repo, uid, sid, **kw):
        cancel(repo, uid, sid)
        return real(repo, uid, sid, **kw)

    monkeypatch.setattr(tr, "advance", racing)
    tenv.clock.advance(60)
    r = tenv.poll(1)
    assert (r.status_code, r.outcome) == (200, "cancelled")
    assert tenv.session.state == "cancelled" and tenv.session.error is None


# ---- run ----


async def test_late_run_noops_with_cancelled(env):  # noqa: F811
    sid = await env.start()
    assert cancel(env.repo, env.uid, sid) == ("cancelled", True)
    env.drain()
    s = env.repo.get_session(env.uid, sid)
    assert s.state == "cancelled" and s.error is None
    assert env.repo.list_reports(env.uid, sid) == []
    assert env.counters()[0] == 0


async def test_cancel_mid_run_aborts_at_the_next_stage_and_never_reports(env):  # noqa: F811
    from onolys_api.adapters import Adapters, FakeEvaluation

    class CancelAtCode(FakeEvaluation):
        async def run(self, ctx, transcript, speaker_map, params, progress_cb=None):
            def cb(stage, status):
                if progress_cb:
                    progress_cb(stage, status)
                if stage == "code" and status == "started":
                    cancel(env.repo, env.uid, holder["sid"])  # lands mid-run

            return await super().run(ctx, transcript, speaker_map, params, cb)

    holder = {}
    env.app.state.adapters = Adapters(stt=env.stt, evaluation=CancelAtCode())
    sid = holder["sid"] = await env.start()
    env.drain()
    s = env.repo.get_session(env.uid, sid)
    assert s.state == "cancelled" and s.error is None
    assert env.repo.list_reports(env.uid, sid) == []
    assert env.repo.get_status(env.uid, sid).state == "cancelled"
    (run,) = env.repo.list_runs(env.uid, sid)
    assert run.error == "cancelled" and run.released
    assert env.counters()[0] == 0  # slot released once, by the cancel
    assert env.blobs.exists(f"{env.uid}/{sid}/audio/canonical.flac")  # data kept


async def test_cancelled_session_keeps_transcripts_and_blobs(env):  # noqa: F811
    sid = await env.start(rate=False)
    cancel(env.repo, env.uid, sid)
    env.drain()
    assert env.repo.get_transcript(env.uid, sid, "current")
    assert env.blobs.list_keys(f"{env.uid}/{sid}/audio/")
    assert env.repo.get_session(env.uid, sid).state == "cancelled"
