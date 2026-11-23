"""Validate legacy/fake Evaluation adapters through the shared engine wrapper.

RealEvaluation declares ``validates_output`` on its class because its public run
already uses the configured engine's schema and wrapper. Other adapters (including
custom test fakes) are bridged here, keeping one validation per API evaluation.
The main API serves MITI only, so the bridge uses MitiEngine's public schema.
"""

from onolys_engine_core.engine import Engine, EngineResult, RunInfo
from onolys_engine_core.validated_run import run_validated
from onolys_miti import MitiEngine

from .base import Evaluation, EvaluationOutput


class _EvaluationEngine(Engine):
    name = "miti"
    version = "evaluation-bridge"

    def __init__(self, evaluation: Evaluation, speaker_map: dict[str, str]):
        self.evaluation = evaluation
        self.speaker_map = speaker_map

    def output_schema(self) -> dict:
        return MitiEngine().output_schema()

    async def run(self, ctx, transcript, params, progress_cb=None) -> EngineResult:
        out = await self.evaluation.run(ctx, transcript, self.speaker_map, params, progress_cb)
        return EngineResult(
            output=out.report, artifacts=out.artifacts,
            run_info=RunInfo(**(out.run_info or out.report.get("run_info", {}))),
        )


async def evaluate_validated(evaluation, ctx, transcript, speaker_map, params, progress_cb=None):
    # This is a trusted Python adapter declaration, never a field in returned data.
    if getattr(type(evaluation), "validates_output", False):
        return await evaluation.run(ctx, transcript, speaker_map, params, progress_cb)
    result = await run_validated(
        _EvaluationEngine(evaluation, speaker_map), ctx, transcript, params, progress_cb,
    )
    return EvaluationOutput(
        report=result.output, artifacts=result.artifacts or {},
        run_info=result.run_info.model_dump(mode="json", exclude_none=True),
    )
