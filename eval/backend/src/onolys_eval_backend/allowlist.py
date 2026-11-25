"""Eval user gate: prod Identity Platform ID token + `EVAL_ALLOWED_EMAILS`, as ASGI middleware.

Never logs the token or the email.
"""

import asyncio
import json
import logging
from typing import Any, Protocol

from onolys_api.auth.idtoken import EmailNotVerified, InvalidToken
from onolys_api.errors import ApiError

log = logging.getLogger("onolys_eval_backend.allowlist")


class ClaimsVerifier(Protocol):
    def verify_claims(self, token: str) -> dict[str, Any]: ...


async def deny(send, status: int, code: str, message: str) -> None:
    body = json.dumps({"error": {"code": code, "message": message}}).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
    ]
    if status == 401:
        headers.append((b"www-authenticate", b"Bearer"))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


def bearer_token(scope) -> str | None:
    for k, v in scope["headers"]:
        if k == b"authorization":
            parts = v.decode("latin-1").split(None, 1)
            if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
                return parts[1].strip()
            return None
    return None


class AllowlistMiddleware:
    def __init__(self, app, verifier: ClaimsVerifier, allowed_emails: frozenset[str]) -> None:
        if not allowed_emails:
            raise ValueError("allowlist is empty: refusing to start")
        self.app = app
        self.verifier = verifier
        self.allowed = frozenset(e.strip().lower() for e in allowed_emails)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        # Preflight is answered by the CORS layer; it carries no credentials.
        if scope["method"] == "OPTIONS":
            return await self.app(scope, receive, send)
        token = bearer_token(scope)
        if token is None:
            return await deny(send, 401, "unauthenticated", "Authentication required.")
        try:
            claims = await asyncio.to_thread(self.verifier.verify_claims, token)
        except EmailNotVerified:
            log.info("eval auth denied: email not verified")
            return await deny(send, 403, "email_unverified", "Not allowed.")
        except InvalidToken:
            log.info("eval auth denied: invalid token")
            return await deny(send, 401, "unauthenticated", "Authentication required.")
        except ApiError:
            log.warning("eval auth: signing keys unavailable")
            return await deny(send, 503, "upstream_unavailable", "Service temporarily unavailable.")
        email = claims.get("email")
        if claims.get("email_verified") is not True or not isinstance(email, str) or not email:
            log.info("eval auth denied: email not verified")
            return await deny(send, 403, "email_unverified", "Not allowed.")
        email = email.strip().lower()
        if email not in self.allowed:
            log.info("eval auth denied: not on allowlist")
            return await deny(send, 403, "not_allowlisted", "Not allowed.")
        scope.setdefault("state", {})["user_email"] = email
        await self.app(scope, receive, send)
