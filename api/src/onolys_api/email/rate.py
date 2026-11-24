"""Cross-instance abuse limits for the email endpoints (R6, D4).

Fixed-window counters, one doc per (scope, subject, window, window index) in `email_rate/{id}`.
The doc id is an HMAC (`UID_HMAC_KEY`), so no raw email, uid or IP is stored or logged. `expires_at`
is the Firestore TTL field. The limiter only answers allow/deny; routes decide the response.
"""

import hashlib
import hmac
import random
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from google.api_core.exceptions import Aborted
from google.cloud import firestore

COLLECTION = "email_rate"
TTL_FIELD = "expires_at"
MINUTE, HOUR = 60, 3600
_TXN_ATTEMPTS = 5
_TXN_ROUNDS = 12


class RateStore(Protocol):
    def hit(self, doc_id: str, limit: int, window_start: datetime, expires_at: datetime) -> bool:
        """Count one attempt in the window doc; False (count unchanged) if already at `limit`."""
        ...


class MemoryRateStore:
    """Process-local store for local/test mode (single instance, so no cross-instance need)."""

    def __init__(self) -> None:
        self._docs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def hit(self, doc_id, limit, window_start, expires_at) -> bool:
        with self._lock:
            doc = self._docs.get(doc_id)
            count = doc["count"] if doc else 0
            if count >= limit:
                return False
            self._docs[doc_id] = {
                "count": count + 1,
                "window_start": window_start,
                TTL_FIELD: expires_at,
            }
            return True

    def documents(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {k: dict(v) for k, v in self._docs.items()}


class FirestoreRateStore:
    def __init__(self, client: firestore.Client, collection: str = COLLECTION) -> None:
        self._client = client
        self._collection = collection

    def hit(self, doc_id, limit, window_start, expires_at) -> bool:
        ref = self._client.collection(self._collection).document(doc_id)

        @firestore.transactional
        def txn_fn(txn) -> bool:
            snap = ref.get(transaction=txn)
            count = (snap.to_dict() or {}).get("count", 0) if snap.exists else 0
            if count >= limit:
                return False
            txn.set(ref, {"count": count + 1, "window_start": window_start, TTL_FIELD: expires_at})
            return True

        for round_ in range(_TXN_ROUNDS):
            try:
                return txn_fn(self._client.transaction(max_attempts=_TXN_ATTEMPTS))
            except (ValueError, Aborted) as e:
                # contention only: the client's "exhausted attempts" ValueError or a raw 409
                if isinstance(e, ValueError) and "attempt" not in str(e).lower():
                    raise
                if round_ == _TXN_ROUNDS - 1:
                    raise
                time.sleep(random.uniform(0.01, 0.15))
        raise AssertionError("unreachable")  # pragma: no cover

    def documents(self) -> dict[str, dict[str, Any]]:
        return {d.id: d.to_dict() for d in self._client.collection(self._collection).stream()}


def first_forwarded_ip(header: str | None) -> str:
    """First `X-Forwarded-For` hop (Cloud Run puts the client there); 'unknown' if absent."""
    first = (header or "").split(",", 1)[0].strip()
    return first or "unknown"


class EmailRateLimiter:
    def __init__(
        self,
        store: RateStore,
        hmac_key: bytes,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._key = hmac_key
        self._clock = clock

    def _hit(self, scope: str, subject: str, window_s: int, limit: int) -> bool:
        now = self._clock()
        index = int(now.timestamp()) // window_s
        start = datetime.fromtimestamp(index * window_s, UTC)
        msg = f"{scope}\x00{subject}\x00{window_s}\x00{index}".encode()
        doc_id = hmac.new(self._key, msg, hashlib.sha256).hexdigest()
        expires = start + timedelta(seconds=window_s * 2)  # TTL lags; keep past the window
        return self._store.hit(doc_id, limit, start, expires)

    def check_verify(self, uid: str) -> bool:
        """Verification email per uid: 1/60 s and 5/h."""
        return self._hit("verify", uid, MINUTE, 1) and self._hit("verify", uid, HOUR, 5)

    def check_reset(self, email: str, client_ip: str) -> bool:
        """Reset email per email-HMAC: 1/60 s and 5/h; plus per client IP 20/h."""
        e = email.strip().lower()
        return (
            self._hit("reset-email", e, MINUTE, 1)
            and self._hit("reset-email", e, HOUR, 5)
            and self._hit("reset-ip", client_ip or "unknown", HOUR, 20)
        )
