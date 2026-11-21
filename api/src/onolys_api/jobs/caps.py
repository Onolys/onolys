"""Usage limits (SP11 R1, R4, R6; formerly the SP04 R8 spend guard): per-kind day + month caps and
the eval concurrent-run limit.

`reserve(repo, settings, uid, kind)` atomically checks and counts one unit, or raises 429:
eval day cap or concurrent limit -> `daily_cap_reached` (period=day), eval month ->
`monthly_cap_reached` (period=month), interview -> `interview_cap_reached` (with the period). When
both periods are spent the month wins. Every reservation must be released exactly once with
`release(repo, uid, reservation, refund)`: `refund=True` when it failed before any LLM call (gives
the day and month counts back), `refund=False` when it ended after spending. A refund hits the
docs the reservation was made on, even if the UTC day/month has rolled over since.

`reserve_run`/`release_run` are the eval wrappers the run call sites use.
"""

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
    "usage_view",
    "utc_date",
    "resets_at",
]

DAILY_MESSAGE = "Daily run limit reached."
CONCURRENT_MESSAGE = "Too many runs in progress."
MONTHLY_MESSAGE = "Monthly run limit reached."
INTERVIEW_MESSAGES: dict[Period, str] = {
    "day": "Daily AI interview limit reached.",
    "month": "Monthly AI interview limit reached.",
}


@dataclass(frozen=True)
class Reservation:
    kind: Kind
    date: str  # UTC day key the reservation was counted on (month key = date[:7])


@dataclass(frozen=True)
class PeriodUsage:
    used: int
    cap: int
    resets_at: datetime


@dataclass(frozen=True)
class KindUsage:
    day: PeriodUsage
    month: PeriodUsage


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


def month_resets_at(now: datetime | None = None) -> datetime:
    """The 1st of the next UTC month, 00:00."""
    d = (now or datetime.now(UTC)).astimezone(UTC)
    return datetime(d.year + (d.month == 12), d.month % 12 + 1, 1, tzinfo=UTC)


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
    period: Period = "month" if outcome == "month_cap" else "day"
    if kind == "interview":
        raise ApiError.of(429, "interview_cap_reached", INTERVIEW_MESSAGES[period], period=period)
    if outcome == "month_cap":
        raise ApiError.of(429, "monthly_cap_reached", MONTHLY_MESSAGE, period="month")
    message = CONCURRENT_MESSAGE if outcome == "concurrent" else DAILY_MESSAGE
    raise ApiError.of(429, "daily_cap_reached", message, period="day")


def release(repo: Repo, uid: str, reservation: Reservation, refund: bool) -> None:
    repo.release_usage(uid, reservation.kind, reservation.date, refund)


def reserve_run(repo: Repo, settings: Settings, uid: str, now: datetime | None = None) -> str:
    """Reserve one eval run; returns the UTC date key to pass to `release_run`."""
    return reserve(repo, settings, uid, "eval", now).date


def release_run(repo: Repo, uid: str, date: str, refund: bool) -> None:
    release(repo, uid, Reservation("eval", date), refund)


def usage_view(repo: Repo, settings: Settings, uid: str, now: datetime | None = None) -> UsageView:
    """Used / cap / resets_at per kind and period, per-user overrides applied."""
    user = repo.get_user(uid)
    user_d = user.model_dump() if user is not None else None
    defaults = LimitDefaults.from_settings(settings)
    day, month = repo.get_usage_docs(uid, utc_date(now))
    day_reset, month_reset = resets_at(now), month_resets_at(now)

    def kind_usage(kind: Kind, d_used: int, m_used: int) -> KindUsage:
        return KindUsage(
            PeriodUsage(d_used, effective_cap(user_d, kind, "day", defaults), day_reset),
            PeriodUsage(m_used, effective_cap(user_d, kind, "month", defaults), month_reset),
        )

    return UsageView(
        eval=kind_usage("eval", day.runs, month.runs),
        interview=kind_usage("interview", day.interviews, month.interviews),
    )
