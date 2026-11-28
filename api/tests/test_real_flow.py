"""The end-to-end flow with `ADAPTERS=real`.

No network: the STT provider is `FixtureStt` (via the real `RealStt` registry), and the engine's
coding stage and tips generator return canned fixtures (see `miti_fixtures.patch_engine`).
Everything else is real: `build_adapters`, `RealEvaluation`, `run_miti`, report assembly, the
worker and its `to_public` error map. A card is submitted (the first run is gated on it) but the
engine never sees it.
"""

import uuid
from dataclasses import replace

import httpx
import pytest
from audio_helpers import MAGIC, StubTools
from cards import valid_card
from google.api_core import exceptions as gexc
from miti_fixtures import TRANSCRIPT, patch_engine
from onolys_engine_core.errors import InputError
from onolys_engine_core.llm import LLMUnavailable, StubClient
from onolys_miti.run import AllRunsFailed
from test_transcribe import words

from onolys_api.adapters import build_adapters
from onolys_api.adapters.real import RealEvaluation, RealStt
from onolys_api.app import create_app
from onolys_api.jobs.transcribe import TRANSCRIPT_ID
from onolys_api.repo.fake import FakeRepo
from onolys_api.transcription.fixture import FixtureStt, uri_hash

pytestmark = pytest.mark.integration
ROUTES = (
    "cheap: &s {litellm_id: anthropic/x, api_key_env: K}\nmid: *s\nstrong: *s\n"
    "miti_code: {alias: mid}\nmiti_globals: {alias: mid}\ntips: {alias: mid}\n"
    "presets:\n  default: {routes: {}}\n  fast: {routes: {}}\n"
)


class SpyStt(FixtureStt):
    """Fixture STT for any audio uri; counts submits; optionally fails its first poll."""

    def __init__(self, fail_first_poll: BaseException | None = None) -> None:
        super().__init__({})
        self.fail_first_poll = fail_first_poll
        self.fetches = 0

    async def _submit(self, audio, params):
        self._fixtures[uri_hash(audio.uri)] = words({"A": 60, "B": 60})
        return await super()._submit(audio, params)

    async def _fetch(self, handle):
        self.fetches += 1
        if self.fail_first_poll is not None and self.fetches == 1:
            raise self.fail_first_poll
        return await super()._fetch(handle)


class Engine:
    """Canned coding stage and tips; `code_failures` are raised one per coding call first."""

    def __init__(self, monkeypatch, code_failures: list[BaseException]) -> None:
        self.calls = patch_engine(monkeypatch, code_failures)

    @property
    def code_calls(self) -> int:
        return self.calls["code"]


def fixture_llm(routes: dict) -> StubClient:
    stub = StubClient()
    return stub


class Env:
    def __init__(self, app, client, repo, stt, engine):
        self.app, self.c, self.repo, self.stt, self.engine = app, client, repo, stt, engine
        self.uid = f"u{uuid.uuid4().hex[:10]}"
        self.h = {"Authorization": f"Bearer test:{self.uid}"}

    async def status(self, sid):
        r = await self.c.get(f"/v1/sessions/{sid}", headers=self.h)
        return r.json()

    async def to_awaiting_input(self) -> str:
        r = await self.c.post("/v1/sessions", json={"title": None}, headers=self.h)
        sid = r.json()["session"]["id"]
        up = (
            await self.c.post(
                f"/v1/sessions/{sid}/audio",
                json={"content_type": "audio/wav", "size_bytes": len(MAGIC["wav"])},
                headers=self.h,
            )
        ).json()
        await self.c.put(
            up["upload_url"].removeprefix("http://localhost:8000"),
            content=MAGIC["wav"],
            headers=up["required_headers"],
        )
        await self.c.post(f"/v1/sessions/{sid}/audio/complete", headers=self.h)
        self.app.state.queue.drain()
        return sid

    async def run(self, sid: str, card: dict) -> None:
        # Install the fixture before acceptance freezes transcript and speaker inputs.
        self.repo.put_transcript(self.uid, sid, TRANSCRIPT_ID, TRANSCRIPT)
        await self.c.post(
            f"/v1/sessions/{sid}/speakers/confirm", json={"clinician_speaker": "A"}, headers=self.h
        )
        r = await self.c.put(
            f"/v1/sessions/{sid}/rating", json={"final": True, "card": card}, headers=self.h
        )
        assert r.status_code in (200, 202), r.text
        self.app.state.queue.drain()


@pytest.fixture
def make_env(settings, blobs, tmp_path, monkeypatch):
    routes = tmp_path / "routes.yaml"
    routes.write_text(ROUTES)
    (tmp_path / "stt_providers.yaml").write_text(
        "providers:\n  base: {provider: p1, model: m1}\ndefault: base\nby_language: {}\n"
    )
    stack: list = []

    async def make(code_failures=(), stt_failure=None) -> Env:
        stt = SpyStt(stt_failure)
        engine = Engine(monkeypatch, list(code_failures))
        s = replace(settings, extra_presets=("fast",), routes_file=str(routes), adapters="real")
        adapters = build_adapters(s, stt_registry={"p1": lambda: stt}, llm_factory=fixture_llm)
        repo = FakeRepo(blobs)
        app = create_app(s, repo=repo, blobs=blobs, audio_tools=StubTools(), adapters=adapters)
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
        stack.append(client)
        return Env(app, client, repo, stt, engine)

    yield make
    # clients are closed by GC with the loop; nothing else to release


def test_build_adapters_real_returns_real_adapters(settings):
    a = build_adapters(replace(settings, adapters="real"))
    assert isinstance(a.stt, RealStt) and isinstance(a.evaluation, RealEvaluation)


async def test_real_flow_reaches_report_ready_with_a_no_rating_report(make_env, monkeypatch):
    from onolys_engine_core import validated_run

    validate = validated_run.validate_output
    calls = []

    def record(output, schema):
        calls.append(output)
        return validate(output, schema)

    monkeypatch.setattr(validated_run, "validate_output", record)
    env = await make_env()
    sid = await env.to_awaiting_input()
    assert (await env.status(sid))["status"] == "awaiting_input"
    await env.run(sid, valid_card())
    s = await env.status(sid)
    assert (s["status"], s["progress"], s["latest_report_version"]) == ("report_ready", 100, 1)
    assert env.engine.code_calls == 1 and len(calls) == 1
    (run,) = env.repo.list_runs(env.uid, sid)
    assert run.validation.attempts == 1
    report = (await env.c.get(f"/v1/sessions/{sid}/reports/1", headers=env.h)).json()["report"]
    assert report["reasons_audit"]["status"] == "skipped"
    assert report["header"]["has_clinician_rating"] is False
    assert len(report["tips"]) == 3  # from the fixture tips


async def test_stt_start_called_once_across_forced_retry(make_env):
    env = await make_env(stt_failure=gexc.ServiceUnavailable("provider blip"))
    sid = await env.to_awaiting_input()
    # the first poll failed transiently, the queue retried it (attempt 2) and it succeeded
    assert (await env.status(sid))["status"] == "awaiting_input"
    assert env.stt.submits == 1 and env.stt.fetches >= 2


async def test_transient_llm_failure_succeeds_on_attempt_2(make_env):
    env = await make_env(code_failures=[LLMUnavailable("overloaded")])
    sid = await env.to_awaiting_input()
    await env.run(sid, valid_card())
    s = await env.status(sid)
    assert s["status"] == "report_ready"
    assert env.engine.code_calls == 2


@pytest.mark.parametrize(
    "failure, code",
    [
        (AllRunsFailed("all runs failed"), "internal_error"),
        (InputError("bad preset"), "invalid_parameters"),
    ],
)
async def test_permanent_failure_ends_failed_with_mapped_code(make_env, failure, code):
    env = await make_env(code_failures=[failure, failure])
    sid = await env.to_awaiting_input()
    await env.run(sid, valid_card())
    s = await env.status(sid)
    assert s["status"] == "failed" and s["error"]["code"] == code
    assert env.engine.code_calls == 1  # not retried


def _all_runs_failed_from(cause):
    try:
        raise cause
    except Exception as c:
        try:
            raise AllRunsFailed("all 1 run(s) failed") from c
        except Exception as e:
            return e


async def test_engine_wrapped_llm_failure_is_retried_then_upstream_unavailable(make_env):
    # the engine raises AllRunsFailed from the LLMUnavailable of its only run (broken preset model)
    env = await make_env(
        code_failures=[
            _all_runs_failed_from(LLMUnavailable("NotFound")),
            _all_runs_failed_from(LLMUnavailable("NotFound")),
        ]
    )
    sid = await env.to_awaiting_input()
    await env.run(sid, valid_card())
    s = await env.status(sid)
    assert s["status"] == "failed" and s["error"]["code"] == "upstream_unavailable"
    assert env.engine.code_calls == 2


async def test_transient_failure_twice_ends_failed_upstream_unavailable(make_env):
    env = await make_env(code_failures=[LLMUnavailable("x"), LLMUnavailable("x")])
    sid = await env.to_awaiting_input()
    await env.run(sid, valid_card())
    s = await env.status(sid)
    assert s["status"] == "failed" and s["error"]["code"] == "upstream_unavailable"
    assert env.engine.code_calls == 2


async def test_real_invalid_lean_result_fails_once_with_safe_detail(make_env, monkeypatch, caplog):
    import json

    from onolys_engine_core.engine import EngineResult, RunInfo, RunUsage
    from onolys_miti import MitiEngine

    env = await make_env()
    calls = []

    async def invalid(self, ctx, transcript, params, progress_cb=None):
        calls.append(1)
        return EngineResult(
            output={"private": "PHI-secret-output"},
            artifacts={"code": {"private": "PHI-secret-output"}},
            run_info=RunInfo(usage=RunUsage(input_tokens=11, output_tokens=2, calls=1)),
        )

    monkeypatch.setattr(MitiEngine, "run", invalid)
    sid = await env.to_awaiting_input()
    await env.run(sid, valid_card())
    (run,) = env.repo.list_runs(env.uid, sid)
    detail = (await env.c.get(f"/v1/runs/{run.run_id}", headers=env.h)).json()
    assert run.status == "failed" and run.error == "output_invalid"
    assert len(calls) == 1 and run.attempts == 1
    assert detail["validation"]["attempts"] == 1
    assert 0 < len(detail["validation"]["first_issues"]) <= 10
    assert detail["run_info"]["usage"] == {
        "input_tokens": 11, "output_tokens": 2, "calls": 1, "cost_usd": None,
    }
    assert "PHI-secret-output" not in json.dumps(detail) + caplog.text + str(run.model_dump())
    assert env.repo.list_reports(env.uid, sid) == []
    assert not any(env.app.state.blobs.root.glob(f"{env.uid}/{sid}/runs/**/*"))
