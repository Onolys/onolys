"""End-to-end log guards.

Everything goes through the real wiring: `configure_logging` installs the root handler, and the
assertions read the JSON lines that actually reach stderr (not caplog.text).
"""

import asyncio
import json
import logging
from types import SimpleNamespace

import httpx
import pytest
from fastapi import Depends, FastAPI
from onolys_engine_core.json_logging import configure_logging
from onolys_engine_core.llm import LiteLLMClient, LLMConfig, LLMRequest, LLMUnavailable
from onolys_engine_core.llm.routes import Route
from onolys_engine_core.safe_log import log_event
from test_worker import SID, UID, payload, repo, runner_with  # noqa: F401

from onolys_api import logs
from onolys_api.app import RequestIdMiddleware
from onolys_api.jobs.queue import TaskPayload

SENTINEL = "SENTINEL-PHI-7731"
IDS = ("session_id", "run_id", "step", "request_id")


@pytest.fixture
def stderr_lines(capsys, monkeypatch):
    monkeypatch.delenv("K_REVISION", raising=False)
    root = logging.getLogger()
    saved_root = (list(root.handlers), root.level)
    names = ("miti", "onolys_api.events", "litellm", "LiteLLM", "LiteLLM Router", "LiteLLM Proxy")
    saved = {n: (list(logging.getLogger(n).handlers), logging.getLogger(n).level,
                 logging.getLogger(n).propagate) for n in names}  # fmt: skip
    configure_logging(SimpleNamespace(git_sha="e2e"))
    capsys.readouterr()

    def lines() -> list[dict]:
        return [json.loads(x) for x in capsys.readouterr().err.splitlines() if x]

    yield lines
    root.handlers[:], root.level = saved_root
    for n, (h, lvl, p) in saved.items():
        lg = logging.getLogger(n)
        lg.handlers[:], lg.level, lg.propagate = h, lvl, p


def test_worker_task_every_line_has_four_ids(repo, stderr_lines):  # noqa: F811
    def fn(ctx):
        log_event("from_miti", calls=1)
        logging.getLogger("litellm").warning("plain litellm warning")
        logs.emit("from_api_emit")

    runner_with(repo, fn).handle(payload(run_id="r1"))
    out = stderr_lines()
    seen = {d.get("event") or d["message"] for d in out}
    assert {"from_miti", "plain litellm warning", "from_api_emit"} <= seen
    for d in out:
        assert {k: d.get(k) for k in IDS} == {
            "session_id": SID, "run_id": "r1", "step": "validate", "request_id": "req-1",
        }, d  # fmt: skip


async def test_sync_route_line_has_session_id(stderr_lines):
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/v1/things/{id}", dependencies=[Depends(logs.bind_session)])
    def sync_thing(id: str):
        logs.emit("in_sync_handler")
        return {}

    sid = "a" * 32
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        await c.get(f"/v1/things/{sid}", headers={"X-Request-ID": "rq-1"})
    (line,) = [d for d in stderr_lines() if d.get("event") == "in_sync_handler"]
    assert line["session_id"] == sid and line["request_id"] == "rq-1"


def test_sentinel_transcript_and_provider_exception_never_logged(repo, stderr_lines):  # noqa: F811
    transcript = f"Client: my name is {SENTINEL} and I take sertraline"

    def fn(ctx):
        err = RuntimeError(f'invalid request "{transcript}" rejected')
        err.status_code = 503

        async def fail(**kwargs):
            raise err

        route = Route(litellm_id="anthropic/claude-sonnet-5-5", api_key_env="ANTHROPIC_API_KEY",
                      max_retries=0)  # fmt: skip
        client = LiteLLMClient(LLMConfig(llm_mode="live", routes={"mid": route}), acompletion=fail)
        req = LLMRequest(tier="mid", system="s", user=transcript, response_schema={})
        try:
            asyncio.run(client.complete_json(req))
        except LLMUnavailable:
            pass
        log_event("with_transcript", text=transcript, transcript=transcript, calls=1)
        raise RuntimeError(f'handler failed on "{transcript}"')  # unexpected exception path

    runner_with(repo, fn).handle(payload(run_id="r1"))
    raw = json.dumps(stderr_lines())
    assert "llm_provider_error" in raw and "http_status" in raw  # the provider line was emitted
    assert SENTINEL not in raw and "sertraline" not in raw


def test_second_task_does_not_carry_first_tasks_ids(repo, stderr_lines):  # noqa: F811
    first = runner_with(repo, lambda ctx: logs.emit("first_task"))
    first.handle(payload(run_id="r1"))
    assert [d for d in stderr_lines() if d.get("event") == "first_task"]

    iid = "d" * 32
    second = runner_with(
        repo, lambda ctx: log_event("second_task"), kind="interview-sweep", claim=False, step=None
    )
    second.handle(TaskPayload(kind="interview-sweep", uid=UID, sid=iid, request_id="rq-2"))
    logging.getLogger("somelib").warning("outside any task")
    out = stderr_lines()
    (line,) = [d for d in out if d.get("event") == "second_task"]
    assert line["session_id"] == iid and line["request_id"] == "rq-2" and "run_id" not in line
    outside = [d for d in out if d.get("logger") == "somelib"]
    assert outside and not any(k in outside[0] for k in IDS)
    assert SID not in json.dumps(out) and "req-1" not in json.dumps(out)
