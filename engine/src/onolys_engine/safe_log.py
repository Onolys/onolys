"""Engine logging: `log_event` and the static `LOG_FIELDS`.

The engine only names the fields it emits; the PHI allowlist (these names plus the API's own),
text-like name blocking, value caps and JSON output are enforced by the API's log handler.
"""

import logging
import re

log = logging.getLogger("miti")

# Fields the engine itself emits (ids, counts, statuses, provider error facts). Never text.
LOG_FIELDS: frozenset[str] = frozenset({
    "request_id", "session_id", "run_id", "step", "status", "outcome",
    "total_ms", "calls", "calls_ok", "input_tokens", "output_tokens",
    "cache_read_tokens", "cache_write_tokens", "models", "retries", "failure", "exc_class",
    "language", "speakers",
    "run_index", "n_runs", "runs_ok", "stage", "stage_status",
    "provider", "model", "http_status", "error_type", "provider_error",
})  # fmt: skip

PROVIDER_ERROR_MAX_CHARS = 300

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
    return out[:PROVIDER_ERROR_MAX_CHARS]


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    """Log one event with ids, counts and statuses only (``fields`` ride on ``record.fields``)."""
    log.log(level, "%s", event, extra={"fields": fields})
