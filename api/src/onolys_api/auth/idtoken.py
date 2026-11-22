"""Identity Platform ID-token verification with Google's public keys.

Checks signature (securetoken certs), expiry, `aud` = project, `iss`, a non-empty `sub`
and `email_verified`. Only `uid` is taken from the claims. The cert fetcher is injectable so
tests mint tokens with a local key and never touch the network.
"""

import threading
import time
from collections.abc import Callable
from typing import Protocol

from google.auth import jwt

from onolys_api.errors import ApiError

CERTS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
)
CERT_TTL_S = 3600
CLOCK_SKEW_S = 10
MIN_REFRESH_S = 60  # floor between cert fetches once certs are cached
UNKNOWN_KID_TTL_S = 300
MAX_UNKNOWN_KIDS = 1024

CertFetcher = Callable[[], dict[str, str]]


class TokenVerifier(Protocol):
    def verify(self, token: str) -> str:
        """Return the uid or raise `InvalidToken`."""
        ...


class InvalidToken(Exception):
    pass


class EmailNotVerified(InvalidToken):
    """A genuine, correctly signed token whose email is not verified yet."""


def fetch_google_certs() -> dict[str, str]:
    import requests

    resp = requests.get(CERTS_URL, timeout=5)
    resp.raise_for_status()
    return resp.json()


class IdTokenVerifier:
    """Cert cache: TTL refresh, rotation refresh bounded by `min_refresh_s`, stale-on-failure.

    An unauthenticated caller controls the token's `kid`, so an unknown kid must never force an
    unbounded fetch: forced refreshes are rate limited, unknown kids are negative-cached, the
    fetch runs single-flight under its own lock (never the cache state lock), and a failed fetch
    keeps serving the previous certs.
    """

    def __init__(
        self,
        project: str,
        fetch_certs: CertFetcher = fetch_google_certs,
        ttl_s: float = CERT_TTL_S,
        clock: Callable[[], float] = time.monotonic,
        min_refresh_s: float = MIN_REFRESH_S,
        unknown_kid_ttl_s: float = UNKNOWN_KID_TTL_S,
    ) -> None:
        self._project = project
        self._fetch = fetch_certs
        self._ttl = ttl_s
        self._clock = clock
        self._min_refresh = min_refresh_s
        self._unknown_ttl = unknown_kid_ttl_s
        self._certs: dict[str, str] = {}
        self._fetched_at = float("-inf")
        self._last_attempt = float("-inf")
        self._unknown: dict[str, float] = {}  # kid -> negative-cache expiry
        self._state_lock = threading.Lock()  # guards the fields above, never held across a fetch
        self._fetch_lock = threading.Lock()  # single-flight

    def _is_unknown(self, kid: object) -> bool:
        if not isinstance(kid, str):
            return False
        with self._state_lock:
            expiry = self._unknown.get(kid)
            return expiry is not None and self._clock() < expiry

    def _remember_unknown(self, kid: object) -> None:
        if not isinstance(kid, str):
            return
        with self._state_lock:
            if len(self._unknown) >= MAX_UNKNOWN_KIDS:
                self._unknown.clear()
            self._unknown[kid] = self._clock() + self._unknown_ttl

    def _get_certs(self, force: bool = False) -> dict[str, str]:
        def due() -> bool:
            now = self._clock()
            if not self._certs:
                return True
            if now - self._last_attempt < self._min_refresh:
                return False
            return force or now - self._fetched_at > self._ttl

        with self._state_lock:
            if not due():
                return self._certs
        with self._fetch_lock:
            with self._state_lock:
                if not due():  # another caller refreshed while we waited
                    return self._certs
                stale = self._certs
            attempt = self._clock()
            try:
                fresh = self._fetch()
            except Exception:
                with self._state_lock:
                    self._last_attempt = attempt
                if stale:
                    return stale
                raise ApiError.of(
                    503, "upstream_unavailable", "Service temporarily unavailable."
                ) from None
            with self._state_lock:
                self._certs = fresh
                self._fetched_at = self._last_attempt = attempt
                self._unknown.clear()
                return fresh

    def _decode(self, token: str, certs: dict[str, str]) -> dict:
        return jwt.decode(
            token,
            certs=certs,
            audience=self._project,
            clock_skew_in_seconds=CLOCK_SKEW_S,
        )

    def verify(self, token: str) -> str:
        try:
            header = jwt.decode_header(token)
            if header.get("alg") != "RS256":
                raise InvalidToken
            certs = self._get_certs()
            kid = header.get("kid")
            if kid not in certs:  # key rotation: rate-limited refresh
                if self._is_unknown(kid):
                    raise InvalidToken
                certs = self._get_certs(force=True)
                if kid not in certs:
                    self._remember_unknown(kid)
                    raise InvalidToken
            claims = self._decode(token, certs)
        except ApiError:
            raise
        except Exception:
            raise InvalidToken from None
        if claims.get("iss") != f"https://securetoken.google.com/{self._project}":
            raise InvalidToken
        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub or len(sub) > 128 or "/" in sub:
            raise InvalidToken
        if claims.get("email_verified") is not True:
            raise EmailNotVerified  # only after signature, iss, aud and sub all checked out
        return sub
