"""SP09 Task 1 (R3, D2, D3, AC2): one table turns any engine exception into one public code."""

import json
import logging

import pytest
import test_run
import test_worker
from google.api_core.exceptions import (
    FailedPrecondition,
    InvalidArgument,
    NotFound,
    PermissionDenied,
    ServiceUnavailable,
    TooManyRequests,
    Unauthenticated,
)
from onolys_engine_core.errors import (
    ConfigError,
    InputError,
    InvalidCodedSpan,
    OnolysError,
    SessionTooLong,
)
from onolys_engine_core.llm.errors import (
    FixtureMiss,
    LLMError,
    LLMBadOutput,
    LLMRateLimited,
    LLMTimeout,
    LLMUnavailable,
)
from onolys_miti.code_pass import CodePassFailed
from onolys_miti.globals_pass import GlobalsPassFailed
from onolys_miti.run import AllRunsFailed
from onolys_miti.stt.google_chirp import SttProviderError
from test_logging import failed
from test_run import swap_eval
from test_worker import SID, payload, runner_with

from onolys_api.adapters import AdapterError, FakeEvaluation
from onolys_api.adapters.error_map import KIND_BY_CODE, PUBLIC_MESSAGES, classify, to_public
from onolys_api.errors import ERROR_CODES
from onolys_api.jobs.worker import MAX_ATTEMPTS

# env is parametrized [fake, firestore]; [firestore] twins run only for tests/params marked
# pytest.mark.firestore_smoke (see conftest.py).
env = test_run.env
repo = test_worker.repo
SECRET = "SECRET-transcript-text"
UPSTREAM, DEADLINE, TRANSCRIBE = "upstream_unavailable", "deadline_exceeded", "transcription_failed"


class UnknownInputError(InputError):
    code = SECRET


# (id, exception factory, stage, attempt, public code, retryable)
CASES = [
    ("input", lambda: InputError(SECRET), "run", 1, "invalid_parameters", False),
    ("input_unknown_code", lambda: UnknownInputError(SECRET), "run", 1, "invalid_parameters", False),
    ("invalid_span", lambda: InvalidCodedSpan(SECRET), "run", 1, "invalid_coded_span", False),
    ("too_long", lambda: SessionTooLong(SECRET), "run", 1, "session_too_long", False),
    ("config", lambda: ConfigError(SECRET), "run", 1, "internal_error", False),
    ("llm_unavailable", lambda: LLMUnavailable(SECRET), "run", 1, UPSTREAM, True),
    ("llm_timeout", lambda: LLMTimeout(SECRET), "run", 1, UPSTREAM, True),
    ("llm_rate_limited", lambda: LLMRateLimited(SECRET, 3.0), "run", 1, UPSTREAM, True),
    ("llm_bad_output", lambda: LLMBadOutput(SECRET), "run", 1, "internal_error", False),
    ("llm_fixture_miss", lambda: FixtureMiss(SECRET), "run", 1, "internal_error", False),
    ("llm_bad_output_a2", lambda: LLMBadOutput(SECRET), "run", 2, "internal_error", False),
    ("deadline_builtin", lambda: TimeoutError(SECRET), "run", 1, DEADLINE, True),
    ("code_pass_failed", lambda: CodePassFailed(SECRET), "run", 1, "internal_error", False),
    ("globals_pass_failed", lambda: GlobalsPassFailed(SECRET), "run", 1, "internal_error", False),
    ("all_runs_failed", lambda: AllRunsFailed(SECRET), "run", 1, "internal_error", False),
    ("unknown", lambda: ValueError(SECRET), "run", 1, "internal_error", False),
    ("onolys_base", lambda: OnolysError(SECRET), "run", 1, "internal_error", False),
    ("adapter_upstream", lambda: AdapterError(UPSTREAM), "run", 1, UPSTREAM, True),
    ("adapter_code", lambda: AdapterError("code_failed"), "run", 1, "internal_error", False),
    ("run_google_transient", lambda: ServiceUnavailable(SECRET), "run", 1, UPSTREAM, True),
    ("run_google_429", lambda: TooManyRequests(SECRET), "run", 1, UPSTREAM, True),
    ("run_google_transient_last", lambda: ServiceUnavailable(SECRET), "run", 2, UPSTREAM, True),
    ("stt_transient_a1", lambda: ServiceUnavailable(SECRET), "stt", 1, UPSTREAM, True),
    ("stt_429_a1", lambda: TooManyRequests(SECRET), "stt", 1, UPSTREAM, True),
    ("stt_transient_a2", lambda: ServiceUnavailable(SECRET), "stt", 2, UPSTREAM, True),
    ("stt_flagged_a1", lambda: _transient_provider_error(), "stt", 1, UPSTREAM, True),
    ("stt_flagged_a2", lambda: _transient_provider_error(), "stt", 2, UPSTREAM, True),
    ("stt_permanent", lambda: SttProviderError(SECRET), "stt", 1, TRANSCRIBE, False),
    ("stt_permanent_a2", lambda: SttProviderError(SECRET), "stt", 2, TRANSCRIBE, False),
    ("stt_adapter_code", lambda: AdapterError(TRANSCRIBE), "stt", 1, TRANSCRIBE, False),
    ("stt_adapter_upstream", lambda: AdapterError(UPSTREAM), "stt", 1, UPSTREAM, True),
    ("stt_adapter_upstream_a2", lambda: AdapterError(UPSTREAM), "stt", 2, UPSTREAM, True),
    ("stt_unknown", lambda: ValueError(SECRET), "stt", 1, "internal_error", False),
    # transcript outcomes carried by adapter codes (SP04 R4 checks)
    ("no_speech", lambda: AdapterError("no_speech"), "stt", 1, "no_speech", False),
    ("not_separated", lambda: AdapterError("speakers_not_separated"), "stt", 1,
     "speakers_not_separated", False),
]  # fmt: skip


def _chained(outer, cause):
    try:
        raise cause
    except Exception as c:
        try:
            raise outer from c
        except Exception as e:
            return e


def _context_only(outer, inner):
    try:
        raise inner
    except Exception:
        try:
            raise outer  # implicit __context__, no explicit cause
        except Exception as e:
            return e


CASES += [
    ("all_runs_from_llm_unavailable",
     lambda: _chained(AllRunsFailed(SECRET), LLMUnavailable(SECRET)), "run", 1, UPSTREAM, True),
    ("all_runs_from_llm_timeout",
     lambda: _chained(AllRunsFailed(SECRET), LLMTimeout(SECRET)), "run", 1, UPSTREAM, True),
    ("all_runs_from_fixture_miss",
     lambda: _chained(AllRunsFailed(SECRET), FixtureMiss(SECRET)), "run", 1,
     "internal_error", False),
    ("all_runs_from_onolys_base",
     lambda: _chained(AllRunsFailed(SECRET), OnolysError(SECRET)), "run", 1,
     "internal_error", False),
    ("all_runs_context_llm",
     lambda: _context_only(AllRunsFailed(SECRET), LLMUnavailable(SECRET)), "run", 1, UPSTREAM, True),
    ("all_runs_no_cause", lambda: AllRunsFailed(SECRET), "run", 1, "internal_error", False),
]  # fmt: skip


def _transient_provider_error() -> SttProviderError:
    e = SttProviderError(SECRET)
    e.transient = True  # type: ignore[attr-defined]
    return e


IDS = [c[0] for c in CASES]


@pytest.mark.parametrize("make,stage,attempt,code,retryable", [c[1:] for c in CASES], ids=IDS)
def test_to_public_table(make, stage, attempt, code, retryable):
    assert to_public(make(), attempt=attempt, stage=stage) == (code, retryable)


def test_every_mapped_code_is_a_public_code_with_fixed_message():
    codes = {c[4] for c in CASES}
    assert codes <= set(ERROR_CODES)
    for code in codes:
        assert PUBLIC_MESSAGES[code] and SECRET not in PUBLIC_MESSAGES[code]


def test_message_is_never_the_exception_message():
    code, _ = to_public(InputError(SECRET))
    assert SECRET not in PUBLIC_MESSAGES[code]


# ---- through SP04's handler wrapper: one `status=failed` line, exc_class only, no text ----


@pytest.mark.parametrize("make,stage,attempt,code,retryable", [c[1:] for c in CASES], ids=IDS)
def test_wrapper_records_code_and_one_failed_line(repo, caplog, make, stage, attempt, code,
                                                  retryable):  # fmt: skip
    exc = make()
    step = "transcribe" if stage == "stt" else "validate"

    def fn(ctx):
        raise exc

    runner = runner_with(repo, fn, kind=step if stage == "stt" else "validate")
    caplog.clear()
    with caplog.at_level(logging.INFO):
        r = runner.handle(payload(step if stage == "stt" else "validate"), retry_count=attempt - 1)
    last = attempt >= MAX_ATTEMPTS
    if retryable and not last:
        assert (r.status_code, r.outcome) == (503, "retry") and failed(caplog) == []
        return
    assert (r.status_code, r.outcome) == (200, "failed")
    s = repo.get_session(test_worker.UID, SID)
    assert s.state == "failed" and s.error.code == code
    (f,) = failed(caplog)
    assert (f["error_code"], f["exc_class"], f["request_id"]) == (code, type(exc).__name__, "req-1")
    assert SECRET not in caplog.text and SECRET not in s.model_dump_json()
    assert SECRET not in json.dumps(repo.get_status(test_worker.UID, SID).model_dump(mode="json"))


# ---- the run path: stubbed engine raises the engine class; API body carries no message ----


@pytest.mark.parametrize(
    "make,code",
    [
        (lambda: InputError(SECRET), "invalid_parameters"),
        (lambda: AllRunsFailed(SECRET), "internal_error"),
        pytest.param(lambda: LLMUnavailable(SECRET), UPSTREAM, marks=pytest.mark.firestore_smoke),
        (lambda: LLMBadOutput(SECRET), "internal_error"),
        (lambda: CodePassFailed(SECRET), "internal_error"),
        (lambda: TimeoutError(SECRET), DEADLINE),
    ],
    ids=["input", "all_runs", "llm", "bad_output", "code_pass", "deadline"],
)
async def test_stubbed_engine_failure_maps_through_run_and_status_body(env, caplog, make, code):
    class Boom(FakeEvaluation):
        async def run(self, *a, **kw):
            raise make()

    swap_eval(env, Boom())
    with caplog.at_level(logging.INFO):
        sid = await env.finished()
    s = env.repo.get_session(env.uid, sid)
    assert s.state == "failed" and s.error.code == code
    (run,) = env.repo.list_runs(env.uid, sid)
    assert run.status == "failed" and run.error == code
    (f,) = failed(caplog)
    assert (f["error_code"], f["exc_class"]) == (code, type(make()).__name__)
    assert f["request_id"] and f["run_id"] == run.run_id
    body = (await env.c.get(f"/v1/sessions/{sid}", headers=env.h)).text
    assert SECRET not in body and SECRET not in caplog.text
    assert env.counters()[0] == 0  # slot released once


def test_output_invalid_has_a_fixed_public_message_and_never_retries():
    from onolys_engine_core.validate import ValidationIssue
    from onolys_engine_core.validated_run import OutputInvalid

    from onolys_api.adapters.error_map import KIND_BY_CODE, PUBLIC_MESSAGES, classify, to_public
    from onolys_api.errors import ERROR_CODES

    failure = OutputInvalid(1, [ValidationIssue(path="/field", message="invalid type")])
    assert to_public(failure) == ("output_invalid", False)
    assert "output_invalid" in ERROR_CODES
    assert PUBLIC_MESSAGES["output_invalid"] == "The engine returned an answer that did not match its schema."


# ---- 03-failure-policy R1: kind per source, stages validate/stt/run ----

T, P, U = "transient", "permanent_internal", "user_file"
INT = "internal_error"


def _llm(status=None, etype=None, cls=LLMUnavailable):
    e = cls(SECRET)
    e.http_status, e.error_type = status, etype
    e.provider_error = "503 timeout overloaded " + SECRET  # never read
    return e


KIND_CASES = [
    ("timeout", lambda: LLMTimeout(SECRET), UPSTREAM, T),
    ("rate_limited", lambda: LLMRateLimited(SECRET), UPSTREAM, T),
    *[(f"llm_{n}", (lambda n=n: _llm(n)), UPSTREAM, T) for n in (408, 429, 500, 502, 503, 504, 529)],
    ("llm_conn", lambda: _llm(None, "APIConnectionError", LLMError), UPSTREAM, T),
    ("llm_timeout_type", lambda: _llm(None, "Timeout", LLMError), UPSTREAM, T),
    *[(f"llm_{n}", (lambda n=n: _llm(n)), INT, P) for n in (400, 401, 403, 404)],
    ("fixture_miss", lambda: FixtureMiss(SECRET), INT, P),
    ("bad_output", lambda: LLMBadOutput(SECRET), INT, P),
    ("output_invalid", lambda: _output_invalid(), "output_invalid", P),
    ("google_transient", lambda: ServiceUnavailable(SECRET), UPSTREAM, T),
    ("google_429", lambda: TooManyRequests(SECRET), UPSTREAM, T),
    ("google_perm_denied", lambda: PermissionDenied(SECRET), INT, P),
    ("google_unauth", lambda: Unauthenticated(SECRET), INT, P),
    ("google_not_found", lambda: NotFound(SECRET), INT, P),
    ("google_precondition", lambda: FailedPrecondition(SECRET), INT, P),
    ("timeout_builtin", lambda: TimeoutError(SECRET), DEADLINE, T),
    ("adapter_upstream", lambda: AdapterError(UPSTREAM), UPSTREAM, T),
    ("adapter_deadline", lambda: AdapterError(DEADLINE), DEADLINE, T),
    ("adapter_rate", lambda: AdapterError("rate_limited"), "rate_limited", T),
    ("adapter_unknown", lambda: AdapterError("zzz"), INT, P),
    ("unknown", lambda: ValueError(SECRET), INT, P),
    ("all_runs_perm_cause", lambda: _chained(AllRunsFailed(SECRET), _llm(404)), INT, P),
    ("all_runs_transient_cause", lambda: _chained(AllRunsFailed(SECRET), _llm(503)), UPSTREAM, T),
    ("all_runs_no_cause", lambda: AllRunsFailed(SECRET), INT, P),
    ("code_pass", lambda: CodePassFailed(SECRET), INT, P),
    ("globals_pass", lambda: GlobalsPassFailed(SECRET), INT, P),
    ("input", lambda: InputError(SECRET), "invalid_parameters", U),
    ("span", lambda: InvalidCodedSpan(SECRET), "invalid_coded_span", U),
    ("too_long", lambda: SessionTooLong(SECRET), "session_too_long", U),
    ("no_speech", lambda: AdapterError("no_speech"), "no_speech", U),
    ("not_separated", lambda: AdapterError("speakers_not_separated"), "speakers_not_separated", U),
    ("adapter_transcription", lambda: AdapterError(TRANSCRIBE), TRANSCRIBE, U),
]  # fmt: skip


def _output_invalid():
    from onolys_engine_core.validate import ValidationIssue
    from onolys_engine_core.validated_run import OutputInvalid

    return OutputInvalid(1, [ValidationIssue(path="/f", message="bad")])


@pytest.mark.parametrize("stage", ["validate", "stt", "run"])
@pytest.mark.parametrize("make,code,kind", [c[1:] for c in KIND_CASES], ids=[c[0] for c in KIND_CASES])
def test_classify_table(make, code, kind, stage):
    f = classify(make(), stage)
    assert (f.code, f.kind) == (code, kind)
    assert KIND_BY_CODE[f.code] == kind


@pytest.mark.parametrize("stage", ["validate", "stt", "run"])
def test_classify_never_reads_provider_error_text(stage):
    assert classify(_llm(404), stage).kind == P  # provider_error says "503 timeout"


def test_stt_stage_kinds():
    assert classify(SttProviderError(SECRET), "stt") == ("transcription_failed", U)
    assert classify(InvalidArgument(SECRET), "stt") == ("transcription_failed", U)
    assert classify(ServiceUnavailable(SECRET), "stt") == (UPSTREAM, T)
    assert classify(_transient_provider_error(), "stt") == (UPSTREAM, T)


def test_second_transient_stt_stays_upstream_unavailable_d6():
    # classify has no attempt: the second failure is classified exactly like the first
    assert to_public(ServiceUnavailable(SECRET), 2, "stt") == (UPSTREAM, True)
    assert classify(ServiceUnavailable(SECRET), "stt") == (UPSTREAM, T)
    assert classify(_transient_provider_error(), "stt") == (UPSTREAM, T)
    assert classify(SttProviderError(SECRET), "stt") == ("transcription_failed", U)


def test_kind_by_code_covers_every_public_message_code():
    assert set(PUBLIC_MESSAGES) <= set(KIND_BY_CODE)
    assert set(KIND_BY_CODE.values()) <= {T, P, U}
