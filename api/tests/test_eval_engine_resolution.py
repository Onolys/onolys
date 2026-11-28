"""Eval-only engine and route resolution; offline, fake LLM factory."""

import time
from pathlib import Path

import pytest
from onolys_engine import EngineRegistry, EngineResult, InputError, RunContext, RunInfo, Transcript
from onolys_oneshot.engine import OneshotEngine

from onolys_api.adapters.real import RealEvaluation
from onolys_api.config import Settings
from onolys_api.engines import build_engine_registry, resolve_engine

pytestmark = pytest.mark.unit
MODELS = Path(__file__).resolve().parents[2] / "config" / "models.yaml"


@pytest.fixture(autouse=True)
def _models_file(monkeypatch):  # cwd-independent: the default path is relative
    monkeypatch.setenv("MODELS_FILE", str(MODELS))

PARAMS = {
    "change_goal": "cut back", "seed": "s", "language": "en", "n_runs": 1,
    "preset": "default", "code_version": "abc",
}
OVERRIDE = {"provider": "anthropic", "model": "claude", "tier": "claude-sonnet-5-5", "effort": "high"}


class Engine:
    name = "miti"
    accepts_feedback = False

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def output_schema(self):
        return {"type": "object", "required": ["schema_version"]}

    async def run(self, *args, **kw):
        self.calls.append(args)
        return EngineResult(output={"schema_version": "1"}, artifacts={}, run_info=RunInfo())


def evaluation(engine, eval_mode, seen):
    registry = EngineRegistry()
    registry.register(engine)

    def factory(routes):
        seen.append(routes)
        return "llm"

    return RealEvaluation(Settings(eval_mode=eval_mode), registry=registry, llm_factory=factory)


def ctx():
    return RunContext(llm=None, metrics=None, request_id="r", deadline=time.monotonic() + 900)


def tr():
    return Transcript(language="en", turns=[], duration_ms=0)


def test_resolve_engine_miti_from_registry():
    s = Settings(eval_mode=False)
    assert resolve_engine(s, "miti").name == "miti"


def test_resolve_engine_oneshot_only_in_eval_mode():
    assert isinstance(resolve_engine(Settings(eval_mode=True), "oneshot:miti"), OneshotEngine)
    with pytest.raises(InputError):
        resolve_engine(Settings(eval_mode=False), "oneshot:miti")


@pytest.mark.parametrize("bad", ["nope", "oneshot:nope", "oneshot:", "miti:x"])
def test_resolve_engine_unknown(bad):
    with pytest.raises(InputError):
        resolve_engine(Settings(eval_mode=True), bad)


async def test_override_changes_routes_in_eval_mode():
    seen, engine = [], Engine()
    await evaluation(engine, True, seen).run(
        ctx(), tr(), {}, {**PARAMS, "route_override": OVERRIDE}
    )
    routes = seen[0]
    assert routes and all(r.litellm_id == "anthropic/claude-sonnet-5-5" for r in routes.values())
    assert all(r.extra_params["reasoning_effort"] == "high" for r in routes.values())
    assert len(engine.calls) == 1


async def test_override_and_engine_ignored_when_eval_mode_off():
    seen, engine = [], Engine()
    await evaluation(engine, False, seen).run(
        ctx(), tr(), {}, {**PARAMS, "route_override": OVERRIDE, "engine": "oneshot:miti"}
    )
    assert all(r.litellm_id != "anthropic/claude-sonnet-5-5" for r in seen[0].values())
    assert len(engine.calls) == 1  # prod engine, not oneshot
    assert "route_override" not in engine.calls[0][2] and "engine" not in engine.calls[0][2]


@pytest.mark.parametrize(
    "patch",
    [{"model": "nope"}, {"tier": "nope"}, {"effort": "nope"}, {"tier": "gemini-4-neon"}],
)
async def test_unknown_override_values_are_input_error(patch):
    seen, engine = [], Engine()
    with pytest.raises(InputError):
        await evaluation(engine, True, seen).run(
            ctx(), tr(), {}, {**PARAMS, "route_override": {**OVERRIDE, **patch}}
        )
    assert engine.calls == []


async def test_unknown_engine_is_input_error():
    with pytest.raises(InputError):
        await evaluation(Engine(), True, []).run(
            ctx(), tr(), {}, {**PARAMS, "engine": "bogus"}
        )


async def test_oneshot_miti_stores_report_and_gets_config():
    s = Settings(eval_mode=True)
    ev = RealEvaluation(s, registry=build_engine_registry(s), llm_factory=lambda r: "llm")
    seen = {}

    async def fake_run(self, ctx, transcript, params, progress_cb=None):
        seen.update(params)
        return EngineResult(output={"ok": 1}, artifacts={}, run_info=RunInfo())

    import onolys_oneshot.engine as oe
    orig, oe.OneshotEngine.run = oe.OneshotEngine.run, fake_run
    try:
        async def passthrough(engine, rctx, transcript, params, cb):
            return await engine.run(rctx, transcript, params, cb)
        import onolys_api.adapters.real as real
        orig_rv, real.run_validated = real.run_validated, passthrough
        try:
            out = await ev.run(ctx(), tr(), {}, {**PARAMS, "engine": "oneshot:miti"})
        finally:
            real.run_validated = orig_rv
    finally:
        oe.OneshotEngine.run = orig
    assert out.report == {"ok": 1}
    assert seen["config"] == "miti"


@pytest.mark.parametrize("tier,effort", [
    (tier, effort)
    for tier in ("gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna")
    for effort in ("none", "low", "medium", "high", "xhigh", "max")
    if (tier, effort) != ("gpt-6.1-sol", "none")
])
async def test_openai_eval_override_reaches_real_engine_factory(tier, effort):
    from onolys_api.engines import eval_snapshot

    seen, engine = [], Engine()
    override = {"provider": "openai", "model": "openai", "tier": tier, "effort": effort}
    await evaluation(engine, True, seen).run(
        ctx(), tr(), {}, {**PARAMS, "route_override": override}
    )
    for route in seen[0].values():
        assert route.litellm_id == f"openai/{tier}"
        assert route.api_key_env == "OPENAI_API_KEY"
        assert route.extra_params["reasoning_effort"] == effort
    snapshot, _ = eval_snapshot(Settings(eval_mode=True), "default", "miti", override)
    assert snapshot["litellm_id"] == f"openai/{tier}" and snapshot["effort"] == effort
    assert snapshot["context_tokens"] == 1050000
