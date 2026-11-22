"""SP10 Task 5: voice relay (R4, D1, D4, D7, D8, AC2, AC4, AC5), fixture adapter + manual clock."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

import pytest
import websockets
from leak_helpers import find_leaks
from onolys_miti.voice import AudioOut, Closed, GoAway, ResumptionHandle, TurnComplete
from onolys_miti.voice.fixture import FixtureVoice, tone_pcm24k
from starlette.websockets import WebSocketDisconnect, WebSocketState
from voice_helpers import ManualClock, serve

from onolys_api.adapters.fake import FakeVoice
from onolys_api.app import create_app
from onolys_api.config import Settings
from onolys_api.jobs.interviews import settle_interview
from onolys_api.repo.fake import FakeRepo
from onolys_api.repo.models import InterviewDoc
from onolys_api.storage.fake import FakeBlobStore
from onolys_api.voice.scenarios import load_scenarios

pytestmark = pytest.mark.unit
ORIGIN = "https://app.onolys.com"
SCENARIO = "sample-drinking-ambivalent"
SC = load_scenarios()[SCENARIO]
TONE = tone_pcm24k(20)
T0 = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


class SeqVoice:
    """Open i -> `voices[i]` (the last repeats): different upstream behaviour per reopen."""

    def __init__(self, *voices: FixtureVoice) -> None:
        self.voices = list(voices)
        self.opened = []

    async def open(self, params):
        self.opened.append(params)
        v = self.voices[min(len(self.opened) - 1, len(self.voices) - 1)]
        return await v.open(params)


def _settings(**kw) -> Settings:
    return Settings(
        env="test", auth_mode="fake", service_mode="voice", cors_origins=(ORIGIN,), **kw
    )


class Env:
    def __init__(self, tmp_path, voice=None, **settings):
        self.repo = FakeRepo(FakeBlobStore(tmp_path / "b"))
        self.clock = ManualClock(T0)
        self.voice = voice or FakeVoice(FixtureVoice([AudioOut(TONE), TurnComplete()]))
        self.app = create_app(_settings(**settings), repo=self.repo)
        self.app.state.voice_adapter = self.voice
        self.app.state.voice_clock = self.clock

    def interview(self, uid="alice", iid="i1", state="created", **kw):
        self.repo.create_interview(
            uid, iid,
            InterviewDoc(
                uid=uid, scenario_id=SCENARIO, voice="Kore", state=state, created_at=T0,
                reservation_date="2026-11-21", **kw,
            ),
        )  # fmt: skip

    def doc(self, uid="alice", iid="i1"):
        return self.repo.get_interview(uid, iid)


class Client:
    """A connected ws that records every server frame and leak-scans it."""

    def __init__(self, ws):
        self.ws = ws
        self.frames: list[str | bytes] = []

    async def recv(self, timeout=2.0):
        f = await asyncio.wait_for(self.ws.recv(), timeout)
        self.frames.append(f)
        if isinstance(f, str):
            assert find_leaks(f, SC) == []
        return f

    async def recv_json(self, timeout=2.0) -> dict:
        while True:
            f = await self.recv(timeout)
            if isinstance(f, str):
                return json.loads(f)

    async def drain_json(self, wait=0.2) -> list[dict]:
        out = []
        try:
            while True:
                f = await self.recv(wait)
                if isinstance(f, str):
                    out.append(json.loads(f))
        except (TimeoutError, websockets.ConnectionClosed):
            return out

    async def send(self, obj):
        await self.ws.send(json.dumps(obj))


async def connect(base, iid="i1", token="test:alice", origin=ORIGIN, auth=True) -> Client:
    ws = await websockets.connect(f"{base}/v1/voice/{iid}", origin=origin)
    c = Client(ws)
    if auth:
        await c.send({"type": "auth", "id_token": token})
    return c


async def expect_close(c: Client, code: int):
    with pytest.raises(websockets.ConnectionClosed) as ei:
        while True:
            await c.recv()
    assert ei.value.rcvd.code == code


async def ready(c: Client) -> dict:
    msg = await c.recv_json()
    assert msg["type"] == "ready"
    return msg


# ---- auth and ownership ----


async def test_bad_or_missing_auth_closes_4401(tmp_path):
    env = Env(tmp_path)
    env.interview()
    async with serve(env.app) as base:
        for first in (
            {"type": "auth", "id_token": "garbage"},
            {"type": "hello"},
            {"type": "auth"},
        ):
            c = await connect(base, auth=False)
            await c.send(first)
            await expect_close(c, 4401)
        c = await connect(base, auth=False)
        await c.ws.send(b"\x00\x01")  # binary before auth
        await expect_close(c, 4401)
    assert env.voice.opened == []
    assert env.doc().state == "created"


async def test_origin_must_be_allowed(tmp_path):
    env = Env(tmp_path)
    env.interview()
    async with serve(env.app) as base:
        with pytest.raises(websockets.InvalidStatus) as ei:
            await websockets.connect(f"{base}/v1/voice/i1", origin="https://evil.example")
        assert ei.value.response.status_code == 403
        with pytest.raises(websockets.InvalidStatus):
            await websockets.connect(f"{base}/v1/voice/i1")  # no Origin header
    assert env.voice.opened == []


async def test_wrong_owner_and_unknown_interview_rejected_alike(tmp_path):
    env = Env(tmp_path)
    env.interview("alice")
    async with serve(env.app) as base:
        for iid, tok in (("i1", "test:bob"), ("nope", "test:alice")):
            c = await connect(base, iid=iid, token=tok)
            assert await c.recv_json() == {"type": "error", "code": "interview_not_found"}
            await expect_close(c, 4404)
    assert env.voice.opened == []
    assert env.doc().state == "created"


@pytest.mark.parametrize("state", ["ended", "abandoned", "uploaded"])
async def test_not_live_states_rejected(tmp_path, state):
    env = Env(tmp_path)
    env.interview(state=state)
    async with serve(env.app) as base:
        c = await connect(base)
        assert await c.recv_json() == {"type": "error", "code": "interview_not_live"}
        await expect_close(c, 4409)
    assert env.voice.opened == []


# ---- audio ----


async def test_ready_audio_down_audio_up_and_prompt_stays_server_side(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    env = Env(tmp_path)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        r = await ready(c)
        assert r == {
            "type": "ready",
            "resumed": False,
            "elapsed_s": 0.0,
            "max_s": 600,
            "warn_s": 480,
        }
        assert env.doc().state == "live"
        got = [await c.recv() for _ in range(2)]  # ai_speaking on, then the tone
        assert json.loads(got[0]) == {"type": "ai_speaking", "on": True}
        assert got[1] == TONE
        assert (await c.recv_json()) == {"type": "ai_speaking", "on": False}
        await c.ws.send(b"\x01\x02" * 80)
        await asyncio.sleep(0.1)
        assert env.voice.opened[0].system_prompt.startswith("You are role-playing")
        assert env.voice.opened[0].voice == "Kore"
        await c.ws.close()
    assert find_leaks(" ".join(str(f) for f in c.frames if isinstance(f, str)), SC) == []
    assert find_leaks(caplog.text, SC) == []
    assert SC["hidden_info"] not in caplog.text
    assert env.voice.opened[0].system_prompt not in caplog.text


# ---- clock ----


async def test_warn_at_480_and_time_up_at_600_ends_the_interview(tmp_path):
    env = Env(tmp_path)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        await c.drain_json()
        await env.clock.advance(479)
        assert await c.drain_json() == []
        await env.clock.advance(2)
        assert await c.recv_json() == {"type": "warn", "at_s": 480}
        await env.clock.advance(118)
        assert await c.drain_json() == []
        await env.clock.advance(2)
        assert await c.recv_json() == {"type": "time_up"}
        await expect_close(c, 1000)
    d = env.doc()
    assert d.state == "ended" and d.duration_s == 600.0 and d.ended_at is not None
    assert env.voice._inner.sessions[0].close_calls >= 1  # upstream closed with the interview


async def test_client_end_records_duration_and_settles(tmp_path):
    env = Env(tmp_path)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        await env.clock.advance(150)
        await c.send({"type": "end"})
        await expect_close(c, 1000)
    d = env.doc()
    assert d.state == "ended" and d.duration_s == 150.0


# ---- reconnect ----


async def _drop_and_return(env, base, gap_s, first_s=100):
    c = await connect(base)
    await ready(c)
    await env.clock.advance(first_s)
    await c.ws.close()
    await asyncio.sleep(0.2)
    d = env.doc()
    assert d.state == "live" and d.disconnected_at is not None
    assert d.duration_s == first_s
    await env.clock.advance(gap_s)
    return await connect(base)


async def test_reconnect_within_window_resumes_with_elapsed_and_handle(tmp_path):
    voice = SeqVoice(
        FixtureVoice([AudioOut(TONE), ResumptionHandle("h-1")]),
        FixtureVoice([TurnComplete()]),
    )
    env = Env(tmp_path, voice=voice)
    env.interview()
    async with serve(env.app) as base:
        c2 = await _drop_and_return(env, base, gap_s=59)
        r = await ready(c2)
        assert r["resumed"] is True and r["elapsed_s"] == 100.0
        assert voice.opened[1].resumption_handle == "h-1"
        await env.clock.advance(381)  # 100 + 381 > 480: warn once, from the carried elapsed
        assert await c2.recv_json() == {"type": "warn", "at_s": 480}
        await env.clock.advance(119)  # 100 + 500 = 600
        assert (await c2.recv_json())["type"] == "time_up"
    assert env.doc().duration_s == 600.0 and env.doc().state == "ended"


async def test_reconnect_after_window_does_not_resume(tmp_path):
    env = Env(tmp_path)
    env.interview()
    async with serve(env.app) as base:
        c2 = await _drop_and_return(env, base, gap_s=61)
        assert await c2.recv_json() == {"type": "error", "code": "interview_not_live"}
        await expect_close(c2, 4409)
    d = env.doc()
    assert d.state == "ended" and d.duration_s == 100.0
    assert len(env.voice.opened) == 1  # no second upstream


async def test_new_connection_takes_over_a_stale_one(tmp_path):
    env = Env(tmp_path)
    env.interview()
    async with serve(env.app) as base:
        c1 = await connect(base)
        await ready(c1)
        await env.clock.advance(30)
        c2 = await connect(base)
        r = await ready(c2)
        assert r["resumed"] is True and r["elapsed_s"] == 30.0
        await expect_close(c1, 1000)


# ---- upstream trouble is invisible ----


async def test_upstream_drop_reopens_with_handle_and_client_sees_nothing(tmp_path):
    voice = SeqVoice(
        FixtureVoice(
            [ResumptionHandle("h-9"), TurnComplete()], fail_events_after=1
        ),  # one event, then drops
        FixtureVoice([AudioOut(TONE)]),
    )
    env = Env(tmp_path, voice=voice)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        msgs = await c.drain_json(0.5)
        assert [m["type"] for m in msgs] == ["ai_speaking"]  # only the tone from the new session
        assert len(voice.opened) == 2
        assert voice.opened[1].resumption_handle == "h-9"
        assert TONE in c.frames
        assert env.doc().state == "live"


async def test_goaway_reopens_with_latest_handle(tmp_path):
    voice = SeqVoice(
        FixtureVoice([ResumptionHandle("h-a"), GoAway(5.0), AudioOut(b"never")]),
        FixtureVoice([AudioOut(TONE)]),
    )
    env = Env(tmp_path, voice=voice)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        msgs = await c.drain_json(0.5)
        assert all(m["type"] == "ai_speaking" for m in msgs)
        assert len(voice.opened) == 2 and voice.opened[1].resumption_handle == "h-a"
        assert b"never" not in c.frames


async def test_upstream_unavailable_at_open_then_reconnect_possible(tmp_path):
    env = Env(tmp_path, voice=FixtureVoice(fail_open=True))
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        assert await c.recv_json() == {"type": "error", "code": "upstream_unavailable"}
        await expect_close(c, 1011)
    d = env.doc()
    assert d.state == "live" and d.disconnected_at is not None


async def test_persistent_upstream_failure_surfaces_error(tmp_path):
    env = Env(tmp_path, voice=FixtureVoice([TurnComplete()], fail_events_after=0))
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        msgs = await c.drain_json(1.0)
        assert {"type": "error", "code": "upstream_unavailable"} in msgs


async def test_upstream_that_closes_right_after_every_open_gives_up_with_error(
    tmp_path, monkeypatch
):
    # mirrors the real Gemini adapter: any failure becomes `Closed(reason)` (never an exception)
    import onolys_api.voice.relay as relay

    monkeypatch.setattr(relay, "REOPEN_BACKOFF_S", 0.0)
    voice = FakeVoice(FixtureVoice([Closed("boom")]))
    env = Env(tmp_path, voice=voice)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        msgs = await c.drain_json(1.0)
        assert {"type": "error", "code": "upstream_unavailable"} in msgs
    assert len(voice.opened) == relay.MAX_REOPENS + 1
    d = env.doc()
    assert d.state == "live" and d.disconnected_at is not None  # re-attach stays possible


async def test_reopen_backs_off_between_fruitless_reopens(tmp_path, monkeypatch):
    import onolys_api.voice.relay as relay

    monkeypatch.setattr(relay, "REOPEN_BACKOFF_S", 0.3)
    voice = FakeVoice(FixtureVoice([Closed("boom")]))
    env = Env(tmp_path, voice=voice)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        await asyncio.sleep(0.2)
        assert len(voice.opened) <= 2  # not a hot loop: the later reopens wait
        msgs = await c.drain_json(3.0)
        assert {"type": "error", "code": "upstream_unavailable"} in msgs


class _StreamVoice:
    """Upstream that streams AI audio continuously (a send races the client drop)."""

    def __init__(self):
        self.closed = 0

    async def open(self, params):
        outer = self

        class S:
            async def send_audio(self, pcm):
                pass

            async def events(self):
                while True:
                    yield AudioOut(TONE)
                    await asyncio.sleep(0.001)

            async def close(self):
                outer.closed += 1

        return S()


async def test_client_drop_seen_by_a_send_is_a_clean_disconnect(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    env = Env(tmp_path, voice=_StreamVoice())
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        await env.clock.advance(35)
        c.ws.transport.abort()  # abrupt drop while AI audio is streaming
        await asyncio.sleep(0.5)
    d = env.doc()
    assert d.state == "live" and d.disconnected_at is not None
    assert d.duration_s == 35.0
    assert "voice_error" not in caplog.text and "internal_error" not in caplog.text
    assert env.voice.closed >= 1


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("Unexpected ASGI message 'websocket.send', after sending 'websocket.close'"),
        WebSocketDisconnect(1006),
    ],
)
@pytest.mark.parametrize("kind", ["json", "audio"])
async def test_send_on_a_dropped_client_is_a_client_drop_not_an_internal_error(exc, kind):
    import onolys_api.voice.relay as relay

    class Dead:
        application_state = WebSocketState.CONNECTED

        async def send_text(self, _):
            raise exc

        async def send_bytes(self, _):
            raise exc

    r = relay.Relay.__new__(relay.Relay)
    r.ws, r._send_lock = Dead(), asyncio.Lock()
    with pytest.raises(relay._Fatal) as ei:
        await (r.send_json({"type": "x"}) if kind == "json" else r.send_audio(b"\x00\x00"))
    assert ei.value.outcome == "client_drop"


# ---- live-state poll (SEC1), ownership, lease ----


async def test_poll_checkpoints_duration_and_seen_at_every_10s(tmp_path):
    env = Env(tmp_path)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        await env.clock.advance(25)
        d = env.doc()
        assert d.duration_s == 20.0 and d.seen_at == T0 + timedelta(seconds=20)
        await c.ws.close()


async def test_rest_end_while_socket_live_closes_socket_and_charges_long_interview(tmp_path):
    env = Env(tmp_path)
    env.interview()
    settings = env.app.state.settings
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        await env.clock.advance(45)
        d = settle_interview(env.repo, settings, "alice", "i1", "ended", env.clock.wall())
        assert d.refunded is False  # 40 s recorded + 5 s since the checkpoint >= 30
        await env.clock.advance(10)  # the next poll sees `ended`
        msgs = await c.drain_json(0.5)
        assert {"type": "error", "code": "interview_not_live"} in msgs
        await expect_close(c, 4409)
    assert env.voice._inner.sessions[0].close_calls >= 1
    assert env.doc().duration_s == 40.0  # the relay did not rewrite a settled interview


async def test_immediate_rest_end_gets_at_most_one_poll_interval_of_upstream(tmp_path):
    env = Env(tmp_path)
    env.interview()
    settings = env.app.state.settings
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        await env.clock.advance(3)
        d = settle_interview(env.repo, settings, "alice", "i1", "ended", env.clock.wall())
        assert d.refunded is True  # honest short interview
        await env.clock.advance(10)
        await expect_close(c, 4409)


async def test_non_owner_cannot_cut_the_owners_socket(tmp_path):
    env = Env(tmp_path)
    env.interview("alice")
    async with serve(env.app) as base:
        c1 = await connect(base)
        await ready(c1)
        c2 = await connect(base, token="test:bob")
        assert await c2.recv_json() == {"type": "error", "code": "interview_not_found"}
        await expect_close(c2, 4404)
        await asyncio.sleep(0.2)
        assert c1.ws.close_code is None  # alice's socket was not taken over
        await env.clock.advance(15)
        assert c1.ws.close_code is None and len(env.voice.opened) == 1


async def test_stale_connection_lease_closes_the_older_connection(tmp_path):
    env = Env(tmp_path)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        env.repo.update_interview("alice", "i1", {"conn_id": "another-instance"})
        await env.clock.advance(10)
        msgs = await c.drain_json(0.5)
        assert {"type": "error", "code": "interview_not_live"} in msgs
        await expect_close(c, 4409)
    d = env.doc()
    assert d.conn_id == "another-instance" and d.disconnected_at is None  # newer owner untouched


async def test_superseded_connections_final_checkpoint_does_not_mark_the_new_owner(tmp_path):
    env = Env(tmp_path)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        await env.clock.advance(5)
        env.repo.update_interview("alice", "i1", {"conn_id": "another-instance"})
        await c.ws.close()  # the old connection sees a client drop and writes its final checkpoint
        await asyncio.sleep(0.3)
    d = env.doc()
    assert d.conn_id == "another-instance" and d.disconnected_at is None


async def test_poll_checkpoint_clears_a_stale_disconnected_at(tmp_path):
    env = Env(tmp_path)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        env.repo.update_interview("alice", "i1", {"disconnected_at": T0})
        await env.clock.advance(10)
        assert env.doc().disconnected_at is None
        await c.ws.close()


async def test_stale_created_interview_is_refused_and_refunded(tmp_path):
    env = Env(tmp_path)
    env.interview()
    await env.clock.advance(600 + 60 + 1)  # older than AI_MAX_SECONDS + AI_RECONNECT_SECONDS
    async with serve(env.app) as base:
        c = await connect(base)
        assert await c.recv_json() == {"type": "error", "code": "interview_not_live"}
        await expect_close(c, 4409)
    d = env.doc()
    assert d.state == "abandoned" and d.refunded is True
    assert env.voice.opened == []


async def test_created_interview_inside_the_start_window_is_served(tmp_path):
    env = Env(tmp_path)
    env.interview()
    await env.clock.advance(600)
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        await c.ws.close()
    assert env.doc().live_at is not None


# ---- mic gate ----


@pytest.mark.parametrize("gate", [True, False])
async def test_mic_gate_drops_frames_while_ai_speaks(tmp_path, gate):
    # the tone starts "speaking" and no TurnComplete follows: the AI is speaking throughout
    voice = FixtureVoice([AudioOut(TONE)])
    env = Env(tmp_path, voice=voice, ai_mic_gate=gate)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        await c.drain_json(0.3)
        await c.ws.send(b"\x07\x07" * 10)
        await asyncio.sleep(0.2)
        sent = voice.sessions[0].sent
        assert (sent == []) if gate else (sent == [b"\x07\x07" * 10])


async def test_voice_service_mode_is_accepted_and_serves_only_health(tmp_path):
    import httpx

    assert Settings.from_env({"ENV": "local", "SERVICE_MODE": "voice"}).service_mode == "voice"
    env = Env(tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=env.app), base_url="http://t"
    ) as c:
        body = (await c.get("/v1/healthz")).json()
        gone = [(await c.get(p)).status_code for p in ("/v1/interviews/x", "/v1/scenarios")]
    assert body["service_mode"] == "voice" and gone == [404, 404]


# ---- A21: frame size / rate caps and a reconnect cap ----


async def test_oversized_audio_frame_closes_1009_and_is_not_forwarded(tmp_path):
    env = Env(tmp_path, ai_max_frame_bytes=1000)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        await c.ws.send(b"\x01\x02" * 501)  # 1002 bytes
        out = await c.drain_json()
        assert {"type": "error", "code": "frame_too_large"} in out
        await expect_close(c, 1009)
    assert env.doc().state == "live"  # the client may re-attach; the interview is not settled


async def test_audio_faster_than_the_rate_cap_closes_1008(tmp_path):
    env = Env(tmp_path, ai_max_frame_bytes=600, ai_max_audio_bytes_per_s=1000)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        await c.ws.send(b"\x01\x02" * 250)  # 500 B, within the 1000 B window
        await c.ws.send(b"\x01\x02" * 250)  # 1000 B
        await c.ws.send(b"\x01\x02" * 250)  # 1500 B > cap
        out = await c.drain_json()
        assert {"type": "error", "code": "rate_limited"} in out
        await expect_close(c, 1008)


async def test_oversized_text_frame_closes_1009(tmp_path):
    env = Env(tmp_path)
    env.interview()
    async with serve(env.app) as base:
        c = await connect(base)
        await ready(c)
        await c.ws.send(json.dumps({"type": "end", "pad": "x" * 10_000}))
        out = await c.drain_json()
        assert {"type": "error", "code": "frame_too_large"} in out
        await expect_close(c, 1009)


async def test_reconnect_cap_ends_the_interview(tmp_path):
    env = Env(tmp_path, ai_max_connects=3)
    env.interview(state="live", connects=3, disconnected_at=T0, duration_s=100.0, conn_id="old")
    async with serve(env.app) as base:
        c = await connect(base)
        assert await c.recv_json() == {"type": "error", "code": "interview_not_live"}
        await expect_close(c, 4409)
    assert env.doc().state == "ended" and len(env.voice.opened) == 0
