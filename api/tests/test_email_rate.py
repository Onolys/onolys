"""Email rate limiter: fixed-window counters (memory store always; Firestore emulator when set)."""

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from onolys_api.email.rate import (
    EmailRateLimiter,
    FirestoreRateStore,
    MemoryRateStore,
    client_ip,
)

T0 = datetime(2026, 11, 24, 12, 0, 0, tzinfo=UTC)
KEY = b"test-hmac-key"


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


@pytest.fixture(params=["memory", pytest.param("firestore", marks=pytest.mark.firestore)])
def store(request):
    if request.param == "memory":
        return MemoryRateStore()
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        pytest.skip("FIRESTORE_EMULATOR_HOST not set")
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore

    return FirestoreRateStore(
        firestore.Client(project="demo-onolys", credentials=AnonymousCredentials()),
        collection=f"email_rate_test_{uuid.uuid4().hex[:8]}",
    )


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def limiter(store, clock):
    return EmailRateLimiter(store, KEY, clock=clock)


@pytest.fixture
def uid():
    return f"u-{uuid.uuid4().hex[:10]}"


def _email():
    return f"{uuid.uuid4().hex[:8]}@example.com"


def test_verify_one_per_minute_then_allowed_after_window(limiter, clock, uid):
    assert limiter.check_verify(uid) is True
    assert limiter.check_verify(uid) is False
    clock.advance(30)
    assert limiter.check_verify(uid) is False
    clock.advance(31)
    assert limiter.check_verify(uid) is True


def test_verify_five_per_hour_cap(limiter, clock, uid):
    for _ in range(5):
        assert limiter.check_verify(uid) is True
        clock.advance(61)
    assert limiter.check_verify(uid) is False  # 6th inside the hour
    clock.advance(3600)
    assert limiter.check_verify(uid) is True  # new hour window


def test_reset_per_email_minute_and_hour(limiter, clock):
    email = _email()
    assert limiter.check_reset(email, "1.1.1.1") is True
    assert limiter.check_reset(email, "1.1.1.1") is False
    clock.advance(61)
    for _ in range(4):
        assert limiter.check_reset(email, "1.1.1.1") is True
        clock.advance(61)
    assert limiter.check_reset(email, "1.1.1.1") is False  # 6th in the hour


def test_reset_email_is_case_and_space_insensitive(limiter):
    email = _email()
    assert limiter.check_reset(email, "2.2.2.2") is True
    assert limiter.check_reset(f"  {email.upper()} ", "2.2.2.2") is False


def test_reset_ip_cap_20_per_hour_across_emails(limiter, clock):
    ip = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.1"
    for _ in range(20):
        assert limiter.check_reset(_email(), ip) is True
    assert limiter.check_reset(_email(), ip) is False
    assert limiter.check_reset(_email(), "9.9.9.9") is True  # other ip unaffected
    clock.advance(3601)
    assert limiter.check_reset(_email(), ip) is True


def test_keys_are_independent(limiter, uid):
    other = f"u-{uuid.uuid4().hex[:10]}"
    assert limiter.check_verify(uid) is True
    assert limiter.check_verify(other) is True
    assert limiter.check_verify(uid) is False
    # verify and reset namespaces do not collide even with the same subject string
    assert limiter.check_reset(uid, "3.3.3.3") is True


def test_ttl_field_set_in_future(store, clock, uid):
    limiter = EmailRateLimiter(store, KEY, clock=clock)
    limiter.check_verify(uid)
    docs = store.documents()
    assert docs
    for data in docs.values():
        assert data["count"] == 1
        assert data["expires_at"] > clock.now
        assert data["expires_at"] <= clock.now + timedelta(hours=3)


def test_no_raw_email_or_ip_in_doc_ids(store, clock, uid):
    limiter = EmailRateLimiter(store, KEY, clock=clock)
    email, ip = "Someone.Secret@example.com", "203.0.113.77"
    limiter.check_reset(email, ip)
    limiter.check_verify(uid)
    ids = list(store.documents())
    assert ids
    for doc_id in ids:
        low = doc_id.lower()
        assert "someone" not in low and "example.com" not in low and "@" not in low
        assert "203.0.113.77" not in doc_id
        assert uid not in doc_id
        assert "/" not in doc_id


def test_concurrent_hits_never_over_allow(store, clock, uid):
    limiter = EmailRateLimiter(store, KEY, clock=clock)
    n = 6
    barrier = threading.Barrier(n)

    def go(_):
        barrier.wait(timeout=30)
        return limiter.check_verify(uid)

    with ThreadPoolExecutor(n) as ex:
        results = list(ex.map(go, range(n)))
    assert results.count(True) == 1  # 1/60s window


def test_denial_does_not_extend_window(limiter, clock, uid):
    assert limiter.check_verify(uid)
    for _ in range(10):
        assert not limiter.check_verify(uid)
    clock.advance(61)
    assert limiter.check_verify(uid)


@pytest.mark.parametrize(
    "header,hops,expected",
    [
        ("203.0.113.7, 130.211.0.1", 1, "203.0.113.7"),  # Hosting path: client, hosting hop
        ("  198.51.100.4  ", 1, "198.51.100.4"),  # shorter than hops+1: clamp to leftmost
        ("6.6.6.6, 7.7.7.7, 203.0.113.7, 130.211.0.1", 1, "203.0.113.7"),  # spoofed prefix ignored
        ("1.2.3.4, 5.6.7.8, 203.0.113.7", 0, "203.0.113.7"),
        ("1.2.3.4, 5.6.7.8, 203.0.113.7", 2, "1.2.3.4"),
        ("2001:db8::1, 130.211.0.1", 1, "2001:db8::1"),
        ("", 1, "unknown"),
        (None, 1, "unknown"),
        (" , ", 1, "unknown"),
        ("evil<script>, 130.211.0.1", 1, "unknown"),  # garbage never becomes a bucket key
    ],
)
def test_client_ip(header, hops, expected):
    assert client_ip(header, hops) == expected


def test_spoofed_prefix_does_not_change_ip_bucket(limiter):
    real = "203.0.113.9, 130.211.0.1"
    for i in range(20):
        spoof = f"10.0.{i}.{i + 1}, {real}"
        assert limiter.check_reset(_email(), client_ip(spoof, 1)) is True
    assert limiter.check_reset(_email(), client_ip("10.9.9.9, " + real, 1)) is False  # same bucket


def test_ip_over_cap_does_not_consume_victim_email_slots(limiter, clock):
    ip = "198.51.100.200"
    for _ in range(20):
        assert limiter.check_reset(_email(), ip) is True
    victim = _email()
    assert limiter.check_reset(victim, ip) is False  # blocked by the IP cap
    assert limiter.check_reset(victim, "192.0.2.50") is True  # victim's email slot untouched
