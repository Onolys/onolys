"""PHI-safe logging: an allowlist of field names; text-like names are always dropped."""

import logging
import re
import sys

log = logging.getLogger("miti")


class _StderrHandler(logging.StreamHandler):
    """Writes to whatever sys.stderr is at emit time (survives stream swaps)."""

    _miti = True

    def __init__(self) -> None:
        super().__init__(sys.stderr)

    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, _value) -> None:
        pass


class _FieldsFormatter(logging.Formatter):
    """Interim text formatter: appends `extra["fields"]` as k=v (replaced by the JSON formatter)."""

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        fields = getattr(record, "fields", None)
        if fields:
            line += " " + " ".join(f"{k}={v!r}" for k, v in sorted(fields.items()))
        return line.replace("\r", " ").replace("\n", " ") if fields else line


def setup_logging(level: str = "INFO") -> None:
    """Attach one stderr handler to the miti logger; safe to call repeatedly."""
    log.setLevel(level)
    if not any(getattr(h, "_miti", False) for h in log.handlers):
        h = _StderrHandler()
        h.setFormatter(_FieldsFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        log.addHandler(h)


# Generic base allowlist; engines add theirs via register_fields().
# Audio URIs, transcript text and ratings are deliberately never loggable.
ALLOWED_FIELDS: set[str] = {
    "request_id",
    "status",
    "outcome",
    "total_ms",
    "calls",
    "calls_ok",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "models",
    "retries",
    "failure",
    "exc_class",
    "audio_ms",
    "stt_provider",
    "stt_model",
    "language",
    "speakers",
    "job_id",
    "step",
    # provider errors (SP02 R8)
    "provider",
    "model",
    "http_status",
    "error_type",
    "provider_error",
    # interview audio check (R12) and version fields (R13)
    "interview_id",
    "uploaded_s",
    "relay_s",
    "diff_s",
    "threshold_s",
    "result",
    "code_version",
    "revision",
    "relay_version",
    "relay_revision",
    "web_version",
    "user_agent",
    "recorder_mime",
    "audio_engine",
    "audio_format",
    "audio_codec",
    "audio_streams",
}


def register_fields(fields: frozenset[str] | set[str]) -> None:
    """Add engine-specific loggable field names (blocked name parts still always drop)."""
    ALLOWED_FIELDS.update(fields)


_BLOCKED_PARTS = ("text", "body", "transcript", "excerpt", "message")


def _blocked(name: str) -> bool:
    # body_bytes is a size, not content
    return name != "body_bytes" and any(p in name for p in _BLOCKED_PARTS)


MAX_VALUE_CHARS = 200
FIELD_CAPS: dict[str, int] = {"provider_error": 300}


def clean_value(name: str, value):
    """Numbers/bools as is; everything else a string capped per field (default MAX_VALUE_CHARS)."""
    if isinstance(value, bool | int | float):
        return value
    return str(value)[: FIELD_CAPS.get(name, MAX_VALUE_CHARS)]


_ECHO_MARKERS = ("Received Messages=", "Invalid Message passed in")
_CREDENTIALS = (
    re.compile(r"(?i)\bbearer\s+[^\s\"',;]+"),
    re.compile(r"(?i)\b((?:api[_-]?)?key)=[^\s&\"',;]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
)
_QUOTED = re.compile(r"\"[^\"]{21,}\"|'[^']{21,}'|`[^`]{21,}`")


def sanitize_provider_text(text) -> str:
    """First line only; echo markers cut; credentials and long quoted spans redacted; 300 chars."""
    out = (str(text).strip().splitlines() or [""])[0]
    for marker in _ECHO_MARKERS:
        out = out.split(marker, 1)[0]
    out = _CREDENTIALS[0].sub("Bearer <redacted>", out)
    out = _CREDENTIALS[1].sub(r"\1=<redacted>", out)
    out = _CREDENTIALS[2].sub("<redacted>", out)
    out = _QUOTED.sub('"<redacted>"', out)
    return out[: FIELD_CAPS["provider_error"]]


def safe_fields(fields: dict) -> dict:
    """Only allowlisted, non-text-like names survive (for callers that format their own line)."""
    return {k: v for k, v in fields.items() if k in ALLOWED_FIELDS and not _blocked(k)}


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    kept = {k: clean_value(k, v) for k, v in safe_fields(fields).items()}
    log.log(level, "%s", event, extra={"fields": kept})
