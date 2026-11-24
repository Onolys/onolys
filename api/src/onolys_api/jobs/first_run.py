"""First-run gate (PRD R4, D13): `maybe_start_first_run`.

Called after each of the three inputs lands (transcribe completion, speaker confirm, final
rating). Each caller sets its own flag first and then calls this, so the last caller always sees
all three flags. The decision is one repo transaction (`Repo.start_first_run`): flags +
`first_run_id` absent + cap check (day; skipped for an AI-interview-linked session, which
is free but still takes an active-run slot) + run creation + `state=running` commit together, so
exactly one caller wins. The cap reservation (runs+1, active_runs+1) lives in that same
transaction: if the transaction loses the race or is refused, nothing was reserved and there is
nothing to compensate.
The `run` task is enqueued only after commit, under the name `{run_id}-run` (duplicates are
no-ops). If that enqueue fails, the committed run is failed and its slot freed (compensation;
refunded unless the run was the free first run).
"""

import logging
from uuid import uuid4

from onolys_api import logs
from onolys_api.adapters.error_map import kind_for_code
from onolys_api.config import Settings
from onolys_api.jobs import caps
from onolys_api.jobs.machine import RUN_START_PROGRESS, advance
from onolys_api.jobs.queue import TaskPayload, TaskQueue
from onolys_api.repo.base import Repo
from onolys_api.repo.limits import HELD_ERROR_CODE, LimitDefaults
from onolys_api.repo.models import SessionError


def maybe_start_first_run(
    repo: Repo, queue: TaskQueue | None, uid: str, sid: str, settings: Settings,
    request_id: str | None = None,
) -> None:  # fmt: skip
    if queue is None:  # nowhere to send the `run` task: leave the session as it is
        logs.emit("first_run_no_queue", logging.ERROR, session_id=sid, request_id=request_id)
        return
    run_id = uuid4().hex
    date = caps.utc_date()
    outcome = repo.start_first_run(
        uid, sid, run_id, date, LimitDefaults.from_settings(settings), settings.max_active_runs,
        settings.git_sha, RUN_START_PROGRESS,
    )  # fmt: skip
    if outcome != "started":
        if outcome in ("daily_cap", "concurrent"):
            logs.emit(
                "first_run_held",
                session_id=sid,
                error_code=HELD_ERROR_CODE[outcome],
                request_id=request_id,
            )
        return
    try:
        queue.enqueue(
            TaskPayload(kind="run", uid=uid, sid=sid, run_id=run_id, request_id=request_id)
        )
    except Exception as e:
        logs.failed(
            "run_failed", session_id=sid, run_id=run_id, step="run",
            error_code="upstream_unavailable", exc_class=type(e).__name__, request_id=request_id,
        )  # fmt: skip
        repo.update_run(uid, sid, run_id, {"status": "failed", "error": "upstream_unavailable"})
        from onolys_api.jobs.run import release_once  # jobs.run imports transcribe imports us

        release_once(repo, uid, sid, run_id, True, date)  # refunds its units unless it was free
        advance(
            repo, uid, sid, to="failed", step=None,
            error=SessionError(
                code="upstream_unavailable", step="run", kind=kind_for_code("upstream_unavailable")
            ),
        )  # fmt: skip
