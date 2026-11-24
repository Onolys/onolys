"""Direct, owner-scoped transcript upload; only normalized v1 is persisted."""

import json
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from onolys_engine_core.transcript_input import (
    TranscriptInputError,
    inferred_clinician_speaker,
    validate_transcript_input,
)
from onolys_engine_core.transcript_txt import parse_transcript_txt

from onolys_api.auth.deps import AuthUser, current_user
from onolys_api.coded_span import validate_coded_input
from onolys_api.errors import ApiError, ErrorResponse
from onolys_api.jobs.first_run import maybe_start_first_run
from onolys_api.jobs.machine import invalid_state, transition_plan
from onolys_api.jobs.transcribe import TRANSCRIPT_ID
from onolys_api.repo import large
from onolys_api.repo.base import NotFoundError
from onolys_api.repo.models import TranscriptDoc
from onolys_api.routes.ids import ResourceId
from onolys_api.routes.sessions import CreateSessionResponse, SessionRef

MAX_TRANSCRIPT_BYTES = 1024 * 1024
router = APIRouter(
    prefix="/sessions/{id}",
    tags=["transcript"],
    responses={"default": {"model": ErrorResponse, "description": "Error"}},
)
User = Annotated[AuthUser, Depends(current_user)]


def _session_language(session_language: str, transcript_language: str | None) -> str:
    """A language the user chose stays; only `auto` takes the transcript's, else `en` (LM-4)."""
    if session_language not in ("", "auto"):
        return session_language
    return transcript_language or "en"


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
    if session.interview_id:
        # an interview session's transcript is its recording's: a typed one would be a free,
        # uncounted evaluation of arbitrary text (LM-5)
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

    validate_coded_input(transcript, session.coded_span)

    # ONE transaction (N1): the `created` check, the transcript doc and the move to
    # `awaiting_input` commit together, so two concurrent PUTs cannot both write.
    blobs = request.app.state.blobs
    pointer = large.pack(
        blobs, f"{user.uid}/{id}/transcripts/{uuid4().hex}.json",
        transcript.model_dump(mode="json"),
    )  # a unique key: the losing PUT must not overwrite the winner's blob
    tdoc = TranscriptDoc(transcript=None if pointer else transcript, pointer=pointer)
    try:
        repo.transition_session(
            user.uid, id,
            transition_plan(
                to="awaiting_input", step=None, only_from=("created",),
                flags={"transcript_ready": True, "speaker_confirmed": clinician is not None},
                extra_fields={
                    "clinician_speaker": clinician, "stt": None,
                    "language": _session_language(session.language, transcript.language),
                },
            ),
            children=((f"transcripts/{TRANSCRIPT_ID}", tdoc.to_store(), False),),
        )  # fmt: skip
    except Exception:
        if pointer is not None:
            blobs.delete(pointer.key)
        raise
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
