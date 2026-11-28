"""Shared engine interface for the existing lean MITI pipeline."""

import json
from importlib.metadata import version

from onolys_engine.context import RunContext
from onolys_engine.engine import Engine, EngineResult, ProgressCb, RunInfo, RunUsage
from onolys_engine.transcript_v1 import TranscriptV1

from onolys_miti.report import schema_path
from onolys_miti.run import run_miti

_USAGE_COUNTERS = (
    "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
)


def _usage_totals(snapshot: dict) -> dict[str, int]:
    return {
        "calls": snapshot["calls"],
        **{
            key: sum(tier[key] for tier in snapshot["by_tier"].values())
            for key in _USAGE_COUNTERS
        },
    }


class MitiEngine(Engine):
    name = "miti"
    version = version("onolys-miti")

    def output_schema(self) -> dict:
        return json.loads(schema_path().read_text(encoding="utf-8"))

    async def run(
        self,
        ctx: RunContext,
        transcript: TranscriptV1,
        params: dict,
        progress_cb: ProgressCb | None = None,
    ) -> EngineResult:
        # A caller can retain the collector across runs; only charge this invocation.
        before = _usage_totals(ctx.metrics.snapshot())
        first_record = len(ctx.metrics.records)
        engine_params = dict(params)
        speaker_map = engine_params.pop("speaker_map")
        result = await run_miti(ctx, transcript, speaker_map, engine_params, progress_cb)
        after = _usage_totals(ctx.metrics.snapshot())
        prices = [record["cost_usd"] for record in ctx.metrics.records[first_record:]]
        cost = None if any(price is None for price in prices) else sum(prices)
        usage = RunUsage(**{key: after[key] - before[key] for key in after}, cost_usd=cost)
        output = result.report.model_dump(mode="json")
        return EngineResult(
            output=output,
            artifacts=result.artifacts,
            run_info=RunInfo(**output["run_info"], usage=usage),
        )
