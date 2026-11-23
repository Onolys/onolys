"""Report assembly (PRD R3): `build_report_no_rating` turns an engine result and tips into the
no-rating `Report`. Pure: no model call, nothing truncated."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from onolys_miti import miti
from onolys_miti.compare import (
    METHOD_LIMIT,
    explain,
    not_rated_diff,
    onolys_summaries,
    representative_instances,
)
from onolys_miti.report import (
    SCHEMA_VERSION,
    Aggregates,
    BehaviourEntry,
    ClinicianGlobal,
    Diff,
    GlobalEntry,
    Header,
    LayoutEntry,
    Line,
    Method,
    OnolysGlobal,
    Protocol,
    RatingCoverage,
    Report,
    ReportRunInfo,
    RunStats,
    ScorecardRow,
    Warning,
)
from onolys_miti.result import MitiResult
from onolys_miti.run_info import RunInfo, RunUsage
from onolys_miti.run_info import code_version as _code_version
from onolys_miti.stt import SttRun
from onolys_miti.tips import TipsArtifact
from onolys_miti.tone import ReportConfig, load_report_config, tone_rules
from onolys_miti.transcript import Transcript


def _stats(s: Any) -> RunStats:
    return RunStats(mean=s.mean, min=s.min, max=s.max, values=list(s.values))


def build_report_no_rating(
    *,
    transcript: Transcript,
    params: Mapping[str, Any],
    result: MitiResult,
    tips: TipsArtifact | None = None,
    warnings: list[Warning] | tuple[Warning, ...] = (),
    models: Mapping[str, str] | None = None,
    prompt_hashes: Mapping[str, str] | None = None,
    evaluation_routes: Mapping[str, Any] | None = None,
    evaluation_usage: RunUsage | None = None,
    cfg: ReportConfig | None = None,
    request_id: str | None = None,
    created_at: str | None = None,
) -> Report:
    """Assemble the no-rating report: Onolys values only, every diff `not_rated`,
    `reasons_audit.status: skipped`, null aggregates, tips and method kept.

    `warnings` are extra warnings from earlier stages (tips); the result's own warnings are
    passed through. `models` maps route name -> litellm id (merged over the result's routes).
    `prompt_hashes` are the report run's (see `hashes.evaluation_prompt_hashes`)."""
    d = miti.MITI
    cfg = cfg or load_report_config(d.data_dir / "report.yaml")
    tone = tone_rules(d)
    rep_idx = result.aggregate.representative_run
    rep = next(r for r in result.results if r.run_index == rep_idx)
    agg = result.aggregate
    labels = {i["id"]: i["label"] for i in d.items}
    global_ids = [i["id"] for i in d.items if i["kind"] == "global"]
    count_ids = [i["id"] for i in d.items if i["kind"] == "count"]

    out_warnings: list[Warning] = [Warning(code=w.code, item_id=w.item_id)
                                   for w in result.warnings]
    scorecard: list[ScorecardRow] = []
    globals_: list[GlobalEntry] = []
    behaviours: list[BehaviourEntry] = []

    for g in global_ids:
        o, gl = agg.globals[g], rep.globals[g]
        diff: Diff = not_rated_diff(o.mean)
        scorecard.append(ScorecardRow(
            item_id=g, kind="global", label=labels[g], clinician={"value": None},
            onolys={"value": gl.score, **_stats(o).model_dump()}, diff=diff))
        evidence = [Line(turn_id=e.turn_id, start=e.start, end=e.end, quote=e.quote)
                    for e in gl.evidence]
        expl, w = explain(item_id=g, kind="global", diff=diff, onolys_value=o.mean,
                          reason=gl.reason, onolys_lines=evidence, rules=tone)
        out_warnings += w
        globals_.append(GlobalEntry(
            item_id=g,
            onolys=OnolysGlobal(score=gl.score, source=gl.source, reason=gl.reason,
                                evidence=evidence),
            clinician=ClinicianGlobal(value=None), diff=diff, explanation=expl))

    for k in count_ids:
        o = agg.counts[k]
        diff = not_rated_diff(o.mean)
        scorecard.append(ScorecardRow(
            item_id=k, kind="count", label=labels[k], clinician={"value": None},
            onolys={"value": o.mean, **_stats(o).model_dump()}, diff=diff))
        inst = representative_instances(result, k)
        expl, w = explain(item_id=k, kind="count", diff=diff, onolys_value=o.mean, reason=None,
                          onolys_lines=inst, rules=tone)
        out_warnings += w
        behaviours.append(BehaviourEntry(
            item_id=k, clinician_count=None, clinician_note=None, onolys_count=_stats(o),
            instances=inst, instances_total=len(inst), diff=diff, explanation=expl))

    seen: set[tuple[str, str | None]] = set()
    final_warnings: list[Warning] = []
    for w in [*out_warnings, *warnings]:
        if (w.code, w.item_id) not in seen:
            seen.add((w.code, w.item_id))
            final_warnings.append(w)

    stt_data = params.get("stt_run")
    stt = SttRun.model_validate(stt_data) if stt_data is not None else None
    routes = {n: r.litellm_id for n, r in result.run_info.routes.items()} | dict(models or {})
    eval_info = RunInfo(
        engine="miti", code_version=params.get("code_version") or _code_version(),
        preset=params.get("preset"), routes=dict(evaluation_routes or {}), stt=stt,
        pack=d.facts(), prompt_hashes=dict(prompt_hashes or {}), n_runs=result.n_runs,
        usage=evaluation_usage or RunUsage())
    span = result.coded_span
    return Report(
        schema_version=SCHEMA_VERSION,
        request_id=request_id,
        created_at=created_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        header=Header(
            change_goal=result.change_goal or "",
            protocol=Protocol(id=d.id, version=d.version, pack_hash=d.hash,
                              label=f"{d.id.upper()} {d.version}"),
            language=result.language,
            coded_span=span.model_dump() if span else None,
            subject_speaker=result.subject_speaker,
            n_runs=result.n_runs, models=routes, stt=stt, preset=params.get("preset"),
            code_version=eval_info.code_version,
            params={k: v for k, v in params.items() if k != "stt_run"},
            has_clinician_rating=False,
            rating_coverage=RatingCoverage(rated=0, total=len(global_ids) + len(count_ids))),
        layout=[LayoutEntry(**e) for e in cfg.layout()],
        scorecard=scorecard, globals=globals_, behaviours=behaviours,
        summaries=onolys_summaries(d.data.get("summaries", []), agg.summaries),
        reasons_audit={"status": "skipped", "items": []},
        tips=list(tips.valid) if tips else [],
        method=Method(statement=cfg.method.statement, limits=[*cfg.method.limits, METHOD_LIMIT],
                      not_official_miti_coding=True, citation=cfg.method.citation),
        aggregates=Aggregates(globals_compared=0, avg_abs_global_difference=None,
                              within_one_share=None, counts_flagged=None),
        warnings=final_warnings,
        run_info=ReportRunInfo(evaluation=eval_info, miti=result.run_info))
