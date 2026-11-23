"""MITI's shared Engine adapter preserves lean output and per-call accounting."""

import json
from datetime import UTC, datetime
from importlib.metadata import version

import pytest
from onolys_engine_core.context import RunContext
from onolys_engine_core.engine import Engine, EngineResult, RunInfo, RunUsage
from onolys_engine_core.llm import MetricsCollector
from onolys_engine_core.llm.types import LLMRequest, Usage
from onolys_engine_core.registry import EngineRegistry
from onolys_engine_core.transcript_v1 import TranscriptV1
from onolys_engine_core.validate import validate_output
from pydantic import BaseModel
from test_golden import FIX, GOLDEN_REPORT, PARAMS, SMAP, GoldenClient, masked

from onolys_miti import MitiEngine, build, run_miti
from onolys_miti.report import schema_path
from onolys_miti.run import Artifacts

pytestmark = pytest.mark.unit


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 23, tzinfo=UTC)


class MeteredGoldenClient(GoldenClient):
    async def complete_json(self, req, metrics=None):
        result = await super().complete_json(req)
        if metrics is not None:
            metrics.record(req, "fixture", Usage(11, 7, 5, 3), 0.0, 1, True)
        return result


def context(metrics=None):
    return RunContext(
        llm=MeteredGoldenClient(),
        metrics=metrics if metrics is not None else MetricsCollector(),
        request_id="req-engine",
    )


def transcript():
    return TranscriptV1.model_validate_json((FIX / "good_practice.json").read_text())


async def test_engine_matches_run_miti_and_golden_report(monkeypatch):
    monkeypatch.setattr(build, "datetime", FixedDatetime)
    params = {**PARAMS, "speaker_map": SMAP}
    expected_events, actual_events = [], []
    direct = await run_miti(
        context(), transcript(), SMAP, PARAMS, lambda *event: expected_events.append(event)
    )
    result = await MitiEngine().run(
        context(), transcript(), params, lambda *event: actual_events.append(event)
    )
    assert isinstance(result, EngineResult)
    assert result.output == direct.report.model_dump(mode="json")
    assert masked(result.output) == masked(GOLDEN_REPORT)
    assert isinstance(result.artifacts, Artifacts)
    assert result.artifacts == direct.artifacts
    assert actual_events == expected_events
    assert params == {**PARAMS, "speaker_map": SMAP}
    assert isinstance(result.run_info, RunInfo)
    assert result.run_info.model_dump(exclude={"usage"}) == result.output["run_info"]
    assert result.run_info.usage == RunUsage(
        input_tokens=33, output_tokens=21, calls=3,
        cache_read_tokens=15, cache_write_tokens=9, cost_usd=None,
    )


async def test_usage_counts_only_current_run_with_reused_collector():
    metrics = MetricsCollector()
    metrics.record(
        LLMRequest("prior", "", "", BaseModel, "prior"),
        "fixture", Usage(1000, 2000, 3000, 4000), 0.0, 1, True,
    )
    ctx = context(metrics)
    engine = MitiEngine()
    for _ in range(2):
        result = await engine.run(ctx, transcript(), {**PARAMS, "speaker_map": SMAP})
        assert result.run_info.usage.model_dump() == {
            "input_tokens": 33, "output_tokens": 21, "calls": 3,
            "cache_read_tokens": 15, "cache_write_tokens": 9, "cost_usd": None,
        }
    assert ctx.metrics is metrics
    assert len(metrics.records) == 7


def test_schema_and_registry_contract():
    engine = MitiEngine()
    assert isinstance(engine, Engine)
    assert engine.name == "miti"
    assert engine.version == version("onolys-miti")
    assert engine.accepts_feedback is False
    assert engine.output_schema() == json.loads(schema_path().read_text())
    assert validate_output(GOLDEN_REPORT, engine.output_schema()) == []
    registry = EngineRegistry(prod_name="miti")
    registry.register(engine)
    assert registry.get("miti") is engine
    assert registry.engines()[0].prod is True
    assert registry.engines()[0].accepts_feedback is False


def test_package_exports_only_entry_points():
    import onolys_miti

    assert set(onolys_miti.__all__) == {"run_miti", "MitiEngine"}
    for name in ("RunInfo", "Artifacts", "ProgressCb", "AudioRef", "VoiceSession"):
        assert not hasattr(onolys_miti, name)
