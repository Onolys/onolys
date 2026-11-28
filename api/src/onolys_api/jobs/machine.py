"""Job state machine core (PRD R4, D13): states, allowed transitions, flags, progress table.

`advance` is the single status-mirror helper: every state/step/progress/flag/error change goes
through it, and it writes `sessions/{sid}` and `session_status/{sid}` in ONE repo transaction
(`Repo.transition_session`): the read, the allowed-source check and the write are atomic, so a
concurrent cancel/delete mark cannot be overwritten. The status document carries no text (R7, AC11).

The first-run gate and `POST /runs` still use their own repo transactions (`start_first_run`,
`start_run`) because they also reserve usage.
"""

from collections.abc import Callable
from typing import Any, get_args

from onolys_api.errors import ApiError
from onolys_api.progress import (
    RUN_START_PROGRESS,
    STAGE_WEIGHTS,
    STAGES,
    STATE_PROGRESS,
    entry_fields,
    stage_fields,
)
from onolys_api.repo.base import NotFoundError, Repo
from onolys_api.repo.models import (
    SessionDoc,
    SessionError,
    SessionState,
    SessionStatusDoc,
    error_status_fields,
    utcnow,
)

STATES: tuple[str, ...] = get_args(SessionState)

_NOT_DELETING = (
    "created", "uploading", "validating", "transcribing", "awaiting_input",
    "running", "report_ready", "failed", "upload_incomplete", "cancelled",
)  # fmt: skip

TRANSITIONS: dict[str, frozenset[str]] = {
    "created": frozenset(
        {"awaiting_input", "uploading", "upload_incomplete", "deleting", "cancelled"}
    ),
    # uploading -> uploading: a fresh signed URL for the same session
    "uploading": frozenset(
        {"uploading", "upload_incomplete", "validating", "deleting", "cancelled"}
    ),
    # never uploaded (lazy stale check): a fresh URL resumes it; a late PUT still completes
    "upload_incomplete": frozenset({"uploading", "validating", "deleting", "cancelled"}),
    "validating": frozenset({"transcribing", "failed", "deleting", "cancelled"}),
    "transcribing": frozenset({"awaiting_input", "failed", "deleting", "cancelled"}),
    "awaiting_input": frozenset({"running", "deleting", "cancelled"}),
    "running": frozenset({"report_ready", "failed", "deleting", "cancelled"}),
    "report_ready": frozenset({"running", "deleting"}),  # re-run
    # one retry path (R4): re-enter the step that failed (`POST /sessions/{id}/retry`)
    "failed": frozenset({"running", "validating", "transcribing", "deleting"}),
    "cancelled": frozenset({"deleting"}),  # terminal (04-cancel R1): only Delete leaves it
    "deleting": frozenset(),
}
assert set(TRANSITIONS) == set(STATES) and all("deleting" in TRANSITIONS[s] for s in _NOT_DELETING)

FLAGS = ("transcript_ready", "speaker_confirmed", "rating_submitted", "has_rating")

# fields of session_status/{sid} (everything the web may read; no text)
STATUS_FIELDS = frozenset(
    {
        "uid", "state", "step", "progress", "error_code", "error_kind", "retries_left", "counted",
        "latest_report_version", "updated_at", "expire_at",
        "started_at", "stage_started_at", "waited_ms", "audio_s", "progress_next",
        "stage_expected_s",
        *FLAGS,
    }
)  # fmt: skip

_KEEP: Any = object()


def invalid_state() -> ApiError:
    return ApiError.of(409, "invalid_state", "The session is not in a state that allows this.")


def rating_final() -> ApiError:
    return ApiError.of(
        409, "rating_final", "The rating is final once submitted and cannot be changed or re-run."
    )


def has_final_report(repo, uid: str, sid: str, state: str) -> bool:
    """FX45: a successful report (or a version from earlier data) makes the rating final."""
    return state == "report_ready" or bool(repo.list_reports(uid, sid))


def check_transition(current: str, to: str) -> None:
    if to not in TRANSITIONS.get(current, frozenset()):
        raise invalid_state()


def next_progress(current: int, to: str) -> int:
    """Progress after entering `to`. Never decreases, except a re-run restarting at 45 (see
    `advance`); `failed`/`deleting` keep the last value."""
    return max(current, STATE_PROGRESS.get(to, current))


def stage_progress(current: int, stage: str) -> int:
    """Add a finished stage's weight. Capped at 99: 100 belongs to `report_ready`."""
    if stage not in STAGE_WEIGHTS:
        raise ValueError(f"unknown stage {stage!r}")
    return min(99, current + STAGE_WEIGHTS[stage])


Plan = Callable[[SessionDoc, SessionStatusDoc], "tuple[dict[str, Any], dict[str, Any]] | None"]


def transition_plan(
    *,
    to: str | None = None,
    step: Any = _KEEP,
    error: SessionError | None | Any = _KEEP,
    flags: dict[str, bool] | None = None,
    stage_done: str | None = None,
    latest_report_version: int | None | Any = _KEEP,
    only_from: tuple[str, ...] | None = None,
    extra_fields: dict[str, Any] | None = None,
    guard: Callable[[SessionDoc], None] | None = None,
) -> Plan:
    """Build the pure function `Repo.transition_session` runs INSIDE its transaction: it gets the
    freshly read session and status and returns `(session_fields, status_fields)` (or None for
    "nothing to write"). It raises for a refused move (409 invalid_state), so the check and the
    write see the same state. `only_from`: the session must be in one of these states.
    `extra_fields`: more session-only fields. `guard`: an extra check on the session.
    A change without `to` on a `deleting` session is a 404, on a `cancelled` one a 409."""
    if to == "failed" and (error is _KEEP or error is None):
        raise ValueError("a failed session needs an error")
    if flags and not set(flags) <= set(FLAGS):
        raise ValueError("unknown flag")

    def plan(session: SessionDoc, status: SessionStatusDoc):
        if to is None:
            if session.state == "deleting":
                raise NotFoundError()
            if session.state == "cancelled":
                raise invalid_state()
        elif to == "deleting" and session.state == "deleting":
            return None  # a second Delete (or the cleanup task) finds it already marked
        else:
            check_transition(session.state, to)
        if only_from is not None and session.state not in only_from:
            raise invalid_state()
        if guard is not None:
            guard(session)
        return _build_fields(
            session, status, to, step, error, flags, stage_done, latest_report_version,
            extra_fields,
        )  # fmt: skip

    return plan


def _build_fields(
    session, status, to, step, error, flags, stage_done, latest_report_version, extra_fields
):
    new_state = to or session.state
    progress = status.progress
    if to == "running" and session.state in ("report_ready", "failed"):
        progress = RUN_START_PROGRESS  # a re-run restarts
    elif to is not None:
        progress = next_progress(progress, to)
    if stage_done is not None:
        progress = stage_progress(progress, stage_done)

    if error is _KEEP and to is not None and to != "failed":
        error = None
    s_fields: dict[str, Any] = {"state": new_state}
    st_fields: dict[str, Any] = {"state": new_state, "progress": progress}
    new_step = session.step if step is _KEEP else step
    if to is not None:
        now = utcnow()
        s_fields["stage_started_at"] = now  # the stale check keys off this, not updated_at
        st_fields.update(
            entry_fields(session.state, session.stage_started_at, status.model_dump(), to,
                         new_step, now)
        )  # fmt: skip
    elif step is not _KEEP or stage_done is not None:
        st_fields.update(stage_fields(new_state, new_step, status.audio_s))
    if stage_done is not None and new_state == "running":
        after = STAGES[STAGES.index(stage_done) + 1 :][:1]
        st_fields.update(stage_fields("running", after[0] if after else STAGES[-1], None))
    if step is not _KEEP:
        s_fields["step"] = step
        st_fields["step"] = step
    if error is not _KEEP:
        s_fields["error"] = error.model_dump() if error else None
        st_fields.update(error_status_fields(error, session.retry_count))
    if latest_report_version is not _KEEP:
        s_fields["latest_report_version"] = latest_report_version
        st_fields["latest_report_version"] = latest_report_version
    for k, v in (flags or {}).items():
        s_fields[k] = v
        st_fields[k] = v
    s_fields.update(extra_fields or {})
    return s_fields, st_fields


def advance(
    repo: Repo,
    uid: str,
    sid: str,
    *,
    to: str | None = None,
    step: Any = _KEEP,
    error: SessionError | None | Any = _KEEP,
    flags: dict[str, bool] | None = None,
    stage_done: str | None = None,
    latest_report_version: int | None | Any = _KEEP,
) -> None:
    """Apply one change to the session and mirror it to `session_status` in ONE repo transaction
    (`transition_session`): the state check and the write see the same state, so a concurrent
    cancel/delete mark is never overwritten.

    `to`: validated against TRANSITIONS (409 invalid_state). `step`: the stage label.
    `error`: the error (session.error + status.error_code); entering a non-failed state clears
    it unless given; `failed` requires one. `stage_done`: a stage finished or failed, adds its
    weight. Raises NotFoundError for another user's session.
    """
    repo.transition_session(
        uid, sid,
        transition_plan(
            to=to, step=step, error=error, flags=flags, stage_done=stage_done,
            latest_report_version=latest_report_version,
        ),
    )  # fmt: skip
