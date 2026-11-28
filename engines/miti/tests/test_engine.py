"""MITI's shared Engine adapter preserves lean output and per-call accounting."""

import asyncio
import json
from datetime import UTC, datetime
from importlib.metadata import version

import pytest
from onolys_engine.context import RunContext
from onolys_engine.engine import Engine, EngineResult, RunInfo, RunUsage
from onolys_engine.llm import LLMBadOutput, MetricsCollector
from onolys_engine.llm.types import LLMRequest, Usage
from onolys_engine.registry import EngineRegistry
from onolys_engine.transcript_v1 import TranscriptV1
from onolys_engine.validate import validate_output
from pydantic import BaseModel
from test_golden import FIX, GOLDEN_REPORT, PARAMS, SMAP, GoldenClient, masked

from onolys_miti import MitiEngine, build, run_miti
from onolys_miti.report import schema_path
from onolys_miti.run import AllRunsFailed, Artifacts

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


@pytest.mark.parametrize("prices,expected", [([0.01, 0.02, 0.03], 0.06), ([0.0, 0.0, 0.0], 0.0), ([0.01, None, 0.03], None)])
async def test_current_run_cost_sums_prices_and_preserves_unknown(prices, expected):
    class PricedClient(GoldenClient):
        async def complete_json(self, req, metrics=None):
            result = await super().complete_json(req)
            metrics.record(req, "fixture", Usage(11, 7, cost_usd=prices.pop(0)), 0.0, 1, True)
            return result

    metrics = MetricsCollector()
    metrics.record(LLMRequest("prior", "", "", BaseModel, "prior"), "fixture", Usage(cost_usd=None), 0.0, 1, True)
    ctx = RunContext(llm=PricedClient(), metrics=metrics, request_id="req-cost")
    result = await MitiEngine().run(ctx, transcript(), {**PARAMS, "speaker_map": SMAP})
    assert result.run_info.usage.cost_usd == expected


async def test_shared_validated_run_accepts_lean_golden_report():
    from onolys_engine.validated_run import run_validated

    result = await run_validated(
        MitiEngine(), context(), transcript(), {**PARAMS, "speaker_map": SMAP}
    )
    assert masked(result.output) == masked(GOLDEN_REPORT)
    assert result.run_info.validation == {"attempts": 1}
    assert result.run_info.usage.calls == 3


@pytest.mark.parametrize("stop_tier,cancel,expected_cost", [("miti_code", False, 0.05), ("miti_code", True, 0.03), ("tips", True, 0.04)])
async def test_engine_retains_coding_usage_on_failure_or_cancellation(stop_tier, cancel, expected_cost):
    received = []
    blocked = asyncio.Event()

    class InterruptedClient(GoldenClient):
        async def complete_json(self, req, metrics=None):
            if req.tier == stop_tier:
                metrics.record(
                    req, "fixture", Usage(13, 7, 5, 3, 0.02), 0.0, 1, False,
                    "cancelled" if cancel else "bad_output",
                )
                received.append(metrics.records[-1])
                if cancel:
                    blocked.set()
                    await asyncio.Future()  # Known reply usage before an unfinished retry.
                raise LLMBadOutput("synthetic malformed reply")
            result = await super().complete_json(req)
            metrics.record(req, "fixture", Usage(11, 7, 5, 3, 0.01), 0.0, 1, True)
            received.append(metrics.records[-1])
            return result

    ctx = RunContext(llm=InterruptedClient(), metrics=MetricsCollector(), request_id="req-interrupted")
    invocation = MitiEngine().run(ctx, transcript(), {**PARAMS, "speaker_map": SMAP})
    if cancel:
        task = asyncio.create_task(invocation)
        await asyncio.wait_for(blocked.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled()
    else:
        with pytest.raises(AllRunsFailed):
            await invocation
    assert received and any(record["tier"].startswith("miti_") for record in received)
    # Preserve the existing whole-run order: tips first, followed by coding records.
    assert ctx.metrics.records == sorted(received, key=lambda record: record["tier"] != "tips")
    assert sum(record["input_tokens"] for record in ctx.metrics.records) == sum(
        record["input_tokens"] for record in received
    )
    assert sum(record["cost_usd"] for record in ctx.metrics.records) == pytest.approx(
        expected_cost
    )


async def test_success_retains_whole_run_usage_once_and_tips_only_evaluation_usage():
    ctx = context()
    result = await MitiEngine().run(ctx, transcript(), {**PARAMS, "speaker_map": SMAP})
    assert [record["tier"] for record in ctx.metrics.records] == ["tips", "miti_code", "miti_globals"]
    assert result.run_info.usage.input_tokens == 33
    assert result.run_info.usage.output_tokens == 21
    assert result.run_info.usage.calls == 3
    evaluation = result.output["run_info"]["evaluation"]["usage"]
    assert evaluation["input_tokens"] == 11 and evaluation["output_tokens"] == 7
    assert evaluation["calls"] == 1
