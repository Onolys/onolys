"""Async/durability fixes (durable reset email, loop-safe transcript upload,
validate publishes the validated bytes + complete/request_upload race, rejection logs,
voice relay first frame + lease-guarded checkpoint). Deterministic: fakes and events only."""

import asyncio
import hashlib
import json
import logging
import threading
from datetime import UTC, datetime

import httpx
import pytest
from audio_helpers import A, StubTools, tiny_wav
from onolys_engine_core.json_logging import render
from test_auth_email_routes import EMAIL, RESET, Env
from test_voice_relay import Env as VoiceEnv
from test_voice_relay import connect, expect_close
from voice_helpers import serve

from onolys_api.adapters.base import AdapterError
from onolys_api.app import create_app
from onolys_api.audio import ProbeResult
from onolys_api.jobs.queue import TaskPayload, task_name
from onolys_api.jobs.reset_email import make_reset_email_handler, reset_payload
from onolys_api.jobs.worker import HandlerSpec, PermanentError, TaskRunner, UploadFailedError
from onolys_api.repo.fake import FakeRepo

pytestmark = pytest.mark.unit
NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


class RecordingQueue:
    def __init__(self, fail=False):
        self.payloads: list[TaskPayload] = []
        self.fail = fail

    def enqueue(self, payload, delay_s=0.0):
        if self.fail:
            raise RuntimeError("queue down")
        self.payloads.append(payload)


# ---- the reset email is enqueued before the 202, then sent by a worker with a retry ----


async def test_reset_is_enqueued_durably_before_the_response(blobs):
    env = Env(blobs)
    env.app.state.queue = q = RecordingQueue()
    async with env.client() as c:
        r = await c.post(RESET, json={"email": EMAIL})
    assert r.status_code == 202 and r.json() == {}
    assert env.sender.messages == []  # nothing sent in the request; a worker does it
    (p,) = q.payloads
    assert p.kind == "reset-email" and p.email == EMAIL
    assert "@" not in task_name(p) and "phi" not in task_name(
        p
    )  # the name never carries the address


def test_same_email_in_one_window_dedupes_and_the_next_window_is_new():
    from onolys_api.config import Settings

    s = Settings(uid_hmac_key="k")
    a = reset_payload(s, "a@x.org", None, NOW)
    assert task_name(a) == task_name(reset_payload(s, "A@x.org ", None, NOW))
    assert task_name(a) != task_name(reset_payload(s, "b@x.org", None, NOW))
    later = NOW.replace(hour=13)
    assert task_name(a) != task_name(reset_payload(s, "a@x.org", None, later))


async def test_queue_failure_falls_back_to_in_process_send_with_the_same_response(blobs):
    env = Env(blobs)
    env.app.state.queue = RecordingQueue(fail=True)
    async with env.client() as c:
        r = await c.post(RESET, json={"email": EMAIL})
    assert r.status_code == 202 and r.json() == {}
    assert [m["to"] for m in env.sender.messages] == [EMAIL]


async def test_fallback_send_uses_the_same_idempotency_key_as_the_task(blobs):
    env = Env(blobs)
    env.app.state.queue = RecordingQueue(fail=True)
    env.app.state.clock = lambda: NOW
    async with env.client() as c:
        await c.post(RESET, json={"email": EMAIL})
    want = task_name(reset_payload(env.app.state.settings, EMAIL, None, NOW))
    assert [m["idempotency_key"] for m in env.sender.messages] == [want]


class FlakySender:
    def __init__(self, failures, code="email_send_failed"):
        self.failures, self.code, self.messages, self.keys = failures, code, [], []

    def send(self, to, subject, html, text, idempotency_key=None):
        self.keys.append(idempotency_key)
        if self.failures:
            self.failures -= 1
            raise AdapterError(self.code)
        self.messages.append(to)


def _runner(env):
    runner = TaskRunner(env.app.state.repo, RecordingQueue())
    runner.register(
        "reset-email",
        HandlerSpec(make_reset_email_handler(lambda: env.app.state.auth_email()), claim=False),
    )
    return runner


def test_worker_retries_a_transient_failure_once_then_sends(blobs):
    sender = FlakySender(1)
    env = Env(blobs, sender=sender)
    runner = _runner(env)
    p = reset_payload(env.app.state.settings, EMAIL, None, NOW)
    first = runner.handle(p, 0)
    assert (first.status_code, first.outcome) == (503, "retry") and sender.messages == []
    second = runner.handle(p, 1)  # Cloud Tasks' redelivery
    assert second.status_code == 200 and sender.messages == [EMAIL]


def test_retry_reuses_the_task_name_as_idempotency_key(blobs):
    sender = FlakySender(1)
    env = Env(blobs, sender=sender)
    runner = _runner(env)
    p = reset_payload(env.app.state.settings, EMAIL, None, NOW)
    runner.handle(p, 0)
    runner.handle(p, 1)
    assert sender.keys == [task_name(p), task_name(p)]
    assert EMAIL not in sender.keys[0] and sender.keys[0].startswith("reset-")


def test_worker_gives_up_after_the_last_attempt_without_logging_the_address(blobs, caplog):
    env = Env(blobs, sender=FlakySender(5))
    runner = _runner(env)
    p = reset_payload(env.app.state.settings, EMAIL, None, NOW)
    with caplog.at_level(logging.INFO):
        assert runner.handle(p, 1).status_code == 200  # last attempt: no further retry
    text = "\n".join(render(r) for r in caplog.records)
    assert "send_failed" in text and EMAIL not in text and "phi.person" not in text


def test_unconfigured_email_is_not_retried(blobs):
    env = Env(blobs, sender=FlakySender(0))
    runner = TaskRunner(env.app.state.repo, RecordingQueue())

    class Svc:
        def send_password_reset(self, email, idempotency_key=None):
            raise AdapterError("email_unconfigured")

    runner.register(
        "reset-email",
        HandlerSpec(make_reset_email_handler(lambda: (Svc(), None)), claim=False),
    )
    p = reset_payload(env.app.state.settings, EMAIL, None, NOW)
    assert runner.handle(p, 0).status_code == 200


def test_unknown_account_sends_nothing(blobs):
    env = Env(blobs)
    runner = _runner(env)
    p = reset_payload(env.app.state.settings, "nobody@example.org", None, NOW)
    assert runner.handle(p, 0).status_code == 200 and env.sender.messages == []


# ---- the transcript upload keeps the event loop free ----


class GatedRepo(FakeRepo):
    """`get_session` blocks (bounded) until the test releases it; records a timeout."""

    def __init__(self, blobs):
        super().__init__(blobs)
        self.armed = False
        self.entered, self.release = threading.Event(), threading.Event()
        self.timed_out = False

    def get_session(self, uid, sid):
        if self.armed:
            self.armed = False
            self.entered.set()
            if not self.release.wait(1.0):
                self.timed_out = True
        return super().get_session(uid, sid)


async def test_transcript_upload_does_not_block_the_event_loop(settings, blobs):
    repo = GatedRepo(blobs)
    app = create_app(settings, repo=repo, blobs=blobs)
    words = " ".join(["word"] * 30)
    body = json.dumps(
        {
            "turns": [
                {"id": "t1", "speaker": "T", "text": words, "role": "clinician"},
                {"id": "t2", "speaker": "C", "text": words, "role": "client"},
            ]
        }
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as c:
        sid = (await c.post("/v1/sessions", json={}, headers=A)).json()["session"]["id"]
        repo.armed = True
        put = asyncio.create_task(
            c.put(
                f"/v1/sessions/{sid}/transcript",
                content=body,
                headers={**A, "Content-Type": "application/json"},
            )
        )
        await asyncio.to_thread(repo.entered.wait, 2.0)
        try:
            health = await asyncio.wait_for(c.get("/v1/healthz"), 3.0)
        finally:
            repo.release.set()
        r = await put
    assert health.status_code == 200
    assert not repo.timed_out, "the handler blocked the event loop on the sync repo call"
    assert r.status_code == 202, r.text


# ---- the published original is the validated bytes; complete vs request_upload ----


async def _staged_session(settings, repo, blobs, data):
    app = create_app(
        settings,
        repo=repo,
        blobs=blobs,
        audio_tools=StubTools(
            probe=ProbeResult(duration_s=900.0, audio_streams=1, video_streams=0)
        ),
    )
    c = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    )
    sid = (await c.post("/v1/sessions", json={}, headers=A)).json()["session"]["id"]
    up = (
        await c.post(
            f"/v1/sessions/{sid}/audio",
            json={"content_type": "audio/wav", "size_bytes": len(data)},
            headers=A,
        )
    ).json()
    blobs.put_bytes(f"uploads/alice/{sid}/{up['upload_id']}", data)
    return app, c, sid, up["upload_id"]


async def test_original_is_the_validated_bytes_even_if_staging_is_overwritten(settings, blobs):
    repo = FakeRepo(blobs)
    good, other = tiny_wav(), tiny_wav(2.0)
    app, c, sid, upload_id = await _staged_session(settings, repo, blobs, good)
    key = f"uploads/alice/{sid}/{upload_id}"
    real = blobs.download_to

    def download_then_overwrite(k, dst):
        real(k, dst)
        if k == key:  # an overlapping signed PUT lands after the bytes were validated
            blobs.put_bytes(key, other)

    blobs.download_to = download_then_overwrite
    assert (await c.post(f"/v1/sessions/{sid}/audio/complete", headers=A)).status_code == 202
    await c.aclose()
    app.state.runner._registry.pop("transcribe")
    app.state.queue.drain()
    (rec,) = repo.list_recordings("alice", sid)
    stored = blobs.get_bytes(f"alice/{sid}/audio/original.wav")
    assert stored == good and hashlib.sha256(stored).hexdigest() == rec.sha256
    assert rec.size == len(good)


async def test_complete_refuses_when_a_new_upload_replaced_the_checked_one(settings, blobs):
    repo = FakeRepo(blobs)
    app, c, sid, upload_id = await _staged_session(settings, repo, blobs, tiny_wav())
    app.state.queue = q = RecordingQueue()
    real_exists = blobs.exists

    def exists_then_new_upload(k):
        ok = real_exists(k)
        if k.endswith(upload_id):  # request_upload committed right after complete's check
            repo.update_session(
                "alice",
                sid,
                {
                    "upload": {
                        "upload_id": "b" * 32,
                        "format": "wav",
                        "content_type": "audio/wav",
                        "size_bytes": 1000,
                    }
                },
            )
            blobs.delete(k)
        return ok

    blobs.exists = exists_then_new_upload
    r = await c.post(f"/v1/sessions/{sid}/audio/complete", headers=A)
    await c.aclose()
    assert r.status_code == 409 and r.json()["details"][0]["code"] == "invalid_state"
    assert repo.get_session("alice", sid).state == "uploading"  # not stuck in validating
    assert q.payloads == []  # no validate task for an upload that is gone


async def test_request_upload_sets_state_and_upload_in_one_write(settings, blobs):
    repo = FakeRepo(blobs)
    real = repo.transition_session
    written = []

    def spy(uid, sid, plan, children=()):
        def inspect(session, status):
            result = plan(session, status)
            written.append(result[0] if result else {})
            return result

        return real(uid, sid, inspect, children)

    repo.transition_session = spy
    _, c, sid, upload_id = await _staged_session(settings, repo, blobs, tiny_wav())
    await c.aclose()
    assert any(f.get("state") == "uploading" and "upload" in f for f in written), written
    s = repo.get_session("alice", sid)
    assert s.state == "uploading" and s.upload.upload_id == upload_id


# ---- a user-file rejection is not a `status=failed` alert line ----


def _lines(caplog):
    return [json.loads(render(r)) for r in caplog.records if r.name.startswith("onolys_api")]


def test_user_file_rejection_logs_a_warning_not_status_failed(blobs, caplog):
    repo = FakeRepo(blobs)
    runner = TaskRunner(repo, RecordingQueue())

    def reject(ctx):
        raise UploadFailedError("unsupported_audio")

    runner.register("validate", HandlerSpec(reject, step="validate"))
    sid = _make_session(repo)
    with caplog.at_level(logging.INFO):
        r = runner.handle(TaskPayload(kind="validate", uid="alice", sid=sid))
    assert r.status_code == 200
    lines = _lines(caplog)
    assert [d for d in lines if d.get("status") == "failed"] == []
    (rej,) = [d for d in lines if d.get("status") == "rejected"]
    assert rej["error_code"] == "unsupported_audio"


def test_a_real_failure_still_logs_status_failed(blobs, caplog):
    repo = FakeRepo(blobs)
    runner = TaskRunner(repo, RecordingQueue())

    def boom(ctx):
        raise PermanentError("internal_error")

    runner.register("validate", HandlerSpec(boom, step="validate"))
    sid = _make_session(repo)
    with caplog.at_level(logging.INFO):
        runner.handle(TaskPayload(kind="validate", uid="alice", sid=sid))
    assert len([d for d in _lines(caplog) if d.get("status") == "failed"]) == 1


def _make_session(repo):
    from onolys_api.repo.models import SessionDoc, SessionStatusDoc

    sid = "a" * 32
    repo.create_session(
        "alice",
        sid,
        SessionDoc(uid="alice", state="validating"),
        SessionStatusDoc(uid="alice", state="validating"),
    )
    return sid


# ---- voice relay ----


async def test_oversized_first_frame_is_refused_before_auth(tmp_path):
    env = VoiceEnv(tmp_path)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base, auth=False)
        # valid auth JSON, but padded far past any real token: refused unread, not authenticated
        await c.send({"type": "auth", "id_token": "test:alice", "pad": "x" * 70_000})
        await expect_close(c, 4401)
    assert env.voice.opened == []
    assert env.doc().state == "created"


async def test_binary_first_frame_is_unauthenticated(tmp_path):
    env = VoiceEnv(tmp_path)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base, auth=False)
        await c.ws.send(b"\x00" * 10)
        await expect_close(c, 4401)


async def test_a_stale_connections_handle_checkpoint_cannot_overwrite_the_new_owner(tmp_path):
    env = VoiceEnv(tmp_path)
    env.interview(
        state="live", conn_id="new-owner", resumption_handle="new-handle", duration_s=42.0
    )
    assert (
        env.repo.update_interview_if_conn(
            "alice", "i1", "stale-instance", {"resumption_handle": "old", "duration_s": 1.0}
        )
        is False
    )
    d = env.doc()
    assert d.resumption_handle == "new-handle" and d.duration_s == 42.0
