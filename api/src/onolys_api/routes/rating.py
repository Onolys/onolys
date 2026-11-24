"""`/v1/sessions/{id}/rating`: the in-app rating card (R2, D15). Firestore only, no parsing.

`final=false` overwrites the single draft doc (size limits only; never gates or starts a run).
`final=true` is refused (409 `rating_final`) once a run started, a rating was submitted
or a report exists; otherwise it validates the card and writes a new revision
`ratings/{rating_id}`, copies `change_goal` to the session, sets
`rating_submitted`/`has_rating`, mirrors them to `session_status` and calls the first-run
hook. Allowed in every state but `deleting` (404).
"""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from onolys_api.auth.deps import AuthUser, current_user
from onolys_api.errors import ApiError, ErrorDetail, ErrorResponse
from onolys_api.jobs.first_run import maybe_start_first_run
from onolys_api.jobs.machine import (
    has_final_report,
    invalid_state,
    rating_final,
    transition_plan,
)
from onolys_api.rating import SCHEMA_VERSION, Issue, has_content, validate_rating
from onolys_api.repo.base import NotFoundError
from onolys_api.repo.models import RatingDoc, RatingDraftDoc
from onolys_api.routes.ids import ResourceId

ERRORS = {"default": {"model": ErrorResponse, "description": "Error"}}
router = APIRouter(prefix="/sessions/{id}/rating", tags=["rating"], responses=ERRORS)
User = Annotated[AuthUser, Depends(current_user)]
INVALID = "The rating card is not valid (shape or length limits)."


class RatingRequest(BaseModel):
    final: bool = Field(description="`false` autosaves the draft; `true` submits a new revision")
    no_rating: bool = Field(False, description='With `final`: submit as a "no rating" revision')
    card: dict[str, Any] = Field(description="The rating card (`rating.schema.json`)")


class RatingSaved(BaseModel):
    final: bool
    rating_id: str | None = None
    no_rating: bool | None = None
    has_rating: bool | None = None
    updated_at: datetime


class FinalRating(BaseModel):
    rating_id: str
    no_rating: bool
    card: dict[str, Any]


class DraftRating(BaseModel):
    card: dict[str, Any]
    updated_at: datetime


class RatingView(BaseModel):
    final: FinalRating | None = None
    draft: DraftRating | None = Field(None, description="Only when newer than the last final")


MAX_ISSUES = 20


def _invalid(issues: list[Issue]) -> ApiError:
    """422 `rating_invalid`: one detail per issue (card path + issue code, never card text)."""
    details: list[ErrorDetail] = []
    for path, code in sorted({(i.path, i.code) for i in issues})[:MAX_ISSUES]:
        field = path or "$"
        details.append(
            {"code": "rating_invalid", "message": f"{field}: {code}", "field": field,
             "issue": code}
        )  # fmt: skip
    return ApiError(422, INVALID, details)


def _open_session(request: Request, user: AuthUser, id: str):
    s = request.app.state.repo.get_session(user.uid, id)
    if s.state == "deleting":
        raise NotFoundError()
    return s


@router.put(
    "",
    operation_id="putRating",
    status_code=202,
    response_model=RatingSaved,
    summary="Save the rating card (draft autosave or final revision)",
    description=(
        "`final=false`: overwrites the draft; the shape and size limits are checked (an unset "
        "`change_goal` is fine) and nothing else changes. `final=true`: validates the card "
        "(`change_goal` required), writes a new revision "
        "and sets `rating_submitted`/`has_rating`; `no_rating=true`, or a card with no scores, "
        'counts or notes, is a "no rating" revision (`has_rating=false`). Over 1,000 chars per '
        "reason/note/example or 3,000 for `notes` is 422 `rating_invalid`. Allowed in every state "
        "but `deleting` (404) and `cancelled` (409 `invalid_state`); a final card is refused "
        "with 409 `rating_final` once a rating was submitted (or a report exists): the "
        "rating is final, only drafts stay open. A final card may start the first run (R4)."
    ),
)
def put_rating(id: ResourceId, body: RatingRequest, request: Request, user: User) -> RatingSaved:
    repo = request.app.state.repo
    uid = user.uid
    session = _open_session(request, user, id)
    if session.state == "cancelled":
        raise invalid_state()  # terminal (04-cancel R6); GET /rating still reads
    now = datetime.now(UTC)
    if not body.final:
        if issues := validate_rating(body.card, final=False):
            raise _invalid(issues)
        repo.put_rating_draft(uid, id, RatingDraftDoc(card=body.card, updated_at=now))
        return RatingSaved(final=False, updated_at=now)

    if (
        session.first_run_id
        or session.rating_submitted
        or has_final_report(repo, uid, id, session.state)
    ):
        raise rating_final()  # The goal is locked when the first run starts.
    if issues := validate_rating(body.card, final=True):
        raise _invalid(issues)
    no_rating = body.no_rating or not has_content(body.card)
    rating_id = uuid4().hex
    revision = RatingDoc(
        card=body.card,
        no_rating=no_rating,
        has_rating=not no_rating,
        schema_version=SCHEMA_VERSION,
        created_at=now,
    )

    def _not_final(s) -> None:  # in the transaction: the loser of two racing submits gets 409
        if (
            s.first_run_id
            or s.rating_submitted
            or s.state == "report_ready"
            or s.latest_report_version
        ):
            raise rating_final()

    # ONE transaction (LM-2): the final-check, the revision and the flags commit together.
    repo.transition_session(
        uid, id,
        transition_plan(
            flags={"rating_submitted": True, "has_rating": not no_rating},
            extra_fields={"change_goal": body.card["change_goal"]},
            guard=_not_final,
        ),
        children=((f"ratings/{rating_id}", revision.to_store(), True),),
    )  # fmt: skip
    maybe_start_first_run(
        repo,
        getattr(request.app.state, "queue", None),
        uid,
        id,
        request.app.state.settings,
        getattr(request.state, "request_id", None),
    )
    return RatingSaved(
        final=True, rating_id=rating_id, no_rating=no_rating, has_rating=not no_rating,
        updated_at=now,
    )  # fmt: skip


@router.get(
    "",
    operation_id="getRating",
    response_model=RatingView,
    summary="The latest final revision and, if newer, the autosaved draft",
)
def get_rating(id: ResourceId, request: Request, user: User) -> RatingView:
    repo = request.app.state.repo
    _open_session(request, user, id)
    final = repo.latest_rating(user.uid, id)
    draft = repo.get_rating_draft(user.uid, id)
    view = RatingView()
    if final is not None:
        view.final = FinalRating(rating_id=final.id, no_rating=final.no_rating, card=final.card)
    if draft is not None and (final is None or draft.updated_at > final.created_at):
        view.draft = DraftRating(card=draft.card, updated_at=draft.updated_at)
    return view
