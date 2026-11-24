"""One JSON log shape for our code, miti, LiteLLM and other libraries (Cloud Logging keys).

``ContextFilter`` (on the handler) copies the bound ids onto the record; ``JsonFormatter`` merges
them with a record's explicit ``fields`` (explicit wins). ``configure_logging`` installs one
stderr handler on the root logger, so every logger propagates to it and no line is duplicated.
"""

from __future__ import annotations

import json
import logging
import os
import sys

from onolys_engine_core.log_context import snapshot
from onolys_engine_core.safe_log import safe_fields

MAX_MESSAGE_CHARS = 300
_HANDLER_MARK = "_onolys_json"
_PER_LOGGER_MARKS = ("_miti", "_onolys")
_PROPAGATING = (
    "miti", "onolys_api.events", "litellm", "LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "httpx",
)  # fmt: skip
_LITELLM_LOGGERS = ("litellm", "LiteLLM", "LiteLLM Router", "LiteLLM Proxy")
FIRST_PARTY_PREFIXES = ("onolys", "miti")  # our loggers: INFO passes; all others need WARNING


class StderrHandler(logging.StreamHandler):
    """Writes to whatever sys.stderr is at emit time (survives stream swaps)."""

    def __init__(self) -> None:
        super().__init__(sys.stderr)

    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, _value) -> None:
        pass


class ContextFilter(logging.Filter):
    """Copy the bound log ids onto each record as ``record.ctx``. Attach to a handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.ctx = snapshot()
        return True


class FirstPartyInfoFilter(logging.Filter):
    """Third-party records need WARNING+; our own loggers (``onolys*``, ``miti*``) pass at INFO.

    Keeps library chatter (``google_genai.*``, ``httpx`` request URLs) out of the logs.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.WARNING or record.name.startswith(FIRST_PARTY_PREFIXES)


class NoExceptionDetail(logging.Filter):
    """Reduce a record carrying an exception to its class name (PRD R5, S1).

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


def _one_line(text: str) -> str:
    return " ".join(str(text).split())[:MAX_MESSAGE_CHARS]


class JsonFormatter(logging.Formatter):
    """``{severity, message, event, <allowlisted fields>, code_version, revision}`` on one line.

    Records from ``log_event`` / ``logs.emit`` carry ``record.fields``; any other record (third
    party or plain) gets ``logger`` instead of ``event``. Exceptions are reduced to their class
    name (``exc_class``); tracebacks and exception text are never rendered.
    """

    def __init__(self, code_version: str = "dev") -> None:
        super().__init__()
        self.code_version = code_version

    def format(self, record: logging.LogRecord) -> str:
        fields = getattr(record, "fields", None)
        msg = _one_line(record.getMessage())
        out: dict = {"severity": record.levelname, "message": msg}
        if fields is not None:
            out["event"] = msg
        else:
            out["logger"] = record.name
        extra = {**getattr(record, "ctx", {}), **safe_fields(fields or {})}
        if exc_class := getattr(record, "exc_class", None):
            extra.setdefault("exc_class", exc_class)
        elif record.exc_info or record.exc_text:  # record that skipped NoExceptionDetail
            exc = record.exc_info[0] if record.exc_info else None
            extra.setdefault("exc_class", exc.__name__ if exc else "Exception")
        extra = {k: v for k, v in extra.items() if v is not None}
        extra.setdefault("code_version", self.code_version)
        if revision := os.environ.get("K_REVISION"):
            extra.setdefault("revision", revision)
        out.update(extra)
        return json.dumps(out)


def render(record: logging.LogRecord) -> str:
    """The JSON line a record would produce (for tests asserting on formatted output)."""
    return JsonFormatter().format(record)


def make_handler(code_version: str = "dev") -> logging.Handler:
    h = StderrHandler()
    h.addFilter(NoExceptionDetail())
    h.addFilter(FirstPartyInfoFilter())
    h.addFilter(ContextFilter())
    h.setFormatter(JsonFormatter(code_version))
    return h


def has_json_handler(logger: logging.Logger) -> bool:
    return any(getattr(h, _HANDLER_MARK, False) for h in logger.handlers)


def configure_logging(settings) -> None:
    """Install the one JSON handler on root; route miti, events, LiteLLM and httpx through it."""
    root = logging.getLogger()
    for h in [h for h in root.handlers if getattr(h, _HANDLER_MARK, False)]:
        root.removeHandler(h)
    handler = make_handler(getattr(settings, "git_sha", "dev"))
    setattr(handler, _HANDLER_MARK, True)
    handler.setLevel(logging.INFO)
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    for name in _PROPAGATING:
        lg = logging.getLogger(name)
        for h in [h for h in lg.handlers if name in _LITELLM_LOGGERS or _marked(h)]:
            lg.removeHandler(h)
        lg.propagate = True
    for name in (*_LITELLM_LOGGERS, "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("onolys_api.events").setLevel(logging.INFO)
    quiet_litellm()  # no-op unless litellm is already imported; never imports it (~3 s, 160 MB)


def quiet_litellm() -> None:
    """Strip LiteLLM's own stderr handlers and pin its loggers to WARNING. Idempotent.

    Call right after a lazy ``import litellm`` (it adds handlers and may reset levels at
    import). Does nothing while litellm is not imported, so api/voice never pay for it.
    """
    os.environ.pop("LITELLM_LOG", None)
    litellm = sys.modules.get("litellm")
    if litellm is None:
        return
    litellm.suppress_debug_info = True
    for name in _LITELLM_LOGGERS:
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.propagate = True
        lg.setLevel(logging.WARNING)


def _marked(handler: logging.Handler) -> bool:
    return any(getattr(handler, m, False) for m in _PER_LOGGER_MARKS)
