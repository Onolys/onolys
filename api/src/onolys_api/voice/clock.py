"""Injectable time source for the voice relay (the relay owns the clock).

`monotonic()` measures connected seconds, `wall()` stamps documents, `sleep()` drives the warn and
time-up timers. Tests inject a manual clock with the same three methods.
"""

import asyncio
import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float: ...

    def wall(self) -> datetime: ...

    async def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def wall(self) -> datetime:
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class ConnectedTimer:
    """Elapsed interview seconds: carried over earlier connections + this one's connected time."""

    def __init__(self, clock: Clock, carried_s: float = 0.0) -> None:
        self._clock = clock
        self._carried = carried_s
        self._since = clock.monotonic()

    def elapsed(self) -> float:
        return self._carried + (self._clock.monotonic() - self._since)
