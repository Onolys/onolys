import asyncio

import pytest

from onolys_engine_core import log_context as lc


def test_bind_reset_restores_prior():
    t1 = lc.bind(session_id="s1", step="a")
    t2 = lc.bind(session_id="s2")
    assert lc.snapshot() == {"session_id": "s2", "step": "a"}
    lc.reset(t2)
    assert lc.snapshot() == {"session_id": "s1", "step": "a"}
    lc.reset(t1)
    assert lc.snapshot() == {}


def test_nested_overrides_only_given_keys_and_no_leak():
    with lc.log_context(session_id="s", run_id="r", step="x"):
        with lc.log_context(step="y"):
            assert lc.snapshot() == {"session_id": "s", "run_id": "r", "step": "y"}
        assert lc.snapshot() == {"session_id": "s", "run_id": "r", "step": "x"}
    assert lc.snapshot() == {}


def test_no_leak_after_exception():
    with pytest.raises(RuntimeError):
        with lc.log_context(request_id="q"):
            raise RuntimeError
    assert lc.snapshot() == {}


def test_snapshot_omits_none():
    with lc.log_context(session_id="s", run_id=None):
        assert lc.snapshot() == {"session_id": "s"}


def test_unknown_key_rejected():
    with pytest.raises(ValueError):
        lc.bind(bogus="x")


def test_survives_asyncio_run_and_to_thread():
    async def inner():
        a = lc.snapshot()
        b = await asyncio.to_thread(lc.snapshot)
        return a, b

    with lc.log_context(session_id="s", step="z"):
        a, b = asyncio.run(inner())
    assert a == b == {"session_id": "s", "step": "z"}


def test_survives_anyio_hops():
    anyio = pytest.importorskip("anyio")

    async def inner():
        out = {}
        async with anyio.create_task_group() as tg:
            async def child():
                out["tg"] = lc.snapshot()
            tg.start_soon(child)
        out["thread"] = await anyio.to_thread.run_sync(lc.snapshot)
        return out

    with lc.log_context(run_id="r"):
        out = anyio.run(inner)
    assert out == {"tg": {"run_id": "r"}, "thread": {"run_id": "r"}}


def test_client_version_is_a_request_scoped_key():
    with lc.log_context(client_version="abc123"):
        assert lc.snapshot() == {"client_version": "abc123"}
    assert lc.snapshot() == {}
