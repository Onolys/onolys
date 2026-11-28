"""Delete one eval run's data, resumably.

`POST /v1/runs/{id}/delete {confirm_run_id}` is refused 409 `run_active` unless the run is
terminal; otherwise it sets `deleting` (the tick ignores it, History shows it), answers 202 and
enqueues `{id}-delete-{n}`. `POST /internal/tasks/delete` walks every ref of the group doc:
(1) output blobs under `{uid}/{sid}/runs/{run_id}/`, (2)+(3) ReportDoc, its blob pointer and the
RunDoc (`repo.delete_run_data`), then the provider slots, and LAST the group doc, so a retry
always still has the refs. A failure keeps `deleting` + `delete_error` and enqueues the next
attempt under a new task name. Sessions, transcripts, datasets, gold and other eval runs' runs
are never touched (refs list only this run's ids); no session field is repaired.
"""

import hashlib
import hmac
import logging

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
logger = logging.getLogger(__name__)

TERMINAL = {"done", "partial", "failed", "cancelled"}
RETRY_DELAY_S = 30
MAX_ATTEMPTS = 10  # then stop retrying by itself; the same POST again starts a fresh chain


def _email_hash(services, email: str) -> str:
    key = (getattr(services.config.settings, "uid_hmac_key", "") or "").encode()
    return hmac.new(key, email.encode(), hashlib.sha256).hexdigest()[:16]


def _release_slots(services, doc: dict, run_ids: list[str]) -> None:
    for entry_ref in run_ids:
        for combo in doc.get("saved_config", {}).get("resolved_combos", {}).values():
            services.repository.release_slot(combo["litellm_id"].split("/")[0], entry_ref)


def _delete_all(services, doc: dict) -> None:
    uid = services.config.eval_owner_uid
    run_ids = []
    for sid, entry in (doc.get("sessions") or {}).items():
        for ref in entry.get("runs") or []:
            run_id = ref.get("run_id")
            if not run_id:  # drift-failed / cancelled cells never created a RunDoc
                continue
            services.blobs.delete_prefix(f"{uid}/{sid}/runs/{run_id}/")  # (1) outputs
            services.repo.delete_run_data(uid, sid, run_id)  # (2) report + pointer, (3) RunDoc
            run_ids.append(run_id)
    _release_slots(services, doc, run_ids)


def run_delete(services, eval_run_id: str, n: int) -> str:
    """One delete attempt: "deleted", "noop" (nothing to do / not deleting) or "failed"."""
    repository = services.repository
    doc = repository.get_run(eval_run_id)
    if doc is None or doc.get("status") != "deleting":
        return "noop"
    try:
        _delete_all(services, doc)
        repository.delete_run(eval_run_id)  # (4) the group doc, last
    except Exception:
        logger.exception("eval_run_delete_failed", extra={"eval_run_id": eval_run_id, "n": n})
        repository.update_run(eval_run_id, {"delete_error": "internal_error"})
        if n < MAX_ATTEMPTS:
            services.queue.enqueue(
                "delete", {"eval_run_id": eval_run_id, "n": n + 1}, delay_seconds=RETRY_DELAY_S,
                task_id=f"{eval_run_id}-delete-{n + 1}",
            )
        return "failed"
    logger.info("eval_run_deleted", extra={"eval_run_id": eval_run_id})
    return "deleted"


@router.post("/v1/runs/{run_id}/delete", status_code=202)
def delete_run(request: Request, run_id: str, body: dict):
    services = request.app.state.services
    if body.get("confirm_run_id") != run_id:
        raise HTTPException(422, "confirm_run_id must equal the run id.")
    repository = services.repository
    doc = repository.get_run(run_id)
    if doc is None:
        raise HTTPException(404, "Run not found.")
    if doc.get("status") not in TERMINAL | {"deleting"}:
        raise HTTPException(409, {
            "code": "run_active",
            "message": "Cancel the run and wait for it to finish before deleting it.",
        })
    n = int(doc.get("delete_n") or 0) + 1
    repository.update_run(run_id, {"status": "deleting", "delete_n": n, "delete_error": None})
    logger.info(
        "eval_run_delete_requested",
        extra={"eval_run_id": run_id,
               "email_hash": _email_hash(services, request.state.user_email)},
    )
    services.queue.enqueue(
        "delete", {"eval_run_id": run_id, "n": n}, task_id=f"{run_id}-delete-{n}",
    )
    return {"run_id": run_id, "status": "deleting"}


@router.post("/internal/tasks/delete")
def delete_task(request: Request, body: dict):
    eval_run_id, n = body.get("eval_run_id"), body.get("n")
    if not isinstance(eval_run_id, str) or not eval_run_id or not isinstance(n, int) or n < 1:
        raise HTTPException(422, "An eval run id and attempt number are required.")
    run_delete(request.app.state.services, eval_run_id, n)
    return {"status": "ok"}
