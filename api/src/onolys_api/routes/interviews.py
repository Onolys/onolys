"""`/v1/interviews`: create (reserves one SP11 unit), get, end/discard (SP10 R5, D11-D14, D16)."""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from onolys_api.auth.deps import AuthUser, current_user
from onolys_api.errors import ApiError, ErrorResponse
from onolys_api.jobs.caps import release, reserve
from onolys_api.jobs.interview_sweep import enqueue_sweep
from onolys_api.jobs.interviews import abandon_open_interviews, settle_interview
from onolys_api.repo.models import InterviewDoc, InterviewState
from onolys_api.routes.ids import ResourceId
from onolys_api.routes.scenarios import ScenarioPublic
from onolys_api.voice.scenarios import public_view

ERRORS = {"default": {"model": ErrorResponse, "description": "Error"}}
router = APIRouter(prefix="/interviews", tags=["interviews"], responses=ERRORS)
User = Annotated[AuthUser, Depends(current_user)]


class CreateInterviewRequest(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=100)
    voice: str | None = Field(
        None, max_length=64, description="One of the configured voices; default: the scenario's"
    )


class EndInterviewRequest(BaseModel):
    discard: bool = Field(False, description="Throw the interview away (state `abandoned`)")


class InterviewLimits(BaseModel):
    max_s: int
    warn_s: int


class InterviewResponse(BaseModel):
    interview_id: str
    state: InterviewState
    voice_url: str = Field(description="`wss://` relay endpoint for this interview")
    scenario: ScenarioPublic
    voice: str
    duration_s: float | None = Field(None, description="Elapsed seconds, as recorded by the relay")
    limits: InterviewLimits


def _view(request: Request, doc: InterviewDoc) -> InterviewResponse:
    settings = request.app.state.settings
    sc = request.app.state.scenarios.get(doc.scenario_id)
    if sc is None:  # scenario removed since the interview was created
        raise ApiError.of(404, "not_found", "Resource not found.")
    return InterviewResponse(
        interview_id=doc.id,
        state=doc.state,
        voice_url=f"{settings.voice_url}/v1/voice/{doc.id}",
        scenario=ScenarioPublic(**public_view(sc)),
        voice=doc.voice,
        duration_s=doc.duration_s,
        limits=InterviewLimits(max_s=settings.ai_max_seconds, warn_s=settings.ai_warn_seconds),
    )


@router.post(
    "", operation_id="createInterview", status_code=201, response_model=InterviewResponse,
    summary="Start a practice interview (counts one usage unit)",
    description=(
        "Reserves one interview unit first (429 `interview_cap_reached` with `period` when "
        "spent); the unit is given back if the interview ends or is abandoned under 30 seconds. "
        "An earlier unfinished interview is abandoned first."
    ),
)  # fmt: skip
def create_interview(
    request: Request, body: CreateInterviewRequest, user: User
) -> InterviewResponse:
    state = request.app.state
    repo, settings, uid = state.repo, state.settings, user.uid
    scenario = state.scenarios.get(body.scenario_id)
    if scenario is None:
        raise ApiError.of(422, "invalid_parameters", "scenario_id: unknown scenario")
    voice = body.voice or scenario["voice"]
    if voice not in state.voices:
        raise ApiError.of(422, "invalid_parameters", "voice: unknown voice")

    now = state.clock()
    abandon_open_interviews(repo, settings, uid, now)
    reservation = reserve(repo, settings, uid, "interview", now)  # 429 passes through
    iid = uuid4().hex
    try:
        # before the doc: a failed enqueue refunds and fails the create (no unswept interview)
        enqueue_sweep(getattr(state, "queue", None), settings, uid, iid)
        repo.create_interview(
            uid, iid,
            InterviewDoc(
                uid=uid, scenario_id=body.scenario_id, voice=voice, created_at=now,
                reservation_date=reservation.date,
            ),
        )  # fmt: skip
    except Exception:
        release(repo, uid, reservation, refund=True)
        raise
    return _view(request, repo.get_interview(uid, iid))


@router.get(
    "/{id}", operation_id="getInterview", response_model=InterviewResponse,
    summary="An interview's state and elapsed time",
)  # fmt: skip
def get_interview(request: Request, id: ResourceId, user: User) -> InterviewResponse:
    return _view(request, request.app.state.repo.get_interview(user.uid, id))


@router.post(
    "/{id}/end", operation_id="endInterview", response_model=InterviewResponse,
    summary="End (or discard) an interview; idempotent",
    description=(
        "`created|live` becomes `ended` (`abandoned` when `discard`). Ending an interview that is "
        "already ended, abandoned or uploaded changes nothing and returns it as it is."
    ),
)  # fmt: skip
def end_interview(
    request: Request, id: ResourceId, user: User, body: EndInterviewRequest | None = None
) -> InterviewResponse:
    state = request.app.state
    state.repo.get_interview(user.uid, id)  # 404 for a foreign or missing id
    to_state = "abandoned" if body is not None and body.discard else "ended"
    doc = settle_interview(state.repo, state.settings, user.uid, id, to_state, state.clock())
    return _view(request, doc)
