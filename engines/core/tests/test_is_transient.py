"""03-failure-policy R2/D8: `is_transient` is the LLM half of the failure taxonomy."""

import ast
from pathlib import Path

import pytest

from onolys_engine_core.llm import errors as llm_errors
from onolys_engine_core.llm.errors import (
    FixtureMiss,
    LLMBadOutput,
    LLMError,
    LLMRateLimited,
    LLMTimeout,
    LLMUnavailable,
    is_transient,
)


def _with(exc: LLMError, status=None, error_type=None) -> LLMError:
    exc.http_status = status
    exc.error_type = error_type
    return exc


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504, 529])
def test_transient_statuses(status):
    assert is_transient(_with(LLMUnavailable("x"), status))


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_permanent_statuses(status):
    assert not is_transient(_with(LLMUnavailable("x"), status))


def test_timeout_and_rate_limited_always_transient():
    assert is_transient(LLMTimeout("x"))
    assert is_transient(LLMRateLimited("x", 2.0))


def test_status_wins_over_class_name_for_unavailable():
    assert not is_transient(_with(LLMUnavailable("x"), 404, "Timeout"))


@pytest.mark.parametrize("etype", ["APIConnectionError", "Timeout", "APITimeoutError"])
def test_no_status_connection_or_timeout_type_is_transient(etype):
    assert is_transient(_with(LLMError("x"), None, etype))


def test_unavailable_without_any_fields_is_transient():
    assert is_transient(LLMUnavailable("x"))


def test_bare_llm_error_without_fields_is_not_transient():
    assert not is_transient(LLMError("x"))


def test_bad_output_and_fixture_miss_are_permanent():
    assert not is_transient(LLMBadOutput("x"))
    assert not is_transient(FixtureMiss("x"))
    assert not is_transient(_with(LLMBadOutput("x"), 503))


def test_non_llm_exception_is_not_transient():
    assert not is_transient(ValueError("x"))
    assert not is_transient(TimeoutError("x"))


def test_walks_cause_chain():
    try:
        try:
            raise _with(LLMUnavailable("x"), 503)
        except LLMError as c:
            raise RuntimeError("wrapped") from c
    except RuntimeError as e:
        assert is_transient(e)


def test_reads_only_structured_fields_not_provider_error_text():
    e = _with(LLMUnavailable("x"), 404)
    e.provider_error = "503 service unavailable timeout"
    assert not is_transient(e)


def test_module_has_no_api_imports():
    tree = ast.parse(Path(llm_errors.__file__).read_text())
    for node in ast.walk(tree):
        names = (
            [a.name for a in node.names] if isinstance(node, ast.Import)
            else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
        )
        assert not any(n.split(".")[0] in ("onolys_api", "onolys_miti") for n in names)
