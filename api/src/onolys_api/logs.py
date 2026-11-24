"""Structured, PHI-free API logs (PRD R10).

One JSON object per line on stderr: Cloud Logging reads `severity` and `message` and exposes
the rest as `jsonPayload.*` (SP06's alert filters on `jsonPayload.status="failed"`, the runbook on
`jsonPayload.request_id`). Field names pass the `onolys_engine_core.safe_log` allowlist,
so text-like or unknown names are dropped; string values are capped.
Values are ids, codes and numbers only.
"""

import hashlib
import hmac
import logging
import re
import threading

from onolys_engine_core.json_logging import configure_logging
from onolys_engine_core.log_context import bind
from onolys_engine_core.safe_log import clean_value, register_fields, safe_fields
from starlette.requests import HTTPConnection

from onolys_api.config import Settings

API_FIELDS = frozenset({
    "uid_hash", "session_id", "run_id", "step", "status", "attempt", "duration_ms",
    "auth_kind", "error_code", "exc_class", "request_id", "code_version",
    "method", "route", "stt_operation", "stt_started", "poll_n", "elapsed_s", "outcome",
    "email_kind", "provider_status",
})  # fmt: skip
register_fields(API_FIELDS)

log = logging.getLogger("onolys_api.events")
_state = {"key": b"", "code_version": "dev"}
_lock = threading.Lock()


class _NoTraceback(logging.Filter):
    """Reduce a record carrying an exception to its class name (S1).

    uvicorn logs `Exception in ASGI application` with the full traceback, and a FastAPI
    ResponseValidationError's text embeds the offending `input` (transcript/rating/report PHI).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info
        if exc or record.exc_text:
            name = exc[0].__name__ if exc and exc[0] else "Exception"
            record.msg = f"Unhandled exception in ASGI application: {name} (details suppressed)"
            record.args = None
            record.exc_info = record.exc_text = None
            record.stack_info = None
        return True


def _guard_uvicorn() -> None:
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        if not any(isinstance(f, _NoTraceback) for f in lg.filters):
            lg.addFilter(_NoTraceback())


def configure(settings: Settings) -> None:
    """Set the HMAC key and code version, and attach the stderr handler once."""
    _guard_uvicorn()
    with _lock:
        _state["key"] = settings.uid_hmac_key.encode()
        _state["code_version"] = settings.git_sha
    configure_logging(settings)


def uid_hash(uid: str) -> str:
    """Keyed HMAC-SHA256 of the uid (first 16 hex chars): correlates a user, reveals nothing."""
    return hmac.new(_state["key"], uid.encode(), hashlib.sha256).hexdigest()[:16]


def _clean(name, value):
    return None if value is None else clean_value(name, value)


def emit(event: str, level: int = logging.INFO, **fields) -> None:
    """Log one line. None values are omitted; `code_version` is always added."""
    kept = {k: _clean(k, v) for k, v in safe_fields(fields).items() if v is not None}
    kept.setdefault("code_version", _state["code_version"])
    log.log(level, "%s", event, extra={"fields": kept})


def failed(
    event: str, *, session_id, step, error_code, exc_class, request_id=None, run_id=None
) -> None:
    """The one `status=failed` line of a failed step or run (SP06 alert + runbook match it)."""
    emit(
        event, logging.ERROR, status="failed", session_id=session_id, run_id=run_id, step=step,
        error_code=error_code, exc_class=exc_class, request_id=request_id,
    )  # fmt: skip


_ID_PARAMS = ("id", "sid", "iid", "interview_id")
_RESOURCE_ID = re.compile(r"^[0-9a-f]{32}$")


async def bind_session(conn: HTTPConnection) -> None:
    """Router dependency: bind the `{id}` path param (session or interview id) as `session_id`.

    Async on purpose: a sync dependency runs in a threadpool copy of the context and its set
    would be lost. Only well-formed resource ids are bound; the request-scoped middleware resets
    the context when the request ends.
    """
    for name in _ID_PARAMS:
        value = conn.path_params.get(name)
        if isinstance(value, str) and _RESOURCE_ID.match(value):
            bind(session_id=value)
            return
