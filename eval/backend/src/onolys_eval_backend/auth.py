"""Separate Firebase user and Google service-account OIDC trust boundaries."""

import asyncio
import json
import threading
import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, Protocol

from google.auth import exceptions, jwt
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from onolys_api.auth.idtoken import IdTokenVerifier, InvalidToken

from onolys_eval_backend.allowlist import AllowlistMiddleware, ClaimsVerifier, bearer_token, deny
from onolys_eval_backend.config import EvalConfig

CERT_TTL_S = 3600

CertFetcher = Callable[[], dict[str, str]]

GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})


class UpstreamUnavailable(Exception):
    pass


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


class TokenVerifier(Protocol):
    def verify(self, token: str) -> dict[str, Any]: ...


class TaskOidcVerifier:
    """google-auth validates signature, expiration, audience and Google issuer."""

    def __init__(
        self,
        audience: str,
        *,
        request=None,
        clock: Callable[[], float] = time.monotonic,
        ttl_s: float = 3600,
    ) -> None:
        self.audience = audience
        self.request = request or Request()
        self._cache = CertificateCache(self._fetch_certs, ttl_s=ttl_s, clock=clock)

    def _fetch_certs(self):
        response = self.request(
            "https://www.googleapis.com/oauth2/v1/certs", method="GET", timeout=5
        )
        if response.status != 200:
            raise exceptions.TransportError("Certificate service unavailable")
        return json.loads(response.data.decode("utf-8"))

    def verify(self, token: str) -> dict[str, Any]:
        certs = self._cache.get(token_key_id(token))

        def cached_request(*args, **kwargs):
            return SimpleNamespace(status=200, data=json.dumps(certs).encode())

        try:
            return id_token.verify_oauth2_token(token, cached_request, audience=self.audience)
        except exceptions.TransportError:
            raise UpstreamUnavailable from None
        except (ValueError, exceptions.GoogleAuthError):
            raise InvalidToken from None


class EvalAuthMiddleware:
    """Only the exact /internal/tasks/ namespace uses the task identity gate."""

    def __init__(
        self,
        app,
        config: EvalConfig,
        verifier: ClaimsVerifier | None = None,
        task_verifier: TokenVerifier | None = None,
    ) -> None:
        self.app = app
        self.config = config
        self.users = AllowlistMiddleware(
            app, verifier or IdTokenVerifier(config.auth_project), config.allowed_emails
        )
        self.task_verifier = task_verifier or TaskOidcVerifier(config.task_audience)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/internal/tasks/"):
            return await self.users(scope, receive, send)
        # Cloud Tasks request headers are metadata, never proof of caller identity.
        token = bearer_token(scope)
        if token is None:
            return await deny(send, 401, "unauthenticated", "Authentication required.")
        try:
            claims = await asyncio.to_thread(self.task_verifier.verify, token)
        except InvalidToken:
            return await deny(send, 401, "unauthenticated", "Authentication required.")
        except UpstreamUnavailable:
            return await deny(send, 503, "upstream_unavailable", "Service temporarily unavailable.")
        if (
            claims.get("iss") not in GOOGLE_ISSUERS
            or claims.get("aud") != self.config.task_audience
            or claims.get("email") != self.config.tasks_sa
            or claims.get("email_verified") is not True
        ):
            return await deny(send, 403, "forbidden", "Not allowed.")
        return await self.app(scope, receive, send)
