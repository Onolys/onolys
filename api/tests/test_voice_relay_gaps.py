"""Voice relay edge paths not covered by test_voice_relay.py: verifier trouble, races between the
ownership check and serve, upstream stream end/reopen failure, junk client frames, poll failure."""

import asyncio
import logging

import pytest
from onolys_engine_core.json_logging import render
from onolys_miti.voice import AudioOut, Interrupted, TurnComplete
from onolys_miti.voice.fixture import FixtureVoice
from test_voice_relay import TONE, Env, SeqVoice, connect, expect_close, ready
from voice_helpers import serve

import onolys_api.voice.relay as relay
from onolys_api.repo.base import NotFoundError

pytestmark = pytest.mark.unit
NOT_LIVE = {"type": "error", "code": "interview_not_live"}


def _fail_after(monkeypatch, obj, name, n, exc):
    """Make `obj.name` raise `exc` from its (n+1)th call on (the first n calls work)."""
    real = getattr(obj, name)
    calls = {"n": 0}

    def wrapper(*a, **kw):
        calls["n"] += 1
        if calls["n"] > n:
            raise exc
        return real(*a, **kw)

    monkeypatch.setattr(obj, name, wrapper)


# ---- connection setup ----


async def test_verifier_crash_is_treated_as_unauthenticated(tmp_path, monkeypatch):
    env = Env(tmp_path)
    env.interview()

    def boom(*a, **kw):
        raise ConnectionError("jwks unreachable")

    monkeypatch.setattr(env.app.state.auth, "authenticate", boom)
    async with serve(env.app) as base:
        c = await connect(base)
        await expect_close(c, 4401)
    assert env.voice.opened == []
    assert env.doc().state == "created"


async def test_unexpected_serve_error_sends_internal_error_and_frees_the_slot(
    tmp_path, monkeypatch, caplog
):
    caplog.set_level(logging.INFO)
    env = Env(tmp_path)
    env.interview()

    async def boom(self, conn):
        raise ValueError("kaboom-secret")

    monkeypatch.setattr(relay.Relay, "_serve", boom)
    async with serve(env.app) as base:
        c = await connect(base)
        assert await c.recv_json() == {"type": "error", "code": "internal_error"}
        await expect_close(c, 1011)
    assert env.app.state.voice_connections == {}
    out = "\n".join(render(r) for r in caplog.records)
    assert "kaboom-secret" not in out  # only the exception class is logged
    assert "ValueError" in out


async def test_interview_vanishing_between_ownership_check_and_serve(tmp_path, monkeypatch):
    env = Env(tmp_path)
    env.interview()
    _fail_after(monkeypatch, env.repo, "get_interview", 1, NotFoundError())
    async with serve(env.app) as base:
        c = await connect(base)
        assert await c.recv_json() == {"type": "error", "code": "interview_not_found"}
        await expect_close(c, 4404)
    assert env.voice.opened == []
    assert env.app.state.voice_connections == {}


async def test_unknown_scenario_id_is_not_live(tmp_path):
    env = Env(tmp_path)
    env.interview()
    env.app.state.scenarios.clear()  # scenario removed since the interview was created
    async with serve(env.app) as base:
        c = await connect(base)
        assert await c.recv_json() == NOT_LIVE
        await expect_close(c, 4409)
    assert env.voice.opened == []
    assert env.doc().state == "created"


async def test_interview_already_at_max_duration_is_settled_not_resumed(tmp_path):
    env = Env(tmp_path)
    env.interview(state="live", duration_s=600.0, conn_id="old", live_at=env.clock.wall())
    async with serve(env.app) as base:
        c = await connect(base)
        assert await c.recv_json() == NOT_LIVE
        await expect_close(c, 4409)
    d = env.doc()
    assert d.state == "ended" and d.duration_s == 600.0
    assert env.voice.opened == []


async def test_losing_the_created_to_live_transition_refuses_connection(tmp_path, monkeypatch):
    env = Env(tmp_path)
    env.interview()
    monkeypatch.setattr(env.repo, "transition_interview", lambda *a, **k: None)
    async with serve(env.app) as base:
        c = await connect(base)
        assert await c.recv_json() == NOT_LIVE
        await expect_close(c, 4409)
    assert env.voice.opened == []


async def test_client_gone_before_ready_closes_upstream_and_marks_disconnected(
    tmp_path, monkeypatch
):
    env = Env(tmp_path)
    env.interview()
    real = relay.Relay.send_json

    async def send_json(self, obj):
        if obj.get("type") == "ready":
            raise relay._Fatal("client_drop")
        await real(self, obj)

    monkeypatch.setattr(relay.Relay, "send_json", send_json)
    async with serve(env.app) as base:
        c = await connect(base)
        await asyncio.sleep(0.2)
        await c.ws.close()
    d = env.doc()
    assert d.state == "live" and d.disconnected_at is not None  # re-attach still possible
    assert env.voice._inner.sessions[0].close_calls >= 1
    assert env.app.state.voice_connections == {}


# ---- client frames ----


async def test_junk_text_frames_are_ignored_until_a_real_end(tmp_path):
    env = Env(tmp_path)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        await c.ws.send("not json at all")
        await c.ws.send("[1, 2, 3]")  # valid JSON, not an object
        await c.ws.send('{"type": "hello"}')  # unknown type
        await asyncio.sleep(0.1)
        assert env.doc().state == "live"  # none of it ended the interview
        await env.clock.advance(40)
        await c.send({"type": "end"})
        await expect_close(c, 1000)
    d = env.doc()
    assert d.state == "ended" and d.duration_s == 40.0


# ---- upstream events ----


async def test_interrupted_clears_speaking_and_tells_the_client(tmp_path):
    env = Env(tmp_path, voice=FixtureVoice([AudioOut(TONE), Interrupted(), TurnComplete()]))
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        msgs = await c.drain_json(0.5)
        assert [m["type"] for m in msgs] == ["ai_speaking", "ai_speaking", "interrupted"]
        assert [m.get("on") for m in msgs[:2]] == [True, False]
        await c.ws.close()


class _EndingVoice:
    """Upstream whose event stream just ends (no Closed event), then works on the next open."""

    def __init__(self):
        self.opened = 0

    async def open(self, params):
        self.opened += 1
        n = self.opened

        class S:
            async def send_audio(self, pcm):
                pass

            async def events(self):
                if n == 1:
                    yield AudioOut(TONE)
                    return  # stream ends silently
                while True:
                    await asyncio.sleep(3600)
                    yield TurnComplete()  # pragma: no cover

            async def close(self):
                pass

        return S()


async def test_upstream_stream_ending_without_closed_is_reopened(tmp_path):
    voice = _EndingVoice()
    env = Env(tmp_path, voice=voice)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        await c.drain_json(0.4)
        assert voice.opened == 2  # reopened once, client still connected
        assert env.doc().state == "live" and env.doc().disconnected_at is None
        await c.ws.close()


async def test_reopen_that_fails_to_open_ends_with_upstream_unavailable(tmp_path):
    voice = SeqVoice(FixtureVoice([AudioOut(TONE), TurnComplete()], fail_events_after=1),
                     FixtureVoice(fail_open=True))  # fmt: skip
    env = Env(tmp_path, voice=voice)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        msgs = await c.drain_json(1.0)
        assert {"type": "error", "code": "upstream_unavailable"} in msgs
    assert len(voice.opened) == 2
    d = env.doc()
    assert d.state == "live" and d.disconnected_at is not None


# ---- state trouble while connected ----


async def test_checkpoint_for_a_deleted_interview_on_client_drop_is_a_noop(tmp_path, monkeypatch):
    env = Env(tmp_path)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        real = env.repo.get_interview

        def gone(*a, **k):
            raise NotFoundError()

        monkeypatch.setattr(env.repo, "get_interview", gone)
        await c.ws.close()
        await asyncio.sleep(0.3)
        monkeypatch.setattr(env.repo, "get_interview", real)
    assert env.doc().disconnected_at is None  # nothing written, nothing crashed
    assert env.app.state.voice_connections == {}


async def test_poll_finding_the_interview_gone_closes_not_live(tmp_path, monkeypatch):
    env = Env(tmp_path)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)

        def gone(*a, **k):
            raise NotFoundError()

        monkeypatch.setattr(env.repo, "get_interview", gone)
        await env.clock.advance(10)
        msgs = await c.drain_json(0.5)
        assert NOT_LIVE in msgs
        await expect_close(c, 4409)


async def test_unexpected_error_in_a_pump_task_surfaces_internal_error(tmp_path, monkeypatch):
    env = Env(tmp_path)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)

        def boom(*a, **k):
            raise RuntimeError("db exploded")

        monkeypatch.setattr(env.repo, "update_interview", boom)
        await env.clock.advance(10)  # poll checkpoint hits the failing write
        msgs = await c.drain_json(0.5)
        assert {"type": "error", "code": "internal_error"} in msgs
        await expect_close(c, 1011)
    assert env.voice._inner.sessions[0].close_calls >= 1
    assert env.app.state.voice_connections == {}
