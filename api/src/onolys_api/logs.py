"""Structured, PHI-free API logs.

Cloud Logging's `StructuredLogHandler` (google-cloud-logging) writes one JSON object per line on
stderr: Cloud Logging reads `severity` and `message` and exposes the rest as `jsonPayload.*` (the
prod alert filters on `jsonPayload.status="failed"`, the runbook on `jsonPayload.request_id`).

`PhiFilter` (a `logging.Filter` on that handler) is the PHI gate: a record's `fields` keep only
`ALLOWED_FIELDS` names (the engine's `LOG_FIELDS` plus `API_FIELDS`; text-like names always drop),
string values are capped, and the bound log ids ride along. Values are ids, codes and numbers only.
"""

import contextlib
import hashlib
import hmac
import logging
import os
import re
import sys
import threading
from collections.abc import Iterator, Mapping
from contextvars import ContextVar, Token
from types import MappingProxyType
from typing import Any

from google.cloud.logging_v2.handlers import StructuredLogHandler
from onolys_engine_core.llm.quiet import LITELLM_LOGGERS, quiet_litellm
from onolys_engine_core.safe_log import LOG_FIELDS, PROVIDER_ERROR_MAX_CHARS
from starlette.requests import HTTPConnection

from onolys_api.config import Settings

API_FIELDS = frozenset({
    "uid_hash", "session_id", "run_id", "step", "status", "attempt", "duration_ms",
    "auth_kind", "error_code", "exc_class", "request_id", "code_version",
    "method", "route", "stt_operation", "stt_started", "poll_n", "elapsed_s", "outcome",
    "email_kind", "provider_status", "from_state", "counted", "reason",
    # STT, voice and rating
    "audio_ms", "stt_provider", "stt_model", "job_id",
    "voice_provider", "voice_model", "voice", "frames",
    "final", "issues", "no_rating",
    # interview audio check and version fields
    "interview_id", "uploaded_s", "relay_s", "diff_s", "threshold_s", "result",
    "revision", "relay_version", "relay_revision", "web_version", "user_agent", "recorder_mime",
    "audio_engine", "audio_format", "audio_codec", "audio_streams",
})  # fmt: skip
ALLOWED_FIELDS = LOG_FIELDS | API_FIELDS

MAX_MESSAGE_CHARS = 300
MAX_VALUE_CHARS = 200
FIELD_CAPS: dict[str, int] = {"provider_error": PROVIDER_ERROR_MAX_CHARS}
_BLOCKED_PARTS = ("text", "body", "transcript", "excerpt", "message")
FIRST_PARTY_PREFIXES = ("onolys", "miti")  # our loggers: INFO passes; all others need WARNING
_HANDLER_MARK = "_onolys_json"
_PER_LOGGER_MARKS = ("_miti", "_onolys")
_PROPAGATING = ("miti", "onolys_api.events", "httpx", *LITELLM_LOGGERS)

log = logging.getLogger("onolys_api.events")
_state = {"key": b"", "code_version": "dev"}
_lock = threading.Lock()


# ---- bound log ids (session, run, step, request, client version) ----

CONTEXT_KEYS = ("session_id", "run_id", "step", "request_id", "client_version")
_NONE: Mapping[str, str | None] = MappingProxyType({})
_ids: ContextVar[Mapping[str, str | None]] = ContextVar("log_ids", default=_NONE)


def bind(**ids: str | None) -> Token:
    """Set the given ids; return a token for `reset`. Omitted ids are untouched."""
    unknown = set(ids) - set(CONTEXT_KEYS)
    if unknown:
        raise ValueError(f"unknown log context keys: {sorted(unknown)}")
    return _ids.set({**_ids.get(), **ids})


def reset(token: Token) -> None:
    """Restore the ids that were current before the matching `bind`."""
    _ids.reset(token)


@contextlib.contextmanager
def log_context(**ids: str | None) -> Iterator[None]:
    """Merge `ids` over the current values for the duration of the block."""
    token = bind(**ids)
    try:
        yield
    finally:
        reset(token)


def snapshot() -> dict[str, Any]:
    """Current non-None ids."""
    return {k: v for k, v in _ids.get().items() if v is not None}


# ---- the PHI gate and the handler ----


def _blocked(name: str) -> bool:
    # body_bytes is a size, not content
    return name != "body_bytes" and any(p in name for p in _BLOCKED_PARTS)


def safe_fields(fields: dict) -> dict:
    """Only allowlisted, non-text-like names survive."""
    return {k: v for k, v in fields.items() if k in ALLOWED_FIELDS and not _blocked(k)}


def clean_value(name: str, value):
    """Numbers/bools as is; everything else a string capped per field (default MAX_VALUE_CHARS)."""
    if isinstance(value, bool | int | float):
        return value
    return str(value)[: FIELD_CAPS.get(name, MAX_VALUE_CHARS)]


def _one_line(text: str) -> str:
    return " ".join(str(text).split())[:MAX_MESSAGE_CHARS]


class FirstPartyInfoFilter(logging.Filter):
    """Third-party records need WARNING+; our own loggers (``onolys*``, ``miti*``) pass at INFO.

    Keeps library chatter (``google_genai.*``, ``httpx`` request URLs) out of the logs.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.WARNING or record.name.startswith(FIRST_PARTY_PREFIXES)


class NoExceptionDetail(logging.Filter):
    """Reduce a record carrying an exception to its class name.

    The message and args may embed exception text or PHI (a FastAPI ResponseValidationError
    embeds the offending ``input``), so the whole message is replaced, not just the traceback.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info
        if exc or record.exc_text:
            name = exc[0].__name__ if exc and exc[0] else "Exception"
            record.msg = f"Exception {name} (details suppressed)"
            record.args = None
            record.exc_info = record.exc_text = None
            record.stack_info = None
            record.exc_class = name
        return True


class PhiFilter(logging.Filter):
    """Build the record's `json_fields` (what `StructuredLogHandler` merges into the payload).

    ``{event|logger, <bound ids>, <allowlisted fields>, code_version, revision}``; the message is
    one line, capped. Records from ``log_event`` / ``emit`` carry ``record.fields``; any other
    record (third party or plain) gets ``logger`` instead of ``event``. Exceptions are reduced to
    their class name (``exc_class``). Safe to run twice on one record.
    """

    def __init__(self, code_version: str = "dev") -> None:
        super().__init__()
        self.code_version = code_version

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, Mapping):  # a dict message would bypass the allowlist
            return False
        fields = getattr(record, "fields", None)
        msg = _one_line(record.getMessage())
        out: dict = {"event": msg} if fields is not None else {"logger": record.name}
        if msg.startswith("{"):  # the handler would parse a JSON-looking message into keys
            msg = f"- {msg}"
        record.msg, record.args = msg, None
        if not hasattr(record, "ctx"):
            record.ctx = snapshot()
        extra = {k: clean_value(k, v) for k, v in safe_fields(fields or {}).items()}
        extra = {**record.ctx, **extra}
        if exc_class := getattr(record, "exc_class", None):
            extra.setdefault("exc_class", exc_class)
        elif record.exc_info or record.exc_text:  # record that skipped NoExceptionDetail
            exc = record.exc_info[0] if record.exc_info else None
            extra.setdefault("exc_class", exc.__name__ if exc else "Exception")
        extra = {k: v for k, v in extra.items() if v is not None}
        extra.setdefault("code_version", self.code_version)
        if revision := os.environ.get("K_REVISION"):
            extra.setdefault("revision", revision)
        record.json_fields = {**out, **extra}
        return True


class _StderrHandler(StructuredLogHandler):
    """`StructuredLogHandler` writing to whatever sys.stderr is at emit time (survives swaps)."""

    def __init__(self) -> None:
        super().__init__(stream=sys.stderr)

    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, _value) -> None:
        pass


def make_handler(code_version: str = "dev") -> logging.Handler:
    h = _StderrHandler()
    h.addFilter(NoExceptionDetail())
    h.addFilter(FirstPartyInfoFilter())
    h.addFilter(PhiFilter(code_version))
    return h


def has_handler(logger: logging.Logger) -> bool:
    return any(getattr(h, _HANDLER_MARK, False) for h in logger.handlers)


def _marked(handler: logging.Handler) -> bool:
    return any(getattr(handler, m, False) for m in _PER_LOGGER_MARKS)


def _install(code_version: str) -> None:
    """Install the one handler on root; route miti, events, LiteLLM and httpx through it."""
    root = logging.getLogger()
    for h in [h for h in root.handlers if getattr(h, _HANDLER_MARK, False)]:
        root.removeHandler(h)
    handler = make_handler(code_version)
    setattr(handler, _HANDLER_MARK, True)
    handler.setLevel(logging.INFO)
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    for name in _PROPAGATING:
        lg = logging.getLogger(name)
        for h in [h for h in lg.handlers if name in LITELLM_LOGGERS or _marked(h)]:
            lg.removeHandler(h)
        lg.propagate = True
    for name in (*LITELLM_LOGGERS, "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    log.setLevel(logging.INFO)
    quiet_litellm()  # no-op unless litellm is already imported; never imports it (~3 s, 160 MB)


def _guard_uvicorn() -> None:
    """uvicorn's loggers keep their own handlers (no propagation to root), so give them the
    same exception rule the handler applies to everything else."""
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        if not any(isinstance(f, NoExceptionDetail) for f in lg.filters):
            lg.addFilter(NoExceptionDetail())


def configure(settings: Settings) -> None:
    """Set the HMAC key and code version, and attach the stderr handler once."""
    _guard_uvicorn()
    with _lock:
        _state["key"] = settings.uid_hmac_key.encode()
        _state["code_version"] = settings.git_sha
    _install(settings.git_sha)


def uid_hash(uid: str) -> str:
    """Keyed HMAC-SHA256 of the uid (first 16 hex chars): correlates a user, reveals nothing."""
    return hmac.new(_state["key"], uid.encode(), hashlib.sha256).hexdigest()[:16]


def emit(event: str, level: int = logging.INFO, **fields) -> None:
    """Log one line. None values are omitted; `code_version` is always added."""
    kept = {k: v for k, v in fields.items() if v is not None}
    kept.setdefault("code_version", _state["code_version"])
    log.log(level, "%s", event, extra={"fields": kept})


def failed(
    event: str, *, session_id, step, error_code, exc_class, request_id=None, run_id=None
) -> None:
    """The one `status=failed` line of a failed step or run (the alert and runbook match it)."""
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
