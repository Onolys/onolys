"""Typed Firestore documents, one per collection.

`id` is the document id: filled on read, never written. Datetimes are tz-aware UTC.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from onolys_engine_core.transcript import Transcript
from onolys_miti.result import CodedSpan
from onolys_miti.stt import SttRun
from pydantic import BaseModel, Field, field_validator

SessionState = Literal[
    "created",
    "uploading",
    "validating",
    "transcribing",
    "awaiting_input",
    "running",
    "report_ready",
    "failed",
    "deleting",
    "upload_incomplete",
    "cancelled",
]
# Only the status doc has this state: the session doc of a discarded upload is gone.
StatusState = Literal[SessionState, "upload_failed"]
UPLOAD_FAILED_TTL = timedelta(days=7)
InterviewState = Literal["created", "live", "ended", "abandoned", "uploaded"]
RunStatus = Literal["pending", "running", "done", "failed"]
StepStatus = Literal["pending", "running", "done", "failed"]


def utcnow() -> datetime:
    return datetime.now(UTC)


class Doc(BaseModel):
    id: str = ""

    def to_store(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"id"})


_CONTROL = dict.fromkeys([*range(32), 127])  # str.translate table: drop control characters
CLIENT_CAPS = {"web_version": 64, "user_agent": 200, "recorder_mime": 100, "audio_engine": 100}


class ClientInfo(BaseModel):
    """What produced a session or interview. Client-reported, so every field is
    optional and sanitized, never rejected: non-strings become absent, control characters are
    stripped, and values are cut to a cap. Unknown keys are ignored."""

    web_version: str | None = Field(None, description="Web build id (git SHA, or `dev`)")
    user_agent: str | None = Field(None, description="Browser User-Agent, trimmed to 200 chars")
    recorder_mime: str | None = Field(None, description="MediaRecorder container the web chose")
    audio_engine: str | None = Field(None, description="Web audio engine name and version")

    @field_validator("web_version", "user_agent", "recorder_mime", "audio_engine", mode="before")
    @classmethod
    def _clean(cls, v: Any, info: Any) -> str | None:
        if not isinstance(v, str):
            return None
        out = v.translate(_CONTROL).strip()[: CLIENT_CAPS[info.field_name]]
        return out or None


class RelayInfo(BaseModel):
    """Which voice relay build served an interview; written by the relay at connect."""

    relay_version: str | None = None  # GIT_SHA
    relay_revision: str | None = None  # K_REVISION


class BlobPointer(BaseModel):
    """Firestore holds this instead of an object larger than 500 KB."""

    key: str
    uri: str
    size_bytes: int


class UserDoc(Doc):
    created_at: datetime = Field(default_factory=utcnow)
    prefs: dict[str, Any] = Field(default_factory=dict)
    expiry_days: int | None = None
    # Raw console values: any shape loads (never a 500); `effective_cap` validates.
    limits: Any = None  # {eval|interview: {day: int}}
    max_active_runs: int | None = None  # per-user override of MAX_ACTIVE_RUNS
    active_runs: int = 0  # runs reserved and not yet released (concurrent-run limit)


class SttInfo(BaseModel):
    run: SttRun | None = None
    provider: str = ""
    model: str = ""
    language: str = ""


class StepRecord(BaseModel):
    status: StepStatus = "pending"
    attempts: int = 0
    started: datetime | None = None
    ended: datetime | None = None
    error: str | None = None
    stt_operation: Any = None  # opaque handle from SttAdapter.start (transcribe step only)
    stt_started: datetime | None = None  # when `start` returned: the poll time limit runs from it
    stt_limit_s: float | None = None  # this recording's poll cap (None: the settings maximum)


class UploadInfo(BaseModel):
    """The signed PUT in flight (staging object `uploads/{uid}/{sid}/{upload_id}`)."""

    upload_id: str
    format: str  # canonical format key: mp3 | wav | m4a | webm | ogg
    content_type: str
    size_bytes: int


FailureKind = Literal["transient", "permanent_internal", "user_file"]


def error_status_fields(error: "SessionError | None", retry_count: int) -> dict[str, Any]:
    """The status-doc mirror of a session error: `error_code`, `error_kind`, `counted`,
    `retries_left` (retries still allowed when the kind is transient, else 0). One place for
    every writer (advance, fail_stale_session in both repos)."""
    from onolys_api.config import MAX_SESSION_RETRIES

    if error is None:
        return {"error_code": None, "error_kind": None, "retries_left": 0, "counted": None}
    kind = error.kind
    left = max(0, MAX_SESSION_RETRIES - retry_count) if kind == "transient" else 0
    return {"error_code": error.code, "error_kind": kind, "retries_left": left,
            "counted": error.counted}  # fmt: skip


def retry_allowed(sess: dict[str, Any], max_retries: int, step: str | None = None) -> bool:
    """The one retry rule on a stored session dict, for the repo transactions: `failed`, a
    `transient` error, room under the cap, and the failed
    `step` when the caller names one."""
    if sess.get("state") != "failed" or not sess.get("error"):
        return False
    err = SessionError.model_validate(sess["error"])
    if err.kind != "transient" or sess.get("retry_count", 0) >= max_retries:
        return False
    return step is None or err.step == step


class SessionError(BaseModel):
    code: str
    step: str | None = None
    kind: FailureKind | None = None  # set by the writer from the code (`kind_for_code`)
    counted: bool | None = None  # did this failure use a unit of the user's limit (None: n/a)


class SessionCancel(BaseModel):
    """The result of a user cancel: did it use a unit, how many, and when."""

    counted: bool
    units: int
    at: datetime


class EvalGold(BaseModel):
    sha256: str
    path: str


class EvalSessionInfo(BaseModel):
    """Eval provenance of a session. Never part of a public view or the OpenAPI schema."""

    dataset_id: str | None = None
    dataset_session_id: str
    source: str
    gold: EvalGold | None = None
    # Server-pinned run inputs survive deletion of any group's RunDocs.
    input_sha256: str | None = None


class SessionDoc(Doc):
    uid: str
    title: str | None = None
    state: SessionState = "created"
    step: str | None = None
    language: str = "auto"
    stt: SttInfo | None = None
    change_goal: str | None = None
    coded_span: CodedSpan | None = None
    n_runs: int = 1
    preset: str | None = None
    clinician_speaker: str | None = None
    transcript_ready: bool = False
    speaker_confirmed: bool = False
    rating_submitted: bool = False
    has_rating: bool = False
    first_run_id: str | None = None
    retry_count: int = 0  # user-visible retries used; capped at MAX_SESSION_RETRIES
    client: ClientInfo = Field(default_factory=ClientInfo)  # web build / browser that created it
    interview_id: str | None = None  # set by the AI interview: its first run is free
    upload: UploadInfo | None = None
    steps: dict[str, StepRecord] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error: SessionError | None = None
    cancel: SessionCancel | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    stage_started_at: datetime | None = None  # entered this state; other writes never bump it
    latest_report_version: int | None = None
    discard_code: str | None = None  # tombstone of `discard_failed_upload` (state is `deleting`)
    eval: EvalSessionInfo | None = None  # eval provenance; absent on prod sessions

    def to_store(self) -> dict[str, Any]:
        d = super().to_store()
        if d.get("eval") is None:
            d.pop("eval", None)  # a prod session document has no `eval` key at all
        return d


class SessionStatusDoc(Doc):
    """The only client-readable document: no transcript, rating, report text or PHI."""

    uid: str
    state: StatusState = "created"
    step: str | None = None
    progress: int = 0
    error_code: str | None = None
    error_kind: FailureKind | None = None
    retries_left: int = 0
    counted: bool | None = None
    latest_report_version: int | None = None
    updated_at: datetime = Field(default_factory=utcnow)
    expire_at: datetime | None = None  # only an `upload_failed` stub: Firestore TTL deletes it
    # numbers and timestamps the processing screen interpolates
    started_at: datetime | None = None  # first `uploading` (a re-run: its start)
    stage_started_at: datetime | None = None  # entered the current state
    waited_ms: int = 0  # total time spent in `awaiting_input`
    audio_s: float | None = None  # recording duration
    progress_next: int | None = None  # base % of the next stage (99 on the last)
    stage_expected_s: int | None = None  # typical duration of the current stage
    transcript_ready: bool = False
    speaker_confirmed: bool = False
    rating_submitted: bool = False
    has_rating: bool = False


def upload_failed_stub(uid: str, code: str, now: datetime) -> SessionStatusDoc:
    """The data-free status doc left by a discarded upload: reason only, gone in 7 days."""
    return SessionStatusDoc(
        uid=uid, state="upload_failed", error_code=code, updated_at=now,
        expire_at=now + UPLOAD_FAILED_TTL,
    )  # fmt: skip


class RecordingDoc(Doc):
    gcs_uri: str
    size: int | None = None
    duration_ms: int | None = None
    format: str | None = None
    sha256: str | None = None


def transcript_sha256(transcript: Transcript) -> str:
    """Hash transcript content independently of its inline/blob storage representation."""
    canonical = json.dumps(
        transcript.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def eval_session_input_sha256(session: dict, transcript: dict) -> str:
    """Hash imported eval inputs independently of disposable RunDocs (server-only)."""
    payload = {
        "transcript_sha256": transcript.get("sha256"),
        "language": transcript.get("language"),
        "clinician_speaker": session.get("clinician_speaker"),
        "change_goal": session.get("change_goal") or "",
        "coded_span": session.get("coded_span"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class TranscriptDoc(Doc):
    sha256: str
    language: str
    transcript: Transcript | None = None  # None when stored out of line (pointer set)
    pointer: BlobPointer | None = None
    created_at: datetime = Field(default_factory=utcnow)

    @classmethod
    def build(
        cls, transcript: Transcript, pointer: BlobPointer | None, session_language: str
    ) -> "TranscriptDoc":
        """Resolve stored run inputs once, while the complete transcript is in memory."""
        return cls(
            transcript=None if pointer else transcript,
            pointer=pointer,
            sha256=transcript_sha256(transcript),
            language=transcript.language or session_language,
        )


class RatingDoc(Doc):
    """One final revision (`ratings/{rating_id}`). Firestore only."""

    card: dict[str, Any]
    no_rating: bool = False
    has_rating: bool = True
    schema_version: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class RatingDraftDoc(Doc):
    """The single autosaved draft (`ratings/draft`), overwritten in place."""

    card: dict[str, Any]
    updated_at: datetime = Field(default_factory=utcnow)


class OutputValidationIssue(BaseModel):
    path: str
    message: str


class OutputValidation(BaseModel):
    attempts: int = Field(ge=1, le=2)
    first_issues: list[OutputValidationIssue] = Field(default_factory=list, max_length=10)


class EvalRunInfo(BaseModel):
    """Eval provenance of a run. Written once in the create txn, never updated, and
    never part of a public view."""

    eval_run_id: str
    combo_key: str
    repeat: int
    engine: str  # "miti" or "oneshot:<variant>"
    route_override: dict[str, Any] | None = None  # {provider, model, tier, effort}
    resolved_route: dict[str, Any]  # snapshot: litellm_id, effort, token limits, caching_mode, ...
    engine_version: str


def reject_eval_write(fields: dict[str, Any]) -> None:
    """`RunDoc.eval` is write-once: no `update_run` field path may touch it."""
    if any(k == "eval" or k.startswith("eval.") for k in fields):
        raise ValueError("RunDoc.eval is write-once")


class RunDoc(Doc):
    change_goal: str
    clinician_speaker: str
    language: str
    transcript_sha256: str
    coded_span: CodedSpan | None = None
    uid: str
    session_id: str
    run_id: str
    n_runs: int = 1
    preset: str | None = None
    rating_id: str | None = None
    stt: SttInfo | None = None
    code_version: str = ""
    status: RunStatus = "pending"
    attempts: int = 0
    stage: str | None = None
    started: datetime | None = None
    ended: datetime | None = None
    error: str | None = None
    run_info: dict[str, Any] | None = None
    validation: OutputValidation | None = None
    artifacts_prefix: str | None = None
    cap_date: str | None = None  # UTC day the cap slot was reserved on
    counted: bool = True  # False: run did not consume an eval slot (exempt first run)
    units: int = 1  # usage units charged when `counted` (= n_runs); a refund gives all back
    released: bool = False  # the cap slot was handed back: guards double release
    llm_started: bool = False  # the evaluation was called on some attempt: a unit is spent
    unit_kept: bool | None = None  # set on release: a unit of the limit stays spent (None: open)
    eval: EvalRunInfo | None = None  # eval provenance; absent on prod runs, write-once

    def to_store(self) -> dict[str, Any]:
        d = super().to_store()
        if d.get("eval") is None:
            d.pop("eval", None)  # a prod run document has no `eval` key at all
        return d


class ReportDoc(Doc):
    version: int
    run_id: str
    report: dict[str, Any] | None = None  # None when stored out of line (pointer set)
    pointer: BlobPointer | None = None
    report_schema_version: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class ApiKeyDoc(Doc):
    uid: str
    hash: str
    created: datetime = Field(default_factory=utcnow)
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None


class UsageDoc(Doc):
    uid: str = ""
    date: str = ""
    runs: int = 0  # eval count (the stored field name)
    interviews: int = 0  # absent until the first interview of the day (eval writes create the doc)
    interview_refunds: int = 0  # short-interview refunds given this day (capped)
    tokens: int = 0


class IdempotencyDoc(Doc):
    body_hash: str
    response: dict[str, Any]
    created_at: datetime = Field(default_factory=utcnow)


class InterviewDoc(Doc):
    """`interviews/{id}`. `state`: created -> live -> ended|abandoned -> uploaded.
    `duration_s` and `live` are written by the voice relay; `reservation_date` is the UTC day key
    of the usage reservation, used for its one refund."""

    uid: str
    scenario_id: str
    voice: str
    state: InterviewState = "created"
    created_at: datetime = Field(default_factory=utcnow)
    reservation_date: str
    duration_s: float | None = None
    ended_at: datetime | None = None
    session_id: str | None = None  # set once, with the session, by `create_session_for_interview`
    # written by the voice relay only; never in any response
    resumption_handle: str | None = None
    disconnected_at: datetime | None = None
    seen_at: datetime | None = None  # last relay checkpoint (a live relay refreshes it ~10 s)
    live_at: datetime | None = None  # first created -> live transition (the sweep ceiling's start)
    conn_id: str | None = None  # connection lease: the newest relay connection owns the interview
    refunded: bool = False  # set with the settle transition: a refunded interview never links
    connects: int = 0  # relay connections that went live; capped by AI_MAX_CONNECTS
    client: ClientInfo = Field(default_factory=ClientInfo)  # web build / browser / recorder
    relay: RelayInfo | None = None  # relay build that last served it (written at connect)


def interview_refundable(data: dict[str, Any], now: datetime, threshold_s: float) -> bool:
    """Refund rule for a settling interview: the best known elapsed time is under
    `threshold_s`. A still-connected relay's last checkpoint is aged by `now - seen_at`, so a stale
    `duration_s` cannot be used to dodge the charge. `created` (never live) is 0 s."""
    elapsed = float(data.get("duration_s") or 0.0)
    seen = data.get("seen_at")
    if seen is not None and data.get("disconnected_at") is None:
        elapsed += max(0.0, (now - seen).total_seconds())
    return elapsed < threshold_s
