"""Per-task log ids (session, run, step, request) carried in contextvars.

Engines read these via ``snapshot()``; they never import ``api``. Context is
copied by ``asyncio.run``, ``asyncio.to_thread`` and anyio task hops.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar, Token
from typing import Any

_VARS: dict[str, ContextVar[str | None]] = {
    name: ContextVar(f"log_{name}", default=None)
    for name in ("session_id", "run_id", "step", "request_id")
}

LogToken = dict[str, Token]


def bind(**ids: str | None) -> LogToken:
    """Set the given ids; return a token for ``reset``. Omitted ids are untouched."""
    unknown = set(ids) - set(_VARS)
    if unknown:
        raise ValueError(f"unknown log context keys: {sorted(unknown)}")
    return {k: _VARS[k].set(v) for k, v in ids.items()}


def reset(token: LogToken) -> None:
    """Restore the values that were current before the matching ``bind``."""
    for k, t in reversed(list(token.items())):
        _VARS[k].reset(t)


@contextlib.contextmanager
def log_context(**ids: str | None) -> Iterator[None]:
    """Merge ``ids`` over the current values for the duration of the block."""
    token = bind(**ids)
    try:
        yield
    finally:
        reset(token)


def snapshot() -> dict[str, Any]:
    """Current non-None ids."""
    return {k: v for k, var in _VARS.items() if (v := var.get()) is not None}
