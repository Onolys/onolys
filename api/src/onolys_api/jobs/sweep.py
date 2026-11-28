"""Server-side sweep: one idempotent, bounded pass that does what reads and
Cloud Tasks retries cannot when nobody is looking.

Called by the internal worker route `POST /tasks/sweep` (OIDC like the other `/tasks/*` routes),
fired every 15 minutes by Cloud Scheduler (infra). Each invocation:

a. settles stale sessions (`stale.settle_if_stale`: the same transactional rule the reads use, so
   an upload that never finished, a lost validate/transcribe/run task is settled without anyone
   opening the page);
b. resumes deletion of sessions stuck in `deleting` longer than `DELETING_GRACE_S` (both the
   inline DELETE and its cleanup task failed; the data would otherwise stay forever). A failed
   upload's tombstone (`discard_code`) is left to its own task;
c. repairs leaked `active_runs` (`Repo.reconcile_active_runs`) for users that still hold slots.

At most `batch` items per step per call. Deletions are oldest first (failed/skipped items go to
the back); active users rotate using a persisted cursor. One item failing never stops the pass.
"""

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from onolys_api import logs
from onolys_api.config import Settings
from onolys_api.jobs.delete import delete_session_data
from onolys_api.jobs.stale import FAILURES, UPLOAD_STATES, scan_cutoff, settle_if_stale
from onolys_api.repo.base import Repo
from onolys_api.storage.base import BlobStore

BATCH = 25
# the inline DELETE plus its cleanup task (2 attempts, <= 30 s backoff) are long done by then
DELETING_GRACE_S = 600
STALE_STATES: tuple[str, ...] = (*UPLOAD_STATES, *FAILURES)


@dataclass(frozen=True)
class SweepResult:
    settled: int = 0
    deleted: int = 0
    repaired: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def _settle_stale(repo: Repo, settings: Settings, now: datetime, batch: int) -> int:
    settled = 0
    for state in STALE_STATES:
        room = batch - settled
        if room <= 0:
            break
        for s in repo.list_sessions_stuck(state, scan_cutoff(state, now, settings), room):
            try:
                if settle_if_stale(repo, s, now, settings).state != s.state:
                    settled += 1
            except Exception as e:  # noqa: BLE001 - one bad session must not stop the pass
                logs.emit("sweep_item_failed", logging.WARNING, session_id=s.id, step="settle",
                          exc_class=type(e).__name__)  # fmt: skip
    return settled


def _back_of_queue(repo: Repo, s, now: datetime) -> None:
    """A session whose deletion keeps failing would stay first in the oldest-first batch and starve
    every later one: restart its grace period so the next sweeps reach the others first."""
    try:
        repo.update_session(s.uid, s.id, {"stage_started_at": now})
    except Exception:  # noqa: BLE001 - best effort; the session may be gone already
        pass


def _resume_deletes(
    repo: Repo, blobs: BlobStore, now: datetime, batch: int
) -> int:
    deleted = 0
    cutoff = now - timedelta(seconds=DELETING_GRACE_S)
    for s in repo.list_sessions_stuck("deleting", cutoff, batch):
        if s.discard_code:
            _back_of_queue(repo, s, now)
            continue  # a failed upload's tombstone: the discard task owns its cleanup
        try:
            delete_session_data(repo, blobs, s.uid, s.id)
            deleted += 1
        except Exception as e:  # noqa: BLE001 - retried by a later sweep
            logs.emit("sweep_item_failed", logging.WARNING, session_id=s.id, step="delete",
                      exc_class=type(e).__name__)  # fmt: skip
            _back_of_queue(repo, s, now)
    return deleted


def _repair_slots(repo: Repo, batch: int) -> int:
    repaired = 0
    for uid in repo.list_uids_with_active_runs(batch):
        try:
            repaired += repo.reconcile_active_runs(uid)
        except Exception as e:  # noqa: BLE001
            logs.emit("sweep_item_failed", logging.WARNING, step="repair",
                      exc_class=type(e).__name__)  # fmt: skip
    return repaired


def run_sweep(
    repo: Repo, blobs: BlobStore, settings: Settings, now: datetime, batch: int = BATCH
) -> SweepResult:
    result = SweepResult(
        settled=_settle_stale(repo, settings, now, batch),
        deleted=_resume_deletes(repo, blobs, now, batch),
        repaired=_repair_slots(repo, batch),
    )
    logs.emit("sweep_done", **result.as_dict())
    return result
