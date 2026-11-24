"""`/v1/sessions`: create (idempotent), list, get. Mutations return 202 with ids (R2)."""

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from onolys_miti.result import CodedSpan
from pydantic import BaseModel, Field, field_validator

from onolys_api import logs
from onolys_api.auth.deps import AuthUser, current_user
from onolys_api.client_info import client_info
from onolys_api.errors import ApiError, ErrorResponse
from onolys_api.jobs.delete import delete_session_data
from onolys_api.jobs.machine import advance
from onolys_api.jobs.queue import TaskPayload
from onolys_api.jobs.stale import settle_if_stale
from onolys_api.languages import is_supported_language
from onolys_api.presets import UnknownPreset
from onolys_api.repo.base import NotFoundError
from onolys_api.repo.models import (
    ClientInfo,
    IdempotencyDoc,
    RatingDraftDoc,
    SessionDoc,
    SessionState,
    SessionStatusDoc,
)
from onolys_api.routes.ids import ResourceId

IDEMPOTENCY_TTL = timedelta(hours=24)
MAX_KEY_LEN = 200

ERRORS = {"default": {"model": ErrorResponse, "description": "Error"}}
router = APIRouter(prefix="/sessions", tags=["sessions"], responses=ERRORS)
User = Annotated[AuthUser, Depends(current_user)]


class CreateSessionRequest(BaseModel):
    coded_span: CodedSpan | None = Field(
        None, description="Half-open milliseconds or zero-based turn range; null codes all turns."
    )
    language: str = Field("auto", description="BCP-47 tag or `auto`")
    n_runs: int = Field(1, ge=1, le=5)
    preset: str | None = Field(None, max_length=64, description="Allowlisted preset name")
    title: str | None = Field(None, max_length=200)
    interview_id: str | None = Field(
        None,
        min_length=1,
        max_length=100,
        description=(
            "An `ended`, not yet linked AI interview of the caller: the session takes its "
            "scenario language and title (unless `title` is set) and a prefilled rating draft"
        ),
    )

    client: ClientInfo | None = Field(
        None, description="Optional: which web build, recorder and audio engine made the request"
    )

    @field_validator("language")
    @classmethod
    def _language(cls, v: str) -> str:
        if not is_supported_language(v):
            raise ValueError("unsupported language")
        return v


class SessionRef(BaseModel):
    id: str
    status: SessionState


class CreateSessionResponse(BaseModel):
    session: SessionRef


class SessionListItem(BaseModel):
    id: str
    title: str | None = None
    status: SessionState
    created_at: datetime
    latest_report_version: int | None = None
    error_code: str | None = None
    interview_id: str | None = Field(None, description="Set for sessions made from an AI interview")


class SessionList(BaseModel):
    items: list[SessionListItem]
    next_cursor: str | None = None


class Flags(BaseModel):
    transcript_ready: bool
    speaker_confirmed: bool
    rating_submitted: bool
    has_rating: bool


class SessionErrorInfo(BaseModel):
    code: str


class SessionDetail(BaseModel):
    id: str
    title: str | None = None
    status: SessionState
    step: str | None = None
    progress: int
    flags: Flags
    warnings: list[str]
    error: SessionErrorInfo | None = None
    latest_report_version: int | None = None
    language: str
    n_runs: int
    preset: str | None = None
    interview_id: str | None = Field(
        default=None,
        description="Set when an AI interview created this session: its first run is free.",
    )
    free_run: bool = Field(
        default=False,
        description=(
            "True for an interview session whose free run stands: its run, and Try again after a "
            "failed free run, cost nothing against the daily evaluation cap."
        ),
    )
    created_at: datetime
    updated_at: datetime
    links: dict[str, str]


def _body_hash(body: CreateSessionRequest) -> str:
    return hashlib.sha256(body.model_dump_json().encode()).hexdigest()


def _replay_target_alive(repo, uid: str, doc: IdempotencyDoc) -> bool:
    """A replay must not hand back the id of a session that has since been deleted."""
    try:
        sid = doc.response["session"]["id"]
        return repo.get_session(uid, sid).state != "deleting"
    except (NotFoundError, KeyError, TypeError):
        return False


def _replay(doc: IdempotencyDoc, body_hash: str, response: Response) -> CreateSessionResponse:
    if doc.body_hash != body_hash:
        raise ApiError.of(409, "conflict", "Idempotency-Key was used with a different request.")
    response.headers["Idempotent-Replayed"] = "true"
    return CreateSessionResponse.model_validate(doc.response)


def _interview_scenario(request: Request, uid: str, iid: str) -> dict:
    interview = request.app.state.repo.get_interview(uid, iid)  # NotFoundError -> 404
    scenario = request.app.state.scenarios.get(interview.scenario_id)
    if scenario is None:
        raise ApiError.of(422, "invalid_parameters", "interview_id: its scenario is gone")
    return scenario


def _create_for_interview(
    request: Request,
    body: CreateSessionRequest,
    uid: str,
    sid: str,
    session: SessionDoc,
    status: SessionStatusDoc,
    now: datetime,
) -> None:
    """Write the session, its link and the prefilled rating draft in one repo transaction."""
    assert body.interview_id is not None
    repo = request.app.state.repo
    scenario = _interview_scenario(request, uid, body.interview_id)
    session.interview_id = body.interview_id
    session.language = scenario["language"]
    session.title = body.title or scenario["public"]["title"]
    draft = RatingDraftDoc(card={"change_goal": scenario["change_goal"]}, updated_at=now)
    outcome = repo.create_session_for_interview(uid, body.interview_id, sid, session, status, draft)
    if outcome == "not_ended":
        raise ApiError.of(409, "invalid_state", "The interview has not ended yet.")
    if outcome == "refunded":
        raise ApiError.of(409, "invalid_state", "A refunded (very short) interview cannot be used.")
    if outcome == "already_linked":
        raise ApiError.of(409, "conflict", "The interview already has a session.")


@router.post(
    "",
    operation_id="createSession",
    status_code=202,
    response_model=CreateSessionResponse,
    summary="Create a session",
    description=(
        "Writes the session and its PHI-free `session_status` document before returning. "
        "`Idempotency-Key` replays the original response for 24 h; the same key with a different "
        "body is 409 `conflict`. With `interview_id` the interview must be the caller's (404 "
        "otherwise), `ended` (else 409 `invalid_state`) and not linked to a session yet (else 409 "
        "`conflict`); the link and the session are written atomically, `language` comes from the "
        "scenario and `ratings/draft` is prefilled with its `change_goal`."
    ),
)
def create_session(
    request: Request,
    response: Response,
    body: CreateSessionRequest,
    user: User,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=MAX_KEY_LEN,
            description="Client-chosen key; replays for 24 h",
        ),
    ] = None,
) -> CreateSessionResponse:
    repo = request.app.state.repo
    uid = user.uid
    body_hash = _body_hash(body)
    now = datetime.now(UTC)

    if idempotency_key:
        prior = repo.get_idempotency(uid, idempotency_key)
        if prior is not None and now - prior.created_at < IDEMPOTENCY_TTL:
            if _replay_target_alive(repo, uid, prior):
                return _replay(prior, body_hash, response)
            repo.delete_idempotency(uid, idempotency_key)  # its session was deleted: start afresh
        elif prior is not None:
            repo.delete_idempotency(uid, idempotency_key)  # expired

    language = body.language
    if body.interview_id is not None:
        # 404 for a foreign or missing interview (never reveals another user's id); its scenario
        # decides the language, and a scenario removed since is not a usable source
        scenario = _interview_scenario(request, uid, body.interview_id)
        language = scenario["language"]
    try:
        preset, stt = request.app.state.presets.resolve(body.preset, language)
    except UnknownPreset as e:
        raise ApiError.of(422, "invalid_parameters", f"preset: {e}") from None

    sid = uuid4().hex
    session = SessionDoc(
        uid=uid,
        title=body.title,
        language=body.language,
        stt=stt,
        n_runs=body.n_runs,
        coded_span=body.coded_span,
        preset=preset,
        client=client_info(request, body.client),
        created_at=now,
        updated_at=now,
    )
    status = SessionStatusDoc(uid=uid, updated_at=now)
    if body.interview_id is None:
        repo.create_session(uid, sid, session, status)
    else:
        _create_for_interview(request, body, uid, sid, session, status, now)
    result = CreateSessionResponse(session=SessionRef(id=sid, status="created"))

    if idempotency_key:
        stored = IdempotencyDoc(
            body_hash=body_hash, response=result.model_dump(mode="json"), created_at=now
        )
        if not repo.put_idempotency(uid, idempotency_key, stored):
            # lost a race with the same key: drop our session, answer with the winner's
            repo.delete_session(uid, sid)
            if body.interview_id is not None:  # give the interview back: this call linked nothing
                repo.update_interview(uid, body.interview_id, {"session_id": None})
            winner = repo.get_idempotency(uid, idempotency_key)
            if winner is not None:
                return _replay(winner, body_hash, response)
    return result


@router.get(
    "",
    operation_id="listSessions",
    response_model=SessionList,
    summary="The caller's sessions, newest first (in-flight and failed included)",
    description=(
        "Not strictly read-only: a session whose pipeline has stalled past its deadline is marked "
        "`failed` here (lazily, in a transaction that yields to a finished task), so no sweeper "
        "job is needed. Sessions being deleted are skipped without shortening the page. "
        "`next_cursor` is an opaque position and stays valid if its session is deleted."
    ),
)
def list_sessions(
    request: Request,
    user: User,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> SessionList:
    try:
        page = request.app.state.repo.list_sessions(user.uid, limit=limit, cursor=cursor)
    except NotFoundError:
        raise ApiError.of(422, "invalid_parameters", "cursor: invalid cursor") from None
    repo, settings = request.app.state.repo, request.app.state.settings
    now = request.app.state.clock()
    sessions = [settle_if_stale(repo, s, now, settings) for s in page.items]
    items = [
        SessionListItem(
            id=s.id,
            title=s.title,
            status=s.state,
            created_at=s.created_at,
            latest_report_version=s.latest_report_version,
            error_code=s.error.code if s.error else None,
            interview_id=s.interview_id,
        )
        for s in sessions
        if s.state != "deleting"  # one that began deleting since the page was read
    ]
    return SessionList(items=items, next_cursor=page.next_cursor)


@router.get(
    "/{id}",
    operation_id="getSession",
    response_model=SessionDetail,
    summary="Session status snapshot (the web app uses the session_status listener instead)",
    description=(
        "Not strictly read-only: a stalled session is marked `failed` on read (see "
        "`listSessions`)."
    ),
)
def get_session(id: ResourceId, request: Request, user: User) -> SessionDetail:
    repo = request.app.state.repo
    s = repo.get_session(user.uid, id)
    s = settle_if_stale(repo, s, request.app.state.clock(), request.app.state.settings)
    if s.state == "deleting":
        raise NotFoundError()
    st = repo.get_status(user.uid, id)
    base = f"/v1/sessions/{id}"
    links = {"self": base}
    if s.transcript_ready:
        links["transcript"] = f"{base}/transcript"
    if s.latest_report_version:
        links["reports"] = f"{base}/reports"
    return SessionDetail(
        id=id,
        title=s.title,
        status=s.state,
        step=st.step,
        progress=st.progress,
        flags=Flags(
            transcript_ready=s.transcript_ready,
            speaker_confirmed=s.speaker_confirmed,
            rating_submitted=s.rating_submitted,
            has_rating=s.has_rating,
        ),
        warnings=s.warnings,
        error={"code": s.error.code} if s.error else None,
        latest_report_version=s.latest_report_version,
        language=s.language,
        n_runs=s.n_runs,
        preset=s.preset,
        interview_id=s.interview_id,
        free_run=bool(s.interview_id) and not s.free_run_void,
        created_at=s.created_at,
        updated_at=s.updated_at,
        links=links,
    )


@router.delete(
    "/{id}",
    operation_id="deleteSession",
    status_code=204,
    response_class=Response,
    summary="Hard delete: audio, transcript, ratings, runs, reports, status",
    description=(
        "Marks the session `deleting`, removes every stored object and document, then answers "
        "204. If storage or Firestore fails the session stays `deleting` (hidden everywhere), a "
        "cleanup task finishes it, and this call answers 503 `upstream_unavailable`: repeat it "
        "or wait. Deleting a finished session again answers 404. Usage counters are kept."
    ),
)
def delete_session(id: ResourceId, request: Request, user: User) -> Response:
    repo, blobs = request.app.state.repo, request.app.state.blobs
    rid = getattr(request.state, "request_id", None)
    s = repo.get_session(user.uid, id)  # 404 for another user's or an unknown session
    if s.state != "deleting":
        advance(repo, user.uid, id, to="deleting")
    try:
        delete_session_data(repo, blobs, user.uid, id, rid)
    except Exception as e:
        logs.emit(
            "session_delete_failed",
            logging.ERROR,
            session_id=id,
            exc_class=type(e).__name__,
            request_id=rid,
        )
        queue = getattr(request.app.state, "queue", None)
        try:
            if queue is not None:
                queue.enqueue(TaskPayload(kind="delete", uid=user.uid, sid=id, request_id=rid))
        except Exception as qe:
            logs.emit(
                "delete_enqueue_failed",
                logging.ERROR,
                session_id=id,
                exc_class=type(qe).__name__,
                request_id=rid,
            )
        raise ApiError.of(
            503, "upstream_unavailable", "Deletion is in progress; it will finish shortly."
        ) from None
    return Response(status_code=204)
