"""Public error bodies. Messages are fixed text only, never instance values."""

from typing import Literal, NotRequired, TypedDict

from pydantic import BaseModel, Field

SCHEMA_VERSION = "0.0.1"

# Mirrors the enum of docs/contracts/public/public-error-response.schema.json.
ERROR_CODES = (
    "invalid_json",
    "unsupported_media_type",
    "schema_violation",
    "empty_transcript",
    "empty_assessment",
    "duplicate_ids",
    "invalid_parameters",
    "body_too_large",
    "too_many_turns",
    "too_many_sections",
    "rate_limited",
    "not_found",
    "method_not_allowed",
    "cors_rejected",
    "request_rejected",
    "upstream_unavailable",
    "deadline_exceeded",
    "internal_error",
    # added to the shared contract for the admin pack routes
    "missing_parameter",
    "unknown_pack",
    "input_rejected",
    "run_failed",
    # new in the public API
    "unauthenticated",
    "forbidden",
    "invalid_state",
    "rating_final",
    "unsupported_audio",
    "audio_too_long",
    "audio_too_large",
    "audio_unreadable",
    "no_speech",
    "speakers_not_separated",
    "transcription_failed",
    "rating_invalid",
    "daily_cap_reached",
    "interview_cap_reached",
    "concurrent_runs",
    "email_unverified",
    "conflict",
    "interview_too_long",
)
ErrorCode = Literal[ERROR_CODES]  # type: ignore[valid-type]


class ErrorDetail(TypedDict):
    code: str
    message: str
    field: NotRequired[str]
    issue: NotRequired[str]
    period: NotRequired[Literal["day"]]


class ErrorDetailModel(BaseModel):
    code: ErrorCode
    message: str
    field: str | None = Field(
        None,
        description=(
            "`/`-joined path of the offending field in the rating card (e.g. "
            "`globals/cct/reason`); `$` is the whole card. Set on `rating_invalid`. A path only, "
            "never user text."
        ),
    )
    issue: (
        Literal[
            "invalid_type",
            "too_long",
            "out_of_range",
            "required",
            "unknown_key",
            "invalid",
            "order",
            "too_large",
        ]
        | None
    ) = Field(None, description="What is wrong at `field`. Set on `rating_invalid`.")
    period: Literal["day"] | None = Field(
        None,
        description=(
            "Which usage period was exhausted. Set on `daily_cap_reached` and "
            "`interview_cap_reached`."
        ),
    )


class ErrorResponse(BaseModel):
    """Body of every non-2xx response (docs/contracts/public/public-error-response.schema.json)."""

    schema_version: Literal["0.0.1"] = SCHEMA_VERSION  # type: ignore[assignment]
    request_id: str | None = None
    status: int
    message: str
    details: list[ErrorDetailModel]


class ApiError(Exception):
    def __init__(
        self, status: int, message: str, details: list[ErrorDetail], request_id: str | None = None
    ):
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details
        self.request_id = request_id

    @classmethod
    def of(
        cls, status: int, code: str, message: str, period: Literal["day"] | None = None
    ) -> "ApiError":
        detail: ErrorDetail = {"code": code, "message": message}
        if period is not None:
            detail["period"] = period
        return cls(status, message, [detail])


def error_responses(*statuses: int) -> dict[int | str, dict]:
    """OpenAPI `responses=` entries that point each status at the shared `ErrorResponse` model."""
    return {s: {"model": ErrorResponse, "description": _STATUS_TEXT[s]} for s in statuses}


_STATUS_TEXT = {
    401: "`unauthenticated`: missing, invalid or revoked credentials",
    403: (
        "`forbidden` (API keys cannot manage API keys) or `email_unverified` (valid sign-in, "
        "email address not verified yet)"
    ),
    404: "`not_found`: no such resource for this user (never 403, so ids cannot be probed)",
    409: (
        "`invalid_state` or `conflict`: not allowed in the session's current state; "
        "`rating_final`: the report is ready, so the rating can no longer be changed or re-run"
    ),
    422: (
        "`invalid_parameters` (incl. a malformed id, cursor or body), `unsupported_audio`, "
        "`audio_too_large` or `rating_invalid`"
    ),
    429: (
        "`daily_cap_reached` (daily run cap), `concurrent_runs` (a run is already in progress) "
        "or `rate_limited`"
    ),
    500: "`internal_error`",
    503: "`upstream_unavailable`: retry shortly",
}


def error_body(
    status: int, message: str, details: list[ErrorDetail], request_id: str | None = None
) -> dict:
    body: dict = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "message": message,
        "details": details,
    }
    if request_id:
        body["request_id"] = request_id
    return body
