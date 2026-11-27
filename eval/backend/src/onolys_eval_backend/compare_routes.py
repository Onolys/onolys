"""Authenticated, read-only compare views with explicit public projections."""
import base64
import binascii
import json
from collections import defaultdict
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Query, Request
from onolys_eval._formulas import compute_summaries
from onolys_eval.gold import COUNT_IDS, GLOBAL_IDS
from onolys_eval.summary.analysis import build_verdict, compute_analysis
from onolys_eval.summary.gold_view import label_coverage
from onolys_eval.summary.line_metrics import (
    DATASET_NOTES,
    LineSession,
    _aligned,
    _label,
    compute_line_metrics,
    turn_agreement,
)
from onolys_eval.summary.operations import (
    coverage,
    excluded,
    final_attempts,
    gate,
    mark_skipped,
    operational,
    skipped_combo_keys,
    split_parsed,
)
from onolys_eval.summary.session_metrics import SessionInput, compute_metrics, kind
from onolys_eval.summary.source import SourceNotFound
from onolys_eval.summary.transcript_view import TranscriptChanged

from onolys_eval_backend.compare_load import (
    CompareLoader,
    GoldHashMismatch,
    ReadLimitExceeded,
    ServiceEvalRunSource,
)

router = APIRouter(prefix="/v1/eval-runs/{eval_run_id}/compare")


def _error(status, code):
    raise HTTPException(status, {"code": code, "message": code.replace("_", " ")})


@dataclass
class View:
    loader: CompareLoader
    projection: object
    combos: list
    keys: list
    skipped: set
    sessions: list
    line_sessions: list
    metrics: object
    ops: dict
    common: dict


def _view(request, eval_run_id, combos):
    services = request.app.state.services
    loader = CompareLoader(ServiceEvalRunSource(services), services.prices,
                           request.app.state.compare_cache)
    try:
        projection = loader.load(eval_run_id)
    except SourceNotFound:
        _error(404, "not_found")
    except GoldHashMismatch:
        _error(409, "gold_changed")
    except ReadLimitExceeded:
        _error(409, "compare_limit_exceeded")
    group = projection.group
    code = gate(group, projection.attempts)
    if code:
        _error(409, code)
    available = {c["combo_key"]: c for c in group["combos"]}
    keys = list(dict.fromkeys(combos.split(","))) if combos else list(available)
    if not keys or any(k not in available for k in keys):
        _error(422, "invalid_combos")
    selected = [available[k] for k in keys]
    pairs = [(r.cell, r.parsed) for r in projection.runs]
    runs, bad = split_parsed(pairs)
    sessions = [SessionInput(sid, s.gold, runs.get(sid, {}))
                for sid, s in projection.sessions.items()]
    line_sessions = [LineSession(sid, s.gold, s.turns, runs.get(sid, {}))
                     for sid, s in projection.sessions.items() if not s.transcript_changed]
    skipped = skipped_combo_keys(group) & set(keys)
    active = [k for k in keys if k not in skipped]
    metrics = mark_skipped(compute_metrics(sessions, active or keys), skipped)
    # Operational metadata comes from saved RunDocs for completed runs, including their
    # pinned route cost. Failed cells retain SP05's saved usage/error metadata.
    docs = {r.cell["run_id"]: r.doc for r in projection.runs}
    attempts = []
    for original in projection.attempts:
        cell = dict(original)
        doc = docs.get(cell.get("run_id"), {})
        for field in ("started", "ended", "run_info", "error"):
            if doc.get(field) is not None:
                cell[field] = doc[field]
        attempts.append(cell)
    ops = operational(attempts, selected, services.prices, bad)
    for combo in selected:
        key = combo["combo_key"]
        mine = [r for r in projection.runs if r.cell["combo_key"] == key
                and (r.doc.get("run_info") or {}).get("usage") is not None]
        costs = [r.cost.cost_usd for r in mine]
        final_failed = [c for c in final_attempts(attempts)
                        if c["combo_key"] == key and c["status"] == "failed"]
        costs += [services.prices.estimate(c["run_info"]["usage"], combo["litellm_id"]).cost_usd
                  for c in final_failed if (c.get("run_info") or {}).get("usage") is not None]
        if costs:
            unknown = next(("no price for " + ((r.doc.get("eval") or {})
                            .get("resolved_route") or {}).get("litellm_id", "unknown")
                            for r in mine if r.cost.cost_usd is None),
                           "no price for " + combo["litellm_id"])
            ops[key]["cost"] = {
                "total_usd": None if None in costs else sum(costs),
                "per_run_usd": None if None in costs else sum(costs) / len(costs),
                "n": len(costs), "na": {"reason": unknown} if None in costs else None}
    final = final_attempts(projection.attempts)
    selected_final = [c for c in final if c["combo_key"] in keys]
    cov = coverage(group, selected_final, bad)
    if not any(r.parsed.status == "ok" for r in projection.runs):
        _error(409, "no_completed_runs")
    common = {
        "eval_run_id": eval_run_id,
        "has_human": any(s.gold.counts or s.gold.globals or s.gold.quality_label
                         or s.gold.utterance_codes is not None
                         for s in projection.sessions.values()),
        "combos": [{"combo_key": c["combo_key"], "engine": c["engine"],
                    "model": c.get("model"), "tier": c.get("tier"), "effort": c.get("effort")}
                   for c in selected],
        "coverage": cov,
        # Readable dataset session name (e.g. "high-001") per internal sid, for display only.
        "session_labels": {s["session_id"]: s.get("dataset_session_id") or s["session_id"]
                           for s in group["sessions"]},
        "excluded": [e for e in excluded(final, bad) if e["combo_key"] in keys]
                    + [e for e in metrics.excluded
                       if e["combo_key"] is None or e["combo_key"] in keys],
    }
    return View(loader, projection, selected, keys, skipped, sessions, line_sessions,
                metrics, ops, common)


@router.get("/overview")
def overview(request: Request, eval_run_id: str, combos: str | None = None):
    v = _view(request, eval_run_id, combos)
    group, m = v.projection.group, v.metrics
    labels = label_coverage(group.get("dataset_id"))
    header = {"name": group.get("name"), "dataset_id": group.get("dataset_id"),
              "sessions": len(v.sessions), "repeats": group["repeats"],
              "progress": group.get("progress") or {
                  key: group.get(key) or 0
                  for key in ("done_units", "total_units", "skipped_units")},
              "line_sessions": [{"session_id": sid, "matched_lines": None
                  if s.transcript_changed else len(_aligned(
                      LineSession(sid, s.gold, s.turns, {}), frozenset(s.gold.counts)))}
                  for sid, s in v.projection.sessions.items()],
              "label_coverage": None if labels is None else {
                  "counts": list(labels.counts), "globals": list(labels.globals),
                  "line_labels": labels.line_labels}, "coverage": v.common["coverage"]}
    for metric, row in m.human.items():
        values = []
        for session in v.sessions:
            raw = {**session.human.counts, **session.human.globals,
                   **compute_summaries(session.human.counts, session.human.globals)}
            if raw.get(metric) is not None:
                values.append({"session_id": session.session_id, "value": raw[metric]})
        row["values"] = values
    count_error = m.cells["count_error"]
    quality = _leaderboard_quality(v)
    best = _operational_best(v)
    heatmap_rows = (*COUNT_IDS, *GLOBAL_IDS, "reflection_question_ratio", "pct_cr")
    return {**v.common, "header": header, "count_error": count_error,
            "verdict": build_verdict({"count_error": count_error, "skipped_combos": v.skipped}),
            "leaderboard": [{"combo_key": key, **count_error[key], **v.ops[key],
                             **quality[key], "operational_best": best[key]} for key in v.keys],
            "heatmap": {"rows": [{"id": key, "kind": kind(key)} for key in heatmap_rows],
                        "human": {k: m.human[k] for k in heatmap_rows},
                        "cells": {k: m.cells[k] for k in heatmap_rows}},
            "cohorts": m.cohorts,
            "footnotes": ["Sessions have equal weight; repeats are averaged within each session.",
                          "Started resets on re-claim; retried_runs counts retried cells."]}


def _line_cohort(v):
    codes = [k for k in COUNT_IDS if any(k in s.human.counts for s in v.sessions)]
    active = [k for k in v.keys if k not in v.skipped]
    paired = [s for s in v.line_sessions if all(s.runs.get(k) for k in active)]
    return codes, active, paired


def _line_metrics(v):
    codes, active, paired = _line_cohort(v)
    result = compute_line_metrics(paired, active,
                                  codes, v.projection.group.get("dataset_id"))
    return {"missing": result.missing, "codes_labeled": list(result.codes_labeled),
            "dataset_notes": result.dataset_notes, "combos": {
                key: {"lane": c.lane, "n": c.sessions, "repeats": c.repeats,
                      "aligned": c.aligned, "per_code": c.per_code, "macro_f1": c.macro_f1,
                      "line_accuracy": c.line_accuracy, "confusion": c.confusion, "multi": c.multi}
                for key, c in result.combos.items()}}


def _operational_best(v):
    """Lowest observed operations, with ties; skipped, wholly failed and missing data never win."""
    final = final_attempts(v.projection.attempts)
    finished = {c["combo_key"] for c in final if c["status"] in ("done", "failed")}
    succeeded = {c["combo_key"] for c in final if c["status"] == "done"}
    failed_only = finished - succeeded
    values = {key: {
        "failures": sum(f["count"] for f in v.ops[key]["failures"])
                    if key in finished else None,
        "cost": v.ops[key]["cost"]["per_run_usd"]
                if v.ops[key]["cost"]["n"] and not v.ops[key]["cost"]["na"] else None,
        "time": v.ops[key]["time"]["mean_seconds"] if v.ops[key]["time"]["n"] else None}
        for key in v.keys if key not in v.skipped and key not in failed_only}
    best = {key: dict.fromkeys(("failures", "cost", "time"), False) for key in v.keys}
    for metric in ("failures", "cost", "time"):
        eligible = [row[metric] for row in values.values() if row[metric] is not None]
        if eligible:
            for key, row in values.items():
                best[key][metric] = row[metric] == min(eligible)
    return best


def _quality_cell(value, n, repeats, reason):
    return {"value": value, "n": n if value is not None else 0, "repeats": repeats,
            "best": False, "na": {"reason": reason} if value is None else None}


def _leaderboard_quality(v):
    """Session-balanced within-one share and line scores; larger is better for these cells."""
    lines = _line_metrics(v)
    active = [k for k in v.keys if k not in v.skipped]
    paired = [s for s in v.sessions if s.human.globals and all(s.runs.get(k) for k in active)]
    result = {}
    for key in v.keys:
        skipped = key in v.skipped
        shares = []
        repeats = 0
        if not skipped:
            for session in paired:
                runs = session.runs[key]
                repeats = max(repeats, len(runs))
                shares.append(sum(abs(run.globals[metric] - human) <= 1
                                  for metric, human in session.human.globals.items()
                                  for run in runs) / (len(session.human.globals) * len(runs)))
        reason = "skipped: provider unavailable" if skipped else "not labeled in this dataset"
        if not paired and any(s.human.globals for s in v.sessions) and not skipped:
            reason = "no paired sessions"
        result[key] = {"globals_within_1": _quality_cell(
            sum(shares) / len(shares) if shares else None, len(shares), repeats, reason)}
        line = lines["combos"].get(key, {})
        line_reason = "skipped: provider unavailable" if skipped else (
            "no human line labels" if lines["missing"] else
            line.get("lane") or "no aligned clinician turns")
        for metric in ("line_accuracy", "macro_f1"):
            result[key][metric] = _quality_cell(line.get(metric), line.get("n", 0),
                                                line.get("repeats", 0), line_reason)
    for metric in ("globals_within_1", "line_accuracy", "macro_f1"):
        values = [row[metric]["value"] for row in result.values()
                  if row[metric]["value"] is not None]
        if values:
            for row in result.values():
                row[metric]["best"] = row[metric]["value"] == max(values)
    return result


@router.get("/deep-dive")
def deep_dive(request: Request, eval_run_id: str, combos: str | None = None):
    v = _view(request, eval_run_id, combos)
    dots, totals, biases = [], [], {}
    for s in v.sessions:
        for key in v.keys:
            runs = s.runs.get(key, ()) if key not in v.skipped else ()
            for metric in GLOBAL_IDS:
                dots.append({"session_id": s.session_id, "combo_key": key, "metric": metric,
                             "human": s.human.globals.get(metric),
                             "values": [r.globals[metric] for r in runs], "n": int(bool(runs)),
                             "repeats": len(runs)})
            totals.append({"session_id": s.session_id, "combo_key": key,
                           "human": dict(s.human.counts),
                           "values": [dict(r.counts) for r in runs],
                           "n": int(bool(runs)), "repeats": len(runs)})
    for metric in COUNT_IDS:
        biases[metric] = {}
        for key in v.keys:
            cell = v.metrics.cells[metric][key]
            # Bias percent uses the same paired sessions as the underlying cell.
            paired = [s for s in v.sessions if metric in s.human.counts and all(
                s.runs.get(k) for k in v.keys if k not in v.skipped)]
            human = sum(s.human.counts[metric] for s in paired) / len(paired) if paired else 0
            biases[metric][key] = {"value": cell["bias"] / human * 100
                                    if cell["bias"] is not None and human else None,
                                    "n": cell["n"], "na": cell["na"] or (
                                        None if human else {"reason": "human count is zero"})}
    counts = defaultdict(lambda: defaultdict(int))
    for run in v.projection.runs:
        if run.cell["combo_key"] in v.keys and run.parsed.status == "ok":
            for instance in run.parsed.instances:
                counts[instance.code][run.cell["combo_key"]] += 1
    return {**v.common, "cohorts": v.metrics.cohorts,
            "globals": {"cells": {k: v.metrics.cells[k] for k in GLOBAL_IDS}, "dots": dots},
            "counts": {"cells": {k: v.metrics.cells[k] for k in COUNT_IDS},
                       "human": {k: _paired_human(v.metrics, k) for k in COUNT_IDS},
                       "totals": totals, "bias_pct": biases},
            "lines": _line_metrics(v), "rationale_counts": dict(counts)}


def _paired_human(metrics, metric):
    # The session-balanced signed bias is AI mean minus human mean on this exact
    # cohort. Reuse those calculated values instead of selecting a second cohort.
    cells = metrics.cells[metric].values()
    cell = next((c for c in cells if c["value"] is not None), None)
    reason = next((c["na"] for c in metrics.cells[metric].values() if c["na"]),
                  {"reason": "no paired sessions"})
    return {**metrics.human[metric],
            "value": cell["value"] - cell["bias"] if cell else None,
            "na": None if cell else reason}


@router.get("/line-matches")
def line_matches(request: Request, eval_run_id: str, combo: str, code: str, metric: str,
                 combos: str | None = None):
    """Bounded session IDs for a confusion cell, or the aggregate multi bucket."""
    v = _view(request, eval_run_id, combos)
    allowed = (*COUNT_IDS, "none", "multi")
    if combo not in v.keys or code not in allowed or metric not in allowed:
        _error(422, "invalid_filter")
    codes, active, paired = _line_cohort(v)
    labeled = [s for s in paired if s.human.utterance_codes is not None]
    if combo not in active or any(not r.has_lines for s in labeled
                                 for r in s.runs.get(combo, ())):
        return {"session_ids": []}
    universe = frozenset(codes)
    matched = []
    for session in labeled:
        for tid, human in _aligned(session, universe):
            row = _label(human)
            labels = [(row, _label(r.turn_codes.get(tid, frozenset()) & universe))
                      for r in session.runs.get(combo, ())]
            if any((a is None or b is None) if code == metric == "multi" else
                   (a == code and b == metric) for a, b in labels):
                matched.append(session.session_id)
                break
    return {"session_ids": matched}


@router.get("/analysis")
def analysis(request: Request, eval_run_id: str, combos: str | None = None):
    v = _view(request, eval_run_id, combos)
    return {**v.common, **compute_analysis(v.sessions, v.keys, v.ops,
                line_sessions=v.line_sessions, skipped_combos=v.skipped)}


def _snippet(run, instance):
    turn = next((t for t in run.turns if t.id == instance.turn_id), None)
    verified = turn is not None and instance.quote in turn.text
    text = run.parsed.rationales[instance.ref]
    return {"session_id": run.cell["sid"], "combo_key": run.cell["combo_key"],
            "repeat": run.cell["repeat"], "turn_id": instance.turn_id,
            "quote": instance.quote if verified else None, "quote_verified": verified,
            "rationale": text, "withheld": text == ""}


def _cursor_decode(cursor, scope):
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor))
        if data["scope"] == scope and type(data["offset"]) is int and data["offset"] >= 0:
            return data["offset"]
    except (ValueError, TypeError, KeyError, binascii.Error):
        pass
    _error(422, "invalid_cursor")


def _human_notes(v, code, session):
    rows = []
    for sid, saved in v.projection.sessions.items():
        if saved.transcript_changed or session is not None and sid != session:
            continue
        line_session = LineSession(sid, saved.gold, saved.turns, {})
        aligned = dict(_aligned(line_session, frozenset(saved.gold.counts)))
        for row in saved.gold.utterance_codes or ():
            if not row.note or row.turn_id not in aligned:
                continue
            for metric in sorted(aligned[row.turn_id]):
                if code is None or code == metric:
                    rows.append((metric, "human_notes", {
                        "session_id": sid, "turn_id": row.turn_id, "note": row.note}))
    return rows


@router.get("/reasoning")
def reasoning(request: Request, eval_run_id: str, combos: str | None = None,
              code: str | None = None, combo: str | None = None,
              session: str | None = None, kind: str | None = None,
              cursor: str | None = Query(None, max_length=2048)):
    v = _view(request, eval_run_id, combos)
    if combo and combo not in v.keys or code and code not in (*COUNT_IDS, *GLOBAL_IDS) \
            or kind not in (None, "global"):
        _error(422, "invalid_filter")
    if session is not None and session not in v.projection.sessions:
        _error(404, "not_found")
    scope = [eval_run_id, v.keys, code, combo, session, kind]
    offset = _cursor_decode(cursor, scope) if cursor else 0
    rows = []
    for run in v.projection.runs:
        if run.parsed.status != "ok" or run.cell["combo_key"] not in v.keys \
                or combo and run.cell["combo_key"] != combo \
                or session is not None and run.cell["sid"] != session:
            continue
        if kind is None:
            for inst in run.parsed.instances:
                if code is None or code == inst.code:
                    rows.append((inst.code, "snippets", _snippet(run, inst)))
        for metric, reason in run.parsed.global_reasons.items():
            if code is None or code == metric:
                turns = {t.id: t for t in run.turns}
                rows.append((metric, "snippets", {"session_id": run.cell["sid"],
                    "combo_key": run.cell["combo_key"], "repeat": run.cell["repeat"],
                    "rationale": reason.reason, "withheld": reason.reason == "",
                    "evidence": [{"turn_id": e.turn_id, "quote": e.quote}
                                 for e in reason.evidence if e.turn_id in turns
                                 and e.quote in turns[e.turn_id].text]}))
    # Gold notes share the same page budget and are omitted for AI-only/global requests.
    if combo is None and kind is None:
        rows.extend(_human_notes(v, code, session))
    grouped = {}
    for metric, section, snippet in rows[offset:offset + 50]:
        group = grouped.setdefault(metric, {"code": metric, "snippets": []})
        group.setdefault(section, []).append(snippet)
    next_cursor = base64.urlsafe_b64encode(json.dumps({"scope": scope, "offset": offset + 50})
                                         .encode()).decode() if len(rows) > offset + 50 else None
    return {**v.common, "groups": list(grouped.values()), "next_cursor": next_cursor}


def _session(v, sid):
    if sid not in v.projection.sessions:
        _error(404, "not_found")
    try:
        turns = v.loader.session_turns(v.projection, sid)
    except TranscriptChanged:
        _error(409, "transcript_changed")
    except SourceNotFound:
        _error(404, "not_found")
    s = next(s for s in v.sessions if s.session_id == sid)
    return s, turns


def _lanes(v, s, turns):
    universe = set(s.human.counts)
    aligned = {t.id for t in turns if t.is_clinician}
    human = {row.turn_id: row for row in s.human.utterance_codes or ()
             if row.turn_id in aligned}
    lanes = {"human": {tid: sorted(set(row.codes) & universe) for tid, row in human.items()}}
    disagreement = dict.fromkeys((t.id for t in turns), False)
    for key in v.keys:
        runs = s.runs.get(key, ())
        no_lines = any(not r.has_lines for r in runs) or next(
            c for c in v.combos if c["combo_key"] == key)["engine"] != "miti"
        lane = {"missing": "no line-level output" if no_lines else None,
                "n": int(bool(runs)), "repeats": len(runs), "turns": {}}
        if not no_lines:
            for t in turns:
                sets = [sorted(r.turn_codes.get(t.id, frozenset()) & universe) for r in runs]
                lane["turns"][t.id] = sets
                if t.id in human and any(set(x) != set(human[t.id].codes) & universe for x in sets):
                    disagreement[t.id] = True
        lanes[key] = lane
    return lanes, disagreement


@router.get("/sessions/{sid}/lines")
def session_lines(request: Request, eval_run_id: str, sid: str, combos: str | None = None):
    v = _view(request, eval_run_id, combos)
    s, turns = _session(v, sid)
    missing = "human" if s.human.utterance_codes is None else None
    lanes, disagreement = _lanes(v, s, turns) if not missing else ({}, {})
    return {**v.common, "session_id": sid, "turns": [t.to_dict() for t in turns],
            "gold": s.human.to_dict(), "missing": missing, "lanes": lanes,
            "disagreement": disagreement,
            "globals": {"human": dict(s.human.globals), "combos": {
                key: [dict(r.globals) for r in s.runs.get(key, ())] for key in v.keys}},
            "dataset_notes": [DATASET_NOTES[v.projection.group["dataset_id"]]]
            if v.projection.group.get("dataset_id") in DATASET_NOTES else []}


@router.get("/sessions/{sid}/lines/{turn_id}")
def turn_popup(request: Request, eval_run_id: str, sid: str, turn_id: str,
               combos: str | None = None):
    v = _view(request, eval_run_id, combos)
    s, turns = _session(v, sid)
    turn = next((t for t in turns if t.id == turn_id), None)
    if turn is None:
        _error(404, "not_found")
    human = next((row for row in s.human.utterance_codes or () if row.turn_id == turn_id), None)
    combos_out = {}
    for key in v.keys:
        loaded = [r for r in v.projection.runs if r.cell["sid"] == sid
                  and r.cell["combo_key"] == key and r.parsed.status == "ok"]
        runs = [r.parsed for r in loaded]
        no_lines = any(not r.has_lines for r in runs) or next(
            c for c in v.combos if c["combo_key"] == key)["engine"] != "miti"
        combos_out[key] = {"missing": "no line-level output" if no_lines else None,
            "codes": [sorted(r.turn_codes.get(turn_id, frozenset()) & set(s.human.counts))
                      for r in runs]
                     if not no_lines else [],
            "rationales": [_snippet(r, i) for r in loaded for i in r.parsed.instances
                           if i.turn_id == turn_id],
            "agree": turn_agreement(human.codes, runs, turn_id, list(s.human.counts))
                     if human and not no_lines else None}
    return {**v.common, "session_id": sid, "turn_id": turn_id, "text": turn.text,
            "human": {"codes": list(human.codes), "note": human.note} if human else None,
            "combos": combos_out if s.human.utterance_codes is not None else {},
            "missing": "human" if s.human.utterance_codes is None else None}
