"""The public entry point: `run_miti` (PRD R2, R7, D6).

Applies the speaker map, selects the caller's span or whole transcript once, runs the code and
globals passes `n_runs` times, averages them (mean/min/max kept), generates tips and assembles
the no-rating report. Progress stages: `code` (code + globals passes), `tips`, `assemble`.

Failure: a run whose code or globals pass fails is excluded with a `run_failed` warning; when
every run fails `AllRunsFailed` is raised (a coding failure never yields a report). A tips
failure degrades to a warning. `ctx.deadline` (absolute `time.monotonic()` value) bounds the whole
call: past it a `TimeoutError` is raised.

Logging goes through `onolys_engine_core.safe_log` with ids, counts and statuses only, never text.
"""

import asyncio
import hashlib
import inspect
import logging
import statistics
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from onolys_engine_core.context import RunContext
from onolys_engine_core.errors import InputError, OnolysError
from onolys_engine_core.llm import LLMClient, LLMError, MetricsCollector
from onolys_engine_core.llm.routes import Route, resolve_preset
from onolys_engine_core.safe_log import log_event, register_fields
from pydantic import BaseModel

from onolys_miti import code_pass as code_mod
from onolys_miti import globals_pass as globals_mod
from onolys_miti import miti
from onolys_miti import tips as tips_mod
from onolys_miti.build import build_report_no_rating
from onolys_miti.formula import label_for
from onolys_miti.hashes import evaluation_prompt_hashes
from onolys_miti.prepare import Prepared, prepare
from onolys_miti.report import Report
from onolys_miti.result import (
    SCHEMA_VERSION,
    Aggregate,
    MitiResult,
    ProtocolBlock,
    Reference,
    ResultWarning,
    RunResult,
    Stat,
    SummaryStat,
)
from onolys_miti.run_info import RunInfo, RunUsage, code_version, hash_files, route_facts
from onolys_miti.score import score_run
from onolys_miti.span import select_coded_span
from onolys_miti.tips import TipsArtifact
from onolys_miti.transcript import Transcript

Stage = Literal["code", "tips", "assemble"]
StageStatus = Literal["started", "done", "failed"]
ProgressCb = Callable[[Stage, StageStatus], None]

register_fields({"run_index", "n_runs", "runs_ok", "stage", "stage_status"})

ROUTES = (code_mod.ROUTE, globals_mod.ROUTE)
_FAILURES = (code_mod.CodePassFailed, globals_mod.GlobalsPassFailed, LLMError)


class AllRunsFailed(OnolysError):
    """Every run failed, so there is nothing trustworthy to return."""

    code = "run_failed"


class Artifacts(BaseModel):
    code: MitiResult
    tips: TipsArtifact | None = None


class MitiOutput(BaseModel):
    """The report plus run artifacts. `run_info` is `report.run_info`."""

    report: Report
    artifacts: Artifacts


def _sha(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:16]


def prompt_hashes() -> dict[str, str]:
    """Hash of every prompt file (keyed by file name) and of each engine-owned template
    (`engine:*`), so a template change shows even when the prompt files are unchanged."""
    out = {p.name: hash_files([p]) for p in miti.MITI.prompt_paths}
    out["engine:code_output_format"] = _sha(code_mod._OUTPUT_FORMAT)
    code_fns = (code_mod._render_definitions, code_mod._render_fewshot, code_mod._render_batch)
    out["engine:code_templates"] = _sha(*(inspect.getsource(f) for f in code_fns))
    out["engine:globals_output_format"] = _sha(globals_mod._OUTPUT_FORMAT)
    glob_fns = (globals_mod._render_definitions, globals_mod._render_fewshot)
    out["engine:globals_templates"] = _sha(*(inspect.getsource(f) for f in glob_fns))
    return out


def _stat(values: list[float]) -> Stat:
    return Stat(mean=statistics.fmean(values), min=min(values), max=max(values), values=values)


def _summary_stat(values: list[float | None], ref: Reference | None) -> SummaryStat:
    known = [v for v in values if v is not None]
    mean = statistics.fmean(known) if known else None
    return SummaryStat(
        mean=mean,
        min=min(known) if known else None,
        max=max(known) if known else None,
        values=values,
        label=label_for(mean, ref.model_dump() if ref else None),
        reference=ref,
    )


def _vectors(runs: list[RunResult]) -> list[list[float]]:
    """One vector per run: counts, global scores, then summary values. A summary that is None in
    any run is left out for all runs (nothing to compare)."""
    first = runs[0]
    keys: list[tuple[str, str]] = [("c", k) for k in first.counts]
    keys += [("g", k) for k in first.globals]
    keys += [
        ("s", k) for k in first.summaries if all(r.summaries[k].value is not None for r in runs)
    ]

    def val(r: RunResult, kind: str, k: str) -> float:
        if kind == "c":
            return float(r.counts[k])
        if kind == "g":
            return float(r.globals[k].score)
        return float(r.summaries[k].value)  # type: ignore[arg-type]

    return [[val(r, kind, k) for kind, k in keys] for r in runs]


def representative_run(runs: list[RunResult]) -> int:
    """`run_index` of the run closest to the mean vector.

    Each dimension is divided by its range across runs (dimensions where all runs agree are
    dropped), so counts, 1-5 scores and ratios weigh alike. Smallest Euclidean distance to the
    per-dimension mean wins; ties go to the lowest `run_index`."""
    vecs = _vectors(runs)
    dims = list(zip(*vecs, strict=True))
    means = [statistics.fmean(d) for d in dims]
    ranges = [max(d) - min(d) for d in dims]

    def dist(v: list[float]) -> float:
        return sum(((x - m) / r) ** 2 for x, m, r in zip(v, means, ranges, strict=True) if r > 0)

    return min((dist(v), r.run_index) for v, r in zip(vecs, runs, strict=True))[1]


def aggregate(runs: list[RunResult]) -> Aggregate:
    """mean/min/max/values over the runs (in run order) for counts, globals and summaries, plus
    `representative_run`. With one run the aggregate equals it."""
    if not runs:
        raise ValueError("aggregate needs at least one run")
    summaries = {}
    for sid in runs[0].summaries:
        ref = runs[0].summaries[sid].reference
        summaries[sid] = _summary_stat([r.summaries[sid].value for r in runs], ref)
    return Aggregate(
        counts={k: _stat([float(r.counts[k]) for r in runs]) for k in runs[0].counts},
        globals={k: _stat([float(r.globals[k].score) for r in runs]) for k in runs[0].globals},
        summaries=summaries,
        representative_run=representative_run(runs),
    )


async def _one_run(
    client: LLMClient,
    prepared: Prepared,
    params: dict[str, Any],
    language: str | None,
    run_index: int,
    metrics: MetricsCollector,
    warmed: asyncio.Event,
) -> RunResult:
    """Code pass and globals pass run together; the code pass sets `warmed` after its warm call."""
    kw = {"language": language, "run_index": run_index, "metrics": metrics}
    code_task = asyncio.ensure_future(
        code_mod.code_pass(client, prepared, params, warmed=warmed, **kw)
    )
    globals_task = asyncio.ensure_future(globals_mod.globals_pass(client, prepared, params, **kw))
    done = await asyncio.gather(code_task, globals_task, return_exceptions=True)
    for d in done:
        if isinstance(d, BaseException):
            raise d
    code_res, glob_res = done
    scores = {k: g.score for k, g in glob_res.globals.items()}
    instances, counts, summaries, score_warns = score_run(code_res.instances, scores)
    return RunResult(
        run_index=run_index,
        instances=instances,
        counts=counts,
        globals=glob_res.globals,
        summaries=summaries,
        warnings=[*code_res.warnings, *glob_res.warnings, *score_warns],
    )


def _usage(metrics: MetricsCollector) -> RunUsage:
    snap = metrics.snapshot()
    tiers = snap["by_tier"].values()
    return RunUsage(
        calls=snap["calls"],
        **{
            k: sum(t[k] for t in tiers)
            for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
        },
    )


def _route_view(client: Any, preset: str | None, names: tuple[str, ...]) -> dict[str, Route]:
    found = getattr(client, "routes", None)
    if not isinstance(found, dict):
        found = resolve_preset(preset)[0]
    return {n: found[n] for n in names if n in found}


def _language(params: dict[str, Any], transcript: Transcript) -> str:
    lang = params.get("language")
    if not lang or lang == "auto":
        lang = transcript.language
    return lang or "und"


def _emit(cb: ProgressCb | None, stage: Stage, status: StageStatus, rid: str | None) -> None:
    """Call the progress callback; an error in it is logged (class name only) and ignored."""
    if cb is None:
        return
    try:
        cb(stage, status)
    except Exception as exc:  # noqa: BLE001 - a callback must never break the run
        log_event(
            "miti.progress_cb_error",
            request_id=rid,
            stage=stage,
            stage_status=status,
            exc_class=type(exc).__name__,
        )


async def _stage[T](cb: ProgressCb | None, stage: Stage, rid: str | None, work: Awaitable[T]) -> T:
    """`started`, then `done`, or `failed` (cancellation counts as failed) if `work` raises."""
    _emit(cb, stage, "started", rid)
    try:
        out = await work
    except BaseException:
        _emit(cb, stage, "failed", rid)
        raise
    _emit(cb, stage, "done", rid)
    return out


async def _code(
    ctx: RunContext,
    transcript: Transcript,
    params: dict[str, Any],
    metrics: MetricsCollector,
) -> MitiResult:
    n_runs = int(params.get("n_runs") or 1)
    if n_runs < 1:
        raise InputError("n_runs must be at least 1")
    rid = ctx.request_id
    seed = str(params.get("seed") or rid)
    choice = select_coded_span(transcript, seed, params.get("coded_span"))
    prepared = prepare(transcript, params, choice.coded_span)
    language = _language(params, transcript)
    lang_arg = None if language == "und" else language
    log_event(
        "miti.start",
        request_id=rid,
        n_runs=n_runs,
        speakers=len({rt.turn.speaker for rt in prepared.turns}),
        language=language,
    )

    warnings: list[ResultWarning] = [*prepared.warnings, *choice.warnings]
    if not language.lower().startswith("en"):
        warnings.append(
            ResultWarning(
                code="language_not_validated",
                severity="info",
                detail=f"language {language} is not validated for this engine",
            )
        )

    events = [asyncio.Event() for _ in range(n_runs)]
    first_failure: list[BaseException] = []  # first run failure: the cause of AllRunsFailed

    async def guarded(i: int) -> RunResult | None:
        if i > 0:  # later runs start once the first run's warm call has returned
            await events[0].wait()
        try:
            res = await _one_run(ctx.llm, prepared, params, lang_arg, i, metrics, events[i])
            log_event("miti.run", request_id=rid, run_index=i, status="ok")
            return res
        except _FAILURES as exc:
            first_failure.append(exc)
            warnings.append(
                ResultWarning(code="run_failed", detail=f"run {i} failed: {type(exc).__name__}")
            )
            log_event(
                "miti.run",
                logging.WARNING,
                request_id=rid,
                run_index=i,
                status="failed",
                exc_class=type(exc).__name__,
            )
            return None
        finally:
            events[i].set()

    outcomes = await asyncio.gather(*(guarded(i) for i in range(n_runs)))
    runs = [r for r in outcomes if r is not None]
    if not runs:
        log_event("miti.done", logging.ERROR, request_id=rid, status="failed", runs_ok=0)
        raise AllRunsFailed(f"all {n_runs} run(s) failed") from (
            first_failure[0] if first_failure else None
        )
    log_event(
        "miti.done", request_id=rid, status="ok", runs_ok=len(runs), calls=len(metrics.records)
    )

    d = miti.MITI
    routes = _route_view(ctx.llm, params.get("preset"), ROUTES)
    run_info = RunInfo(
        engine="miti",
        code_version=code_version(),
        preset=params.get("preset"),
        routes={n: route_facts(r) for n, r in routes.items()},
        pack=d.facts(),
        prompt_hashes=prompt_hashes(),
        n_runs=n_runs,
        usage=_usage(metrics),
        span=choice.info(),
    )
    return MitiResult(
        schema_version=SCHEMA_VERSION,
        request_id=rid,
        protocol=ProtocolBlock(
            id=d.id, version=d.version, pack_hash=d.hash, pack_format=d.pack_format
        ),
        language=language,
        change_goal=params.get("change_goal"),
        coded_span=choice.coded_span,
        subject_speaker=params["speaker_map"]["subject"],
        n_runs=n_runs,
        results=runs,
        aggregate=aggregate(runs),
        warnings=warnings,
        run_info=run_info,
    )


async def _run(
    ctx: RunContext,
    transcript: Transcript,
    speaker_map: dict[str, str],
    params: dict[str, Any],
    progress_cb: ProgressCb | None,
) -> MitiOutput:
    rid = ctx.request_id
    code_metrics = MetricsCollector()
    engine_params = {**params, "speaker_map": speaker_map}
    log_event("miti.run_start", request_id=rid)

    result = await _stage(
        progress_cb, "code", rid, _code(ctx, transcript, engine_params, code_metrics)
    )

    _emit(progress_cb, "tips", "started", rid)
    try:
        art, tip_warnings = await tips_mod.generate_tips(
            ctx.llm, transcript, speaker_map, result, metrics=ctx.metrics
        )
    except BaseException:
        _emit(progress_cb, "tips", "failed", rid)
        raise
    failed = any(w.code == "tips_failed" for w in tip_warnings)
    _emit(progress_cb, "tips", "failed" if failed else "done", rid)

    evaluation_usage = _usage(ctx.metrics)  # the report run's own calls (tips)
    ctx_records = getattr(ctx.metrics, "records", None)
    if isinstance(ctx_records, list):  # one call log for the whole run
        ctx_records += code_metrics.records
    route = (
        getattr(ctx.llm, "routes", {}).get(tips_mod.ROUTE) if hasattr(ctx.llm, "routes") else None
    )

    async def assemble() -> MitiOutput:
        report = build_report_no_rating(
            transcript=transcript,
            params=params,
            result=result,
            tips=art,
            warnings=list(tip_warnings),
            prompt_hashes=evaluation_prompt_hashes(),
            evaluation_routes={tips_mod.ROUTE: route_facts(route)} if route is not None else None,
            evaluation_usage=evaluation_usage,
            request_id=rid,
        )
        return MitiOutput(report=report, artifacts=Artifacts(code=result, tips=art))

    out = await _stage(progress_cb, "assemble", rid, assemble())
    log_event("miti.run_done", request_id=rid, status="ok")
    return out


async def run_miti(
    ctx: RunContext,
    transcript: Transcript,
    speaker_map: dict[str, str],
    params: dict[str, Any],
    progress_cb: ProgressCb | None = None,
) -> MitiOutput:
    """Code `transcript` and build the no-rating report.

    `params`: `change_goal`, `language`, `n_runs` (default 1), `preset`, `code_version`, `seed`
    (default `ctx.request_id`; recorded for provenance), `volleys_per_call`, `code_max_tokens`,
    `globals_max_tokens`, `coded_span` (half-open milliseconds or zero-based turns).
    Without `coded_span`, the whole transcript is coded."""
    if ctx.deadline is None:
        return await _run(ctx, transcript, speaker_map, params, progress_cb)
    remaining = ctx.deadline - asyncio.get_running_loop().time()
    async with asyncio.timeout(max(remaining, 0)):
        return await _run(ctx, transcript, speaker_map, params, progress_cb)
