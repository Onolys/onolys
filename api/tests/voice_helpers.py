"""Test helpers for the voice relay: a manual clock and a real in-process uvicorn server."""

import asyncio
import contextlib
import heapq
import itertools
from datetime import UTC, datetime, timedelta

import uvicorn


class ManualClock:
    """`voice.clock.Clock` whose time only moves when a test calls `advance`."""

    def __init__(self, wall0: datetime | None = None) -> None:
        self._t = 0.0
        self._wall0 = wall0 or datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
        self._waiters: list = []
        self._seq = itertools.count()

    def monotonic(self) -> float:
        return self._t

    def wall(self) -> datetime:
        return self._wall0 + timedelta(seconds=self._t)

    async def sleep(self, seconds: float) -> None:
        fut = asyncio.get_running_loop().create_future()
        heapq.heappush(self._waiters, (self._t + max(0.0, seconds), next(self._seq), fut))
        await fut

    async def _settle(self) -> None:
        await asyncio.sleep(0.05)  # let real socket I/O and woken tasks run

    async def advance(self, dt: float) -> None:
        target = self._t + dt
        while self._waiters and self._waiters[0][0] <= target:
            due, _, fut = heapq.heappop(self._waiters)
            self._t = max(self._t, due)
            if not fut.cancelled():
                fut.set_result(None)
            await self._settle()
        self._t = target
        await self._settle()


@contextlib.asynccontextmanager
async def serve(app):
    """Run `app` on an ephemeral localhost port; yields the ws base URL."""
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", ws="websockets")
    )
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"ws://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task
