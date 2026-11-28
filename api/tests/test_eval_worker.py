"""Worker eval params and guards; no first run in eval mode.

Offline: fake STT/evaluation; `RealEvaluation` only with a fake LLM factory.
"""

# ruff: noqa: F811

import logging
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from audio_helpers import StubTools
from test_run import ROUTES, Env, spy

from onolys_api.adapters import Adapters, FakeEvaluation, FakeStt
from onolys_api.adapters.real import RealEvaluation
from onolys_api.app import create_app
from onolys_api.engines import eval_snapshot
from onolys_api.jobs.run import make_run_handler
from onolys_api.jobs.worker import HandlerSpec
from onolys_api.repo.fake import FakeRepo
from onolys_api.repo.models import EvalRunInfo
from onolys_api.routes.runs import RunRequest, create_run

pytestmark = pytest.mark.integration
OVERRIDE = {"provider": "claude", "model": "claude", "tier": "claude-sonnet-5-5", "effort": "high"}


class Capture(FakeEvaluation):
    async def run(self, ctx, transcript, speaker_map, params, progress_cb=None):
        self.seen = params
        return await super().run(ctx, transcript, speaker_map, params, progress_cb)


@pytest.fixture
async def mk(settings, blobs, tmp_path):
    clients = []

    async def make(evaluation, **kw):
        routes = tmp_path / "routes.yaml"
        routes.write_text(ROUTES)
        (tmp_path / "stt_providers.yaml").write_text(
            "providers:\n  base: {provider: p1, model: m1}\ndefault: base\nby_language: {}\n"
        )
        repo = spy(FakeRepo(blobs))
        stt = FakeStt()
        s = replace(settings, extra_presets=("fast",), routes_file=str(routes), **kw)
        app = create_app(s, repo=repo, blobs=blobs, audio_tools=StubTools(),
                         adapters=Adapters(stt=stt, evaluation=evaluation))  # fmt: skip
        c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
        clients.append(c)
        return Env(app, c, repo, blobs, stt, evaluation), s

    yield make
    for c in clients:
        await c.aclose()


def info_for(settings, env, sid, engine="miti", override=None, **kw):
    preset = env.repo.get_session(env.uid, sid).preset
    snap, version = eval_snapshot(settings, preset, engine, override)
    return EvalRunInfo(
        eval_run_id="e1", combo_key="c", repeat=0, engine=engine, route_override=override,
        resolved_route=snap, engine_version=version,
    ).model_copy(update=kw)  # fmt: skip


def start_eval(env, settings, sid, **kw):
    out = create_run(env.app, env.uid, sid, RunRequest(),
                     is_eval=True, eval_spec=info_for(settings, env, sid, **kw))  # fmt: skip
    return out.run_id


def reasons(caplog):
    return [r.fields.get("reason") for r in caplog.records if hasattr(r, "fields")]


async def test_no_first_run_in_eval_mode_on_any_route(mk):
    env, s = await mk(FakeEvaluation(), eval_mode=True)
    sid = await env.start()  # transcript, speaker confirm and final rating all landed
    env.drain()
    assert env.repo.list_runs(env.uid, sid) == []
    assert env.repo.get_session(env.uid, sid).state == "awaiting_input"
    assert env.counters() == (0, 0)


async def test_prod_params_unchanged_and_eval_params_added(mk):
    cap = Capture()
    env, s = await mk(cap, eval_mode=True)
    sid = await env.start(n_runs=3)
    start_eval(env, s, sid)
    env.drain()
    assert {"engine", "route_override"} <= cap.seen.keys() and cap.seen["n_runs"] == 1
    assert cap.seen["engine"] == "miti" and cap.seen["route_override"] is None
    assert env.repo.get_session(env.uid, sid).state == "report_ready"

    prod = Capture()
    env2, _ = await mk(prod)  # eval mode off: the first run starts as today
    await env2.finished(n_runs=3)
    assert set(prod.seen) == {
        "change_goal", "seed", "coded_span", "language", "n_runs", "preset", "code_version",
        "stt_run", "stub_title",
    }
    assert prod.seen["n_runs"] == 3


@pytest.mark.parametrize("override,expected_id,effort", [
    (OVERRIDE, "anthropic/claude-sonnet-5-5", "high"),
    ({"provider": "openai", "model": "openai", "tier": "gpt-6.1-sol", "effort": "xhigh"}, "openai/gpt-6.1-sol", "xhigh"),
    ({"provider": "openai", "model": "openai", "tier": "gpt-6.1-terra", "effort": "none"}, "openai/gpt-6.1-terra", "none"),
    ({"provider": "openai", "model": "openai", "tier": "gpt-6-luna", "effort": "max"}, "openai/gpt-6-luna", "max"),
])
async def test_override_reaches_real_evaluation(mk, monkeypatch, override, expected_id, effort):
    monkeypatch.setenv("MODELS_FILE", str(Path(__file__).resolve().parents[2] / "config" / "models.yaml"))
    seen = {}

    def factory(routes):
        seen["routes"] = routes
        raise RuntimeError("stop after route capture")

    env, s = await mk(FakeEvaluation(), eval_mode=True)
    real = RealEvaluation(s, llm_factory=factory)
    env.app.state.adapters = Adapters(stt=env.stt, evaluation=real)
    sid = await env.start()
    start_eval(env, s, sid, override=override)
    env.drain()
    route = next(iter(seen["routes"].values()))
    assert route.litellm_id == expected_id
    assert route.extra_params["reasoning_effort"] == effort


async def test_block_with_eval_mode_off_fails_internal_error(mk, caplog):
    cap = Capture()
    env, s = await mk(cap, eval_mode=True)
    sid = await env.start()
    rid = start_eval(env, s, sid)
    off = replace(s, eval_mode=False)
    env.app.state.runner.register(
        "run", HandlerSpec(make_run_handler(env.blobs, lambda: cap, off), scope="run")
    )
    with caplog.at_level(logging.ERROR):
        env.drain()
    assert "eval_mode_off" in reasons(caplog) and not hasattr(cap, "seen")
    run = env.repo.get_run(env.uid, sid, rid)
    assert run.status == "failed" and run.error == "internal_error"
    assert env.repo.get_session(env.uid, sid).state == "failed"


@pytest.mark.parametrize("what", ["engine_version", "route", "code_version"])
async def test_drift_fails_internal_error_and_stays_failed(mk, caplog, what):
    cap = Capture()
    env, s = await mk(cap, eval_mode=True)
    sid = await env.start()
    good = info_for(s, env, sid)
    if what == "engine_version":
        kw = {"engine_version": "other"}
    elif what == "route":
        kw = {"resolved_route": {**good.resolved_route, "max_output_tokens": 1}}
    else:
        kw = {}
    rid = create_run(
        env.app, env.uid, sid, RunRequest(), is_eval=True, eval_spec=good.model_copy(update=kw)
    ).run_id
    if what == "code_version":
        env.repo.update_run(env.uid, sid, rid, {"code_version": "older-sha"})
    with caplog.at_level(logging.ERROR):
        env.drain()
    assert "eval_config_drift" in reasons(caplog) and not hasattr(cap, "seen")
    run = env.repo.get_run(env.uid, sid, rid)
    assert run.status == "failed" and run.error == "internal_error"
    assert len(env.repo.list_runs(env.uid, sid)) == 1  # nothing re-created
    env.drain()
    assert env.repo.get_run(env.uid, sid, rid).status == "failed"
