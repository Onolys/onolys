"""`/v1/auth/email/*`: verification and password-reset emails sent through our own sender.

PHI/PII-safe logs (R10): `email_kind`, `outcome`, `provider_status` only; verify adds `uid_hash`,
reset logs no identifier. Never the address, the link or the action code.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from onolys_api import logs
from onolys_api.adapters.base import AdapterError
from onolys_api.auth.deps import AuthUser, current_user_unverified_ok
from onolys_api.email.rate import client_ip
from onolys_api.errors import ApiError, ErrorResponse
from onolys_api.jobs.reset_email import reset_payload

ERRORS = {"default": {"model": ErrorResponse, "description": "Error"}}
router = APIRouter(prefix="/auth/email", tags=["auth-email"], responses=ERRORS)

UnverifiedOkUser = Annotated[AuthUser, Depends(current_user_unverified_ok)]


class VerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    next: str | None = Field(
        None, max_length=512, description="Optional in-app path to continue to after verifying."
    )


class ResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)


class Empty(BaseModel):
    pass


def _failure_fields(exc: Exception) -> dict:
    code = getattr(exc, "code", None)
    return {
        "outcome": "unconfigured" if code == "email_unconfigured" else "send_failed",
        "provider_status": getattr(exc, "provider_status", None),
    }


def _verify_failed(exc: Exception, uid_hash: str):
    logs.emit("auth_email", logging.ERROR, email_kind="verify", uid_hash=uid_hash,
              exc_class=type(exc).__name__,
              **(_failure_fields(exc) if isinstance(exc, AdapterError)
                 else {"outcome": "send_failed"}))  # fmt: skip
    raise ApiError.of(503, "email_unavailable", "Email is temporarily unavailable.") from None


@router.post(
    "/verification",
    operation_id="sendVerificationEmail",
    status_code=202,
    response_model=Empty,
    summary="Email the signed-in user a verification link (unverified tokens allowed)",
    description=(
        "Sends to the account's own address, never one from the request. An already verified "
        "account gets `202` and no email. `429 rate_limited` after 1 per minute / 5 per hour; "
        "`503 email_unavailable` when the email could not be sent."
    ),
)
def send_verification(request: Request, body: VerificationRequest, user: UnverifiedOkUser) -> Empty:
    service, limiter = request.app.state.auth_email()
    uid_hash = logs.uid_hash(user.uid)
    try:
        service.require_configured()
        account = service.get_account(user.uid)
        if account.email_verified:  # no send, no rate consumption (AC4)
            logs.emit("auth_email", email_kind="verify", uid_hash=uid_hash,
                      outcome="already_verified")  # fmt: skip
            return Empty()
    except Exception as exc:
        _verify_failed(exc, uid_hash)
    if not limiter.check_verify(user.uid):
        logs.emit("auth_email", logging.WARNING, email_kind="verify", outcome="rate_limited",
                  uid_hash=uid_hash)  # fmt: skip
        raise ApiError.of(429, "rate_limited", "Too many requests.")
    try:
        sent = service.send_verification(user.uid, body.next, account=account)
    except Exception as exc:
        _verify_failed(exc, uid_hash)
    logs.emit("auth_email", email_kind="verify", uid_hash=uid_hash,
              outcome="sent" if sent else "already_verified")  # fmt: skip
    return Empty()


def _send_reset(service, email: str) -> None:
    """In-process fallback (no queue, or enqueue failed): runs after the 202, only logged."""
    try:
        sent = service.send_password_reset(email)
    except Exception as exc:
        logs.emit("auth_email", logging.ERROR, email_kind="reset", exc_class=type(exc).__name__,
                  **(_failure_fields(exc) if isinstance(exc, AdapterError)
                     else {"outcome": "send_failed"}))  # fmt: skip
        return
    logs.emit("auth_email", email_kind="reset", outcome="sent" if sent else "unknown_account")


@router.post(
    "/password-reset",
    operation_id="sendPasswordResetEmail",
    status_code=202,
    response_model=Empty,
    summary="Email a password-reset link if the account exists (no auth)",
    description=(
        "Always `202 {}`: known, unknown, disabled, rate-limited and failed sends are "
        "indistinguishable, so account existence cannot be probed."
    ),
)
def send_password_reset(request: Request, body: ResetRequest, background: BackgroundTasks) -> Empty:
    service, limiter = request.app.state.auth_email()
    ip = client_ip(
        request.headers.get("x-forwarded-for"), request.app.state.settings.client_ip_trusted_hops
    )
    if not limiter.check_reset(body.email, ip):
        logs.emit("auth_email", logging.WARNING, email_kind="reset", outcome="rate_limited")
        return Empty()
    queue = getattr(request.app.state, "queue", None)
    if queue is not None:  # durable: enqueued before the 202, sent by the worker with a retry (M-5)
        try:
            state = request.app.state
            queue.enqueue(
                reset_payload(
                    state.settings, body.email, getattr(request.state, "request_id", None),
                    state.clock(),
                )
            )
            return Empty()
        except Exception as exc:  # noqa: BLE001 - never leak "known account" through a 5xx
            logs.emit("auth_email", logging.ERROR, email_kind="reset", outcome="enqueue_failed",
                      exc_class=type(exc).__name__)  # fmt: skip
    background.add_task(_send_reset, service, body.email)  # no queue (local) or queue down
    return Empty()
