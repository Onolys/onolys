"""Per-user usage limits (SP11 R3, D5, D6): kinds, periods, defaults and the one override resolver.

Lives under `repo/` (imports only `config` and `logs`) so `FirestoreRepo`, `FakeRepo` and
`jobs/caps.py` can all import it without a cycle.
"""

import logging
from dataclasses import dataclass
from typing import Any, Literal

from onolys_api import logs
from onolys_api.config import Settings

Kind = Literal["eval", "interview"]
Period = Literal["day"]

# Kind -> usage-doc counter field. Day docs predate interviews: `runs` stays the eval count.
KIND_FIELD: dict[Kind, str] = {"eval": "runs", "interview": "interviews"}


@dataclass(frozen=True)
class LimitDefaults:
    eval_day: int
    interview_day: int

    @classmethod
    def from_settings(cls, s: Settings) -> "LimitDefaults":
        return cls(s.eval_cap_day, s.ai_cap_day)

    def get(self, kind: Kind, period: Period) -> int:
        return getattr(self, f"{kind}_{period}")


def _valid(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _warn(kind: Kind, period: Period) -> None:
    logs.emit("limit_override_ignored", logging.WARNING, step=f"{kind}.{period}", outcome="ignored")


def effective_cap(user: dict[str, Any] | None, kind: Kind, period: Period, d: LimitDefaults) -> int:
    """`limits.<kind>.<period>` > legacy `daily_cap` (eval day only) > default.

    A malformed leaf (non-int, bool, negative) is ignored with a value-free warning: never raises.
    """
    user = user or {}
    limits = user.get("limits")
    leaf: Any = None
    if isinstance(limits, dict):
        sub = limits.get(kind)
        if isinstance(sub, dict):
            leaf = sub.get(period)
        elif sub is not None:
            _warn(kind, period)
    elif limits is not None:
        _warn(kind, period)
    if leaf is not None:
        if _valid(leaf):
            return leaf
        _warn(kind, period)
    if kind == "eval" and period == "day":
        legacy = user.get("daily_cap")
        if legacy is not None:
            if _valid(legacy):
                return legacy
            _warn(kind, period)
    return d.get(kind, period)


ReserveUsageOutcome = Literal["ok", "day_cap", "concurrent"]


def decide_reserve(
    user: dict[str, Any] | None,
    day: dict[str, Any] | None,
    kind: Kind,
    d: LimitDefaults,
    max_active: int,
    units: int = 1,
) -> ReserveUsageOutcome:
    """Shared reserve rule (both repos): the daily cap, then the concurrent limit, which applies to
    `eval` only (`users/{uid}.max_active_runs` overrides). There is no monthly cap.
    `units` is what the action costs (an n_runs run costs n_runs): refused unless all fit."""
    user = user or {}
    field = KIND_FIELD[kind]
    if (day or {}).get(field, 0) + units > effective_cap(user, kind, "day", d):
        return "day_cap"
    if kind == "eval" and _at_active_limit(user, max_active):
        return "concurrent"
    return "ok"


def _at_active_limit(user: dict[str, Any], max_active: int) -> bool:
    eff = user.get("max_active_runs")
    return user.get("active_runs", 0) >= (max_active if eff is None else eff)


def decide_start(
    user: dict[str, Any] | None,
    day: dict[str, Any] | None,
    d: LimitDefaults,
    max_active: int,
    exempt: bool,
    units: int = 1,
) -> ReserveUsageOutcome:
    """Run-start rule (`start_first_run`/`start_run`, both repos): the eval reserve rule, except an
    `exempt` run (first AI-linked evaluation, SP11 R5) skips the day check and still obeys
    the concurrent-run limit. A counted run costs `units` (= its n_runs)."""
    if not exempt:
        return decide_reserve(user, day, "eval", d, max_active, units)
    return "concurrent" if _at_active_limit(user or {}, max_active) else "ok"


# `decide_start` outcome -> repo `StartOutcome` and the session error code a held first run gets.
START_OUTCOME = {"day_cap": "daily_cap", "concurrent": "concurrent"}
HELD_ERROR_CODE = {
    "daily_cap": "daily_cap_reached",
    "concurrent": "concurrent_runs",
}
