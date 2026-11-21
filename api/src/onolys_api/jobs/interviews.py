"""Interview settlement (SP10 R5, D11): the one place an interview leaves `created|live`.

`settle_interview` is used by `POST /interviews/{id}/end`, the lazy abandon at the next create,
and (Task 6) the delayed sweeper task. The state change is one repo transaction, so exactly one
caller wins; only the winner touches the SP11 reservation: `refund=True` when the best known
elapsed time (relay-recorded `duration_s`, aged by `now - seen_at` while the relay is connected) is
under `AI_ABANDON_COUNT_SECONDS`, else the unit stays counted. The verdict is stored as
`refunded` in the same write as the transition; a refunded interview can never be linked to a
session (no free evaluation on top of the refund). A caller that loses (already
ended/abandoned/uploaded) changes nothing.
"""

from datetime import datetime
from typing import Literal

from onolys_api.config import Settings
from onolys_api.jobs.caps import Reservation, release
from onolys_api.repo.base import Repo
from onolys_api.repo.models import InterviewDoc

OPEN_STATES = ("created", "live")


def settle_interview(
    repo: Repo,
    settings: Settings,
    uid: str,
    iid: str,
    to_state: Literal["ended", "abandoned"],
    now: datetime,
) -> InterviewDoc:
    """Move an open interview to `to_state` and settle its usage unit exactly once.
    Returns the interview as it now is (unchanged when it was already settled)."""
    doc = repo.transition_interview(
        uid, iid, OPEN_STATES, to_state, {"ended_at": now},
        refund_rule=(now, float(settings.ai_abandon_count_seconds)),
    )  # fmt: skip
    if doc is None:
        return repo.get_interview(uid, iid)
    release(repo, uid, Reservation("interview", doc.reservation_date), doc.refunded)
    return doc


def abandon_open_interviews(repo: Repo, settings: Settings, uid: str, now: datetime) -> None:
    """Lazily abandon every unfinished interview of `uid` (same refund rule)."""
    for doc in repo.list_open_interviews(uid):
        settle_interview(repo, settings, uid, doc.id, "abandoned", now)
