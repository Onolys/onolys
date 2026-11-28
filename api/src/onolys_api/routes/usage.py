"""`GET /v1/usage`: eval + interview used/cap/resets_at for the UTC day."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from onolys_api.auth.deps import AuthUser, current_user
from onolys_api.errors import ErrorResponse
from onolys_api.jobs import caps

ERRORS = {"default": {"model": ErrorResponse, "description": "Error"}}
router = APIRouter(prefix="/usage", tags=["usage"], responses=ERRORS)
User = Annotated[AuthUser, Depends(current_user)]


class Period(BaseModel):
    used: int
    cap: int
    resets_at: datetime


class KindUsage(BaseModel):
    day: Period


class Usage(BaseModel):
    eval: KindUsage
    interview: KindUsage


def _kind(k: caps.KindUsage) -> KindUsage:
    return KindUsage(
        day=Period(used=k.day.used, cap=k.day.cap, resets_at=k.day.resets_at),
    )


@router.get("", operation_id="getUsage", response_model=Usage, summary="Usage and caps (UTC day)")
def get_usage(request: Request, user: User) -> Usage:
    view = caps.usage_view(request.app.state.repo, request.app.state.settings, user.uid)
    return Usage(eval=_kind(view.eval), interview=_kind(view.interview))
