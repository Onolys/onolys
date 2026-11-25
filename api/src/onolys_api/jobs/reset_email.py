"""`reset-email` task (M-5): the password-reset email is enqueued BEFORE the route answers 202, so
a process or revision ending right after the response cannot lose it (the API service runs with
request-based CPU). A worker sends it; one retry on a transient failure (the queue's max attempts).

Privacy: the route's answer stays the generic `202 {}`. The address travels only in the task body;
the task name uses a keyed hash and the window index, so a repeat request inside the window is
deduplicated by the queue. No log line carries the address, the link or the action code (R10).
"""

import hashlib
import hmac
import logging
from collections.abc import Callable
from datetime import datetime

from onolys_api import logs
from onolys_api.adapters.base import AdapterError
from onolys_api.config import Settings
from onolys_api.jobs.queue import MAX_ATTEMPTS, TaskPayload, task_name
from onolys_api.jobs.worker import Handler, RetryableError, TaskContext

WINDOW_S = 600  # a repeat inside it is one task; the limiter bounds requests anyway
_NO_RETRY = ("email_unconfigured",)


def reset_payload(
    settings: Settings, email: str, request_id: str | None, now: datetime
) -> TaskPayload:
    norm = email.strip().lower()
    key = hmac.new(settings.uid_hmac_key.encode(), norm.encode(), hashlib.sha256).hexdigest()[:24]
    return TaskPayload(
        kind="reset-email", uid="-", sid="reset-email", email=email, key=key,
        n=int(now.timestamp() // WINDOW_S), request_id=request_id,
    )  # fmt: skip


def _failure_fields(exc: Exception) -> dict:
    code = getattr(exc, "code", None)
    return {
        "outcome": "unconfigured" if code == "email_unconfigured" else "send_failed",
        "provider_status": getattr(exc, "provider_status", None),
    }


def make_reset_email_handler(get_service: Callable[[], tuple]) -> Handler:
    """`get_service()` -> `(AuthEmailService, limiter)`, resolved per delivery (built lazily)."""

    def handle(ctx: TaskContext) -> None:
        email = ctx.payload.email
        if not email:
            return
        try:
            service = get_service()[0]
            sent = service.send_password_reset(email, idempotency_key=task_name(ctx.payload))
        except Exception as exc:  # noqa: BLE001
            fields = (
                _failure_fields(exc)
                if isinstance(exc, AdapterError)
                else {"outcome": "send_failed"}
            )
            final = ctx.attempt >= MAX_ATTEMPTS or getattr(exc, "code", None) in _NO_RETRY
            logs.emit(
                "auth_email", logging.ERROR if final else logging.WARNING, email_kind="reset",
                exc_class=type(exc).__name__, **fields,
            )  # fmt: skip
            if final:
                return  # nothing more to try; the 2xx stops the queue
            raise RetryableError("upstream_unavailable") from None
        logs.emit("auth_email", email_kind="reset", outcome="sent" if sent else "unknown_account")

    return handle
