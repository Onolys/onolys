import pytest

from onolys_engine_core.errors import ConfigError, InputError, OnolysError


def test_error_hierarchy():
    assert issubclass(InputError, OnolysError) and issubclass(ConfigError, OnolysError)
    with pytest.raises(OnolysError):
        raise InputError("bad")


def test_run_context_defaults():
    from onolys_engine_core.context import RunContext

    ctx = RunContext(llm=object(), metrics=object(), request_id="r1")
    assert ctx.deadline is None and ctx.request_id == "r1"
