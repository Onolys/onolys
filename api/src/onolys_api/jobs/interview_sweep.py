"""`interview-sweep` task (SP10 R5, D11): every interview reaches a terminal state.

Enqueued at create, due `AI_MAX_SECONDS + AI_RECONNECT_SECONDS + 60 s` later (past the longest a
relay can legitimately keep an interview live), so one still `created|live` then is stuck. The
handler abandons it through `settle_interview`, the single settle/refund routine (End, discard,
lazy abandon and this sweep share it): the relay-recorded `duration_s` decides the refund
(`< AI_ABANDON_COUNT_SECONDS`), and only the transition's winner releases, so it is exactly once.
Already settled (or deleted) interviews are a no-op. No Cloud Scheduler: it is a delayed task.
"""

from collections.abc import Callable
from datetime import datetime

from onolys_api import logs
from onolys_api.config import Settings
from onolys_api.jobs.interviews import settle_interview
from onolys_api.jobs.queue import TaskPayload, TaskQueue
from onolys_api.jobs.worker import Handler, TaskContext

SWEEP_GRACE_S = 60


def sweep_delay_s(settings: Settings) -> int:
    return settings.ai_max_seconds + settings.ai_reconnect_seconds + SWEEP_GRACE_S


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
        settle_interview(ctx.repo, settings, ctx.uid, ctx.sid, "abandoned", clock())

    return handle
