"""Read adapter: legacy-shaped units built from RunDocs, ReportDocs and gold.

The group doc (`eval_runs/{id}`) holds only refs; everything else is read from the prod pipeline
on demand. Scores are computed on read (`miti_lean_scores` / `oneshot_scores` / `gold_scores`),
never stored. `list_cells`, `load_report` and `load_gold` are the surface the compare summary uses.

A Cell is `{sid, dataset_session_id, engine, combo_key, repeat, attempt, run_id, status, started,
ended, error, run_info{usage, cost_usd_est}, gold_ref}`, ordered session -> plan -> attempt. The
final attempt of a (sid, engine, combo_key, repeat) is its highest `attempt`; earlier failed
attempts stay listed. A planned cell with no run yet is listed as one placeholder (`queued`,
`skipped` or `cancelled`, `run_id` None).
"""

import hashlib
import json
import logging

from onolys_api.repo.base import NotFoundError
from onolys_api.storage.base import BlobNotFoundError
from onolys_eval.adapters import miti_lean_scores, oneshot_scores
from onolys_eval.gold import Gold
from onolys_eval.metrics import gold_scores

from onolys_eval_backend.eval_scheduler import plan_cells, provider_of

logger = logging.getLogger(__name__)
# Scheduler-level states the RunDoc cannot express; they win over the RunDoc status.
REF_STATES = {"waiting", "skipped", "cancelled"}
RUN_STATES = {"pending": "queued", "running": "running", "done": "done", "failed": "failed"}
STAGE_LABELS = {"code": "coding", "tips": "tips", "assemble": "assembling"}
ZERO_USAGE ={"input_tokens": 0, "output_tokens": 0, "calls": 0}


def human_unit_id(sid: str) -> str:
    return f"human-{sid}"


def placeholder_unit_id(sid: str, cell: dict, attempt: int = 0) -> str:
    """Stable id for a cell with no RunDoc (queued, skipped, drift-failed)."""
    raw = f"{sid}|{cell['engine']}|{cell['combo_key']}|{cell['repeat']}|{attempt}"
    return "cell-" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def _uid(services) -> str:
    return services.config.eval_owner_uid


def _ordered_sessions(doc: dict) -> list[tuple[str, dict]]:
    return sorted((doc.get("sessions") or {}).items(), key=lambda kv: kv[1].get("order", 0))


def provider_skips(doc: dict) -> list[dict]:
    """Group-doc `provider_skips` ({provider: {...}}) as the public list; tolerant of absence."""
    raw = doc.get("provider_skips") or {}
    if isinstance(raw, list):
        return [dict(item) for item in raw]
    return [{"provider": name, **(value or {})} for name, value in raw.items()]


def provider_cooldowns(services, doc: dict) -> list[dict]:
    """`cooldown_until` of each provider the run uses, from its `eval_slots/{provider}` doc."""
    names = []
    for resolved in ((doc.get("saved_config") or {}).get("resolved_combos") or {}).values():
        name = str(resolved.get("litellm_id", "")).split("/")[0]
        if name and name not in names:
            names.append(name)
    out = []
    for name in names:
        until = (services.repository.get_slots(name) or {}).get("cooldown_until")
        if until:
            out.append({"provider": name, "cooldown_until": until})
    return out


def _gold_ref(services, sid: str) -> dict | None:
    try:
        info = services.repo.get_session(_uid(services), sid).eval
    except NotFoundError:
        return None
    gold = info.gold if info is not None else None
    return {"sha256": gold.sha256, "path": gold.path} if gold is not None else None


def load_gold(services, sid: str) -> dict | None:
    """The session's gold JSON (copied once to `gold/<sha256>.json`), or None without gold."""
    ref = _gold_ref(services, sid)
    if ref is None:
        return None
    try:
        return json.loads(services.blobs.get_bytes(ref["path"]))
    except (BlobNotFoundError, FileNotFoundError, ValueError):
        return None


def load_report(services, cell: dict) -> dict | None:
    """The ReportDoc body of a cell's run (blob pointer resolved), or None."""
    if not cell.get("run_id"):
        return None
    try:
        return services.repo.get_report(_uid(services), cell["sid"], cell["run_id"]).report
    except NotFoundError:
        return None


def _cost(services, doc: dict, cell: dict, usage: dict) -> float | None:
    try:
        litellm_id = doc["saved_config"]["resolved_combos"][cell["combo_key"]]["litellm_id"]
        return services.prices.estimate(usage, litellm_id).cost_usd
    except Exception:  # noqa: BLE001 - missing or broken price data must never block a read
        return usage.get("cost_usd")


def _status(ref: dict, run) -> str:
    if ref.get("status") in REF_STATES:
        return ref["status"]
    if run is not None:
        return RUN_STATES.get(run.status, run.status)
    return ref.get("status") or "queued"


def _placeholder_status(doc: dict, cell: dict) -> str:
    try:
        if any(s.get("provider") == provider_of(doc, cell) for s in provider_skips(doc)):
            return "skipped"
    except (KeyError, TypeError):
        pass
    if doc.get("cancelled_at") or doc.get("status") in ("cancelled", "partial"):
        return "cancelled"
    return "queued"


def _build_cell(services, doc, sid, entry, gold_ref, plan, ref, run) -> dict:
    usage = (run.run_info or {}).get("usage") if run is not None else None
    code = (run.error if run is not None and run.error else None) or ref.get("error")
    cell = {
        "sid": sid,
        "dataset_session_id": entry.get("dataset_session_id"),
        "engine": plan["engine"],
        "combo_key": plan["combo_key"],
        "repeat": plan["repeat"],
        "attempt": ref.get("attempt", 0),
        "run_id": ref.get("run_id"),
        "status": _status(ref, run),
        "started": run.started.isoformat() if run is not None and run.started else None,
        "ended": run.ended.isoformat() if run is not None and run.ended else None,
        "error": {"code": code} if code else None,
        "run_info": None,
        "gold_ref": gold_ref,
    }
    if run is not None:
        cell["run_info"] = {
            "usage": {**ZERO_USAGE, **(usage or {})},
            "cost_usd_est": _cost(services, doc, plan, usage or {}),
        }
    return cell


def _cells(services, doc: dict) -> list[tuple[dict, dict, dict, object]]:
    """(cell, plan entry, session entry, RunDoc or None) in session -> plan -> attempt order."""
    out = []
    plan = plan_cells(doc)
    for sid, entry in _ordered_sessions(doc):
        refs = entry.get("runs") or []
        run_ids = [r["run_id"] for r in refs if r.get("run_id")]
        runs = {r.run_id: r for r in services.repo.get_runs(_uid(services), sid, run_ids)}
        gold_ref = _gold_ref(services, sid)
        for item in plan:
            mine = sorted(
                (
                    r for r in refs
                    if (r.get("engine"), r.get("combo_key"), r.get("repeat"))
                    == (item["engine"], item["combo_key"], item["repeat"])
                ),
                key=lambda r: r.get("attempt", 0),
            )
            if not mine:
                mine = [{"run_id": None, "attempt": 0, "status": _placeholder_status(doc, item)}]
            for ref in mine:
                run = runs.get(ref.get("run_id"))
                out.append((_build_cell(services, doc, sid, entry, gold_ref, item, ref, run),
                            item, entry, run))
    return out


def list_cells(services, eval_run_id: str, doc: dict | None = None) -> list[dict]:
    """Every cell of an eval run (all attempts), ordered session -> plan -> attempt."""
    doc = doc if doc is not None else services.repository.get_run(eval_run_id)
    return [t[0] for t in _cells(services, doc)] if doc else []


def _scores(services, cell: dict) -> tuple[dict | None, list[str]]:
    report = load_report(services, cell)
    if report is None:
        return None, ["Scores unavailable: the report could not be read."]
    try:
        project = oneshot_scores if cell["engine"].startswith("oneshot:") else miti_lean_scores
        return project(report).model_dump(mode="json"), []
    except Exception:  # noqa: BLE001 - one unreadable report must not break the whole view
        logger.warning("scores_unavailable", extra={"run_id": cell["run_id"]})
        return None, ["Scores unavailable: the report could not be scored."]


def _human_unit(services, sid: str, entry: dict) -> dict:
    gold = load_gold(services, sid)
    unit = {
        "unit_id": human_unit_id(sid),
        "session_id": entry.get("dataset_session_id"),
        "run_id": None,
        "prod_session_id": sid,
        "attempt": 0,
        "final": True,
        "engine": "human",
        "combo": None,
        "combo_key": None,
        "repeat": None,
        "status": "done" if gold is not None else "failed",
        "error": None if gold is not None else {"code": "gold_unavailable"},
        "run_info": {"usage": dict(ZERO_USAGE)},
        "cost_usd_est": 0.0,
    }
    if gold is not None:
        unit["scores"] = gold_scores(Gold.model_validate(gold)).model_dump(mode="json")
    return unit


def _live_stage(services, sid: str, cache: dict) -> str:
    """Label of the stage the worker is in. The worker writes it to the prod session's `step`
    (the RunDoc `stage` is never set while running); a run that started but has not reported a
    stage yet is `starting`."""
    if sid not in cache:
        try:
            cache[sid] = services.repo.get_session(_uid(services), sid).step
        except NotFoundError:
            cache[sid] = None
    return STAGE_LABELS.get(cache[sid], cache[sid]) if cache[sid] else "starting"


def live_counts(units: list[dict]) -> dict[str, int]:
    """Running and queued AI attempts (final attempts only; the human reference never runs)."""
    finals = [u for u in units if u["engine"] != "human" and u["final"]]
    return {
        "running_units": sum(u["status"] == "running" for u in finals),
        "queued_units": sum(u["status"] == "queued" for u in finals),
    }


def build_units(services, doc: dict) -> list[dict]:
    """Legacy-shaped units: Human per session, then every AI attempt in listing order."""
    combos = {item["combo_key"]: item["combo"] for item in plan_cells(doc)}
    triples = _cells(services, doc)
    finals = {}
    for cell, *_ in triples:
        key = (cell["sid"], cell["engine"], cell["combo_key"], cell["repeat"])
        finals[key] = max(finals.get(key, -1), cell["attempt"])
    units = []
    steps: dict[str, str | None] = {}
    for sid, entry in _ordered_sessions(doc):
        if "human" in doc.get("engines", []):
            units.append(_human_unit(services, sid, entry))
        for cell, _, _, run in (t for t in triples if t[0]["sid"] == sid):
            key = (sid, cell["engine"], cell["combo_key"], cell["repeat"])
            final = finals[key] == cell["attempt"]
            unit = {
                "unit_id": cell["run_id"] or placeholder_unit_id(sid, cell, cell["attempt"]),
                "session_id": cell["dataset_session_id"],
                "run_id": cell["run_id"],
                "prod_session_id": sid,
                "attempt": cell["attempt"],
                "final": final,
                "engine": cell["engine"],
                "combo": combos[cell["combo_key"]],
                "combo_key": cell["combo_key"],
                "repeat": cell["repeat"],
                "status": cell["status"],
                "error": cell["error"],
                "started": cell["started"],
                "ended": cell["ended"],
                "run_info": cell["run_info"],
                "cost_usd_est": (cell["run_info"] or {}).get("cost_usd_est"),
            }
            if cell["status"] == "running":
                unit["stage"] = (run.stage if run is not None else None) or _live_stage(
                    services, sid, steps)
            if cell["status"] == "done" and final:
                unit["scores"], warnings = _scores(services, cell)
                if warnings:
                    unit["warnings"] = warnings
            units.append(unit)
    return units


def output_for(services, doc: dict, unit_id: str) -> dict | None:
    """Report (or gold, for `human-<sid>`) of a unit that belongs to this eval run, else None."""
    sessions = doc.get("sessions") or {}
    if unit_id.startswith("human-"):
        sid = unit_id[len("human-"):]
        return load_gold(services, sid) if sid in sessions else None
    for sid, entry in sessions.items():
        if any(ref.get("run_id") == unit_id for ref in entry.get("runs") or []):
            return load_report(services, {"sid": sid, "run_id": unit_id})
    return None
