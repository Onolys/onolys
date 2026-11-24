"""Runs and reports (PRD R2, R4, D12, D18).

`POST /sessions/{id}/runs` starts a run by hand: "Try again" after a system failure (same
transcript, stored final rating, current speaker choice) or the first run when auto-start was
held back by the cap. A rating is final once its report is ready (FX45): 409 `rating_final`.
It reserves a cap slot (429 `daily_cap_reached`), creates the run, moves the
session to `running` (clears the cap error) and enqueues the `run` task; the worker does the rest.
`preset` changes LLM routes only: the transcript and its STT are reused.
"""

from datetime import datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response
from onolys_miti.result import CodedSpan
from pydantic import BaseModel, Field

from onolys_api import logs
from onolys_api.adapters.error_map import kind_for_code
from onolys_api.auth.deps import AuthUser, current_user
from onolys_api.coded_span import validate_coded_input
from onolys_api.errors import ApiError, ErrorResponse
from onolys_api.jobs import caps
from onolys_api.jobs.machine import (
    RUN_START_PROGRESS,
    advance,
    has_final_report,
    invalid_state,
    rating_final,
)
from onolys_api.jobs.queue import TaskPayload
from onolys_api.jobs.run import release_once
from onolys_api.presets import UnknownPreset
from onolys_api.repo.base import NotFoundError
from onolys_api.repo.limits import LimitDefaults
from onolys_api.repo.models import (
    OutputValidation,
    RunDoc,
    SessionDoc,
    SessionError,
    SessionState,
    SttInfo,
)
from onolys_api.routes.ids import ResourceId

ERRORS = {"default": {"model": ErrorResponse, "description": "Error"}}
router = APIRouter(prefix="/sessions/{id}", tags=["runs"], responses=ERRORS)
runs_router = APIRouter(tags=["runs"], responses=ERRORS)
User = Annotated[AuthUser, Depends(current_user)]
# FX45: no `report_ready` (the rating is final once its report is ready); a `failed` session may
# only be retried after a system failure, never after a bad-file code.
RERUN_STATES = ("awaiting_input", "failed")


class RunRequest(BaseModel):
    coded_span: CodedSpan | None = Field(
        None, description="Half-open milliseconds or zero-based turn range; null codes all turns."
    )
    n_runs: int | None = Field(None, ge=1, le=5, description="Default: the session's")
    preset: str | None = Field(None, max_length=64, description="Allowlisted; LLM routes only")


class RunSessionRef(BaseModel):
    id: str
    status: SessionState


class RunStarted(BaseModel):
    run_id: str
    session: RunSessionRef


class RunView(BaseModel):
    run_id: str
    session_id: str
    status: str
    stage: str | None = None
    n_runs: int
    preset: str | None = None
    stt: SttInfo | None = None
    rating_id: str | None = None
    code_version: str
    attempts: int
    started: datetime | None = None
    ended: datetime | None = None
    error: str | None = None
    run_info: dict[str, Any] | None = None
    validation: OutputValidation | None = None


class RunList(BaseModel):
    items: list[RunView]


class ReportListItem(BaseModel):
    version: int
    report_id: str
    run_id: str
    created_at: datetime


class ReportList(BaseModel):
    items: list[ReportListItem]


class ReportView(ReportListItem):
    report_schema_version: str
    report: dict[str, Any] = Field(description="The typed report JSON, stored verbatim")


def _view(r: RunDoc) -> RunView:
    return RunView(
        run_id=r.run_id, session_id=r.session_id, status=r.status, stage=r.stage,
        n_runs=r.n_runs, preset=r.preset, stt=r.stt, rating_id=r.rating_id,
        code_version=r.code_version, attempts=r.attempts, started=r.started, ended=r.ended,
        error=r.error, run_info=r.run_info, validation=r.validation,
    )  # fmt: skip


def _open_session(request: Request, user: AuthUser, id: str) -> SessionDoc:
    s = request.app.state.repo.get_session(user.uid, id)
    if s.state == "deleting":
        raise NotFoundError()
    return s


@router.post(
    "/runs",
    operation_id="startRun",
    status_code=202,
    response_model=RunStarted,
    summary="Start a run by hand (Try again after a system failure, or the first run held back)",
    description=(
        "Needs the transcript and the confirmed speaker; uses the stored final rating revision "
        "or runs as no-rating. `preset` changes LLM routes only (the transcript is reused). "
        "On Try again (a failed session) `preset` and `n_runs` are ignored: the failed run's "
        "values are reused. "
        "Counts against the daily cap: 429 `daily_cap_reached`; 429 `concurrent_runs` while "
        "another run is in progress. 409 `rating_final` once a report exists (the rating is "
        "final: no re-run, interview sessions included). 409 `invalid_state` while a run "
        "is in progress, before the inputs exist, or after a bad-file failure (upload a "
        "different file instead)."
    ),
)
def start_run(
    id: ResourceId, request: Request, user: User, body: RunRequest | None = None
) -> RunStarted:
    body = body or RunRequest()
    app = request.app
    repo, uid = app.state.repo, user.uid
    s = _open_session(request, user, id)
    if has_final_report(repo, uid, id, s.state):
        raise rating_final()
    if s.state == "failed" and s.error is not None and s.error.kind == "user_file":
        raise invalid_state()
    if s.state not in RERUN_STATES or not (
        s.transcript_ready and s.speaker_confirmed and s.clinician_speaker
    ):
        raise invalid_state()
    preset, n_runs = s.preset, body.n_runs
    span = s.coded_span
    if s.state == "failed":
        # Try again re-runs the SAME submission: the client's `preset`/`n_runs` are ignored
        prior = repo.list_runs(uid, id)
        if prior:
            preset, n_runs = prior[-1].preset, prior[-1].n_runs
            span = prior[-1].coded_span
    elif body.preset is not None:
        try:
            preset, _ = app.state.presets.resolve(body.preset, s.language)
        except UnknownPreset as e:
            raise ApiError.of(422, "invalid_parameters", f"preset: {e}") from None
    if "coded_span" in body.model_fields_set:
        span = body.coded_span
    transcript = repo.get_transcript(uid, id, "current").transcript
    if transcript is None:
        raise invalid_state()
    validate_coded_input(transcript, span)
    settings = app.state.settings
    run_id = uuid4().hex
    date = caps.utc_date()
    # One transaction: state check, cap reservation, run creation, first_run_id and `running`.
    # The loser of a race gets 409 and holds no slot.
    outcome = repo.start_run(
        uid, id, run_id, date, LimitDefaults.from_settings(settings), settings.max_active_runs,
        settings.git_sha, RUN_START_PROGRESS, RERUN_STATES, n_runs, preset,
        coded_span=span.model_dump(exclude_none=True) if span else None,
    )  # fmt: skip
    if outcome == "not_ready":
        raise invalid_state()
    if outcome == "daily_cap":
        raise ApiError.of(429, "daily_cap_reached", caps.DAILY_MESSAGE, period="day")
    if outcome == "concurrent":
        raise ApiError.of(429, "concurrent_runs", caps.CONCURRENT_MESSAGE)
    try:
        queue = getattr(app.state, "queue", None)
        if queue is None:
            raise RuntimeError("no queue")
        queue.enqueue(
            TaskPayload(
                kind="run", uid=uid, sid=id, run_id=run_id,
                request_id=getattr(request.state, "request_id", None),
            )
        )  # fmt: skip
    except Exception as e:
        logs.failed(
            "run_failed", session_id=id, run_id=run_id, step="run",
            error_code="upstream_unavailable", exc_class=type(e).__name__,
            request_id=getattr(request.state, "request_id", None),
        )  # fmt: skip
        _compensate(repo, uid, id, run_id, date)
        advance(
            repo, uid, id, to="failed", step=None,
            error=SessionError(
                code="upstream_unavailable", step="run", kind=kind_for_code("upstream_unavailable")
            ),
        )  # fmt: skip
        raise ApiError.of(503, "upstream_unavailable", "Could not start the run.") from None
    return RunStarted(run_id=run_id, session=RunSessionRef(id=id, status="running"))


def _compensate(repo, uid: str, sid: str, run_id: str, date: str) -> None:
    """The run never started: mark it failed and give the slot (and the day's count) back."""
    try:
        repo.update_run(uid, sid, run_id, {"status": "failed", "error": "upstream_unavailable"})
    except NotFoundError:
        pass
    release_once(repo, uid, sid, run_id, True, date)


@router.get(
    "/runs",
    operation_id="listRuns",
    response_model=RunList,
    summary="The session's runs, oldest first",
)
def list_runs(id: ResourceId, request: Request, user: User) -> RunList:
    _open_session(request, user, id)
    return RunList(items=[_view(r) for r in request.app.state.repo.list_runs(user.uid, id)])


@runs_router.get(
    "/runs/{run_id}",
    operation_id="getRun",
    response_model=RunView,
    summary="One run: status, params, run_info",
)
def get_run(run_id: ResourceId, request: Request, user: User) -> RunView:
    repo = request.app.state.repo
    run = repo.get_run_by_id(user.uid, run_id)
    _open_session(request, user, run.session_id)
    return _view(run)


@router.get(
    "/reports",
    operation_id="listReports",
    response_model=ReportList,
    summary="Report versions, oldest first",
)
def list_reports(id: ResourceId, request: Request, user: User) -> ReportList:
    _open_session(request, user, id)
    docs = request.app.state.repo.list_reports(user.uid, id)
    return ReportList(
        items=[
            ReportListItem(version=d.version, report_id=d.id, run_id=d.run_id,
                           created_at=d.created_at)
            for d in docs
        ]
    )  # fmt: skip


@router.get(
    "/reports/{version}",
    operation_id="getReport",
    response_model=ReportView,
    summary="One report by integer version (the public report address)",
    description="`Cache-Control: private, no-store`: the report carries PHI.",
)
def get_report(id: ResourceId, version: int, request: Request, response: Response, user: User):
    _open_session(request, user, id)
    d = request.app.state.repo.get_report_by_version(user.uid, id, version)
    response.headers["Cache-Control"] = "private, no-store"
    assert d.report is not None
    return ReportView(
        version=d.version, report_id=d.id, run_id=d.run_id, created_at=d.created_at,
        report_schema_version=d.report_schema_version, report=d.report,
    )  # fmt: skip
