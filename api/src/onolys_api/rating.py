"""Rating-card validation: the one seam `PUT /sessions/{id}/rating` goes through.

A thin wrapper over `onolys_miti.rating` (`validate_rating`, `is_no_rating`), so a card the API
stores is one the engine accepts, with the engine's rules (item ids, score scales, counts and
spans >= 0, limits) and its issue format (`Issue(path, code)`, `/`-joined paths). The only
API-only rule is the HTTP size cap `MAX_CARD_BYTES`. The rating schema is the engine's packaged
`MITI.rating_schema`; `create_app` reads it at startup. Issues are paths and codes only, never
card text.
"""

import json
from typing import Any

from onolys_miti.miti import MITI
from onolys_miti.rating import is_no_rating
from onolys_miti.rating import validate_rating as engine_validate_rating
from onolys_miti.report import Issue

SCHEMA_VERSION = "miti-1"
# Hard cap on a stored card (UTF-8 JSON bytes): bounds unknown keys the shape check does not cover.
MAX_CARD_BYTES = 256 * 1024

__all__ = ["MAX_CARD_BYTES", "SCHEMA_VERSION", "Issue", "has_content", "validate_rating"]


def load_schema() -> dict[str, Any]:
    """The engine's rating schema (the canonical `rating.schema.json`)."""
    return MITI.rating_schema


def card_size(obj: Any) -> int:
    return len(json.dumps(obj, ensure_ascii=False, default=str).encode())


def validate_rating(obj: Any, final: bool) -> list[Issue]:
    """Engine issues for a card, plus `too_large` over the size cap.

    `final=False` (autosave): shape and limits only. `final=True`: also a non-empty `change_goal`.
    """
    issues = list(engine_validate_rating(obj, final))
    if card_size(obj) > MAX_CARD_BYTES:
        issues.insert(0, Issue(path="", code="too_large"))
    return issues


def has_content(card: dict[str, Any]) -> bool:
    """True when the card carries any score, count or non-blank notes ("no rating" otherwise)."""
    return not is_no_rating(card)
