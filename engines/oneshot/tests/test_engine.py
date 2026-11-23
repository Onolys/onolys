"""One-shot execution uses one call and preserves the selected schema and route."""

import asyncio
import json

import pytest
import yaml
from onolys_engine_core.context import RunContext
from onolys_engine_core.errors import ConfigError, InputError
from onolys_engine_core.llm.errors import LLMBadOutput
from onolys_engine_core.llm.fixture_client import RecordingClient
from onolys_engine_core.llm.routes import Route
from onolys_engine_core.llm.types import LLMResult, MetricsCollector, Usage
from onolys_engine_core.registry import EngineRegistry
from onolys_engine_core.transcript_v1 import TranscriptV1

from onolys_oneshot import OneshotEngine
from onolys_oneshot.config import load_config


@pytest.fixture
def configs(tmp_path, monkeypatch):
    for name in ("miti", "other"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "config.yaml").write_text(yaml.safe_dump({
            "name": name, "version": "test-2", "max_output_tokens": 123,
            "inputs": ["transcript", "params"], "schema_hint": True,
            "params_schema": {"type": "object", "properties": {"change_goal": {"type": "string"}}},
        }))
        (directory / "instructions.md").write_text("Use only the supplied source.")
        (directory / "schema.json").write_text(json.dumps({
            "$id": f"urn:test:{name}", "type": "object",
            "properties": {name: {"type": "string"}}, "required": [name],
            "additionalProperties": False,
        }))
    monkeypatch.setattr("onolys_oneshot.config._root", lambda root: root or tmp_path)
    return tmp_path


@pytest.fixture
def transcript():
    return TranscriptV1.model_validate({"turns": [
        {"id": "a", "speaker": "A", "text": "Before"},
        {"id": "b", "speaker": "B", "text": "Selected"},
    ]})


class FakeLLM:
    def __init__(self, *, mode="json_schema", cost=0.012, error=None):
        self.routes = {"oneshot": Route(litellm_id="provider/actual", structured_output_mode=mode)}
        self.requests = []
        self.error = error
        self.usage = Usage(input_tokens=15, output_tokens=7, cost_usd=cost,
                           cache_read_tokens=3, cache_write_tokens=2)

    async def complete_json(self, req, metrics=None):
        self.requests.append(req)
        await asyncio.sleep(0)
        if self.error:
            raise self.error
        return LLMResult(parsed={"miti": "ok"}, usage=self.usage, model="provider/actual")


def context(llm, feedback=None):
    return RunContext(llm=llm, metrics=MetricsCollector(), request_id="test",
                      deadline=456.0, feedback=feedback)


async def test_single_call_with_feedback_and_complete_provenance(configs, transcript):
    engine = OneshotEngine()
    llm = FakeLLM()
    ctx = context(llm, "Fix required fields.")
    # Existing collector records must never be charged to this run.
    ctx.metrics.records.append({"input_tokens": 999, "cost_usd": 99})
    params = {"config": "miti", "change_goal": "Read", "coded_span": {"start_turn": 1, "end_turn": 2}}
    result = await engine.run(ctx, transcript, params)
    assert len(llm.requests) == 1
    request = llm.requests[0]
    assert request.temperature == 0
    assert request.response_schema == engine.output_schema()
    assert request.response_model is None
    assert request.tier == "oneshot"
    assert request.max_tokens == 123
    assert request.deadline == 456.0
    assert "Before" not in request.user
    assert request.user.index("Selected") < request.user.index('"change_goal"') < request.user.index(ctx.feedback)
    assert request.user.endswith(ctx.feedback)
    assert "Output JSON Schema:" not in request.system
    assert type(result.output) is dict
    assert result.output == {"miti": "ok"}
    info = result.run_info.model_dump()
    assert info["engine"] == "oneshot"
    assert info["config"] == "miti"
    assert info["config_hash"] == load_config("miti").config_hash
    assert info["span"] == params["coded_span"]
    assert info["model"] == "provider/actual"
    assert info["route"] == "oneshot"
    assert info["structured_output_mode"] == "json_schema"
    assert info["usage"] == {"input_tokens": 15, "output_tokens": 7, "calls": 1,
                             "cost_usd": 0.012, "cache_read_tokens": 3, "cache_write_tokens": 2}
    assert params["config"] == "miti"


async def test_object_mode_uses_actual_client_route_and_null_unpriced_cost(configs, transcript):
    llm = FakeLLM(mode="json_object", cost=None)
    result = await OneshotEngine().run(context(llm), transcript, {"config": "miti"})
    assert "Output JSON Schema:" in llm.requests[0].system
    assert result.run_info.structured_output_mode == "json_object"
    assert result.run_info.usage.cost_usd is None
    assert result.run_info.span == {"start_turn": 0, "end_turn": 2}


async def test_recording_wrapper_uses_inner_resolved_route(configs, transcript, tmp_path):
    llm = FakeLLM(mode="json_object")
    result = await OneshotEngine().run(context(RecordingClient(llm, tmp_path / "replies")), transcript, {"config": "miti"})
    assert result.run_info.structured_output_mode == "json_object"
    assert "Output JSON Schema:" in llm.requests[0].system


async def test_fixture_client_without_routes_resolves_requested_preset(configs, transcript, monkeypatch):
    llm = FakeLLM(mode="json_object")
    del llm.routes
    presets = []

    def resolve(name):
        presets.append(name)
        return {"oneshot": Route(litellm_id="fixture", structured_output_mode="json_object")}, None

    monkeypatch.setattr("onolys_oneshot.engine.resolve_preset", resolve)
    result = await OneshotEngine().run(context(llm), transcript, {"config": "miti", "preset": "test-preset"})
    assert presets == ["test-preset"]
    assert result.run_info.structured_output_mode == "json_object"


async def test_schema_exception_propagates_without_engine_retry(configs, transcript):
    error = LLMBadOutput("bad schema")
    llm = FakeLLM(error=error)
    with pytest.raises(LLMBadOutput) as raised:
        await OneshotEngine().run(context(llm), transcript, {"config": "miti"})
    assert raised.value is error
    assert len(llm.requests) == 1


async def test_invalid_dict_is_returned_for_wrapper_validation(configs, transcript):
    # The engine delegates schema validation/retry to run_validated.
    llm = FakeLLM()
    result = await OneshotEngine(config="other").run(context(llm), transcript, {"config": "other"})
    assert result.output == {"miti": "ok"}
    assert len(llm.requests) == 1


@pytest.mark.parametrize("params", [{}, {"config": "absent"}, {"config": "other"}, {"config": None}])
async def test_missing_unknown_or_unbound_config_rejected_before_call(configs, transcript, params):
    llm = FakeLLM()
    with pytest.raises(InputError):
        await OneshotEngine().run(context(llm), transcript, params)
    assert llm.requests == []


def test_unknown_constructor_config_is_input_error(configs):
    with pytest.raises(InputError):
        OneshotEngine(config="absent")


async def test_bound_schemas_stable_before_after_and_during_concurrent_runs(configs, transcript):
    engines = [OneshotEngine(), OneshotEngine(config="other")]
    schemas = [engine.output_schema() for engine in engines]
    assert [schema["$id"] for schema in schemas] == ["urn:test:miti", "urn:test:other"]
    schemas[0]["required"].append("mutated")
    assert engines[0].output_schema()["required"] == ["miti"]
    await asyncio.gather(*[
        engine.run(context(FakeLLM()), transcript, {"config": name})
        for engine, name in zip(engines, ["miti", "other"], strict=True)
    ])
    assert [engine.output_schema()["required"] for engine in engines] == [["miti"], ["other"]]


def test_variants_and_registry_schema_are_available_before_run(configs):
    engine = OneshotEngine()
    registry = EngineRegistry()
    registry.register(engine)
    info = registry.engines()[0]
    assert engine.name == "oneshot"
    assert engine.accepts_feedback is True
    assert info.output_schema_id == "urn:test:miti"
    assert [variant.id for variant in info.variants] == ["miti", "other"]
    assert info.variants[0].label == "One-shot · MITI"


async def test_unknown_route_fails_before_call(configs, transcript):
    llm = FakeLLM()
    llm.routes = {}
    with pytest.raises(ConfigError):
        await OneshotEngine().run(context(llm), transcript, {"config": "miti"})
    assert llm.requests == []


@pytest.mark.parametrize("span,words,duration", [
    (None, 6001, None),
    (None, 2, 1_500_001),
    ({"start_turn": 0, "end_turn": 1}, 6001, None),
    ({"start_turn": 0, "end_turn": 2}, 2, 1_500_001),
    ({"start_ms": 0, "end_ms": 1_500_001}, 2, 1_500_001),
])
async def test_oversized_coded_portion_rejected_before_model_call(configs, span, words, duration):
    from onolys_engine_core.errors import SessionTooLong

    tx = TranscriptV1.model_validate({"turns": [
        {"id": "a", "speaker": "A", "text": "word " * words,
         "start_ms": 0, "end_ms": 1},
        {"id": "b", "speaker": "B", "text": "word", "start_ms": 1,
         "end_ms": duration or 2},
    ]})
    original = tx.model_dump()
    llm = FakeLLM()
    with pytest.raises(SessionTooLong, match="narrower coded_span") as error:
        await OneshotEngine().run(context(llm), tx, {"config": "miti", "coded_span": span})
    assert error.value.code == "session_too_long"
    assert llm.requests == []
    assert tx.model_dump() == original


@pytest.mark.parametrize("span,timed,duration,words", [
    (None, True, 1_500_000, 5999),
    ({"start_turn": 1, "end_turn": 2}, True, 3_600_000, 6001),
    ({"start_ms": 3_599_999, "end_ms": 3_600_000}, True, 3_600_000, 6001),
    ({"start_turn": 1, "end_turn": 2}, False, 3_600_000, 6001),
])
async def test_coded_portion_boundaries_and_narrow_long_sources_pass(configs, span, timed, duration, words):
    turns = [
        {"id": "a", "speaker": "A", "text": "word " * words},
        {"id": "b", "speaker": "B", "text": "selected"},
    ]
    if timed:
        turns[0].update(start_ms=0, end_ms=duration - 1)
        turns[1].update(start_ms=duration - 1, end_ms=duration)
    tx = TranscriptV1.model_validate({"duration_ms": duration, "turns": turns})
    original = tx.model_dump()
    llm = FakeLLM()
    await OneshotEngine().run(context(llm), tx, {"config": "miti", "coded_span": span})
    assert len(llm.requests) == 1
    assert tx.model_dump() == original


async def test_untimed_whole_session_uses_header_duration(configs, transcript):
    from onolys_engine_core.errors import SessionTooLong

    transcript.duration_ms = 1_500_001
    llm = FakeLLM()
    with pytest.raises(SessionTooLong, match="narrower coded_span"):
        await OneshotEngine().run(context(llm), transcript, {"config": "miti"})
    assert llm.requests == []


async def test_future_configs_do_not_inherit_miti_specific_caps(configs, transcript):
    transcript.duration_ms = 1_500_001
    llm = FakeLLM()
    await OneshotEngine(config="other").run(context(llm), transcript, {"config": "other"})
    assert len(llm.requests) == 1
