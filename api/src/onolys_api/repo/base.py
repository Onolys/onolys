"""The `Repo` protocol: the single uid-checked choke point for Firestore (R7, D7).

Every call takes `uid` first. A document that is missing, or owned by another uid, raises
`NotFoundError` (HTTP 404, never 403) with identical text, so ids cannot be probed.
Sync on purpose: routes/handlers call it from threadpool workers.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol

from onolys_engine_core.transcript import Transcript

from onolys_api.errors import ApiError
from onolys_api.repo.limits import Kind, LimitDefaults, ReserveUsageOutcome
from onolys_api.repo.models import (
    ApiKeyDoc,
    EvalRunInfo,
    IdempotencyDoc,
    InterviewDoc,
    InterviewState,
    RatingDoc,
    RatingDraftDoc,
    RecordingDoc,
    ReportDoc,
    RunDoc,
    SessionDoc,
    SessionError,
    SessionStatusDoc,
    TranscriptDoc,
    UsageDoc,
    UserDoc,
)


class NotFoundError(ApiError):
    def __init__(self) -> None:
        super().__init__(
            404, "Resource not found.", [{"code": "not_found", "message": "Resource not found."}]
        )


class ConflictError(ApiError):
    def __init__(self) -> None:
        super().__init__(409, "Conflict.", [{"code": "conflict", "message": "Conflict."}])


# `Repo.transition_session`: pure `(session, status) -> (session_fields, status_fields)` run INSIDE
# the transaction on the freshly read docs; raise to refuse; None = nothing to write.
SessionPlan = Callable[
    [SessionDoc, SessionStatusDoc], "tuple[dict[str, Any], dict[str, Any]] | None"
]
# a child doc written in the same transaction: ("transcripts/current", stored dict, exclusive)
ChildWrite = tuple[str, dict[str, Any], bool]


@dataclass
class Page[T]:
    items: list[T] = field(default_factory=list)
    next_cursor: str | None = None


StartOutcome = Literal["started", "not_ready", "already", "daily_cap", "concurrent"]
# `cancel_session` result: ("cancelled", counted) | ("invalid",)
CancelOutcome = tuple[Literal["cancelled"], bool] | tuple[Literal["invalid"]]
InterviewLinkOutcome = Literal["linked", "not_ended", "already_linked", "refunded"]
ClaimOutcome = Literal["claimed", "done", "failed", "busy"]


@dataclass(frozen=True)
class Claim:
    """Result of claiming a step/run record: `claimed` (caller owns it now, `attempts` counts
    claims), `done`/`failed` (terminal: a duplicate delivery), `busy` (running inside its lease)."""

    outcome: ClaimOutcome
    attempts: int = 0


def decide_claim(
    status: str | None, started: datetime | None, attempts: int, now: datetime, lease_s: float
) -> Claim:
    """Shared claim rule. A `running` record older than the lease is re-claimable."""
    if status in ("done", "failed"):
        return Claim(status, attempts)  # type: ignore[arg-type]
    if status == "running" and started is not None and now < started + timedelta(seconds=lease_s):
        return Claim("busy", attempts)
    return Claim("claimed", attempts + 1)


class Repo(Protocol):
    # users
    def get_user(self, uid: str) -> UserDoc | None: ...
    def ensure_user(self, uid: str) -> UserDoc: ...

    # sessions + session_status (one batch for create; update mirrors `status`)
    def create_session(
        self, uid: str, sid: str, session: SessionDoc, status: SessionStatusDoc
    ) -> None: ...
    # AI interview link (SP10 R6), ONE transaction: the interview must be the caller's (else
    # NotFoundError), `ended` ("not_ended" otherwise), not `refunded` ("refunded": its unit was
    # given back, so it must not also buy a free run) and unlinked ("already_linked" otherwise).
    # Then it writes the session, its status, the `ratings/draft` doc and `interview.session_id`.
    def create_session_for_interview(
        self, uid: str, iid: str, sid: str, session: SessionDoc, status: SessionStatusDoc,
        draft: RatingDraftDoc,
    ) -> InterviewLinkOutcome: ...  # fmt: skip
    def get_session(self, uid: str, sid: str) -> SessionDoc: ...
    def get_status(self, uid: str, sid: str) -> SessionStatusDoc: ...
    def update_session(
        self, uid: str, sid: str, fields: dict[str, Any], status: dict[str, Any] | None = None
    ) -> None: ...
    # ONE transaction (M-10/N1/LM-2): reads the session and its status, runs `plan` on them (it
    # does the allowed-source check and may raise), then writes session + status and every
    # `children` doc ("<subcollection>/<id>"; `exclusive` -> ConflictError if it exists). A
    # concurrent cancel/delete mark is therefore never overwritten. NotFoundError for a foreign,
    # missing session. The plan may run more than once (txn retry): keep it pure.
    def transition_session(
        self, uid: str, sid: str, plan: SessionPlan, children: tuple[ChildWrite, ...] = ()
    ) -> None: ...
    # ONE transaction (M-11): publish a finished run. If the report doc `report_id=run_id`
    # exists it is returned unchanged (nothing written). If the session is `deleting` ->
    # NotFoundError; if it is not `running` (cancelled, failed, ...) -> None and nothing is
    # written. Else it writes the report (the version is max+1, assigned in the txn; a large body
    # goes to a blob first), updates the run with `run_fields`, moves the session with
    # `plan_for(version)` and releases the run's slot without refund. All or nothing: a report is
    # visible only together with its run completion and `report_ready`.
    def publish_report(
        self, uid: str, sid: str, run_id: str, doc: ReportDoc, run_fields: dict[str, Any],
        plan_for: Callable[[int], SessionPlan], date: str | None,
    ) -> ReportDoc | None: ...  # fmt: skip
    # Atomic write-once selection; same returns without writing, even after a run starts.
    # Failed/cancelled/deleting sessions conflict before the idempotency check.
    def confirm_speaker(
        self, uid: str, sid: str, clinician: str, states: tuple[str, ...]
    ) -> Literal["written", "same", "conflict"]: ...
    def list_sessions(
        self, uid: str, limit: int = 20, cursor: str | None = None
    ) -> Page[SessionDoc]: ...
    def delete_session(self, uid: str, sid: str) -> bool: ...
    # R11: a validation file-check failure is an upload failure. ONE transaction writes the
    # data-free status stub (`state=upload_failed`, `error_code`, `expire_at` +7 days), marks the
    # session `deleting` with a `discard_code` tombstone (hidden; cancel and every transition
    # refuse it) and unlinks its interview (back to `ended`, `session_id` cleared) so the unit can
    # be linked again (M-4). Then it deletes the session doc and every subcollection, but only
    # while the tombstone is still there. NotFoundError if the session is not the caller's, is
    # gone or is `deleting` for any other reason (the Delete path owns it); ConflictError if
    # `cancelled`. Idempotent: a redelivered task resumes the cleanup.
    def discard_failed_upload(self, uid: str, sid: str, code: str) -> None: ...

    # One transaction: if the session is still in `state` with `updated_at < before`, set it
    # `to` (default `failed`) with `error` (mirrored to session_status; `steps.<error.step>`
    # marked failed; `error` is None for the non-terminal `upload_incomplete`) and return True.
    # Anything else (moved on, written to since, already failed): nothing, False.
    # Used by the lazy stale check on read; a poll that just finished wins the race.
    # `release_runs` (the `running` stale case, M-2): in the SAME transaction every run of the
    # session that is not `released` is marked `failed` (`error=run_failed`, unless it is `done`)
    # and its cap slot is handed back (refund unless the run is `done`), so a failure of a
    # separate release step can never leave the session `failed` with a leaked `active_runs`.
    def fail_stale_session(
        self,
        uid: str,
        sid: str,
        state: str,
        before: datetime,
        error: SessionError | None,
        to: str = "failed",
        release_runs: bool = False,
    ) -> bool: ...

    # M-2 self-repair, ONE transaction over `users/{uid}` and the user's runs: `active_runs` is
    # lowered to the number of runs that really hold a slot (unreleased, `pending|running`, in a
    # `running` or `deleting` session: the delete owns that one). Any other unreleased run is a
    # leak: marked `released` (no refund; `unit_kept` = counted). Returns the slots reclaimed.
    def reconcile_active_runs(self, uid: str) -> int: ...

    # Server sweep reads (M-1, M-3). NOT uid-scoped on purpose: the internal worker sweep walks
    # every user. Sessions in `state` whose `stage_started_at` is before `before`, oldest first,
    # at most `limit`. Never used by a user-facing route.
    def list_sessions_stuck(
        self, state: str, before: datetime, limit: int
    ) -> list[SessionDoc]: ...
    # Bounded, rotating uids whose active_runs is above 0. The persisted internal checkpoint
    # advances across processes and wraps; positive counts and uid break candidate ties.
    def list_uids_with_active_runs(self, limit: int) -> list[str]: ...

    # children of a session
    def add_recording(self, uid: str, sid: str, rid: str, rec: RecordingDoc) -> None: ...
    def list_recordings(self, uid: str, sid: str) -> list[RecordingDoc]: ...
    def put_transcript(self, uid: str, sid: str, tid: str, transcript: Transcript) -> None: ...
    def get_transcript(
        self, uid: str, sid: str, tid: str, resolve: bool = True
    ) -> TranscriptDoc: ...
    def put_rating_revision(self, uid: str, sid: str, rating_id: str, doc: RatingDoc) -> None: ...
    def get_rating(self, uid: str, sid: str, rating_id: str) -> RatingDoc: ...
    def latest_rating(self, uid: str, sid: str) -> RatingDoc | None: ...
    def put_rating_draft(self, uid: str, sid: str, draft: RatingDraftDoc) -> None: ...
    def get_rating_draft(self, uid: str, sid: str) -> RatingDraftDoc | None: ...
    def create_run(self, uid: str, sid: str, run_id: str, run: RunDoc) -> None: ...
    def get_run(self, uid: str, sid: str, run_id: str) -> RunDoc: ...
    def update_run(self, uid: str, sid: str, run_id: str, fields: dict[str, Any]) -> None: ...
    def list_runs(self, uid: str, sid: str) -> list[RunDoc]: ...
    # eval-only hooks (05 R3/R8): prod routes never call them
    def get_runs(self, uid: str, sid: str, run_ids: list[str]) -> list[RunDoc]: ...
    def delete_run_data(self, uid: str, sid: str, run_id: str) -> None: ...
    # atomic claim with lease (R5): pending|expired-running -> running, attempts+1
    def claim_step(self, uid: str, sid: str, step: str, now: datetime, lease_s: float) -> Claim: ...
    def claim_run(
        self, uid: str, sid: str, run_id: str, now: datetime, lease_s: float
    ) -> Claim: ...
    def get_run_by_id(self, uid: str, run_id: str) -> RunDoc: ...
    def put_report(self, uid: str, sid: str, report_id: str, doc: ReportDoc) -> None: ...
    def get_report(self, uid: str, sid: str, report_id: str, resolve: bool = True) -> ReportDoc: ...
    def get_report_by_version(
        self, uid: str, sid: str, version: int, resolve: bool = True
    ) -> ReportDoc: ...
    def list_reports(self, uid: str, sid: str) -> list[ReportDoc]: ...

    # api keys. `get_api_key` is the ONE unscoped read: auth looks a key up by id before the
    # uid is known, then compares the secret hash. Everything else is uid-scoped.
    def get_api_key(self, keyid: str) -> ApiKeyDoc | None: ...
    def create_api_key(self, uid: str, keyid: str, doc: ApiKeyDoc) -> None: ...
    def rotate_api_key(self, uid: str, keyid: str, doc: ApiKeyDoc, at: datetime) -> None: ...
    def revoke_active_api_keys(self, uid: str, at: datetime) -> None: ...
    def active_api_key(self, uid: str) -> ApiKeyDoc | None: ...
    def revoke_api_key(self, uid: str, keyid: str, at: datetime) -> None: ...
    def mark_api_key_used(self, uid: str, keyid: str, at: datetime) -> None: ...

    # usage + idempotency
    def get_usage(self, uid: str, date: str) -> UsageDoc: ...
    def add_usage(self, uid: str, date: str, runs: int = 0, tokens: int = 0) -> UsageDoc: ...
    # SP11 R1/R4: ONE transaction over users/{uid} and the day doc
    # (`usage/{uid}_{YYYY-MM-DD}`; no monthly caps). The day is checked first
    # ("day_cap"), then, for `eval` only, the active-run limit ("concurrent"). Caps come from
    # `effective_cap(user, ...)`. On "ok": the day counter +1 (and `active_runs`+1 for
    # eval). Nothing is written on a refusal.
    def reserve_usage(
        self, uid: str, kind: Kind, date: str, defaults: LimitDefaults, max_active: int
    ) -> ReserveUsageOutcome: ...
    # Decrements `active_runs` (eval only, floor 0); with `refund` also the day
    # counter of the doc given by `date` (floor 0). One transaction.
    def release_usage(
        self, uid: str, kind: Kind, date: str, refund: bool, units: int = 1
    ) -> None: ...
    # ONE transaction: if run `run_id` is not yet `released`, set `released=True` and hand its eval
    # slot back (`active_runs`-1; with `refund and run.counted` also the day counter of
    # `run.cap_date or date`; nothing is handed back when both dates are None). Returns False when
    # it was already released (nothing written). NotFoundError when the run is gone.
    def release_run_slot(
        self, uid: str, sid: str, run_id: str, refund: bool, date: str | None
    ) -> bool: ...
    # the day usage doc for `date` (zero-valued when absent).
    def get_usage_doc(self, uid: str, date: str) -> UsageDoc: ...
    # R4 first run, ONE transaction: reads session + status + user + usage + latest rating; if
    # `state=awaiting_input`, the three flags are set and `first_run_id` is absent, checks the cap
    # like `reserve_usage("eval")`, then creates run `run_id` (snapshot: rating_id, n_runs, preset,
    # stt, code_version), counts it (day runs+1, active_runs+1), sets `first_run_id`,
    # `state=running`, the status mirror and clears the error. Cap/concurrent hit: writes
    # `error=daily_cap_reached` (day) or `concurrent_runs` (concurrent) (state
    # unchanged) and nothing else. Anything not ready: nothing written.
    # Exempt (SP11 R5): when the session has `interview_id` the first run skips the day
    # check and counters (still takes an `active_runs` slot and obeys the concurrent limit); the
    # run doc stores `counted=false` so its release never refunds counters.
    def start_first_run(
        self, uid: str, sid: str, run_id: str, date: str, defaults: LimitDefaults, max_active: int,
        code_version: str, start_progress: int,
    ) -> StartOutcome: ...  # fmt: skip
    # Manual start (`POST /runs`), ONE transaction: reads session + status + user + usage + latest
    # rating; if the session is in one of `allowed_states` with `transcript_ready`,
    # `speaker_confirmed` and `clinician_speaker` set (else "not_ready", nothing written), checks
    # the caps like `reserve_usage("eval")` (hit: "daily_cap"/"concurrent", nothing
    # written), then creates run `run_id` (snapshot: rating_id, `n_runs` or the session's,
    # `preset` or the session's, stt, code_version), counts it (day runs+1, active_runs+1;
    # counted unless free: an interview session's free run, or Try again after a failed free
    # run), sets `first_run_id` if absent, `state=running`, the status mirror
    # (progress `start_progress`, or the max with it when entering from `awaiting_input`) and
    # clears the error. With `retry_max` (R4 retry of a failed run) the start is a retry: only
    # `retry_allowed(session, retry_max, "run")` passes (else "not_ready"), and it also bumps
    # `retry_count` in the same transaction; a cap/concurrent refusal bumps nothing.
    # `eval` (SP04 R3, eval run): also allows report_ready/failed, skips decide_start (no cap or
    # concurrent check), writes counted=False and no usage, and writes the block via txn.create.
    # Exactly one of two racing callers (two manual starts, or a manual start
    # and the first-run gate) wins; the loser reserved nothing, so there is nothing to release.
    def start_run(
        self, uid: str, sid: str, run_id: str, date: str, defaults: LimitDefaults, max_active: int,
        code_version: str, start_progress: int, allowed_states: tuple[str, ...],
        n_runs: int | None, preset: str | None, coded_span: dict | None = None,
        retry_max: int | None = None, eval: EvalRunInfo | None = None,  # noqa: A002
    ) -> StartOutcome: ...  # fmt: skip
    # R4 retry of a validate/transcribe failure, ONE transaction: if `retry_allowed(session,
    # max_retries, step)` (failed, transient, under the cap, failed at `step`), set `state=to`,
    # `retry_count`+1, clear the error, reset `steps.{step}` to a fresh record, restamp
    # `stage_started_at`, mirror the status (progress max'd with `progress`) and return True;
    # otherwise write nothing and return False.
    def retry_step(
        self, uid: str, sid: str, step: str, to: str, max_retries: int, progress: int
    ) -> bool: ...
    # 04-cancel R3, ONE transaction over session + status + usage + user (+ the active run):
    # `cancelled` -> ("cancelled", stored counted), nothing written; a state outside the seven
    # cancellable ones -> ("invalid",); `deleting`/foreign/missing -> NotFoundError. In `running`
    # the unreleased run is marked `failed` (`error="cancelled"`) and its slot released without
    # refund (the same in-txn code as `release_run_slot`). Then `decide_cancel` charges
    # `usage.runs` (also past the cap), and session `state/cancel` + status `state/counted` and
    # `stage_started_at` are set. Nothing is deleted.
    def cancel_session(
        self, uid: str, sid: str, date: str, defaults: LimitDefaults
    ) -> CancelOutcome: ...
    # interviews (SP10 R5): uid-scoped `interviews/{id}`; foreign or missing -> NotFoundError.
    def create_interview(self, uid: str, iid: str, doc: InterviewDoc) -> None: ...
    # ONE transaction (A9): refuse with "open_exists" when the caller has an interview in
    # `created|live`; else check the interview day cap like `reserve_usage("interview")`
    # ("day_cap"), then count the unit on `doc.reservation_date` and create the doc.
    # Concurrent callers: exactly one reserves; nothing is written on a refusal.
    def create_interview_reserved(
        self, uid: str, iid: str, doc: InterviewDoc, defaults: LimitDefaults, max_active: int
    ) -> ReserveUsageOutcome | Literal["open_exists"]: ...
    def get_interview(self, uid: str, iid: str) -> InterviewDoc: ...
    # the caller's interviews still in `created` or `live`
    def list_open_interviews(self, uid: str) -> list[InterviewDoc]: ...
    # ONE transaction: if the interview is in one of `from_states`, set `state=to_state` and
    # `fields` (e.g. `ended_at`, `discarded`) and return the updated doc; otherwise write nothing
    # and return None. Exactly one of several racing callers gets the doc (settle-once).
    # With `refund_rule=(now, threshold_s[, max_refunds])` the same write also stores `refunded`
    # (see `models.interview_refundable`); an interview with `refunded` is never linkable to a
    # session. With `max_refunds` the refund is only given while the reservation day's
    # `interview_refunds` count is below it (the count is bumped in the same transaction).
    def transition_interview(
        self, uid: str, iid: str, from_states: tuple[InterviewState, ...],
        to_state: InterviewState, fields: dict[str, Any] | None = None,
        refund_rule: tuple[datetime, float] | tuple[datetime, float, int] | None = None,
    ) -> InterviewDoc | None: ...  # fmt: skip
    # plain field merge for the relay/uploader (`duration_s`, `state=live`, ...)
    def update_interview(self, uid: str, iid: str, fields: dict[str, Any]) -> None: ...
    # ONE transaction (A19): write `fields` only while the interview's `conn_id` is `conn_id` (the
    # relay's connection lease); True when written, False when another connection owns it now.
    def update_interview_if_conn(
        self, uid: str, iid: str, conn_id: str, fields: dict[str, Any]
    ) -> bool: ...
    def get_idempotency(self, uid: str, key: str) -> IdempotencyDoc | None: ...
    def put_idempotency(self, uid: str, key: str, doc: IdempotencyDoc) -> bool: ...
    def delete_idempotency(self, uid: str, key: str) -> None: ...  # no-op if absent/foreign
