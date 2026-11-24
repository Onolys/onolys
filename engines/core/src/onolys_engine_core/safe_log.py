"""PHI-safe logging: an allowlist of field names; text-like names are always dropped."""

import logging
import re

log = logging.getLogger("miti")


def setup_logging(level: str = "INFO") -> None:
    """Standalone use (no `configure_logging`): one JSON stderr handler on the miti logger."""
    from onolys_engine_core.json_logging import has_json_handler, make_handler  # noqa: PLC0415

    log.setLevel(level)
    if not any(getattr(h, "_miti", False) for h in log.handlers) and not has_json_handler(
        logging.getLogger()
    ):
        h = make_handler()
        h._miti = True
        log.addHandler(h)


# Generic base allowlist; engines add theirs via register_fields().
# Audio URIs, transcript text and ratings are deliberately never loggable.
ALLOWED_FIELDS: set[str] = {
    "request_id",
    "session_id",
    "run_id",
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
