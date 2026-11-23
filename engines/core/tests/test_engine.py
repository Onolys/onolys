import inspect

import pytest

from onolys_engine_core.context import RunContext
from onolys_engine_core.engine import Engine, EngineResult, EngineVariant, RunInfo, RunUsage
from onolys_engine_core.transcript_v1 import TranscriptV1


class StubEngine(Engine):
    name = "stub"
    version = "1"

    async def run(self, ctx, transcript, params, progress_cb=None):
        if progress_cb:
            progress_cb("output", "done")
        return EngineResult(output={"feedback": ctx.feedback}, run_info=RunInfo())

    def output_schema(self):
        return {"type": "object"}


def test_engine_requires_both_abstract_methods():
    assert inspect.iscoroutinefunction(Engine.run)
    assert Engine.__abstractmethods__ == {"run", "output_schema"}
    with pytest.raises(TypeError):
        Engine()


def test_engine_defaults_and_variant_contract():
    engine = StubEngine()
    assert engine.accepts_feedback is False
    assert engine.variants() == []
    engine.variants().append(EngineVariant(id="a", label="Variant A"))
    assert engine.variants() == []
    assert EngineVariant(id="a", label="Variant A").model_dump() == {"id": "a", "label": "Variant A"}


def test_result_preserves_artifacts_and_engine_specific_run_info():
    artifacts = object()
    usage = RunUsage(input_tokens=4, output_tokens=5, calls=1, cache_read_tokens=2)
    info = RunInfo(usage=usage, engine="stub", provenance={"version": "1"})
    result = EngineResult(output={"ok": True}, artifacts=artifacts, run_info=info)
    assert result.artifacts is artifacts
    assert result.run_info.model_dump()["provenance"] == {"version": "1"}
    assert result.run_info.usage.cost_usd is None
    assert result.run_info.usage.model_dump()["cache_read_tokens"] == 2
    assert RunInfo().usage is None
    assert EngineResult(output={}, run_info=RunInfo()).artifacts is None


@pytest.mark.asyncio
async def test_feedback_reaches_engine_without_changing_the_call_contract():
    ctx = RunContext(llm=None, metrics=None, request_id="stub")
    assert ctx.feedback is None
    ctx.feedback = "Correct the output schema."
    events = []
    result = await StubEngine().run(ctx, TranscriptV1(turns=[]), {}, lambda *event: events.append(event))
    assert result.output == {"feedback": "Correct the output schema."}
    assert events == [("output", "done")]
