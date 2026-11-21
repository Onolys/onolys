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
Period = Literal["day", "month"]

# Kind -> usage-doc counter field. Day docs predate interviews: `runs` stays the eval count.
KIND_FIELD: dict[Kind, str] = {"eval": "runs", "interview": "interviews"}


@dataclass(frozen=True)
class LimitDefaults:
    eval_day: int
    eval_month: int
    interview_day: int
    interview_month: int

    @classmethod
    def from_settings(cls, s: Settings) -> "LimitDefaults":
        return cls(s.eval_cap_day, s.eval_cap_month, s.ai_cap_day, s.ai_cap_month)

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
