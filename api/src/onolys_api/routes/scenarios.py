"""`GET /v1/scenarios`: public fields of the curated AI-interview scenarios (R1)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from onolys_api.auth.deps import AuthUser, current_user
from onolys_api.errors import ErrorResponse
from onolys_api.voice.scenarios import public_view

ERRORS = {"default": {"model": ErrorResponse, "description": "Error"}}
router = APIRouter(prefix="/scenarios", tags=["interviews"], responses=ERRORS)
User = Annotated[AuthUser, Depends(current_user)]


class ScenarioPublic(BaseModel):
    id: str
    title: str
    difficulty: str
    summary: str
    language: str


class ScenarioList(BaseModel):
    scenarios: list[ScenarioPublic]


@router.get(
    "", operation_id="listScenarios", response_model=ScenarioList,
    summary="Practice-client scenarios (public fields only)",
)  # fmt: skip
def list_scenarios(request: Request, user: User) -> ScenarioList:
    return ScenarioList(
        scenarios=[ScenarioPublic(**public_view(s)) for s in request.app.state.scenarios.values()]
    )
