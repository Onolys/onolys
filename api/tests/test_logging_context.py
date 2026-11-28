"""Ids bound in the API, worker and voice entrypoints."""

import logging

import httpx
import pytest
from fastapi import Depends, FastAPI
from log_helpers import Capture
from test_worker import SID, UID, payload, repo, runner_with  # noqa: F401

from onolys_api import logs
from onolys_api.app import RequestIdMiddleware, create_app
from onolys_api.config import Settings
from onolys_api.jobs.queue import TaskPayload
from onolys_api.jobs.worker import PermanentError
from onolys_api.repo.fake import FakeRepo
from onolys_api.storage.fake import FakeBlobStore


@pytest.fixture
def cap():
    h = Capture()
    root = logging.getLogger()
    old = root.level
    root.addHandler(h)
    root.setLevel(logging.INFO)
    yield h
    root.removeHandler(h)
    root.setLevel(old)


def by_event(cap, event):
    return [d for d in cap.out if d.get("event") == event]


async def get(app, path, **headers):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.get(path, headers=headers)


def mini_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/v1/things/{id}", dependencies=[Depends(logs.bind_session)])
    def sync_thing(id: str):  # sync on purpose: runs in a threadpool copy of the context
        logs.emit("in_sync_handler")
        return {}

    @app.get("/v1/plain")
    def plain():
        logs.emit("in_plain_handler")
        return {}

    return app


async def test_request_id_bound_for_lines_inside_the_request(cap):
    r = await get(mini_app(), "/v1/plain", **{"X-Request-ID": "req-9"})
    assert r.status_code == 200
    (line,) = by_event(cap, "in_plain_handler")
    assert line["request_id"] == "req-9"


async def test_generated_request_id_is_bound_and_matches_the_response(cap):
    r = await get(mini_app(), "/v1/plain")
    (line,) = by_event(cap, "in_plain_handler")
    assert line["request_id"] == r.headers["x-request-id"]


async def test_client_version_bound_from_header_and_sanitized(cap):
    await get(mini_app(), "/v1/plain", **{"X-Client-Version": "sha-1.2"})
    await get(mini_app(), "/v1/plain", **{"X-Client-Version": "bad value\x01<script>"})
    first, second = by_event(cap, "in_plain_handler")
    assert first["client_version"] == "sha-1.2"
    assert "client_version" not in second


async def test_context_is_clean_after_request(cap):
    await get(mini_app(), "/v1/things/" + "a" * 32, **{"X-Request-ID": "r1"})
    assert logs.snapshot() == {}


async def test_sync_endpoint_on_id_route_logs_with_session_id(cap):
    sid = "a" * 32
    await get(mini_app(), f"/v1/things/{sid}", **{"X-Request-ID": "r2"})
    (line,) = by_event(cap, "in_sync_handler")
    assert line["session_id"] == sid and line["request_id"] == "r2"


async def test_real_session_route_logs_request_line_with_session_id(cap, settings, blobs):
    app = create_app(settings, repo=FakeRepo(blobs), blobs=blobs)
    sid = "b" * 32
    await get(app, f"/v1/sessions/{sid}", **{"X-Request-ID": "r3"})
    (req,) = by_event(cap, "request")
    assert req["session_id"] == sid and req["request_id"] == "r3"


async def test_real_interview_route_binds_interview_id_as_session_id(cap, settings, blobs):
    app = create_app(settings, repo=FakeRepo(blobs), blobs=blobs)
    iid = "c" * 32
    await get(app, f"/v1/interviews/{iid}")
    (req,) = by_event(cap, "request")
    assert req["session_id"] == iid


async def test_non_hex_path_id_is_not_bound(cap):
    await get(mini_app(), "/v1/things/not%20an%20id%0A")
    (line,) = by_event(cap, "in_sync_handler")
    assert "session_id" not in line


# ---- worker ----

IDS = {"session_id": SID, "run_id": "r1", "request_id": "req-1", "step": "validate"}


def test_handle_lines_carry_all_four_ids_and_context_is_clean_after(repo, cap):  # noqa: F811
    def fn(ctx):
        logs.emit("inside_handler")

    runner = runner_with(repo, fn)
    runner.handle(payload(run_id="r1"))
    (line,) = by_event(cap, "inside_handler")
    assert {k: line[k] for k in IDS} == IDS
    assert logs.snapshot() == {}


def test_error_path_lines_carry_ids_and_context_is_clean(repo, cap):  # noqa: F811
    def boom(ctx):
        raise PermanentError("internal_error")

    runner = runner_with(repo, boom)
    runner.handle(payload(run_id="r1"))
    (line,) = by_event(cap, "step_failed")
    assert {k: line[k] for k in IDS} == IDS
    assert logs.snapshot() == {}


def test_bookkeeping_failed_and_unhandled_lines_gain_ids_through_context(repo, cap, monkeypatch):  # noqa: F811
    def boom(ctx):
        raise RuntimeError("x")

    runner = runner_with(repo, boom)
    monkeypatch.setattr(
        "onolys_api.jobs.worker.advance", lambda *a, **k: (_ for _ in ()).throw(KeyError("b"))
    )
    runner.handle(payload(run_id="r1"))
    (line,) = by_event(cap, "bookkeeping_failed")
    assert (
        line["session_id"] == SID and line["request_id"] == "req-1" and line["step"] == "validate"
    )
    assert logs.snapshot() == {}


def test_context_clean_even_if_handler_raises_base_exception(repo, cap):  # noqa: F811
    def boom(ctx):
        raise KeyboardInterrupt

    runner = runner_with(repo, boom)
    with pytest.raises(KeyboardInterrupt):
        runner.handle(payload(run_id="r1"))
    assert logs.snapshot() == {}


def test_no_handler_line_has_ids_and_context_is_clean(repo, cap):  # noqa: F811
    runner = runner_with(repo, lambda ctx: None)
    runner.handle(TaskPayload(kind="delete", uid=UID, sid=SID, request_id="req-1"))
    (line,) = by_event(cap, "no_handler")
    assert line["session_id"] == SID and line["request_id"] == "req-1"
    assert logs.snapshot() == {}


def test_interview_task_binds_interview_id_as_session_id(repo, cap):  # noqa: F811
    iid = "d" * 32

    def fn(ctx):
        logs.emit("in_sweep")

    runner = runner_with(repo, fn, kind="interview-sweep", claim=False, step=None)
    runner.handle(TaskPayload(kind="interview-sweep", uid=UID, sid=iid, request_id="rq"))
    (line,) = by_event(cap, "in_sweep")
    assert line["session_id"] == iid and line["step"] == "interview-sweep"
    assert logs.snapshot() == {}


# ---- voice ----


def test_voice_entrypoint_configures_structured_logging(blobs):
    root = logging.getLogger()
    for h in [h for h in root.handlers if getattr(h, "_onolys_json", False)]:
        root.removeHandler(h)
    assert not logs.has_handler(root)
    create_app(
        Settings(env="test", auth_mode="fake", service_mode="voice", cors_origins=()),
        repo=FakeRepo(FakeBlobStore(blobs.root if hasattr(blobs, "root") else None)),
    )
    assert logs.has_handler(root)
