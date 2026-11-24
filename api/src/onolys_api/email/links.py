"""Rebuild action links using only validated application configuration and action codes."""

import re
from typing import Literal
from urllib.parse import urlencode

from onolys_api.config import Settings

EmailKind = Literal["verify", "reset"]
_NEXT = re.compile(r"^/[^/\\]")
_MODES = {"verify": "verifyEmail", "reset": "resetPassword"}


def build_action_link(
    settings: Settings, kind: EmailKind, code: str, *, next_path: str | None = None
) -> str:
    query = {"mode": _MODES[kind], "oobCode": code}
    if kind == "verify" and next_path and _NEXT.match(next_path):
        query["continueUrl"] = (
            f"{settings.app_base_url}/verify-email?{urlencode({'next': next_path})}"
        )
    return f"{settings.app_base_url}/auth/action?{urlencode(query)}"
