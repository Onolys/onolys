"""Typed LLM errors. Stages decide the degraded behaviour; the client never swallows."""


class LLMError(Exception):
    """Provider fields are set by the client on provider failures (sanitized, see safe_log)."""

    provider: str | None = None
    model: str | None = None
    http_status: int | None = None
    error_type: str | None = None
    provider_error: str | None = None


class LLMTimeout(LLMError):
    """The per-call timeout elapsed."""


class LLMUnavailable(LLMError):
    """Provider down, rate limited after retry, or auth failure."""


class LLMRateLimited(LLMUnavailable):
    """HTTP 429/529. The client backs off and retries within the deadline; raised only when the
    deadline leaves no room. `retry_after` is the provider's hint in seconds, if any."""

    def __init__(self, message: str = "LLM rate limited", retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class LLMBadOutput(LLMError):
    """Output unparseable or schema-invalid after the retry."""


class FixtureMiss(LLMError):
    """No recorded fixture for this request (never falls back to the network)."""


TRANSIENT_STATUSES = frozenset({408, 429, 500, 502, 503, 504, 529})
_TRANSIENT_ERROR_TYPES = frozenset(
    {"APIConnectionError", "APITimeoutError", "Timeout", "ConnectionError", "ReadTimeout",
     "ConnectTimeout", "TimeoutError"}
)  # fmt: skip


def is_transient(exc: BaseException) -> bool:
    """True when retrying the same call may succeed.

    Looks at `exc` and its `__cause__`/`__context__` chain for the nearest `LLMError`; any
    other exception is not an LLM failure, so False. Reads only the structured fields set by the
    client (`http_status`, `error_type`), never `provider_error` text. Defaults: 529 is
    transient, 400 permanent. `LLMBadOutput` (after the engine's retry) and `FixtureMiss` are
    permanent; `LLMTimeout`/`LLMRateLimited` always transient; an `LLMUnavailable` with no
    status or type is transient (unknown provider blip).
    """
    err = _nearest_llm_error(exc)
    if err is None or isinstance(err, (LLMBadOutput, FixtureMiss)):
        return False
    if isinstance(err, (LLMTimeout, LLMRateLimited)):
        return True
    if err.http_status is not None:
        return err.http_status in TRANSIENT_STATUSES
    if err.error_type is not None:
        return err.error_type in _TRANSIENT_ERROR_TYPES
    return isinstance(err, LLMUnavailable)


def _nearest_llm_error(exc: BaseException) -> LLMError | None:
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        if isinstance(cur, LLMError):
            return cur
        seen.add(id(cur))
        cur = cur.__cause__ or cur.__context__
    return None
