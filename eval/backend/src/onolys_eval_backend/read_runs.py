"""Authenticated history, comparisons on read, and reruns from saved snapshots."""

import re
from importlib.resources import files

import yaml
from fastapi import APIRouter, HTTPException, Request
from onolys_engine_core.errors import InputError
from onolys_eval._formulas import compute_summaries
from onolys_eval.gold import COUNT_IDS, GLOBAL_IDS
from onolys_eval.metrics import Scores, aggregate, compare
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from onolys_eval_backend.matrix import RunTooLarge, SelectionError
from onolys_eval_backend.runs import RunRequest, Selection, create_run
from onolys_eval_backend.storage import load_output

router = APIRouter()
SUMMARY_IDS = ("reflection_question_ratio", "pct_cr")
METRIC_IDS = (*COUNT_IDS, *GLOBAL_IDS, *SUMMARY_IDS)
SUMMARY_FIELDS = (
    "status",
    "created_at",
    "input",
    "engines",
    "presets",
    "repeats",
    "change_goal",
    "language",
    "coded_span",
    "total_units",
    "completed_units",
    "done_units",
    "failed_units",
    "cancelled_units",
    "usage",
    "cost_usd_est",
    "unpriced_units",
    "engine_versions",
    "engine_git_sha",
    "resolved_presets",
)
_PACK = yaml.safe_load(files("onolys_miti").joinpath("data/pack.yaml").read_text())
_LABELS = {item["id"]: item["label"] for item in [*_PACK["items"], *_PACK["summaries"]]}
METRICS = [
    {"id": key, "group": group, "label": _LABELS[key]}
    for group, keys in [("counts", COUNT_IDS), ("globals", GLOBAL_IDS), ("summaries", SUMMARY_IDS)]
    for key in keys
]


def _valid_id(value):
    # Reject Firestore path syntax before passing any document ID to a repository.
    return re.fullmatch(r"[A-Za-z0-9_-]+", value) is not None


def _run(repository, rid):
    run = repository.get_run(rid) if _valid_id(rid) else None
    if run is None:
        raise HTTPException(404, "Run not found.")
    return run


def run_summary(rid, run):
    """Allowlist the public saved fields so storage paths never become API fields."""
    return {"run_id": rid, **{key: run.get(key) for key in SUMMARY_FIELDS}}


def _values(scores):
    return {
        **scores.counts,
        **scores.globals,
        **{
            key: value
            for key, value in compute_summaries(scores.counts, scores.globals).items()
            if key in SUMMARY_IDS
        },
    }


def _range(values):
    return {
        "mean": sum(values) / len(values) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "n": len(values),
    }


def build_compare(run, units):
    """Keep repeats as individual core comparisons; only presentation cells use means."""
    has_human = "human" in run["engines"]
    notes, sessions = [], []
    comparisons = {
        (engine, preset): []
        for engine in run["engines"]
        if engine != "human"
        for preset in run["presets"]
    }
    session_ids = run["input"].get("session_ids") or [run["input"].get("upload_id")]
    for sid in session_ids:
        selected = {uid: unit for uid, unit in units.items() if unit["session_id"] == sid}
        humans = [u for u in selected.values() if u["engine"] == "human"]
        human = next(
            (
                Scores.model_validate(u["scores"])
                for u in humans
                if u["status"] == "done" and u.get("scores") is not None
            ),
            None,
        )
        reference = _values(human) if human is not None else None
        for unit in selected.values():
            notes.extend(unit.get("warnings", []))
        cells = []
        for (engine, preset), errors in comparisons.items():
            cell_units = {
                uid: unit
                for uid, unit in selected.items()
                if unit["engine"] == engine and unit["preset"] == preset
            }
            successful = [
                Scores.model_validate(u["scores"])
                for u in cell_units.values()
                if u["status"] == "done" and u.get("scores") is not None
            ]
            values = [_values(score) for score in successful]
            ranges = {
                key: _range([row[key] for row in values if row[key] is not None])
                for key in METRIC_IDS
            }
            cell = {
                "engine": engine,
                "preset": preset,
                "n": len(successful),
                "failed": sum(u["status"] == "failed" for u in cell_units.values()),
                "unit_ids": list(cell_units),
                "values": ranges,
            }
            if has_human:
                cell["diff"] = {
                    key: (ranges[key]["mean"] - reference[key])
                    if reference is not None
                    and reference[key] is not None
                    and ranges[key]["mean"] is not None
                    else None
                    for key in METRIC_IDS
                }
            if human is not None:
                for score in successful:
                    comparison = compare(human, score)
                    errors.append(comparison)
                    notes.extend(comparison["notes"])
            cells.append(cell)
        sessions.append({"session_id": sid, "human": reference, "cells": cells})
    for source in run.get("input_ref", {}).get("sessions", []):
        caveat = source.get("provenance", {}).get("notes")
        if caveat:
            notes.append(f"{source['session_id']}: {caveat}")
    return {
        "has_human": has_human,
        "metrics": METRICS,
        "sessions": sessions,
        "aggregates": [
            {"engine": engine, "preset": preset, "metrics": aggregate(errors)}
            for (engine, preset), errors in comparisons.items()
        ]
        if has_human
        else [],
        "notes": list(dict.fromkeys(notes)),
    }


@router.get("/v1/runs")
def history(request: Request):
    repository = request.app.state.services.repository
    return {"runs": [run_summary(rid, run) for rid, run in repository.list_runs().items()]}


def _public_unit(run_id, unit_id, unit):
    spilled = unit.get("output_ref") == f"runs/{run_id}/{unit_id}.json"
    return {
        "unit_id": unit_id,
        **{
            key: value
            for key, value in unit.items()
            if key != "output_ref" and not (key == "output" and value is None and spilled)
        },
    }


@router.get("/v1/runs/{run_id}")
def run_detail(request: Request, run_id: str):
    repository = request.app.state.services.repository
    run = _run(repository, run_id)
    units = repository.list_units(run_id)
    return {
        **run_summary(run_id, run),
        "units": [
            _public_unit(run_id, uid, unit)
            for uid, unit in units.items()
        ],
        "compare": build_compare(run, units),
    }


@router.get("/v1/runs/{run_id}/units/{unit_id}/output")
def unit_output(request: Request, run_id: str, unit_id: str):
    services = request.app.state.services
    _run(services.repository, run_id)
    unit = services.repository.get_unit(run_id, unit_id) if _valid_id(unit_id) else None
    if unit is None:
        raise HTTPException(404, "Unit output not found.")
    # Never accept arbitrary paths, URLs, or another run's saved output reference.
    if unit.get("output_ref") and unit["output_ref"] != f"runs/{run_id}/{unit_id}.json":
        raise HTTPException(404, "Unit output not found.")
    try:
        output = load_output(services.bucket, unit)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "Unit output not found.") from None
    if not isinstance(output, dict):
        raise HTTPException(404, "Unit output not found.")
    return output


class RerunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engines: list[str] = Field(min_length=1)
    selection: Selection = Field(default_factory=Selection)
    repeats: StrictInt = 1


@router.post("/v1/runs/{run_id}/rerun")
def rerun(request: Request, run_id: str, body: RerunRequest):
    services = request.app.state.services
    saved = _run(services.repository, run_id)
    try:
        selection = RunRequest.model_validate(
            {
                **body.model_dump(),
                "input": saved["input"],
                **{key: saved.get(key) for key in ("change_goal", "language", "coded_span")},
            }
        )
        rid, status = create_run(
            services,
            request.app.state.config,
            selection,
            request.state.admin_claims["email"].strip().lower(),
            registry=getattr(services, "registry", None) or request.app.state.catalog.registry,
            input_ref=saved["input_ref"],
        )
        return {
            "run_id": rid,
            "status": status,
            "engines": services.repository.get_run(rid)["engines"],
        }
    except HTTPException:
        raise
    except (SelectionError, RunTooLarge) as error:
        raise HTTPException(422, str(error)) from None
    except (ValueError, KeyError, FileNotFoundError, InputError):
        raise HTTPException(422, "Invalid run selection or saved input.") from None
    except Exception:
        raise HTTPException(503, "Run creation unavailable.") from None
