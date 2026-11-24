"""Identity Platform ID-token verification (signature, aud, iss, expiry) via google-auth.

The cert fetcher is injectable so tests sign tokens with a local key (no network).
"""

import threading
import time
from collections.abc import Callable

from google.auth import jwt

CERTS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
)
CERT_TTL_S = 3600
CLOCK_SKEW_S = 10

CertFetcher = Callable[[], dict[str, str]]


class InvalidToken(Exception):
    pass


class UpstreamUnavailable(Exception):
    pass


def fetch_google_certs() -> dict[str, str]:
    import requests

    resp = requests.get(CERTS_URL, timeout=5)
    resp.raise_for_status()
    return resp.json()


class CertificateCache:
    """Single-flight refresh with bounded waits, cooldown, and no expired-key fallback.

    Unknown IDs share one refresh deadline rather than accumulating per-token state.
    Normal key rotation is discovered within a cooldown after the last fetch.
    """

    def __init__(
        self,
        fetch: CertFetcher,
        ttl_s: float = CERT_TTL_S,
        clock: Callable[[], float] = time.monotonic,
        cooldown_s: float = 30,
        lock_timeout_s: float = 6,
    ) -> None:
        self._fetch = fetch
        self._ttl = ttl_s
        self._clock = clock
        self._cooldown = cooldown_s
        self._lock_timeout = lock_timeout_s
        self._certs: dict[str, str] = {}
        self._fetched_at = float("-inf")
        self._retry_at = float("-inf")
        self._failed = False
        self._lock = threading.Lock()

    def get(self, kid: str) -> dict[str, str]:
        if not self._lock.acquire(timeout=self._lock_timeout):
            raise UpstreamUnavailable
        try:
            now = self._clock()
            fresh = bool(self._certs) and now - self._fetched_at < self._ttl
            if fresh and kid in self._certs:
                return self._certs
            if now < self._retry_at:
                if self._failed or not fresh:
                    raise UpstreamUnavailable
                return self._certs
            try:
                certs = self._fetch()
                if (
                    not isinstance(certs, dict)
                    or not certs
                    or not all(
                        isinstance(k, str) and isinstance(v, str) and v for k, v in certs.items()
                    )
                ):
                    raise ValueError("Invalid certificate response")
            except Exception:
                self._failed = True
                raise UpstreamUnavailable from None
            else:
                self._certs = dict(certs)
                self._fetched_at = self._clock()
                self._failed = False
                return self._certs
            finally:
                self._retry_at = self._clock() + self._cooldown
        finally:
            self._lock.release()


def token_key_id(token: str) -> str:
    try:
        header = jwt.decode_header(token)
        kid = header.get("kid")
        if header.get("alg") != "RS256" or not isinstance(kid, str) or not kid:
            raise InvalidToken
        return kid
    except Exception:
        raise InvalidToken from None


class IdTokenVerifier:
    def __init__(
        self,
        project: str,
        fetch_certs: CertFetcher = fetch_google_certs,
        ttl_s: float = CERT_TTL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._project = project
        self._cache = CertificateCache(fetch_certs, ttl_s, clock)

    def verify(self, token: str) -> dict:
        """Return the verified claims or raise InvalidToken / UpstreamUnavailable."""
        kid = token_key_id(token)
        certs = self._cache.get(kid)
        try:
            claims = jwt.decode(
                token,
                certs=certs,
                audience=self._project,
                clock_skew_in_seconds=CLOCK_SKEW_S,
            )
        except Exception:
            raise InvalidToken from None
        if claims.get("iss") != f"https://securetoken.google.com/{self._project}":
            raise InvalidToken
        return claims
