"""`/v1/auth/email/*`: verification and password-reset emails sent through our own sender.

PHI/PII-safe logs (R10): `email_kind`, `outcome`, `provider_status` only; verify adds `uid_hash`,
reset logs no identifier. Never the address, the link or the action code.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field

from onolys_api import logs
from onolys_api.adapters.base import AdapterError
from onolys_api.auth.deps import AuthUser, current_user_unverified_ok
from onolys_api.email.rate import first_forwarded_ip
from onolys_api.errors import ApiError, ErrorResponse

ERRORS = {"default": {"model": ErrorResponse, "description": "Error"}}
router = APIRouter(prefix="/auth/email", tags=["auth-email"], responses=ERRORS)

UnverifiedOkUser = Annotated[AuthUser, Depends(current_user_unverified_ok)]


class VerificationRequest(BaseModel):
    next: str | None = Field(
        None, max_length=512, description="Optional in-app path to continue to after verifying."
    )


class ResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class Empty(BaseModel):
    pass


def _failure_fields(exc: Exception) -> dict:
    code = getattr(exc, "code", None)
    return {
        "outcome": "unconfigured" if code == "email_unconfigured" else "send_failed",
        "provider_status": getattr(exc, "provider_status", None),
    }


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
    if not limiter.check_verify(user.uid):
        logs.emit("auth_email", logging.WARNING, email_kind="verify", outcome="rate_limited",
                  uid_hash=uid_hash)  # fmt: skip
        raise ApiError.of(429, "rate_limited", "Too many requests.")
    try:
        sent = service.send_verification(user.uid, body.next)
    except Exception as exc:
        logs.emit("auth_email", logging.ERROR, email_kind="verify", uid_hash=uid_hash,
                  exc_class=type(exc).__name__,
                  **(_failure_fields(exc) if isinstance(exc, AdapterError)
                     else {"outcome": "send_failed"}))  # fmt: skip
        raise ApiError.of(503, "email_unavailable", "Email is temporarily unavailable.") from None
    logs.emit("auth_email", email_kind="verify", uid_hash=uid_hash,
              outcome="sent" if sent else "already_verified")  # fmt: skip
    return Empty()


def _send_reset(service, email: str) -> None:
    """Background: runs after the 202, so a failure is only logged."""
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
    ip = first_forwarded_ip(request.headers.get("x-forwarded-for"))
    if not limiter.check_reset(body.email, ip):
        logs.emit("auth_email", logging.WARNING, email_kind="reset", outcome="rate_limited")
        return Empty()
    background.add_task(_send_reset, service, body.email)
    return Empty()
