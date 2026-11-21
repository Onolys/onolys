"""`interview-sweep` task (SP10 R5, D11): every interview reaches a terminal state.

Enqueued at create, due `AI_MAX_SECONDS + AI_RECONNECT_SECONDS + 60 s` later. The relay counts
*connected* seconds only, so wall time since create is not proof the interview is stuck (picker,
mic prompt, reconnect gaps). The handler therefore re-checks instead of abandoning blindly:
- `live`, connected: alive while the relay's last checkpoint (`seen_at`, ~10 s cadence) is fresh;
- `live`, disconnected: alive while within the reconnect window (plus a margin);
- `created` (not connected yet): alive;
all bounded by a hard ceiling of `2 * (AI_MAX_SECONDS + AI_RECONNECT_SECONDS)` after create.
Alive: the sweep re-enqueues itself (`n + 1`, a distinct task name). Otherwise it abandons through
`settle_interview`, the single settle/refund routine (End, discard, lazy abandon and this sweep
share it); only the transition's winner releases, so it is exactly once. Already settled (or
deleted) interviews are a no-op. No Cloud Scheduler: it is a delayed task.
"""

from collections.abc import Callable
from datetime import datetime

from onolys_api import logs
from onolys_api.config import Settings
from onolys_api.jobs.interviews import OPEN_STATES, settle_interview
from onolys_api.jobs.queue import TaskPayload, TaskQueue
from onolys_api.jobs.worker import Handler, TaskContext
from onolys_api.repo.models import InterviewDoc

SWEEP_GRACE_S = 60


def sweep_delay_s(settings: Settings) -> int:
    return settings.ai_max_seconds + settings.ai_reconnect_seconds + SWEEP_GRACE_S


def hard_ceiling_s(settings: Settings) -> int:
    return 2 * (settings.ai_max_seconds + settings.ai_reconnect_seconds)


def recheck_delay_s(settings: Settings) -> int:
    return settings.ai_reconnect_seconds + SWEEP_GRACE_S


def interview_is_alive(doc: InterviewDoc, settings: Settings, now: datetime) -> bool:
    """Is a still-open interview legitimately in progress (so the sweep must not abandon it)?"""
    if (now - doc.created_at).total_seconds() >= hard_ceiling_s(settings):
        return False
    if doc.state == "created":
        return True
    ref = doc.disconnected_at if doc.disconnected_at is not None else doc.seen_at
    if ref is None:
        return False
    return (now - ref).total_seconds() <= settings.ai_reconnect_seconds + SWEEP_GRACE_S


def enqueue_sweep(queue: TaskQueue | None, settings: Settings, uid: str, iid: str) -> None:
    """Schedule the sweep for interview `iid`. No queue configured (local api-only): skipped with
    a warning, lazy abandon at the next create still covers it. Enqueue errors propagate."""
    if queue is None:
        logs.emit("interview_sweep_unscheduled", session_id=iid)
        return
    queue.enqueue(TaskPayload(kind="interview-sweep", uid=uid, sid=iid), sweep_delay_s(settings))


def make_interview_sweep_handler(settings: Settings, clock: Callable[[], datetime]) -> Handler:
    def handle(ctx: TaskContext) -> None:
        # NotFoundError (interview/user gone) is answered 2xx "gone" by the runner
        now = clock()
        doc = ctx.repo.get_interview(ctx.uid, ctx.sid)
        if doc.state in OPEN_STATES and interview_is_alive(doc, settings, now):
            n = (ctx.payload.n or 0) + 1
            ctx.queue.enqueue(
                TaskPayload(kind="interview-sweep", uid=ctx.uid, sid=ctx.sid, n=n),
                recheck_delay_s(settings),
            )
            logs.emit("interview_sweep_recheck", session_id=ctx.sid, n=n)
            return
        settle_interview(ctx.repo, settings, ctx.uid, ctx.sid, "abandoned", now)

    return handle
