"""Stale check (on read, and by the server sweep `jobs/sweep.py`): fail a session whose task chain
stopped without a terminal state.

A `created`|`uploading` session older than the upload URL lifetime + margin moves to the
non-terminal `upload_incomplete` (resume or delete; no units involved).

A session stuck in `transcribing` (more than its cap `steps.transcribe.stt_limit_s`, else the
settings maximum, + 60 s), `validating` or `running` (more than every attempt's deadline + lease
+ margin) has lost its chain: Cloud Tasks gave up, a worker crashed, a task was dropped. The age
is measured from `stage_started_at` (when the state was entered), never `updated_at`, which
rating / speaker writes also bump. It is failed when read (or by the server sweep,
`jobs/sweep.py`), in one repo transaction that re-checks the state, so a task that finished in the
meantime wins. A failed `running` session also fails its unfinished runs and hands their cap slots
back IN THAT SAME transaction (`release_runs`): a release that fails separately would leave the
session `failed` (never re-checked) and the user's `active_runs` leaked (M-2).

A stale failure is a lost task, not a bad file or a bug: it is `transient` with
`deadline_exceeded` ("took too long, run again"), so `/retry` works (LM-1).
"""

from datetime import datetime, timedelta

from onolys_api import logs
from onolys_api.adapters.error_map import kind_for_code
from onolys_api.config import Settings
from onolys_api.jobs.queue import MAX_ATTEMPTS
from onolys_api.jobs.worker import DEADLINE_S, LEASE_GRACE_S
from onolys_api.repo.base import NotFoundError, Repo
from onolys_api.repo.models import SessionDoc, SessionError
from onolys_api.storage.base import UPLOAD_URL_TTL_S

STALE_MARGIN_S = 60
RETRY_SLACK_S = 300  # Cloud Tasks backoff between attempts
STEP = "transcribe"
LOST_TASK_CODE = "deadline_exceeded"  # transient: the chain stopped, a retry can succeed
# state -> step label of the failure
FAILURES = {
    "transcribing": STEP,
    "validating": "validate",
    "running": "run",
}


# created|uploading: no PUT finished before the signed URL (+ margin) lapsed: nothing to wait for
UPLOAD_STATES = ("created", "uploading")
UPLOAD_INCOMPLETE = "upload_incomplete"


def _cutoff(s: SessionDoc, now: datetime, settings: Settings) -> datetime:
    if s.state == "transcribing":
        rec = s.steps.get(STEP)
        limit = (rec.stt_limit_s if rec else None) or settings.stt_time_limit_s
        return now - timedelta(seconds=limit + STALE_MARGIN_S)
    budget = MAX_ATTEMPTS * (DEADLINE_S + LEASE_GRACE_S) + RETRY_SLACK_S
    return now - timedelta(seconds=budget)


def scan_cutoff(state: str, now: datetime, settings: Settings) -> datetime:
    """The sweep's candidate query: sessions in `state` entered before this MAY be stale (never
    later than the exact per-session cutoff; `settle_if_stale` decides)."""
    if state in UPLOAD_STATES:
        return now - timedelta(seconds=UPLOAD_URL_TTL_S + STALE_MARGIN_S)
    if state == "transcribing":  # a recording's own cap is at least the configured minimum
        return now - timedelta(
            seconds=min(settings.stt_cap_min_s, settings.stt_time_limit_s) + STALE_MARGIN_S
        )
    return now - timedelta(seconds=MAX_ATTEMPTS * (DEADLINE_S + LEASE_GRACE_S) + RETRY_SLACK_S)


def settle_if_stale(repo: Repo, s: SessionDoc, now: datetime, settings: Settings) -> SessionDoc:
    """`s`, or its fresh copy after trying to fail it because its chain is dead (the transaction
    may find it moved on: a finished task wins)."""
    if s.state in UPLOAD_STATES:
        # non-terminal and free: the user can resume (new URL + complete) or delete it
        cutoff = now - timedelta(seconds=UPLOAD_URL_TTL_S + STALE_MARGIN_S)
        if (s.stage_started_at or s.updated_at) >= cutoff:
            return s
        try:
            repo.fail_stale_session(s.uid, s.id, s.state, cutoff, None, to=UPLOAD_INCOMPLETE)
        except NotFoundError:
            return s
        return repo.get_session(s.uid, s.id)
    failure = FAILURES.get(s.state)
    if failure is None:
        return s
    cutoff = _cutoff(s, now, settings)
    if (s.stage_started_at or s.updated_at) >= cutoff:
        return s
    step, code = failure, LOST_TASK_CODE
    try:
        failed = repo.fail_stale_session(
            s.uid,
            s.id,
            s.state,
            cutoff,
            SessionError(code=code, step=step, kind=kind_for_code(code)),
            release_runs=s.state == "running",
        )
    except NotFoundError:
        return s
    if failed:
        logs.failed("session_stale", session_id=s.id, step=step, error_code=code,
                    exc_class="StaleSession")  # fmt: skip
    return repo.get_session(s.uid, s.id)
