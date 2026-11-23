"""One place that turns any engine exception into one public error code (SP09 R3, D2, D3).

`to_public(exc, attempt=1, stage="run") -> (code, retryable)`. Codes are existing public codes
(`onolys_api.errors.ERROR_CODES`); the user-facing text is `PUBLIC_MESSAGES[code]`, fixed text,
never the exception message. Engine failures (`AllRunsFailed`, `CodePassFailed`,
`GlobalsPassFailed`) are matched by the `code` attribute they inherit from `OnolysError`.
`stage="stt"` is the transcription path, where a transient provider error is
`upstream_unavailable` on attempt 1 and `transcription_failed` afterwards.
"""

from typing import Literal

from google.api_core import exceptions as gexc
from onolys_engine_core.errors import InputError, OnolysError
from onolys_engine_core.llm.errors import LLMError
from onolys_engine_core.validated_run import OutputInvalid
from onolys_miti.stt.google_chirp import SttProviderError

Stage = Literal["run", "stt"]

UPSTREAM = "upstream_unavailable"
DEADLINE = "deadline_exceeded"
TRANSCRIPTION = "transcription_failed"
INTERNAL = "internal_error"

PUBLIC_MESSAGES = {
    "output_invalid": "The engine returned an answer that did not match its schema.",
    "invalid_coded_span": (
        "Choose a valid coded_span within the transcript; time spans require timestamps."
    ),
    "session_too_long": (
        "The coded portion exceeds 25 minutes or 6000 words; supply a narrower coded_span."
    ),
    "invalid_parameters": "The request could not be run with this input.",
    UPSTREAM: "A service we depend on is unavailable. Run again shortly.",
    DEADLINE: "The run took too long. Run again.",
    TRANSCRIPTION: "The recording could not be transcribed. Upload a different file.",
    "no_speech": "No usable speech was found in the recording.",
    "speakers_not_separated": "The speakers could not be told apart in the recording.",
    "rate_limited": "Too many requests. Try again shortly.",
    INTERNAL: "Something went wrong on our side. Run again.",
}

# AdapterError codes that already are public codes: code -> retryable (SP04 R5)
_ADAPTER_CODES = {
    UPSTREAM: True,
    DEADLINE: True,
    "rate_limited": True,
    TRANSCRIPTION: False,
    "no_speech": False,
    "speakers_not_separated": False,
}

_GOOGLE_TRANSIENT = (
    gexc.TooManyRequests,
    gexc.ServiceUnavailable,
    gexc.InternalServerError,
    gexc.GatewayTimeout,
    gexc.DeadlineExceeded,
    gexc.Aborted,
    gexc.RetryError,
)


def _stt_transient(exc: BaseException) -> bool:
    return bool(getattr(exc, "transient", False)) or isinstance(exc, _GOOGLE_TRANSIENT)


def to_public(exc: BaseException, attempt: int = 1, stage: Stage = "run") -> tuple[str, bool]:
    """Public error code and whether another attempt may help (the caller applies the attempt
    limit). `attempt` is 1-based."""
    code, retryable = _classify(exc, stage)
    if stage == "stt" and code == UPSTREAM and attempt >= 2:
        return TRANSCRIPTION, False  # a second transient failure: ask for a different file
    return code, retryable


def _classify(exc: BaseException, stage: Stage) -> tuple[str, bool]:
    # AdapterError lives in adapters.base (imports onolys_miti only); import lazily: no cycle
    from onolys_api.adapters.base import AdapterError

    if isinstance(exc, AdapterError):
        if exc.code in _ADAPTER_CODES:
            return exc.code, _ADAPTER_CODES[exc.code]
        return INTERNAL, False
    if isinstance(exc, OutputInvalid):
        return "output_invalid", False
    if isinstance(exc, InputError):
        code = getattr(exc, "code", None)
        if code in ("invalid_coded_span", "session_too_long"):
            return code, False
        return "invalid_parameters", False
    if stage == "stt":
        if isinstance(exc, SttProviderError):
            return (UPSTREAM, True) if _stt_transient(exc) else (TRANSCRIPTION, False)
        if _stt_transient(exc):
            return UPSTREAM, True
    if isinstance(exc, _GOOGLE_TRANSIENT):  # validate/run read GCS and Firestore: a blip retries
        return UPSTREAM, True
    if isinstance(exc, LLMError):
        return _classify_llm(exc)
    if isinstance(exc, TimeoutError):
        return DEADLINE, True
    if isinstance(exc, OnolysError):
        # an engine that wrapped a provider failure (AllRunsFailed from LLMUnavailable)
        # keeps it as `__cause__`/`__context__`: map it like the direct LLM error
        cause = _llm_cause(exc)
        if cause is not None:
            return _classify_llm(cause)
        # CodePassFailed / GlobalsPassFailed / AllRunsFailed (`code = "run_failed"`): the
        # engine already halved/retried; R3 "anything else": not retried, owner alerted
        return INTERNAL, False
    return INTERNAL, False


def _llm_cause(exc: BaseException) -> LLMError | None:
    seen: set[int] = set()
    cur = exc.__cause__ or exc.__context__
    while cur is not None and id(cur) not in seen:
        if isinstance(cur, LLMError):
            return cur
        seen.add(id(cur))
        cur = cur.__cause__ or cur.__context__
    return None


def _classify_llm(exc: LLMError) -> tuple[str, bool]:
    # unavailable, timeout, rate limited, bad output (D3): all retryable; FixtureMiss is a
    # test-only miss and never a provider outage
    if type(exc).__name__ == "FixtureMiss":
        return INTERNAL, False
    return UPSTREAM, True
