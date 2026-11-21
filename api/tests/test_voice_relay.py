"""SP10 Task 5: voice relay (R4, D1, D4, D7, D8, AC2, AC4, AC5), fixture adapter + manual clock."""

import asyncio
import json
import logging
from datetime import UTC, datetime

import pytest
import websockets
from leak_helpers import find_leaks
from onolys_core.voice import AudioOut, GoAway, ResumptionHandle, TurnComplete
from onolys_core.voice.fixture import FixtureVoice, tone_pcm24k
from voice_helpers import ManualClock, serve

from onolys_api.adapters.fake import FakeVoice
from onolys_api.app import create_app
from onolys_api.config import Settings
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
