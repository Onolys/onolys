"""One place that turns any engine exception into one public error code and kind (SP09 R3,
03-failure-policy R1).

`classify(exc, stage) -> Failure(code, kind)`; `to_public(exc, attempt=1, stage="run") ->
(code, retryable)` is a thin wrapper (retryable == kind is transient). Kinds: `transient` (a blip),
`permanent_internal` (our fault), `user_file` (the input's fault). Reads only structured fields
(`LLMError.http_status`/`error_type`, via `is_transient`), never exception or `provider_error`
text. Codes are existing public codes (`onolys_api.errors.ERROR_CODES`); the user-facing text is
`PUBLIC_MESSAGES[code]`, fixed text, never the exception message. Engine failures
(`AllRunsFailed`, `CodePassFailed`, `GlobalsPassFailed`) are matched by the `code` attribute they inherit from `OnolysError`.
`stage="stt"` is the transcription path; a transient provider error stays `upstream_unavailable`
on every attempt (D6: the file is not at fault).
"""

from typing import Literal, NamedTuple

from google.api_core import exceptions as gexc
from onolys_engine_core.errors import InputError, OnolysError
from onolys_engine_core.llm.errors import LLMError, is_transient
from onolys_engine_core.validated_run import OutputInvalid
from onolys_miti.stt.google_chirp import SttProviderError

Stage = Literal["validate", "stt", "run"]
Kind = Literal["transient", "permanent_internal", "user_file"]
TRANSIENT, PERMANENT, USER_FILE = "transient", "permanent_internal", "user_file"


class Failure(NamedTuple):
    code: str
    kind: Kind


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

# public code -> kind (one table; fills `SessionError.kind` at every write site)
KIND_BY_CODE: dict[str, Kind] = {
    UPSTREAM: TRANSIENT,
    DEADLINE: TRANSIENT,
    "rate_limited": TRANSIENT,
    INTERNAL: PERMANENT,
    "output_invalid": PERMANENT,
    "invalid_coded_span": USER_FILE,
    "session_too_long": USER_FILE,
    "invalid_parameters": USER_FILE,
    TRANSCRIPTION: USER_FILE,
    "no_speech": USER_FILE,
    "speakers_not_separated": USER_FILE,
}


# Validate file-check codes (03-failure-policy R11): an UPLOAD failure, never a session failure,
# so they are not in KIND_BY_CODE. They are kept here for old `failed` docs that carry one.
UPLOAD_FAILURE_CODES = frozenset(
    {"audio_unreadable", "audio_too_large", "unsupported_audio", "audio_too_long",
     "interview_too_long"}
)  # fmt: skip


def kind_for_code(code: str | None) -> Kind:
    """The kind of a stored error code; an unknown or missing code is `permanent_internal`
    (03-failure-policy R6): never offer a retry that cannot help."""
    if code in UPLOAD_FAILURE_CODES:
        return USER_FILE  # an old failed doc: the file was at fault
    return KIND_BY_CODE.get(code or "", PERMANENT)


# AdapterError codes that already are public codes
_ADAPTER_CODES = frozenset(
    {UPSTREAM, DEADLINE, "rate_limited", TRANSCRIPTION, "no_speech", "speakers_not_separated"}
)

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


def _failure(code: str) -> Failure:
    return Failure(code, KIND_BY_CODE[code])


def to_public(exc: BaseException, attempt: int = 1, stage: Stage = "run") -> tuple[str, bool]:
    """Public error code and whether another attempt may help (the caller applies the attempt
    limit). `attempt` is kept for the callers and no longer changes the result (D6)."""
    f = classify(exc, stage)
    return f.code, f.kind == TRANSIENT


def classify(exc: BaseException, stage: Stage = "run") -> Failure:
    # AdapterError lives in adapters.base (imports onolys_miti only); import lazily: no cycle
    from onolys_api.adapters.base import AdapterError

    if isinstance(exc, AdapterError):
        return _failure(exc.code if exc.code in _ADAPTER_CODES else INTERNAL)
    if isinstance(exc, OutputInvalid):
        return _failure("output_invalid")
    if isinstance(exc, InputError):
        code = getattr(exc, "code", None)
        if code in ("invalid_coded_span", "session_too_long"):
            return _failure(code)
        return _failure("invalid_parameters")
    if stage == "stt":
        if isinstance(exc, SttProviderError):
            return _failure(UPSTREAM if _stt_transient(exc) else TRANSCRIPTION)
        if _stt_transient(exc):
            return _failure(UPSTREAM)
        if isinstance(exc, gexc.InvalidArgument):
            return _failure(TRANSCRIPTION)
    if isinstance(exc, _GOOGLE_TRANSIENT):  # validate/run read GCS and Firestore: a blip retries
        return _failure(UPSTREAM)
    if isinstance(exc, LLMError):
        return _classify_llm(exc)
    if isinstance(exc, TimeoutError):
        return _failure(DEADLINE)
    if isinstance(exc, OnolysError):
        # an engine that wrapped a provider failure (AllRunsFailed from LLMUnavailable)
        # keeps it as `__cause__`/`__context__`: classify it like the direct LLM error
        cause = _llm_cause(exc)
        if cause is not None:
            return _classify_llm(cause)
        # CodePassFailed / GlobalsPassFailed / AllRunsFailed without a provider cause
        return _failure(INTERNAL)
    return _failure(INTERNAL)


def _llm_cause(exc: BaseException) -> LLMError | None:
    seen: set[int] = set()
    cur = exc.__cause__ or exc.__context__
    while cur is not None and id(cur) not in seen:
        if isinstance(cur, LLMError):
            return cur
        seen.add(id(cur))
        cur = cur.__cause__ or cur.__context__
    return None


def _classify_llm(exc: LLMError) -> Failure:
    # status/type rules live in engine-core `is_transient`; FixtureMiss/LLMBadOutput are permanent
    return _failure(UPSTREAM if is_transient(exc) else INTERNAL)
