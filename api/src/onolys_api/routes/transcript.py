"""Direct, owner-scoped transcript upload; only normalized v1 is persisted."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from onolys_miti.transcript_input import (
    TranscriptInputError,
    inferred_clinician_speaker,
    validate_transcript_input,
)
from onolys_miti.transcript_txt import parse_transcript_txt

from onolys_api.auth.deps import AuthUser, current_user
from onolys_api.errors import ApiError, ErrorResponse
from onolys_api.jobs.first_run import maybe_start_first_run
from onolys_api.jobs.machine import advance, invalid_state
from onolys_api.jobs.transcribe import TRANSCRIPT_ID
from onolys_api.repo.base import NotFoundError
from onolys_api.routes.ids import ResourceId
from onolys_api.routes.sessions import CreateSessionResponse, SessionRef

MAX_TRANSCRIPT_BYTES = 1024 * 1024
router = APIRouter(
    prefix="/sessions/{id}",
    tags=["transcript"],
    responses={"default": {"model": ErrorResponse, "description": "Error"}},
)
User = Annotated[AuthUser, Depends(current_user)]


def _public_error(error: TranscriptInputError) -> ApiError:
    return ApiError(
        413 if error.code == "transcript_too_large" else 422,
        error.message,
        [
            {
                "code": error.code,
                "message": error.message,
                "field": error.field,
                "issue": error.issue,
            }
        ],
    )


@router.put(
    "/transcript",
    operation_id="uploadTranscript",
    status_code=202,
    response_model=CreateSessionResponse,
    summary="Upload a transcript.v1 JSON or label-prefixed UTF-8 text file",
    description="Created sessions only. Maximum 1 MiB. May start the first run.",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": {"type": "object"}},
                "text/plain": {"schema": {"type": "string"}},
            },
        }
    },
)
async def upload_transcript(
    id: ResourceId,
    request: Request,
    user: User,
) -> CreateSessionResponse:
    repo = request.app.state.repo
    session = repo.get_session(user.uid, id)
    if session.state == "deleting":
        raise NotFoundError()
    if session.state != "created":
        raise invalid_state()
    media = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media not in ("application/json", "text/plain"):
        raise ApiError.of(415, "unsupported_media_type", "Use application/json or text/plain.")

    # This route owns its body limit so an oversized stream can never be parsed and stored
    # as a valid prefix by the generic middleware. Check before appending each chunk.
    raw = bytearray()
    try:
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > MAX_TRANSCRIPT_BYTES:
            raise TranscriptInputError(
                "transcript_too_large",
                "The transcript may contain at most 1 MiB.",
                "$",
                "too_large",
            )
        async for chunk in request.stream():
            if len(raw) + len(chunk) > MAX_TRANSCRIPT_BYTES:
                raise TranscriptInputError(
                    "transcript_too_large",
                    "The transcript may contain at most 1 MiB.",
                    "$",
                    "too_large",
                )
            raw.extend(chunk)
        if not raw.strip():
            raise TranscriptInputError(
                "empty_transcript",
                "The transcript must contain at least 50 words.",
                "turns",
                "required",
            )
        if media == "text/plain":
            transcript = parse_transcript_txt(bytes(raw))
        else:
            try:
                value = json.loads(raw)
            except (ValueError, UnicodeDecodeError, RecursionError):
                raise TranscriptInputError(
                    "transcript_invalid", "The transcript must be valid JSON.", "$", "invalid"
                ) from None
            transcript = validate_transcript_input(value)
        clinician = inferred_clinician_speaker(transcript)
    except TranscriptInputError as error:
        raise _public_error(error) from None

    # Recheck after awaiting the body, before any write or usage reservation.
    if repo.get_session(user.uid, id).state != "created":
        raise invalid_state()
    repo.put_transcript(user.uid, id, TRANSCRIPT_ID, transcript)
    repo.update_session(
        user.uid,
        id,
        {"clinician_speaker": clinician, "stt": None, "language": transcript.language or "en"},
    )
    advance(
        repo,
        user.uid,
        id,
        to="awaiting_input",
        step=None,
        flags={"transcript_ready": True, "speaker_confirmed": clinician is not None},
    )
    maybe_start_first_run(
        repo,
        getattr(request.app.state, "queue", None),
        user.uid,
        id,
        request.app.state.settings,
        getattr(request.state, "request_id", None),
    )
    return CreateSessionResponse(
        session=SessionRef(id=id, status=repo.get_session(user.uid, id).state)
    )
