"""Typed Firestore documents, one per collection in the PRD R7 table.

`id` is the document id: filled on read, never written. Datetimes are tz-aware UTC.
"""

from datetime import UTC, datetime
from typing import Any, Literal

from onolys_core.transcript import Transcript
from pydantic import BaseModel, Field

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
]
InterviewState = Literal["created", "live", "ended", "abandoned", "uploaded"]
RunStatus = Literal["pending", "running", "done", "failed"]
StepStatus = Literal["pending", "running", "done", "failed"]


def utcnow() -> datetime:
    return datetime.now(UTC)


class Doc(BaseModel):
    id: str = ""

    def to_store(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"id"})


class BlobPointer(BaseModel):
    """Firestore holds this instead of an object larger than 500 KB (D11)."""

    key: str
    uri: str
    size_bytes: int


class UserDoc(Doc):
    created_at: datetime = Field(default_factory=utcnow)
    prefs: dict[str, Any] = Field(default_factory=dict)
    expiry_days: int | None = None
    # Raw console values: any shape loads (never a 500, SP11 D6); `effective_cap` validates.
    daily_cap: Any = None  # legacy eval day override (D5, deprecated)
    limits: Any = None  # {eval|interview: {day|month: int}} (SP11 R3)
    max_active_runs: int | None = None  # per-user override of MAX_ACTIVE_RUNS (R8)
    active_runs: int = 0  # runs reserved and not yet released (R8 concurrent limit)


class SttInfo(BaseModel):
    provider: str = ""
    model: str = ""
    language: str = ""


class CodedSpan(BaseModel):
    from_s: float
    to_s: float


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


class SessionError(BaseModel):
    code: str
    step: str | None = None


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
    interview_id: str | None = None  # set by the AI interview (SP10): its first run is free (SP11)
    # set by `validate`: the upload is not the audio the interview's relay recorded, so the free
    # first run is void (A10); an unset flag on an interview session means the free run stands
    free_run_void: bool = False
    upload: UploadInfo | None = None
    steps: dict[str, StepRecord] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error: SessionError | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    stage_started_at: datetime | None = None  # entered this state; other writes never bump it
    latest_report_version: int | None = None


class SessionStatusDoc(Doc):
    """The only client-readable document: no transcript, rating, report text or PHI."""

    uid: str
    state: SessionState = "created"
    step: str | None = None
    progress: int = 0
    error_code: str | None = None
    latest_report_version: int | None = None
    updated_at: datetime = Field(default_factory=utcnow)
    transcript_ready: bool = False
    speaker_confirmed: bool = False
    rating_submitted: bool = False
    has_rating: bool = False


class RecordingDoc(Doc):
    gcs_uri: str
    size: int | None = None
    duration_ms: int | None = None
    format: str | None = None
    sha256: str | None = None


class TranscriptDoc(Doc):
    transcript: Transcript | None = None  # None when stored out of line (pointer set)
    pointer: BlobPointer | None = None
    created_at: datetime = Field(default_factory=utcnow)


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


class RunDoc(Doc):
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
    artifacts_prefix: str | None = None
    cap_date: str | None = None  # UTC day the cap slot was reserved on (R8)
    counted: bool = True  # False: run did not consume an eval slot (exempt first run, SP11 R5)
    units: int = 1  # usage units charged when `counted` (= n_runs); a refund gives all back
    released: bool = False  # the cap slot was handed back: guards double release
    llm_started: bool = False  # the evaluation was called on some attempt: a unit is spent


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
    runs: int = 0  # eval count (name kept: old docs hold it)
    interviews: int = 0  # missing on old docs reads 0
    interview_refunds: int = 0  # short-interview refunds given this day (capped, A9)
    tokens: int = 0


class UsageMonthDoc(Doc):
    """`usage/{uid}_{YYYY-MM}`: per-month counters (SP11 D1)."""

    uid: str = ""
    month: str = ""
    runs: int = 0
    interviews: int = 0


class IdempotencyDoc(Doc):
    body_hash: str
    response: dict[str, Any]
    created_at: datetime = Field(default_factory=utcnow)


class InterviewDoc(Doc):
    """`interviews/{id}` (SP10 R5). `state`: created -> live -> ended|abandoned -> uploaded.
    `duration_s` and `live` are written by the voice relay; `reservation_date` is the UTC day key
    of the SP11 reservation, used for its one refund."""

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


def interview_refundable(data: dict[str, Any], now: datetime, threshold_s: float) -> bool:
    """Refund rule for a settling interview (SP10 R5): the best known elapsed time is under
    `threshold_s`. A still-connected relay's last checkpoint is aged by `now - seen_at`, so a stale
    `duration_s` cannot be used to dodge the charge. `created` (never live) is 0 s."""
    elapsed = float(data.get("duration_s") or 0.0)
    seen = data.get("seen_at")
    if seen is not None and data.get("disconnected_at") is None:
        elapsed += max(0.0, (now - seen).total_seconds())
    return elapsed < threshold_s
