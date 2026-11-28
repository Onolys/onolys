"""`GET /v1/upload-limits`: the limits the validator enforces, for web pre-checks."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from onolys_api import logs
from onolys_api.audio import (
    ACCEPTED_EXTENSIONS,
    ACCEPTED_MIME_TYPES,
    DEFAULT_MAX_DURATION_S,
    SHORT_RECORDING_S,
)
from onolys_api.auth.deps import AuthUser, current_user
from onolys_api.errors import ErrorResponse
from onolys_api.storage.base import MAX_UPLOAD_BYTES

ERRORS = {"default": {"model": ErrorResponse, "description": "Error"}}
router = APIRouter(prefix="/upload-limits", tags=["upload"], responses=ERRORS)
User = Annotated[AuthUser, Depends(current_user)]


class UploadLimits(BaseModel):
    max_bytes: int
    max_duration_s: float
    interview_max_duration_s: float
    short_warning_s: float
    extensions: list[str]
    mime_types: list[str]


@router.get(
    "", operation_id="getUploadLimits", response_model=UploadLimits, summary="Upload limits"
)
def get_upload_limits(request: Request, user: User) -> UploadLimits:
    settings = request.app.state.settings
    presets = request.app.state.presets
    try:
        stt = presets.resolve(None, "en")[1]  # the default STT preset
        max_duration_s = presets.max_audio_s(stt.provider, stt.model)
    except Exception as e:  # noqa: BLE001 - a bad preset config must not break the page's pre-check
        logs.emit("upload_limits_preset_failed", logging.ERROR, exc_class=type(e).__name__)
        max_duration_s = DEFAULT_MAX_DURATION_S
    return UploadLimits(
        max_bytes=MAX_UPLOAD_BYTES,
        max_duration_s=max_duration_s,
        interview_max_duration_s=settings.ai_max_seconds + settings.ai_tolerance_seconds,
        short_warning_s=SHORT_RECORDING_S,
        extensions=list(ACCEPTED_EXTENSIONS),
        mime_types=list(ACCEPTED_MIME_TYPES),
    )
