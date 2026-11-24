"""Separate Firebase user and Google service-account OIDC trust boundaries."""

import asyncio
import json
import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, Protocol

from google.auth import exceptions
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from onolys_admin_auth import AdminAuthMiddleware, InvalidToken, UpstreamUnavailable
from onolys_admin_auth.verifier import CertificateCache, token_key_id

from onolys_eval_backend.config import EvalConfig

GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})


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
        verifier: TokenVerifier | None = None,
        task_verifier: TokenVerifier | None = None,
    ) -> None:
        self.app = app
        self.config = config
        self.admin = AdminAuthMiddleware(app, config=config.auth, verifier=verifier)
        self.task_verifier = task_verifier or TaskOidcVerifier(config.task_audience)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/internal/tasks/"):
            if scope["type"] != "http":
                return await self.admin(scope, receive, send)
            # Preserve verified identity for audit records without another token verification.
            verifier = self.admin.verifier

            class CaptureIdentity:
                def verify(self, token):
                    claims = verifier.verify(token)
                    scope.setdefault("state", {})["admin_claims"] = claims
                    return claims

            return await AdminAuthMiddleware(
                self.app, config=self.config.auth, verifier=CaptureIdentity()
            )(scope, receive, send)
        # Cloud Tasks request headers are metadata, never proof of caller identity.
        authorization = next(
            (v.decode("latin-1") for k, v in scope["headers"] if k == b"authorization"), ""
        ).split(None, 1)
        if len(authorization) != 2 or authorization[0].lower() != "bearer":
            return await self.admin._deny(send, 401, "unauthenticated", "Authentication required.")
        try:
            claims = await asyncio.to_thread(self.task_verifier.verify, authorization[1])
        except InvalidToken:
            return await self.admin._deny(send, 401, "unauthenticated", "Authentication required.")
        except UpstreamUnavailable:
            return await self.admin._deny(
                send, 503, "upstream_unavailable", "Service temporarily unavailable."
            )
        if (
            claims.get("iss") not in GOOGLE_ISSUERS
            or claims.get("aud") != self.config.task_audience
            or claims.get("email") != self.config.tasks_sa
            or claims.get("email_verified") is not True
        ):
            return await self.admin._deny(send, 403, "forbidden", "Not allowed.")
        return await self.app(scope, receive, send)
