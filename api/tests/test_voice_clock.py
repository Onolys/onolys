"""SystemClock and ConnectedTimer."""

import time
from datetime import UTC

import pytest
from voice_helpers import ManualClock

from onolys_api.voice.clock import ConnectedTimer, SystemClock

pytestmark = pytest.mark.unit


def test_system_clock_monotonic_and_wall_are_sane():
    c = SystemClock()
    a = c.monotonic()
    b = c.monotonic()
    assert b >= a
    w = c.wall()
    assert w.tzinfo is UTC
    assert abs(w.timestamp() - time.time()) < 5


async def test_system_clock_sleep_delegates_to_asyncio_sleep(monkeypatch):
    seen = []

    async def fake_sleep(s):
        seen.append(s)

    monkeypatch.setattr("onolys_api.voice.clock.asyncio.sleep", fake_sleep)
    await SystemClock().sleep(7.5)
    assert seen == [7.5]


def test_connected_timer_counts_carried_plus_this_connection():
    clock = ManualClock()
    clock._t = 100.0  # the timer measures from creation, not from clock zero
    t = ConnectedTimer(clock, carried_s=30.0)
    assert t.elapsed() == 30.0
    clock._t += 12.5
    assert t.elapsed() == 42.5


def test_connected_timer_defaults_to_zero_carried():
    clock = ManualClock()
    t = ConnectedTimer(clock)
    clock._t += 3
    assert t.elapsed() == 3
