"""Voice relay (SP10 R4, D1, D4, D7, D8): `wss://<voice-host>/v1/voice/{interview_id}`.

The relay owns the persona prompt, the upstream session and the clock. Nothing from the scenario
(prompt, hidden_info, rules) is ever sent to the client or logged. Protocol (PRD Architecture):
C->S `{type:auth, id_token}` first (else close 4401), binary PCM16 16 kHz, `{type:end}`;
S->C `ready`, binary PCM16 24 kHz, `ai_speaking`, `interrupted`, `warn`, `time_up`, `error`.
"""

import asyncio
import contextlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import anyio
from fastapi import APIRouter, WebSocket
from onolys_core.voice import (
    AudioOut,
    Closed,
    GoAway,
    Interrupted,
    ResumptionHandle,
    TurnComplete,
    VoiceProviderError,
    VoiceSession,
)
from onolys_core.voice.select import load_voice_config, select_voice
from starlette.websockets import WebSocketDisconnect, WebSocketState

from onolys_api import logs
from onolys_api.errors import ApiError
from onolys_api.jobs.interviews import settle_interview
from onolys_api.repo.base import NotFoundError
from onolys_api.repo.models import InterviewDoc
from onolys_api.voice.clock import Clock, ConnectedTimer
from onolys_api.voice.prompt import build_system_prompt

router = APIRouter()
AUTH_TIMEOUT_S = 10.0
MAX_REOPENS = 3  # consecutive upstream reopens without any content event (audio, turn, handle)
REOPEN_BACKOFF_S = 0.25  # real-time wait before the 2nd, 3rd... consecutive fruitless reopen
POLL_INTERVAL_S = 10.0  # live-state poll + checkpoint cadence: bounds free time after an End
CLOSE_UNAUTH, CLOSE_FORBIDDEN, CLOSE_NOT_FOUND, CLOSE_NOT_LIVE = 4401, 4403, 4404, 4409


class _Stop(Exception):
    """Ends the connection from inside a task (carries nothing)."""


@dataclass
class Connection:
    """One live client connection of an interview on this instance (for takeover)."""

    stop: asyncio.Event = field(default_factory=asyncio.Event)
    done: asyncio.Event = field(default_factory=asyncio.Event)
    superseded: bool = False


async def _io(fn, *args):
    return await anyio.to_thread.run_sync(fn, *args)


class Relay:
    def __init__(self, ws: WebSocket, iid: str) -> None:
        self.ws = ws
        self.iid = iid
        st = ws.app.state
        self.settings = st.settings
        self.repo = st.repo
        self.clock: Clock = st.voice_clock
        self._send_lock = asyncio.Lock()
        self.session: VoiceSession | None = None
        self.handle: str | None = None
        self.ai_speaking = False
        self.uid = ""
        self.conn_id = ""

    # ---- client frames ----

    async def _send(self, fn, payload) -> None:
        async with self._send_lock:
            if self.ws.application_state == WebSocketState.CONNECTED:
                try:
                    await fn(payload)
                except (RuntimeError, WebSocketDisconnect):
                    # the client went away and this send noticed first: same as a receive-side drop
                    raise _Fatal("client_drop") from None

    async def send_json(self, obj: dict[str, Any]) -> None:
        await self._send(self.ws.send_text, json.dumps(obj))

    async def send_audio(self, pcm: bytes) -> None:
        await self._send(self.ws.send_bytes, pcm)

    async def fail(self, code: str, close: int) -> None:
        with contextlib.suppress(Exception):
            await self.send_json({"type": "error", "code": code})
        await self.close(close)

    async def close(self, code: int = 1000) -> None:
        with contextlib.suppress(Exception):
            if self.ws.application_state == WebSocketState.CONNECTED:
                await self.ws.close(code)

    # ---- connection ----

    async def authenticate(self) -> str | None:
        try:
            raw = await asyncio.wait_for(self.ws.receive_text(), AUTH_TIMEOUT_S)
            msg = json.loads(raw)
        except (TimeoutError, WebSocketDisconnect, RuntimeError, ValueError, KeyError):
            return None
        token = msg.get("id_token") if isinstance(msg, dict) else None
        if not isinstance(msg, dict) or msg.get("type") != "auth" or not isinstance(token, str):
            return None
        try:
            user = await _io(self.ws.app.state.auth.authenticate, token, None)
        except ApiError:
            return None
        except Exception:  # noqa: BLE001  (verifier/network trouble: treat as unauthenticated)
            return None
        return user.uid

    def _params(self, doc: InterviewDoc):
        sc = self.ws.app.state.scenarios[doc.scenario_id]
        return select_voice(
            voice=doc.voice,
            language=sc["language"],
            system_prompt=build_system_prompt(sc),
            resumption_handle=self.handle,
            config=load_voice_config(),
        )

    async def run(self) -> None:
        st = self.ws.app.state
        origin = self.ws.headers.get("origin")
        if origin not in self.settings.cors_origins:
            await self.ws.close(CLOSE_FORBIDDEN)  # before accept: the handshake is refused (403)
            return
        await self.ws.accept()
        uid = await self.authenticate()
        if uid is None:
            await self.close(CLOSE_UNAUTH)
            return
        self.uid = uid
        try:  # ownership first: a non-owner must not even cut the owner's socket
            await _io(self.repo.get_interview, uid, self.iid)
        except NotFoundError:
            await self.fail("interview_not_found", CLOSE_NOT_FOUND)  # same for foreign and missing
            return

        registry: dict[str, Connection] = st.voice_connections
        old = registry.get(self.iid)
        if old is not None:  # same interview already connected here (half-open socket): take over
            old.superseded = True
            old.stop.set()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(old.done.wait(), 5)
        conn = Connection()
        registry[self.iid] = conn
        try:
            await self._serve(conn)
        except _Stop:
            pass
        except Exception as e:  # noqa: BLE001
            logs.emit("voice_error", logging.ERROR, exc_class=type(e).__name__)
            await self.fail("internal_error", 1011)
        finally:
            if registry.get(self.iid) is conn:
                del registry[self.iid]
            conn.done.set()

    async def _serve(self, conn: Connection) -> None:
        settings = self.settings
        try:
            doc = await _io(self.repo.get_interview, self.uid, self.iid)
        except NotFoundError:
            await self.fail("interview_not_found", CLOSE_NOT_FOUND)  # same for foreign and missing
            return
        if doc.state not in ("created", "live"):
            await self.fail("interview_not_live", CLOSE_NOT_LIVE)
            return
        sc_ok = doc.scenario_id in self.ws.app.state.scenarios
        if not sc_ok:
            await self.fail("interview_not_live", CLOSE_NOT_LIVE)
            return

        resumed = doc.state == "live"
        if resumed and doc.disconnected_at is not None:
            gap = (self.clock.wall() - doc.disconnected_at).total_seconds()
            if gap > settings.ai_reconnect_seconds:  # too late: the interview ends as it was
                await _io(
                    settle_interview, self.repo, settings, self.uid, self.iid, "ended",
                    self.clock.wall(),
                )  # fmt: skip
                await self.fail("interview_not_live", CLOSE_NOT_LIVE)
                return
        carried = doc.duration_s or 0.0
        if carried >= settings.ai_max_seconds:
            await self._finish(carried)
            await self.fail("interview_not_live", CLOSE_NOT_LIVE)
            return
        self.handle = doc.resumption_handle if resumed else None
        self.conn_id = uuid.uuid4().hex

        won = await _io(
            self.repo.transition_interview, self.uid, self.iid, ("created", "live"), "live",
            {
                "disconnected_at": None, "conn_id": self.conn_id, "duration_s": carried,
                "seen_at": self.clock.wall(),
            },
        )  # fmt: skip
        if won is None:
            await self.fail("interview_not_live", CLOSE_NOT_LIVE)
            return

        timer = ConnectedTimer(self.clock, carried)
        try:
            await self._open_upstream(doc)
        except VoiceProviderError:
            await self._checkpoint(timer, disconnected=True)
            await self.fail("upstream_unavailable", 1011)
            return
        logs.emit("voice_open", outcome="resumed" if resumed else "new")
        try:
            await self.send_json({
                "type": "ready", "resumed": resumed, "elapsed_s": round(timer.elapsed(), 3),
                "max_s": settings.ai_max_seconds, "warn_s": settings.ai_warn_seconds,
            })  # fmt: skip
        except _Fatal:  # the client vanished before `ready`
            await self._close_upstream()
            await self._checkpoint(timer, disconnected=True)
            return

        tasks = {
            "up": asyncio.create_task(self._pump_up(), name="up"),
            "down": asyncio.create_task(self._pump_down(doc, timer), name="down"),
            "timer": asyncio.create_task(self._run_timer(timer), name="timer"),
            "poll": asyncio.create_task(self._run_poll(timer), name="poll"),
            "stop": asyncio.create_task(conn.stop.wait(), name="stop"),
        }
        outcome = "client_drop"
        try:
            done, _ = await asyncio.wait(tasks.values(), return_when=asyncio.FIRST_COMPLETED)
            for name, t in tasks.items():
                if t in done:
                    outcome = name
                    if name in ("up", "down", "timer", "poll") and t.exception() is not None:
                        exc = t.exception()
                        if isinstance(exc, _Fatal):
                            outcome = exc.outcome
                        else:
                            raise exc
                    elif name in ("up", "down", "timer", "poll"):
                        outcome = t.result() or name
        finally:
            for t in tasks.values():
                t.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)
            await self._close_upstream()

        elapsed = min(timer.elapsed(), float(settings.ai_max_seconds))
        if outcome == "not_live":  # settled elsewhere (End/abandon) or a newer connection owns it
            await self.fail("interview_not_live", CLOSE_NOT_LIVE)  # no checkpoint: not ours now
        elif outcome == "time_up":
            await self._finish(float(settings.ai_max_seconds))
            await self.close(1000)
        elif outcome == "end":
            await self._finish(elapsed)
            await self.close(1000)
        elif outcome == "upstream_unavailable":
            await self._checkpoint(timer, disconnected=True)
            await self.fail("upstream_unavailable", 1011)
        elif conn.superseded:
            await self._checkpoint(timer, disconnected=False)
            await self.close(1000)
        else:  # client dropped: keep the interview live for a re-attach
            await self._checkpoint(timer, disconnected=True)
        logs.emit("voice_close", outcome=outcome, elapsed_s=round(elapsed, 1))

    # ---- state ----

    async def _checkpoint(self, timer: ConnectedTimer, *, disconnected: bool) -> None:
        fields: dict[str, Any] = {
            "duration_s": min(timer.elapsed(), float(self.settings.ai_max_seconds)),
            "resumption_handle": self.handle,
            "seen_at": self.clock.wall(),
        }
        if disconnected:
            fields["disconnected_at"] = self.clock.wall()
        await _io(self.repo.update_interview, self.uid, self.iid, fields)

    async def _finish(self, duration_s: float) -> None:
        await _io(
            self.repo.update_interview, self.uid, self.iid,
            {"duration_s": duration_s, "seen_at": self.clock.wall()},
        )  # fmt: skip
        await _io(
            settle_interview, self.repo, self.settings, self.uid, self.iid, "ended",
            self.clock.wall(),
        )  # fmt: skip

    # ---- upstream ----

    async def _open_upstream(self, doc: InterviewDoc) -> None:
        voice = self.ws.app.state.voice_adapter
        self.session = await voice.open(self._params(doc))

    async def _close_upstream(self) -> None:
        s, self.session = self.session, None
        if s is not None:
            with contextlib.suppress(Exception):
                await s.close()

    async def _pump_up(self) -> str | None:
        gate = self.settings.ai_mic_gate
        while True:
            msg = await self.ws.receive()
            if msg["type"] == "websocket.disconnect":
                return "client_drop"
            data = msg.get("bytes")
            if data is not None:
                if gate and self.ai_speaking:
                    continue
                s = self.session
                if s is not None:
                    with contextlib.suppress(VoiceProviderError):
                        await s.send_audio(data)  # a dying upstream is the down pump's concern
                continue
            text = msg.get("text")
            if text is None:
                continue
            try:
                obj = json.loads(text)
            except ValueError:
                continue
            if isinstance(obj, dict) and obj.get("type") == "end":
                return "end"

    async def _set_speaking(self, on: bool) -> None:
        if on != self.ai_speaking:
            self.ai_speaking = on
            await self.send_json({"type": "ai_speaking", "on": on})

    async def _pump_down(self, doc: InterviewDoc, timer: ConnectedTimer) -> str | None:
        fruitless = 0
        while True:
            session = self.session
            reopen = False
            if session is None:
                raise _Fatal("upstream_unavailable")
            try:
                async for ev in session.events():
                    if isinstance(ev, (AudioOut, TurnComplete, Interrupted, ResumptionHandle)):
                        fruitless = 0  # only real content proves the upstream works
                    if isinstance(ev, AudioOut):
                        await self._set_speaking(True)
                        await self.send_audio(ev.pcm24k)
                    elif isinstance(ev, Interrupted):
                        await self._set_speaking(False)
                        await self.send_json({"type": "interrupted"})
                    elif isinstance(ev, TurnComplete):
                        await self._set_speaking(False)
                    elif isinstance(ev, ResumptionHandle):
                        self.handle = ev.h
                        await self._checkpoint(timer, disconnected=False)
                    elif isinstance(ev, GoAway):
                        reopen = True
                        break
                    elif isinstance(ev, Closed):
                        reopen = True
                        break
                else:
                    reopen = True
            except VoiceProviderError:
                reopen = True
            if not reopen:
                return None
            fruitless += 1
            if fruitless > MAX_REOPENS:
                raise _Fatal("upstream_unavailable")
            await self._close_upstream()
            await self._set_speaking(False)
            if fruitless > 1:  # a session that dies right after open: do not hot-loop
                await asyncio.sleep(REOPEN_BACKOFF_S * (fruitless - 1))
            try:
                await self._open_upstream(doc)
            except VoiceProviderError:
                raise _Fatal("upstream_unavailable") from None

    # ---- clock ----

    async def _run_poll(self, timer: ConnectedTimer) -> None:
        """Every POLL_INTERVAL_S: stop if the interview left `live` (End, abandon, sweep) or another
        connection took the lease; else checkpoint, so the stored duration is never far stale."""
        while True:
            await self.clock.sleep(POLL_INTERVAL_S)
            try:
                doc = await _io(self.repo.get_interview, self.uid, self.iid)
            except NotFoundError:
                raise _Fatal("not_live") from None
            if doc.state != "live" or doc.conn_id != self.conn_id:
                raise _Fatal("not_live")
            await self._checkpoint(timer, disconnected=False)

    async def _run_timer(self, timer: ConnectedTimer) -> str:
        s = self.settings
        if timer.elapsed() < s.ai_warn_seconds:
            await self.clock.sleep(s.ai_warn_seconds - timer.elapsed())
            await self.send_json({"type": "warn", "at_s": s.ai_warn_seconds})
        await self.clock.sleep(max(0.0, s.ai_max_seconds - timer.elapsed()))
        await self.send_json({"type": "time_up"})
        return "time_up"


class _Fatal(Exception):
    def __init__(self, outcome: str) -> None:
        super().__init__(outcome)
        self.outcome = outcome


@router.websocket("/v1/voice/{interview_id}")
async def voice_ws(ws: WebSocket, interview_id: str) -> None:
    await Relay(ws, interview_id).run()


__all__ = ["Relay", "router"]
