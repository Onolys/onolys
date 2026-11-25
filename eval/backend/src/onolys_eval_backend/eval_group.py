"""The `eval_runs/{id}` grouping doc (05 R4): the single rollup record of an eval run.

Run refs are embedded (no units subcollection). The doc is bounded by `MAX_UNITS` cells x at
most 8 attempts, which stays well under Firestore's 1 MiB document limit.
"""

ZERO_USAGE = {"input_tokens": 0, "output_tokens": 0, "calls": 0, "cost_usd": 0.0}


def session_entry(dataset_session_id: str, order: int, transcript_sha256: str) -> dict:
    return {
        "dataset_session_id": dataset_session_id,
        "order": order,
        "transcript_sha256": transcript_sha256,  # pinned: rerun refuses a changed transcript
        "cursor": 0,
        "active_run_id": None,
        "state": "pending",
        "runs": [],  # [{run_id, combo_key, repeat, attempt, status}]
    }


def build_group_doc(
    *,
    name,
    description,
    input,  # noqa: A002
    created_by,
    created_at,
    engines,
    selection,
    combos,
    repeats,
    base_preset,
    resolved_combos,
    engine_versions,
    engine_git_sha,
    change_goal,
    language,
    coded_span,
    sessions: dict,
    total_units: int,
    human_units: int,
) -> dict:
    """All units start `pending` except Human, which is gold by sha and complete at creation."""
    finished = human_units == total_units
    doc = {
        "name": name,
        "description": description,
        "input": input,
        "created_by": created_by,
        "created_at": created_at,
        "status": "done" if finished else "queued",
        "cancel_requested": False,
        "cancelled_at": None,
        "engines": engines,
        "selection": selection,
        "combos": combos,
        "repeats": repeats,
        "base_preset": base_preset,
        "change_goal": change_goal,
        "language": language,
        "coded_span": coded_span,
        "saved_config": {"base_preset": base_preset, "resolved_combos": resolved_combos},
        "engine_versions": engine_versions,
        "engine_git_sha": engine_git_sha,
        "human": "human" in engines,
        "total_units": total_units,
        "completed_units": human_units,
        "done_units": human_units,
        "failed_units": 0,
        "cancelled_units": 0,
        "skipped_units": 0,
        "usage": dict(ZERO_USAGE),
        "cost_usd_est": 0.0,
        "unpriced_units": 0,
        "tick_seq": 1,
        "last_tick_at": None,
        "consecutive_failures": {},
        "provider_skips": {},
        "cells_wait": {},
        "sessions": sessions,
    }
    if finished:
        doc["finished_at"] = created_at
    return doc
