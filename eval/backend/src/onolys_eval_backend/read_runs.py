"""Authenticated history, unit outputs, and reruns from saved snapshots."""

import base64
import binascii
import json
import logging
import re

from fastapi import APIRouter, HTTPException, Query, Request
from onolys_engine_core.errors import InputError
from pydantic import ConfigDict, Field, StrictInt

from onolys_eval_backend import eval_view
from onolys_eval_backend.eval_scheduler import ensure_tick
from onolys_eval_backend.eval_sessions import SessionImportError
from onolys_eval_backend.matrix import RunTooLarge, SelectionError, combo_key
from onolys_eval_backend.runs import (
    RunInputError,
    RunMetadata,
    RunRequest,
    SavedInputUnavailable,
    Selection,
    create_run,
)

router = APIRouter()
logger = logging.getLogger(__name__)
SUMMARY_FIELDS = (
    "name",
    "description",
    "status",
    "created_at",
    "cancel_requested",
    "cancelled_at",
    "input",
    "engines",
    "presets",
    "selection",
    "combos",
    "repeats",
    "change_goal",
    "language",
    "coded_span",
    "total_units",
    "skipped_units",
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
    "resolved_combos",
    "base_preset",
)
def _valid_id(value):
    # Reject Firestore path syntax before passing any document ID to a repository.
    return re.fullmatch(r"[A-Za-z0-9_-]+", value) is not None


def _run(repository, rid):
    run = repository.get_run(rid) if _valid_id(rid) else None
    if run is None:
        raise HTTPException(404, "Run not found.")
    return run


def is_legacy(run):
    """Stored pre-matrix runs carry preset names and no combo selection."""
    return bool(run.get("presets"))


def _label(key):
    if key.startswith("preset:"):
        return f"preset: {key[len('preset:'):]} (legacy)"
    return key


def _run_keys(run):
    if is_legacy(run):
        return [f"preset:{name}" for name in run["presets"]]
    return [combo_key(c) for c in run.get("combos") or []]


def run_summary(rid, run):
    """Allowlist the public saved fields so storage paths never become API fields."""
    legacy = is_legacy(run)
    keys = _run_keys(run)
    out = {"run_id": rid, **{key: run.get(key) for key in SUMMARY_FIELDS}}
    error = run.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    out["error"] = {"code": code} if code else None  # code only; never the raw error body
    out["skipped_units"] = run.get("skipped_units") or 0
    out["provider_skips"] = eval_view.provider_skips(run)
    if out["resolved_combos"] is None:
        out["resolved_combos"] = (run.get("saved_config") or {}).get("resolved_combos")
    if legacy:
        out["selection"] = out["combos"] = None
    return {
        **out,
        "legacy_selection": legacy,
        "combo_keys": keys,
        "combo_labels": {key: _label(key) for key in keys},
    }


def _decode_cursor(cursor):
    try:
        created_at, rid = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if isinstance(created_at, str) and isinstance(rid, str) and _valid_id(rid):
            return created_at, rid
    except (ValueError, TypeError, binascii.Error):
        pass
    raise HTTPException(422, "Invalid cursor.")


def _encode_cursor(created_at, rid):
    return base64.urlsafe_b64encode(json.dumps([created_at, rid]).encode()).decode()


@router.get("/v1/runs")
def history(
    request: Request,
    limit: int = Query(100, ge=1, le=200),
    cursor: str | None = Query(None, max_length=512),
):
    """Newest first. `next_cursor` (null on the last page) continues the listing."""
    repository = request.app.state.services.repository
    runs, more = repository.list_runs_page(limit, _decode_cursor(cursor) if cursor else None)
    last = list(runs.items())[-1] if runs else None
    return {
        "runs": [run_summary(rid, run) for rid, run in runs.items()],
        "next_cursor": _encode_cursor(last[1]["created_at"], last[0]) if more and last else None,
    }


@router.get("/v1/runs/{run_id}")
def run_detail(request: Request, run_id: str):
    services = request.app.state.services
    run = _run(services.repository, run_id)
    try:  # safety net only: a stalled tick chain is restarted; nothing else needs GET to finish
        ensure_tick(services, run_id, run)
    except Exception:
        logger.exception("tick_reenqueue_failed", extra={"eval_run_id": run_id})
    units = eval_view.build_units(services, run)
    # Outputs are fetched through /units/{id}/output; compare has dedicated read routes.
    return {
        **run_summary(run_id, run),
        "units": units,
        "provider_cooldowns": eval_view.provider_cooldowns(services, run),
    }


@router.get("/v1/runs/{run_id}/units/{unit_id}/output")
def unit_output(request: Request, run_id: str, unit_id: str):
    services = request.app.state.services
    run = _run(services.repository, run_id)
    # Only units of this eval run resolve: a run id from another group, or any path, is a 404.
    output = eval_view.output_for(services, run, unit_id) if _valid_id(unit_id) else None
    if not isinstance(output, dict):
        raise HTTPException(404, "Unit output not found.")
    return output


class RerunRequest(RunMetadata):
    model_config = ConfigDict(extra="forbid")
    engines: list[str] = Field(min_length=1)
    selection: Selection = Field(default_factory=Selection)
    repeats: StrictInt = 1


@router.post("/v1/runs/{run_id}/rerun")
def rerun(request: Request, run_id: str, body: RerunRequest):
    services = request.app.state.services
    saved = _run(services.repository, run_id)
    if not saved.get("sessions"):
        # Runs saved before the grouping doc carry no pinned sessions to reuse.
        raise HTTPException(422, "Invalid run selection or saved input.")
    try:
        selection = RunRequest.model_validate(
            {
                **body.model_dump(),
                **{
                    key: saved.get(key)
                    for key in ("name", "description")
                    if key not in body.model_fields_set
                },
                "input": saved["input"],
                **{key: saved.get(key) for key in ("change_goal", "language", "coded_span")},
            }
        )
        rid, status = create_run(
            services,
            request.app.state.config,
            selection,
            request.state.user_email,
            registry=getattr(services, "registry", None) or request.app.state.catalog.registry,
            pinned=saved.get("sessions") or None,
            saved_config=saved.get("saved_config"),
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
    except (RunInputError, SessionImportError) as error:
        raise HTTPException(422, str(error)) from None
    except SavedInputUnavailable as error:
        raise HTTPException(409, str(error)) from None
    except (ValueError, KeyError, FileNotFoundError, InputError):
        raise HTTPException(422, "Invalid run selection or saved input.") from None
    except Exception:
        raise HTTPException(503, "Run creation unavailable.") from None
