"""Usage limits (SP11 R1, R4, R6; formerly the SP04 R8 spend guard): one DAILY cap per kind and
the eval concurrent-run limit (FX46: no monthly caps).

`reserve(repo, settings, uid, kind)` atomically checks and counts one unit, or raises 429:
eval day cap -> `daily_cap_reached` (period=day), eval concurrent limit -> `concurrent_runs`,
interview -> `interview_cap_reached` (period=day). Every reservation must be released exactly once
with
`release(repo, uid, reservation, refund)`: `refund=True` when it failed before any LLM call (gives
the day count back), `refund=False` when it ended after spending. A refund hits the
docs the reservation was made on, even if the UTC day has rolled over since.

`reserve_run`/`release_run` are the eval wrappers the run call sites use.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import NoReturn

from onolys_api.config import Settings
from onolys_api.errors import ApiError
from onolys_api.repo.base import Repo
from onolys_api.repo.limits import Kind, LimitDefaults, Period, effective_cap
from onolys_api.repo.models import InterviewDoc

__all__ = [
    "Kind",
    "Period",
    "Reservation",
    "KindUsage",
    "PeriodUsage",
    "UsageView",
    "reserve",
    "start_interview",
    "release",
    "reserve_run",
    "release_run",
    "start_with_repair",
    "usage_view",
    "utc_date",
    "resets_at",
]

DAILY_MESSAGE = "Daily run limit reached."
CONCURRENT_MESSAGE = "Too many runs in progress."
INTERVIEW_DAILY_MESSAGE = "Daily AI interview limit reached."


@dataclass(frozen=True)
class Reservation:
    kind: Kind
    date: str  # UTC day key the reservation was counted on


@dataclass(frozen=True)
class PeriodUsage:
    used: int
    cap: int
    resets_at: datetime


@dataclass(frozen=True)
class KindUsage:
    day: PeriodUsage


@dataclass(frozen=True)
class UsageView:
    eval: KindUsage
    interview: KindUsage


def utc_date(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%d")


def resets_at(now: datetime | None = None) -> datetime:
    """Next UTC midnight."""
    d = (now or datetime.now(UTC)).astimezone(UTC)
    return datetime(d.year, d.month, d.day, tzinfo=UTC) + timedelta(days=1)


def reserve(
    repo: Repo, settings: Settings, uid: str, kind: Kind, now: datetime | None = None
) -> Reservation:
    date = utc_date(now)
    outcome = repo.reserve_usage(uid, kind, date, LimitDefaults.from_settings(settings),
                                 settings.max_active_runs)  # fmt: skip
    if outcome == "ok":
        return Reservation(kind, date)
    _refuse(kind, outcome)


def start_interview(
    repo: Repo, settings: Settings, uid: str, iid: str, doc: InterviewDoc
) -> Reservation:
    """Reserve one interview unit and create `doc` in ONE repo transaction (A9): concurrent starts
    cannot both reserve. 429 when capped; 409 `conflict` when the caller already has an open one."""
    outcome = repo.create_interview_reserved(
        uid, iid, doc, LimitDefaults.from_settings(settings), settings.max_active_runs
    )
    if outcome == "ok":
        return Reservation("interview", doc.reservation_date)
    if outcome == "open_exists":
        raise ApiError.of(409, "conflict", "Another interview is already starting.")
    _refuse("interview", outcome)


def _refuse(kind: Kind, outcome: str) -> NoReturn:
    if kind == "interview":
        raise ApiError.of(429, "interview_cap_reached", INTERVIEW_DAILY_MESSAGE, period="day")
    if outcome == "concurrent":
        raise ApiError.of(429, "concurrent_runs", CONCURRENT_MESSAGE)
    raise ApiError.of(429, "daily_cap_reached", DAILY_MESSAGE, period="day")


def release(repo: Repo, uid: str, reservation: Reservation, refund: bool) -> None:
    repo.release_usage(uid, reservation.kind, reservation.date, refund)


def reserve_run(repo: Repo, settings: Settings, uid: str, now: datetime | None = None) -> str:
    """Reserve one eval run; returns the UTC date key to pass to `release_run`."""
    return reserve(repo, settings, uid, "eval", now).date


def release_run(repo: Repo, uid: str, date: str, refund: bool) -> None:
    release(repo, uid, Reservation("eval", date), refund)


def start_with_repair(repo: Repo, uid: str, start: Callable[[], str]) -> str:
    """Run a start transaction; when it is refused for the concurrent-run cap, first reconcile
    the user's `active_runs` against the runs that really hold a slot (M-2: a leaked slot would
    otherwise 429 the user forever) and try once more if that freed any."""
    outcome = start()
    if outcome == "concurrent" and repo.reconcile_active_runs(uid) > 0:
        outcome = start()
    return outcome


def usage_view(repo: Repo, settings: Settings, uid: str, now: datetime | None = None) -> UsageView:
    """Used / cap / resets_at per kind (UTC day), per-user overrides applied."""
    user = repo.get_user(uid)
    user_d = user.model_dump() if user is not None else None
    defaults = LimitDefaults.from_settings(settings)
    day = repo.get_usage_doc(uid, utc_date(now))
    reset = resets_at(now)

    def kind_usage(kind: Kind, used: int) -> KindUsage:
        return KindUsage(PeriodUsage(used, effective_cap(user_d, kind, "day", defaults), reset))

    return UsageView(
        eval=kind_usage("eval", day.runs), interview=kind_usage("interview", day.interviews)
    )
