"""In-memory `Repo` with the same semantics as FirestoreRepo. Records `session_status` writes."""

import copy
import threading
from datetime import datetime
from typing import Any, Literal

from onolys_engine_core.transcript import Transcript

from onolys_api.repo import large
from onolys_api.repo.base import (
    Claim,
    ConflictError,
    InterviewLinkOutcome,
    NotFoundError,
    Page,
    StartOutcome,
    decide_claim,
)
from onolys_api.repo.firestore import (
    DRAFT_ID,
    MAX_LIMIT,
    _decode_cursor,
    _encode_cursor,
    _idem_id,
)
from onolys_api.repo.limits import (
    HELD_ERROR_CODE,
    KIND_FIELD,
    START_OUTCOME,
    Kind,
    LimitDefaults,
    ReserveUsageOutcome,
    decide_reserve,
    decide_start,
)
from onolys_api.repo.models import (
    ApiKeyDoc,
    Doc,
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
    error_status_fields,
    interview_refundable,
    utcnow,
)
from onolys_api.storage.base import BlobStore


def _set_path(d: dict[str, Any], dotted: str, value: Any) -> None:
    *parents, leaf = dotted.split(".")
    for p in parents:
        d = d.setdefault(p, {})
    d[leaf] = value


class FakeRepo:
    def __init__(self, blobs: BlobStore) -> None:
        self._blobs = blobs
        self._docs: dict[str, dict[str, Any]] = {}  # full path -> stored dict
        self.status_writes: list[tuple[str, str, dict[str, Any]]] = []
        self._claim_lock = threading.RLock()  # reentrant: release_run_slot calls release_usage

    # ---- storage primitives ----

    def _put(self, path: str, data: dict[str, Any]) -> None:
        self._docs[path] = copy.deepcopy(data)

    def _get(self, path: str) -> dict[str, Any] | None:
        d = self._docs.get(path)
        return copy.deepcopy(d) if d is not None else None

    def _create(self, path: str, data: dict[str, Any]) -> None:
        if path in self._docs:
            raise ConflictError()
        self._put(path, data)

    def _owned(self, path: str, uid: str, missing_ok: bool = False) -> dict[str, Any] | None:
        d = self._get(path)
        if d is None:
            if missing_ok:
                return None
            raise NotFoundError()
        if d.get("uid") != uid:
            raise NotFoundError()
        return d

    def _children(self, sid: str, kind: str) -> list[tuple[str, dict[str, Any]]]:
        prefix = f"sessions/{sid}/{kind}/"
        return [
            (p.removeprefix(prefix), copy.deepcopy(d))
            for p, d in self._docs.items()
            if p.startswith(prefix)
        ]

    @staticmethod
    def _load[M: Doc](model: type[M], doc_id: str, data: dict[str, Any]) -> M:
        return model.model_validate({**data, "id": doc_id})

    def _own(self, uid: str, sid: str) -> None:
        self._owned(f"sessions/{sid}", uid)

    def _own_open(self, uid: str, sid: str) -> None:
        """Owned and not being deleted: the guard of every write that creates a child doc."""
        if self._owned(f"sessions/{sid}", uid).get("state") == "deleting":
            raise NotFoundError()

    def _guarded(self, uid: str, sid: str, pointer) -> None:
        """Re-check after a blob write: a DELETE in between must not keep the blob."""
        try:
            self._own_open(uid, sid)
        except NotFoundError:
            if pointer is not None:
                self._blobs.delete(pointer.key)
            raise

    def _record_status(self, uid: str, sid: str) -> None:
        self.status_writes.append((uid, sid, copy.deepcopy(self._docs[f"session_status/{sid}"])))

    def paths(self, sid: str) -> list[str]:
        """Every stored path of one session (doc, subcollections, status): for deletion checks."""
        return sorted(
            p
            for p in self._docs
            if p in (f"sessions/{sid}", f"session_status/{sid}") or p.startswith(f"sessions/{sid}/")
        )

    # ---- users ----

    def get_user(self, uid: str) -> UserDoc | None:
        d = self._get(f"users/{uid}")
        return self._load(UserDoc, uid, d) if d is not None else None

    def ensure_user(self, uid: str) -> UserDoc:
        d = self._get(f"users/{uid}")
        if d is None:
            doc = UserDoc(id=uid)
            self._put(f"users/{uid}", doc.to_store())
            return doc
        return self._load(UserDoc, uid, d)

    # ---- sessions ----

    def create_session(
        self, uid: str, sid: str, session: SessionDoc, status: SessionStatusDoc
    ) -> None:
        if session.uid != uid or status.uid != uid:
            raise ValueError("document uid does not match the caller")
        if f"sessions/{sid}" in self._docs or f"session_status/{sid}" in self._docs:
            raise ConflictError()
        self._put(f"sessions/{sid}", session.to_store())
        self._put(f"session_status/{sid}", status.to_store())
        self._record_status(uid, sid)

    def create_session_for_interview(
        self, uid: str, iid: str, sid: str, session: SessionDoc, status: SessionStatusDoc,
        draft: RatingDraftDoc,
    ) -> InterviewLinkOutcome:  # fmt: skip
        if session.uid != uid or status.uid != uid:
            raise ValueError("document uid does not match the caller")
        with self._claim_lock:  # the fake's "transaction"
            iv = self._owned(f"interviews/{iid}", uid)
            if iv.get("state") != "ended":
                return "not_ended"
            if iv.get("refunded"):
                return "refunded"
            if iv.get("session_id"):
                return "already_linked"
            if f"sessions/{sid}" in self._docs or f"session_status/{sid}" in self._docs:
                raise ConflictError()
            self._put(f"sessions/{sid}", session.to_store())
            self._put(f"session_status/{sid}", status.to_store())
            self._put(f"sessions/{sid}/ratings/{DRAFT_ID}", draft.to_store())
            self._put(f"interviews/{iid}", {**iv, "session_id": sid})
            self._record_status(uid, sid)
            return "linked"

    def get_session(self, uid: str, sid: str) -> SessionDoc:
        return self._load(SessionDoc, sid, self._owned(f"sessions/{sid}", uid))

    def get_status(self, uid: str, sid: str) -> SessionStatusDoc:
        return self._load(SessionStatusDoc, sid, self._owned(f"session_status/{sid}", uid))

    def update_session(
        self, uid: str, sid: str, fields: dict[str, Any], status: dict[str, Any] | None = None
    ) -> None:
        doc = self._owned(f"sessions/{sid}", uid)
        now = utcnow()
        for k, v in {**fields, "updated_at": now}.items():
            _set_path(doc, k, v)
        self._put(f"sessions/{sid}", doc)
        if status is not None:
            st = self._get(f"session_status/{sid}") or {}
            st.update({**status, "uid": uid, "updated_at": now})
            self._put(f"session_status/{sid}", st)
            self._record_status(uid, sid)

    def confirm_speaker(
        self, uid: str, sid: str, clinician: str, states: tuple[str, ...]
    ) -> bool:
        with self._claim_lock:  # the fake's "transaction"
            doc = self._owned(f"sessions/{sid}", uid)
            if doc.get("state") not in states:
                return False
            self.update_session(
                uid,
                sid,
                {"clinician_speaker": clinician, "speaker_confirmed": True},
                status={"speaker_confirmed": True},
            )
            return True

    def list_sessions(
        self, uid: str, limit: int = 20, cursor: str | None = None
    ) -> Page[SessionDoc]:
        limit = max(1, min(limit, MAX_LIMIT))
        mine = sorted(
            (
                (p.removeprefix("sessions/"), d)
                for p, d in self._docs.items()
                if p.count("/") == 1 and p.startswith("sessions/") and d.get("uid") == uid
            ),
            key=lambda t: (t[1]["created_at"], t[0]),
            reverse=True,
        )
        mine = [(i, d) for i, d in mine if d.get("state") != "deleting"]
        if cursor:
            at, after = _decode_cursor(cursor)
            mine = [(i, d) for i, d in mine if (d["created_at"], i) < (at, after)]
        page = [self._load(SessionDoc, i, copy.deepcopy(d)) for i, d in mine[: limit + 1]]
        more = len(page) > limit
        items = page[:limit]
        return Page(items, _encode_cursor(items[-1].created_at, items[-1].id) if more else None)

    def fail_stale_session(
        self,
        uid: str,
        sid: str,
        state: str,
        before: datetime,
        error: SessionError | None,
        to: str = "failed",
    ) -> bool:
        with self._claim_lock:  # the fake's "transaction"
            sess = self._owned(f"sessions/{sid}", uid)
            assert sess is not None
            started = sess.get("stage_started_at") or sess["updated_at"]
            if sess.get("state") != state or started >= before:
                return False
            now = utcnow()
            sess.update(state=to, error=error.model_dump() if error else None, updated_at=now)
            if error and error.step and error.step in (sess.get("steps") or {}):
                for k, v in (("status", "failed"), ("ended", now), ("error", error.code)):
                    _set_path(sess, f"steps.{error.step}.{k}", v)
            self._put(f"sessions/{sid}", sess)
            status = self._get(f"session_status/{sid}") or {}
            status.update(
                state=to, **error_status_fields(error, sess.get("retry_count", 0)),
                uid=uid, updated_at=now,
            )
            self._put(f"session_status/{sid}", status)
            self._record_status(uid, sid)
            return True

    def delete_session(self, uid: str, sid: str) -> bool:
        s = self._owned(f"sessions/{sid}", uid, missing_ok=True)
        st = self._owned(f"session_status/{sid}", uid, missing_ok=True)
        if s is not None:
            for p in [p for p in self._docs if p.startswith(f"sessions/{sid}/")]:
                del self._docs[p]
            del self._docs[f"sessions/{sid}"]
        if st is not None:
            del self._docs[f"session_status/{sid}"]
        return s is not None or st is not None

    # ---- recordings ----

    def add_recording(self, uid: str, sid: str, rid: str, rec: RecordingDoc) -> None:
        self._own_open(uid, sid)
        self._put(f"sessions/{sid}/recordings/{rid}", rec.to_store())

    def list_recordings(self, uid: str, sid: str) -> list[RecordingDoc]:
        self._own(uid, sid)
        return [self._load(RecordingDoc, i, d) for i, d in self._children(sid, "recordings")]

    # ---- transcripts ----

    def put_transcript(self, uid: str, sid: str, tid: str, transcript: Transcript) -> None:
        self._own_open(uid, sid)
        pointer = large.pack(
            self._blobs, large.transcript_key(uid, sid), transcript.model_dump(mode="json")
        )
        doc = TranscriptDoc(transcript=None if pointer else transcript, pointer=pointer)
        self._guarded(uid, sid, pointer)
        self._put(f"sessions/{sid}/transcripts/{tid}", doc.to_store())

    def get_transcript(self, uid: str, sid: str, tid: str, resolve: bool = True) -> TranscriptDoc:
        self._own(uid, sid)
        d = self._get(f"sessions/{sid}/transcripts/{tid}")
        if d is None:
            raise NotFoundError()
        doc = self._load(TranscriptDoc, tid, d)
        if resolve and doc.pointer is not None:
            doc.transcript = Transcript.model_validate(large.unpack(self._blobs, doc.pointer))
        return doc

    # ---- ratings ----

    def put_rating_revision(self, uid: str, sid: str, rating_id: str, doc: RatingDoc) -> None:
        if rating_id == DRAFT_ID:
            raise ValueError("reserved rating id")
        self._own_open(uid, sid)
        self._create(f"sessions/{sid}/ratings/{rating_id}", doc.to_store())

    def get_rating(self, uid: str, sid: str, rating_id: str) -> RatingDoc:
        self._own(uid, sid)
        d = None if rating_id == DRAFT_ID else self._get(f"sessions/{sid}/ratings/{rating_id}")
        if d is None:
            raise NotFoundError()
        return self._load(RatingDoc, rating_id, d)

    def latest_rating(self, uid: str, sid: str) -> RatingDoc | None:
        self._own(uid, sid)
        revs = [(i, d) for i, d in self._children(sid, "ratings") if i != DRAFT_ID]
        if not revs:
            return None
        i, d = max(revs, key=lambda t: (t[1]["created_at"], t[0]))
        return self._load(RatingDoc, i, d)

    def put_rating_draft(self, uid: str, sid: str, draft: RatingDraftDoc) -> None:
        self._own_open(uid, sid)
        self._put(f"sessions/{sid}/ratings/{DRAFT_ID}", draft.to_store())

    def get_rating_draft(self, uid: str, sid: str) -> RatingDraftDoc | None:
        self._own(uid, sid)
        d = self._get(f"sessions/{sid}/ratings/{DRAFT_ID}")
        return self._load(RatingDraftDoc, DRAFT_ID, d) if d is not None else None

    # ---- runs ----

    def create_run(self, uid: str, sid: str, run_id: str, run: RunDoc) -> None:
        if run.uid != uid:
            raise ValueError("document uid does not match the caller")
        self._own_open(uid, sid)
        self._create(f"sessions/{sid}/runs/{run_id}", run.to_store())

    def get_run(self, uid: str, sid: str, run_id: str) -> RunDoc:
        self._own(uid, sid)
        d = self._get(f"sessions/{sid}/runs/{run_id}")
        if d is None:
            raise NotFoundError()
        return self._load(RunDoc, run_id, d)

    def update_run(self, uid: str, sid: str, run_id: str, fields: dict[str, Any]) -> None:
        self._own(uid, sid)
        d = self._get(f"sessions/{sid}/runs/{run_id}")
        if d is None:
            raise NotFoundError()
        for k, v in fields.items():
            _set_path(d, k, v)
        self._put(f"sessions/{sid}/runs/{run_id}", d)

    def claim_step(self, uid: str, sid: str, step: str, now: datetime, lease_s: float) -> Claim:
        with self._claim_lock:
            doc = self._owned(f"sessions/{sid}", uid)
            rec = (doc.get("steps") or {}).get(step) or {}
            claim = decide_claim(
                rec.get("status"), rec.get("started"), rec.get("attempts", 0), now, lease_s
            )
            if claim.outcome == "claimed":
                for k, v in (
                    ("status", "running"),
                    ("attempts", claim.attempts),
                    ("started", now),
                    ("error", None),
                ):
                    _set_path(doc, f"steps.{step}.{k}", v)
                self._put(f"sessions/{sid}", doc)
            return claim

    def claim_run(self, uid: str, sid: str, run_id: str, now: datetime, lease_s: float) -> Claim:
        self._own(uid, sid)
        with self._claim_lock:
            d = self._get(f"sessions/{sid}/runs/{run_id}")
            if d is None:
                raise NotFoundError()
            claim = decide_claim(
                d.get("status"), d.get("started"), d.get("attempts", 0), now, lease_s
            )
            if claim.outcome == "claimed":
                d.update(status="running", attempts=claim.attempts, started=now, error=None)
                self._put(f"sessions/{sid}/runs/{run_id}", d)
            return claim

    def list_runs(self, uid: str, sid: str) -> list[RunDoc]:
        self._own(uid, sid)
        return sorted(
            (self._load(RunDoc, i, d) for i, d in self._children(sid, "runs")),
            key=lambda r: (r.started or utcnow(), r.run_id),
        )

    def get_run_by_id(self, uid: str, run_id: str) -> RunDoc:
        for path, d in self._docs.items():
            parts = path.split("/")
            if (
                len(parts) == 4
                and parts[0] == "sessions"
                and parts[2] == "runs"
                and d.get("uid") == uid
                and d.get("run_id") == run_id
            ):
                return self._load(RunDoc, parts[3], copy.deepcopy(d))
        raise NotFoundError()

    # ---- reports ----

    def put_report(self, uid: str, sid: str, report_id: str, doc: ReportDoc) -> None:
        self._own_open(uid, sid)
        pointer = large.pack(self._blobs, large.report_key(uid, sid, report_id), doc.report or {})
        stored = doc.model_copy(
            update={"report": None if pointer else doc.report, "pointer": pointer}
        )
        self._guarded(uid, sid, pointer)
        self._put(f"sessions/{sid}/reports/{report_id}", stored.to_store())

    def _resolve_report(self, doc: ReportDoc, resolve: bool) -> ReportDoc:
        if resolve and doc.pointer is not None:
            doc.report = large.unpack(self._blobs, doc.pointer)
        return doc

    def get_report(self, uid: str, sid: str, report_id: str, resolve: bool = True) -> ReportDoc:
        self._own(uid, sid)
        d = self._get(f"sessions/{sid}/reports/{report_id}")
        if d is None:
            raise NotFoundError()
        return self._resolve_report(self._load(ReportDoc, report_id, d), resolve)

    def get_report_by_version(
        self, uid: str, sid: str, version: int, resolve: bool = True
    ) -> ReportDoc:
        self._own(uid, sid)
        for i, d in self._children(sid, "reports"):
            if d.get("version") == version:
                return self._resolve_report(self._load(ReportDoc, i, d), resolve)
        raise NotFoundError()

    def list_reports(self, uid: str, sid: str) -> list[ReportDoc]:
        self._own(uid, sid)
        return sorted(
            (self._load(ReportDoc, i, d) for i, d in self._children(sid, "reports")),
            key=lambda r: r.version,
        )

    # ---- api keys ----

    def get_api_key(self, keyid: str) -> ApiKeyDoc | None:
        d = self._get(f"api_keys/{keyid}")
        return self._load(ApiKeyDoc, keyid, d) if d is not None else None

    def create_api_key(self, uid: str, keyid: str, doc: ApiKeyDoc) -> None:
        if doc.uid != uid:
            raise ValueError("document uid does not match the caller")
        self._create(f"api_keys/{keyid}", doc.to_store())

    def rotate_api_key(self, uid: str, keyid: str, doc: ApiKeyDoc, at: datetime) -> None:
        if doc.uid != uid:
            raise ValueError("document uid does not match the caller")
        with self._claim_lock:
            self.revoke_active_api_keys(uid, at)
            self._create(f"api_keys/{keyid}", doc.to_store())

    def revoke_active_api_keys(self, uid: str, at: datetime) -> None:
        with self._claim_lock:
            for path, d in list(self._docs.items()):
                if (
                    path.startswith("api_keys/")
                    and d.get("uid") == uid
                    and d.get("revoked_at") is None
                ):
                    self._put(path, {**d, "revoked_at": at})

    def active_api_key(self, uid: str) -> ApiKeyDoc | None:
        for path, d in self._docs.items():
            if path.startswith("api_keys/") and d.get("uid") == uid and d.get("revoked_at") is None:
                return self._load(ApiKeyDoc, path.removeprefix("api_keys/"), copy.deepcopy(d))
        return None

    def _update_key(self, uid: str, keyid: str, **fields: datetime) -> None:
        d = self._owned(f"api_keys/{keyid}", uid)
        d.update(fields)
        self._put(f"api_keys/{keyid}", d)

    def revoke_api_key(self, uid: str, keyid: str, at: datetime) -> None:
        self._update_key(uid, keyid, revoked_at=at)

    def mark_api_key_used(self, uid: str, keyid: str, at: datetime) -> None:
        self._update_key(uid, keyid, last_used_at=at)

    # ---- usage + idempotency ----

    def get_usage(self, uid: str, date: str) -> UsageDoc:
        d = self._get(f"usage/{uid}_{date}")
        return self._load(UsageDoc, f"{uid}_{date}", d) if d else UsageDoc(uid=uid, date=date)

    def add_usage(self, uid: str, date: str, runs: int = 0, tokens: int = 0) -> UsageDoc:
        path = f"usage/{uid}_{date}"
        d = self._get(path) or {"uid": uid, "date": date, "runs": 0, "tokens": 0}
        d["runs"] += runs
        d["tokens"] += tokens
        self._put(path, d)
        return self._load(UsageDoc, f"{uid}_{date}", d)

    def reserve_usage(
        self, uid: str, kind: Kind, date: str, defaults: LimitDefaults, max_active: int
    ) -> ReserveUsageOutcome:
        field = KIND_FIELD[kind]
        with self._claim_lock:
            user = self._get(f"users/{uid}") or {}
            day = self._get(f"usage/{uid}_{date}") or {"uid": uid, "date": date}
            outcome = decide_reserve(user, day, kind, defaults, max_active)
            if outcome != "ok":
                return outcome
            self._put(f"usage/{uid}_{date}", {**day, field: day.get(field, 0) + 1})
            if kind == "eval":
                self._put(f"users/{uid}", {**user, "active_runs": user.get("active_runs", 0) + 1})
            return "ok"

    def release_usage(self, uid: str, kind: Kind, date: str, refund: bool, units: int = 1) -> None:
        field = KIND_FIELD[kind]
        with self._claim_lock:
            user = self._get(f"users/{uid}") or {}
            if kind == "eval" and user.get("active_runs", 0) > 0:
                self._put(f"users/{uid}", {**user, "active_runs": user["active_runs"] - 1})
            if refund:
                path = f"usage/{uid}_{date}"
                doc = self._get(path)
                if doc and doc.get(field, 0) > 0:
                    self._put(path, {**doc, field: max(0, doc[field] - units)})

    def release_run_slot(
        self, uid: str, sid: str, run_id: str, refund: bool, date: str | None
    ) -> bool:
        with self._claim_lock:  # the fake's "transaction"
            self._own(uid, sid)
            path = f"sessions/{sid}/runs/{run_id}"
            d = self._get(path)
            if d is None:
                raise NotFoundError()
            if d.get("released"):
                return False
            self._put(path, {**d, "released": True})
            date = d.get("cap_date") or date
            if date:
                self.release_usage(
                    uid, "eval", date, refund and d.get("counted", True), d.get("units", 1)
                )
            return True

    def get_usage_doc(self, uid: str, date: str) -> UsageDoc:
        day = self._get(f"usage/{uid}_{date}")
        return self._load(UsageDoc, f"{uid}_{date}", day) if day else UsageDoc(uid=uid, date=date)

    def start_first_run(
        self, uid: str, sid: str, run_id: str, date: str, defaults: LimitDefaults, max_active: int,
        code_version: str, start_progress: int,
    ) -> StartOutcome:  # fmt: skip
        with self._claim_lock:  # the fake's "transaction"
            sess = self._owned(f"sessions/{sid}", uid)
            assert sess is not None
            if sess.get("first_run_id"):
                return "already"
            if sess.get("state") != "awaiting_input" or not all(
                sess.get(f) for f in ("transcript_ready", "speaker_confirmed", "rating_submitted")
            ):
                return "not_ready"
            status = self._get(f"session_status/{sid}") or {}
            user = self._get(f"users/{uid}") or {}
            usage = self._get(f"usage/{uid}_{date}") or {"uid": uid, "date": date, "runs": 0}
            now = utcnow()
            exempt = bool(sess.get("interview_id")) and not sess.get("free_run_void")
            units = sess.get("n_runs", 1)
            decided = decide_start(user, usage, defaults, max_active, exempt, units)
            if decided != "ok":
                outcome: StartOutcome = START_OUTCOME[decided]  # type: ignore[assignment]
                code = HELD_ERROR_CODE[outcome]
                err = {"code": code, "step": None}
                self._put(f"sessions/{sid}", {**sess, "error": err, "updated_at": now})
                self._put(
                    f"session_status/{sid}", {**status, "error_code": code, "updated_at": now}
                )
                self._record_status(uid, sid)
                return outcome
            revs = [(i, d) for i, d in self._children(sid, "ratings") if i != DRAFT_ID]
            rating_id = max(revs, key=lambda t: (t[1]["created_at"], t[0]))[0] if revs else None
            run = RunDoc(
                uid=uid, session_id=sid, run_id=run_id, n_runs=sess.get("n_runs", 1),
                preset=sess.get("preset"), rating_id=rating_id,
                stt=sess.get("stt"), code_version=code_version, cap_date=date,
                counted=not exempt, units=units, coded_span=sess.get("coded_span"),
            )  # fmt: skip
            self._create(f"sessions/{sid}/runs/{run_id}", run.to_store())
            if not exempt:
                self._put(f"usage/{uid}_{date}", {**usage, "runs": usage.get("runs", 0) + units})
            self._put(f"users/{uid}", {**user, "active_runs": user.get("active_runs", 0) + 1})
            self._put(
                f"sessions/{sid}",
                {**sess, "first_run_id": run_id, "state": "running", "step": None, "error": None,
                 "updated_at": now, "stage_started_at": now},
            )  # fmt: skip
            self._put(
                f"session_status/{sid}",
                {**status, "state": "running", "step": None, "error_code": None,
                 "progress": max(status.get("progress", 0), start_progress), "updated_at": now},
            )  # fmt: skip
            self._record_status(uid, sid)
            return "started"

    def start_run(
        self, uid: str, sid: str, run_id: str, date: str, defaults: LimitDefaults, max_active: int,
        code_version: str, start_progress: int, allowed_states: tuple[str, ...],
        n_runs: int | None, preset: str | None, coded_span: dict | None = None,
    ) -> StartOutcome:  # fmt: skip
        with self._claim_lock:  # the fake's "transaction"
            sess = self._owned(f"sessions/{sid}", uid)
            assert sess is not None
            if sess.get("state") not in allowed_states or not (
                sess.get("transcript_ready")
                and sess.get("speaker_confirmed")
                and sess.get("clinician_speaker")
            ):
                return "not_ready"
            status = self._get(f"session_status/{sid}") or {}
            user = self._get(f"users/{uid}") or {}
            usage = self._get(f"usage/{uid}_{date}") or {"uid": uid, "date": date, "runs": 0}
            # the free first run of an interview-linked session (SP11 R5), same as start_first_run
            first = (
                self._get(f"sessions/{sid}/runs/{sess['first_run_id']}")
                if sess.get("first_run_id")
                else None
            )
            # Try again after a failed free run stays free (review R1): the free rating is owed
            exempt = (
                bool(sess.get("interview_id"))
                and not sess.get("free_run_void")
                and (not sess.get("first_run_id")
                     or (sess.get("state") == "failed" and first is not None
                         and first.get("counted") is False))
            )  # fmt: skip
            units = n_runs or sess.get("n_runs", 1)
            decided = decide_start(user, usage, defaults, max_active, exempt, units)
            if decided != "ok":
                return START_OUTCOME[decided]  # type: ignore[return-value]
            revs = [(i, d) for i, d in self._children(sid, "ratings") if i != DRAFT_ID]
            rating_id = max(revs, key=lambda t: (t[1]["created_at"], t[0]))[0] if revs else None
            run = RunDoc(
                uid=uid, session_id=sid, run_id=run_id,
                n_runs=n_runs or sess.get("n_runs", 1),
                preset=preset or sess.get("preset"), rating_id=rating_id,
                stt=sess.get("stt"), code_version=code_version, cap_date=date,
                counted=not exempt, units=units, coded_span=coded_span,
            )  # fmt: skip
            now = utcnow()
            progress = (
                start_progress
                if sess["state"] in ("report_ready", "failed")
                else max(status.get("progress", 0), start_progress)
            )
            self._create(f"sessions/{sid}/runs/{run_id}", run.to_store())
            if not exempt:
                self._put(f"usage/{uid}_{date}", {**usage, "runs": usage.get("runs", 0) + units})
            self._put(f"users/{uid}", {**user, "active_runs": user.get("active_runs", 0) + 1})
            self._put(
                f"sessions/{sid}",
                {**sess, "first_run_id": sess.get("first_run_id") or run_id, "state": "running",
                 "step": None, "error": None, "updated_at": now, "stage_started_at": now},
            )  # fmt: skip
            self._put(
                f"session_status/{sid}",
                {**status, "state": "running", "step": None, "error_code": None,
                 "progress": progress, "updated_at": now},
            )  # fmt: skip
            self._record_status(uid, sid)
            return "started"

    # ---- interviews ----

    def create_interview(self, uid: str, iid: str, doc: InterviewDoc) -> None:
        if doc.uid != uid:
            raise ValueError("document uid does not match the caller")
        self._create(f"interviews/{iid}", doc.to_store())

    def get_interview(self, uid: str, iid: str) -> InterviewDoc:
        return self._load(InterviewDoc, iid, self._owned(f"interviews/{iid}", uid))

    def create_interview_reserved(
        self, uid: str, iid: str, doc: InterviewDoc, defaults: LimitDefaults, max_active: int
    ) -> ReserveUsageOutcome | Literal["open_exists"]:
        if doc.uid != uid:
            raise ValueError("document uid does not match the caller")
        with self._claim_lock:
            if self.list_open_interviews(uid):
                return "open_exists"
            outcome = self.reserve_usage(
                uid, "interview", doc.reservation_date, defaults, max_active
            )
            if outcome == "ok":
                self._create(f"interviews/{iid}", doc.to_store())
            return outcome

    def list_open_interviews(self, uid: str) -> list[InterviewDoc]:
        return [
            self._load(InterviewDoc, p.removeprefix("interviews/"), copy.deepcopy(d))
            for p, d in self._docs.items()
            if p.startswith("interviews/") and d.get("uid") == uid
            and d.get("state") in ("created", "live")
        ]  # fmt: skip

    def transition_interview(
        self, uid: str, iid: str, from_states: tuple[InterviewState, ...],
        to_state: InterviewState, fields: dict[str, Any] | None = None,
        refund_rule: tuple[datetime, float] | tuple[datetime, float, int] | None = None,
    ) -> InterviewDoc | None:  # fmt: skip
        with self._claim_lock:
            d = self._owned(f"interviews/{iid}", uid)
            if d.get("state") not in from_states:
                return None
            d = {**d, **(fields or {}), "state": to_state}
            if refund_rule is not None:
                d["refunded"] = interview_refundable(d, *refund_rule[:2])
                if d["refunded"] and len(refund_rule) > 2:
                    day_path = f"usage/{uid}_{d['reservation_date']}"
                    day = self._get(day_path) or {"uid": uid, "date": d["reservation_date"]}
                    if day.get("interview_refunds", 0) >= refund_rule[2]:
                        d["refunded"] = False
                    else:
                        self._put(
                            day_path,
                            {**day, "interview_refunds": day.get("interview_refunds", 0) + 1},
                        )
            self._put(f"interviews/{iid}", d)
            return self._load(InterviewDoc, iid, d)

    def update_interview(self, uid: str, iid: str, fields: dict[str, Any]) -> None:
        with self._claim_lock:
            d = self._owned(f"interviews/{iid}", uid)
            self._put(f"interviews/{iid}", {**d, **fields})

    def get_idempotency(self, uid: str, key: str) -> IdempotencyDoc | None:
        path = f"idempotency/{_idem_id(uid, key)}"
        d = self._owned(path, uid, missing_ok=True)
        return self._load(IdempotencyDoc, _idem_id(uid, key), d) if d is not None else None

    def put_idempotency(self, uid: str, key: str, doc: IdempotencyDoc) -> bool:
        path = f"idempotency/{_idem_id(uid, key)}"
        if path in self._docs:
            return False
        self._put(path, {**doc.to_store(), "uid": uid})
        return True

    def delete_idempotency(self, uid: str, key: str) -> None:
        path = f"idempotency/{_idem_id(uid, key)}"
        if self._owned(path, uid, missing_ok=True) is not None:
            del self._docs[path]
