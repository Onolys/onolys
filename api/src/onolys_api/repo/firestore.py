"""Firestore-backed `Repo`. Honours FIRESTORE_DATABASE; uses the emulator when
FIRESTORE_EMULATOR_HOST is set.

uid discipline (D7): collection queries go through `_uid_query`; documents addressed by id go
through `_owned`; both raise `NotFoundError` on a foreign or missing document. A test greps this
file so no function queries without one of the helpers.
"""

import base64
import hashlib
import os
import random
import threading
import time
import weakref
from datetime import datetime
from typing import Any, Literal

from google.api_core.exceptions import Aborted, AlreadyExists, InvalidArgument
from google.api_core.exceptions import NotFound as GoogleNotFound
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter, Increment
from onolys_engine_core.transcript import Transcript

from onolys_api.config import Settings
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
    StepRecord,
    TranscriptDoc,
    UsageDoc,
    UserDoc,
    error_status_fields,
    interview_refundable,
    retry_allowed,
    utcnow,
)
from onolys_api.storage.base import BlobStore

DRAFT_ID = "draft"
MAX_LIMIT = 50
_TXN_ATTEMPTS = 5
_TXN_ROUNDS = 12  # cap/limit counters are hot docs: re-run exhausted transactions with jitter


def make_firestore_client(settings: Settings) -> firestore.Client:
    emulator = bool(os.environ.get("FIRESTORE_EMULATOR_HOST"))
    kwargs: dict[str, Any] = {
        "project": settings.gcp_project or ("demo-onolys" if emulator else None),
        "database": settings.firestore_database or "(default)",
    }
    if emulator:
        from google.auth.credentials import AnonymousCredentials

        kwargs["credentials"] = AnonymousCredentials()
    return firestore.Client(**kwargs)


def _load[M: Doc](model: type[M], snap) -> M:
    return model.model_validate({**(snap.to_dict() or {}), "id": snap.id})


def _encode_cursor(created_at: datetime, sid: str) -> str:
    raw = f"{created_at.isoformat()}|{sid}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    """A cursor is `created_at|id` in urlsafe base64 (a position, not a lookup, so it survives
    its session being deleted); malformed is NotFound (-> 422)."""
    try:
        raw = base64.b64decode(
            (cursor + "=" * (-len(cursor) % 4)).replace("-", "+").replace("_", "/"), validate=True
        ).decode()
        stamp, sep, sid = raw.partition("|")
        created_at = datetime.fromisoformat(stamp)
    except ValueError:  # binascii.Error, UnicodeDecodeError, bad timestamp, non-ASCII input
        raise NotFoundError() from None
    if not sep or not sid or created_at.tzinfo is None:
        raise NotFoundError()
    return created_at, sid


def _is_exhausted(e: ValueError) -> bool:
    """The Firestore client's "Failed to commit transaction in N attempts" ValueError."""
    return str(e).startswith("Failed to commit transaction")


def _uid_query(source, uid: str):
    """The only way a collection (or collection group) is queried: always filtered by uid."""
    return source.where(filter=FieldFilter("uid", "==", uid))


def _owned(ref, uid: str, missing_ok: bool = False):
    """Snapshot of `ref` if it exists and belongs to `uid`; else NotFoundError (or None)."""
    try:
        snap = ref.get()
    except InvalidArgument:  # reserved or over-long doc id: it cannot exist
        raise NotFoundError() from None
    if not snap.exists:
        if missing_ok:
            return None
        raise NotFoundError()
    if (snap.to_dict() or {}).get("uid") != uid:
        raise NotFoundError()
    return snap


def _idem_id(uid: str, key: str) -> str:
    return hashlib.sha256(f"{uid}\0{key}".encode()).hexdigest()


class FirestoreRepo:
    def __init__(self, client: firestore.Client, blobs: BlobStore) -> None:
        self._client = client
        self._blobs = blobs
        # weak values: a uid's lock is dropped once no caller holds it (callers keep a strong ref)
        self._uid_locks: weakref.WeakValueDictionary[str, threading.Lock] = (
            weakref.WeakValueDictionary()
        )
        self._uid_locks_guard = threading.Lock()

    # ---- ownership helpers (every id-addressed call starts here) ----

    def _top(self, name: str, doc_id: str):
        return self._client.collection(name).document(doc_id)

    def _owned_session(self, uid: str, sid: str, missing_ok: bool = False):
        ref = self._top("sessions", sid)
        return ref, _owned(ref, uid, missing_ok)

    def _owned_status(self, uid: str, sid: str, missing_ok: bool = False):
        ref = self._top("session_status", sid)
        return ref, _owned(ref, uid, missing_ok)

    def _session_ref(self, uid: str, sid: str):
        return self._owned_session(uid, sid)[0]

    def _create_child(
        self, uid: str, sid: str, ref, data: dict[str, Any], *, exclusive: bool
    ) -> None:
        """Write one child doc in a transaction that also reads the parent session: it must exist,
        belong to `uid` and not be `deleting`. A DELETE racing the write either runs first (the
        write answers NotFoundError) or after it (the recursive delete removes the doc): no
        orphan. `exclusive` makes an existing doc a ConflictError (create semantics)."""
        sref = self._top("sessions", sid)

        @firestore.transactional
        def txn_fn(txn) -> None:
            snap = sref.get(transaction=txn)
            sess = snap.to_dict() or {}
            if not snap.exists or sess.get("uid") != uid or sess.get("state") == "deleting":
                raise NotFoundError()
            if exclusive and ref.get(transaction=txn).exists:
                raise ConflictError()
            txn.set(ref, data)

        self._contended(txn_fn, uid)

    def _drop_pointer(self, pointer) -> None:
        if pointer is not None:
            self._blobs.delete(pointer.key)

    # ---- users ----

    def get_user(self, uid: str) -> UserDoc | None:
        snap = self._top("users", uid).get()
        return _load(UserDoc, snap) if snap.exists else None

    def ensure_user(self, uid: str) -> UserDoc:
        ref = self._top("users", uid)
        doc = UserDoc(id=uid)
        try:
            ref.create(doc.to_store())
            return doc
        except AlreadyExists:
            return _load(UserDoc, ref.get())

    # ---- sessions ----

    def create_session(
        self, uid: str, sid: str, session: SessionDoc, status: SessionStatusDoc
    ) -> None:
        if session.uid != uid or status.uid != uid:
            raise ValueError("document uid does not match the caller")
        sref, stref = self._top("sessions", sid), self._top("session_status", sid)
        if sref.get().exists or stref.get().exists:
            raise ConflictError()
        batch = self._client.batch()
        batch.create(sref, session.to_store())
        batch.create(stref, status.to_store())
        try:
            batch.commit()
        except AlreadyExists:
            raise ConflictError() from None

    def create_session_for_interview(
        self, uid: str, iid: str, sid: str, session: SessionDoc, status: SessionStatusDoc,
        draft: RatingDraftDoc,
    ) -> InterviewLinkOutcome:  # fmt: skip
        if session.uid != uid or status.uid != uid:
            raise ValueError("document uid does not match the caller")
        iref = self._top("interviews", iid)
        _owned(iref, uid)  # 404 for a foreign or missing interview
        sref, stref = self._top("sessions", sid), self._top("session_status", sid)
        dref = sref.collection("ratings").document(DRAFT_ID)

        @firestore.transactional
        def txn_fn(txn) -> InterviewLinkOutcome:
            snap = iref.get(transaction=txn)
            data = snap.to_dict() or {}
            if not snap.exists or data.get("uid") != uid:
                raise NotFoundError()
            if data.get("state") != "ended":
                return "not_ended"
            if data.get("refunded"):
                return "refunded"
            if data.get("session_id"):
                return "already_linked"
            if sref.get(transaction=txn).exists or stref.get(transaction=txn).exists:
                raise ConflictError()
            txn.create(sref, session.to_store())
            txn.create(stref, status.to_store())
            txn.set(dref, draft.to_store())
            txn.update(iref, {"session_id": sid})
            return "linked"

        return self._contended(txn_fn, uid)

    def get_session(self, uid: str, sid: str) -> SessionDoc:
        return _load(SessionDoc, self._owned_session(uid, sid)[1])

    def get_status(self, uid: str, sid: str) -> SessionStatusDoc:
        return _load(SessionStatusDoc, self._owned_status(uid, sid)[1])

    def update_session(
        self, uid: str, sid: str, fields: dict[str, Any], status: dict[str, Any] | None = None
    ) -> None:
        sref, _ = self._owned_session(uid, sid)
        now = utcnow()
        batch = self._client.batch()
        batch.update(sref, {**fields, "updated_at": now})
        if status is not None:
            stref = self._top("session_status", sid)
            batch.set(stref, {**status, "uid": uid, "updated_at": now}, merge=True)
        for attempt in range(_TXN_ROUNDS):  # a transaction holding the doc can time this write out
            try:
                batch.commit()
                return
            except Aborted:
                if attempt == _TXN_ROUNDS - 1:
                    raise
                time.sleep(random.uniform(0.01, 0.15))

    def confirm_speaker(
        self, uid: str, sid: str, clinician: str, states: tuple[str, ...]
    ) -> bool:
        """Record the clinician only while the session is still in one of `states` (checked and
        written in one transaction, so a run starting concurrently cannot be overwritten)."""
        sref = self._top("sessions", sid)  # read inside the txn only: a plain read can abort
        stref = self._top("session_status", sid)

        @firestore.transactional
        def txn_fn(txn) -> bool:
            snap = sref.get(transaction=txn)
            cur = snap.to_dict() or {}
            if not snap.exists or cur.get("uid") != uid:
                raise NotFoundError()
            if cur.get("state") not in states:
                return False
            now = utcnow()
            txn.update(
                sref,
                {"clinician_speaker": clinician, "speaker_confirmed": True, "updated_at": now},
            )
            txn.set(
                stref, {"speaker_confirmed": True, "uid": uid, "updated_at": now}, merge=True
            )
            return True

        return self._contended(txn_fn, uid)

    def list_sessions(
        self, uid: str, limit: int = 20, cursor: str | None = None
    ) -> Page[SessionDoc]:
        limit = max(1, min(limit, MAX_LIMIT))
        q = (
            _uid_query(self._client.collection("sessions"), uid)
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .order_by("__name__", direction=firestore.Query.DESCENDING)
        )
        after: Any = None
        if cursor:
            created_at, sid = _decode_cursor(cursor)
            after = {"created_at": created_at, "__name__": self._top("sessions", sid)}
        # `deleting` sessions are skipped here, not after paging, so a page is never short
        # while more remain: keep reading until limit + 1 visible docs or the end.
        docs: list[SessionDoc] = []
        while len(docs) <= limit:
            page = list((q if after is None else q.start_after(after)).limit(limit + 1).stream())
            for snap in page:
                after = snap
                doc = _load(SessionDoc, snap)
                if doc.state != "deleting":
                    docs.append(doc)
                    if len(docs) > limit:
                        break
            if len(page) < limit + 1:
                break
        more = len(docs) > limit
        items = docs[:limit]
        nxt = _encode_cursor(items[-1].created_at, items[-1].id) if more and items else None
        return Page(items, nxt)

    def fail_stale_session(
        self,
        uid: str,
        sid: str,
        state: str,
        before: datetime,
        error: SessionError | None,
        to: str = "failed",
    ) -> bool:
        sref, _ = self._owned_session(uid, sid)
        stref = self._top("session_status", sid)

        @firestore.transactional
        def txn_fn(txn) -> bool:
            snap = sref.get(transaction=txn)
            sess = snap.to_dict() or {}
            if sess.get("uid") != uid:
                raise NotFoundError()
            started = sess.get("stage_started_at") or sess["updated_at"]
            if sess.get("state") != state or started >= before:
                return False
            now = utcnow()
            fields: dict[str, Any] = {"state": to, "error": error.model_dump() if error else None,
                                      "updated_at": now}  # fmt: skip
            if error and error.step and error.step in (sess.get("steps") or {}):
                fields[f"steps.{error.step}.status"] = "failed"
                fields[f"steps.{error.step}.ended"] = now
                fields[f"steps.{error.step}.error"] = error.code
            txn.update(sref, fields)
            txn.set(
                stref,
                {
                    "state": to,
                    **error_status_fields(error, sess.get("retry_count", 0)),
                    "uid": uid,
                    "updated_at": now,
                },  # fmt: skip
                merge=True,
            )
            return True

        return self._contended(txn_fn, uid)

    def delete_session(self, uid: str, sid: str) -> bool:
        sref, ssnap = self._owned_session(uid, sid, missing_ok=True)
        stref, stsnap = self._owned_status(uid, sid, missing_ok=True)
        if ssnap is not None:
            self._client.recursive_delete(sref)
        if stsnap is not None:
            stref.delete()
        return ssnap is not None or stsnap is not None

    # ---- recordings ----

    def add_recording(self, uid: str, sid: str, rid: str, rec: RecordingDoc) -> None:
        ref = self._session_ref(uid, sid).collection("recordings").document(rid)
        self._create_child(uid, sid, ref, rec.to_store(), exclusive=False)

    def list_recordings(self, uid: str, sid: str) -> list[RecordingDoc]:
        coll = self._session_ref(uid, sid).collection("recordings")
        return [_load(RecordingDoc, s) for s in coll.stream()]

    # ---- transcripts (large-object rule) ----

    def put_transcript(self, uid: str, sid: str, tid: str, transcript: Transcript) -> None:
        ref = self._session_ref(uid, sid).collection("transcripts").document(tid)
        pointer = large.pack(
            self._blobs, large.transcript_key(uid, sid), transcript.model_dump(mode="json")
        )
        doc = TranscriptDoc(transcript=None if pointer else transcript, pointer=pointer)
        try:
            self._create_child(uid, sid, ref, doc.to_store(), exclusive=False)
        except NotFoundError:
            self._drop_pointer(pointer)  # the session went away while the blob was written
            raise

    def get_transcript(self, uid: str, sid: str, tid: str, resolve: bool = True) -> TranscriptDoc:
        ref = self._session_ref(uid, sid).collection("transcripts").document(tid)
        snap = ref.get()
        if not snap.exists:
            raise NotFoundError()
        doc = _load(TranscriptDoc, snap)
        if resolve and doc.pointer is not None:
            doc.transcript = Transcript.model_validate(large.unpack(self._blobs, doc.pointer))
        return doc

    # ---- ratings ----

    def put_rating_revision(self, uid: str, sid: str, rating_id: str, doc: RatingDoc) -> None:
        if rating_id == DRAFT_ID:
            raise ValueError("reserved rating id")
        ref = self._session_ref(uid, sid).collection("ratings").document(rating_id)
        self._create_child(uid, sid, ref, doc.to_store(), exclusive=True)

    def get_rating(self, uid: str, sid: str, rating_id: str) -> RatingDoc:
        if rating_id == DRAFT_ID:
            raise NotFoundError()
        snap = self._session_ref(uid, sid).collection("ratings").document(rating_id).get()
        if not snap.exists:
            raise NotFoundError()
        return _load(RatingDoc, snap)

    def latest_rating(self, uid: str, sid: str) -> RatingDoc | None:
        coll = self._session_ref(uid, sid).collection("ratings")
        # the draft has no created_at, so ordering by it leaves the draft out
        q = coll.order_by("created_at", direction=firestore.Query.DESCENDING).limit(1)
        snaps = [s for s in q.stream() if s.id != DRAFT_ID]
        return _load(RatingDoc, snaps[0]) if snaps else None

    def put_rating_draft(self, uid: str, sid: str, draft: RatingDraftDoc) -> None:
        ref = self._session_ref(uid, sid).collection("ratings").document(DRAFT_ID)
        self._create_child(uid, sid, ref, draft.to_store(), exclusive=False)

    def get_rating_draft(self, uid: str, sid: str) -> RatingDraftDoc | None:
        snap = self._session_ref(uid, sid).collection("ratings").document(DRAFT_ID).get()
        return _load(RatingDraftDoc, snap) if snap.exists else None

    # ---- runs ----

    def create_run(self, uid: str, sid: str, run_id: str, run: RunDoc) -> None:
        if run.uid != uid:
            raise ValueError("document uid does not match the caller")
        ref = self._session_ref(uid, sid).collection("runs").document(run_id)
        self._create_child(uid, sid, ref, run.to_store(), exclusive=True)

    def _run_ref(self, uid: str, sid: str, run_id: str):
        return self._session_ref(uid, sid).collection("runs").document(run_id)

    def get_run(self, uid: str, sid: str, run_id: str) -> RunDoc:
        snap = self._run_ref(uid, sid, run_id).get()
        if not snap.exists:
            raise NotFoundError()
        return _load(RunDoc, snap)

    def update_run(self, uid: str, sid: str, run_id: str, fields: dict[str, Any]) -> None:
        ref = self._run_ref(uid, sid, run_id)
        if not ref.get().exists:
            raise NotFoundError()
        try:  # fails when the run (or its session) was deleted since the check: no resurrection
            ref.update(fields)
        except GoogleNotFound:
            raise NotFoundError() from None

    def claim_step(self, uid: str, sid: str, step: str, now: datetime, lease_s: float) -> Claim:
        ref = self._session_ref(uid, sid)

        @firestore.transactional
        def txn_fn(txn) -> Claim:
            snap = ref.get(transaction=txn)
            if not snap.exists or (snap.to_dict() or {}).get("uid") != uid:
                raise NotFoundError()
            rec = ((snap.to_dict() or {}).get("steps") or {}).get(step) or {}
            claim = decide_claim(
                rec.get("status"), rec.get("started"), rec.get("attempts", 0), now, lease_s
            )
            if claim.outcome == "claimed":
                txn.update(
                    ref,
                    {
                        f"steps.{step}.status": "running",
                        f"steps.{step}.attempts": claim.attempts,
                        f"steps.{step}.started": now,
                        f"steps.{step}.error": None,
                    },
                )
            return claim

        return self._contended(txn_fn, uid)

    def claim_run(self, uid: str, sid: str, run_id: str, now: datetime, lease_s: float) -> Claim:
        ref = self._run_ref(uid, sid, run_id)

        @firestore.transactional
        def txn_fn(txn) -> Claim:
            snap = ref.get(transaction=txn)
            if not snap.exists:
                raise NotFoundError()
            d = snap.to_dict() or {}
            claim = decide_claim(
                d.get("status"), d.get("started"), d.get("attempts", 0), now, lease_s
            )
            if claim.outcome == "claimed":
                txn.update(
                    ref,
                    {
                        "status": "running",
                        "attempts": claim.attempts,
                        "started": now,
                        "error": None,
                    },
                )
            return claim

        return self._contended(txn_fn, uid)

    def list_runs(self, uid: str, sid: str) -> list[RunDoc]:
        coll = self._session_ref(uid, sid).collection("runs")
        return sorted(
            (_load(RunDoc, s) for s in coll.stream()),
            key=lambda r: (r.started or utcnow(), r.run_id),
        )

    def get_run_by_id(self, uid: str, run_id: str) -> RunDoc:
        q = _uid_query(self._client.collection_group("runs"), uid)
        for snap in q.where(filter=FieldFilter("run_id", "==", run_id)).limit(1).stream():
            return _load(RunDoc, snap)
        raise NotFoundError()

    # ---- reports (large-object rule) ----

    def put_report(self, uid: str, sid: str, report_id: str, doc: ReportDoc) -> None:
        ref = self._session_ref(uid, sid).collection("reports").document(report_id)
        payload = doc.report or {}
        pointer = large.pack(self._blobs, large.report_key(uid, sid, report_id), payload)
        stored = doc.model_copy(
            update={"report": None if pointer else doc.report, "pointer": pointer}
        )
        try:
            self._create_child(uid, sid, ref, stored.to_store(), exclusive=False)
        except NotFoundError:
            self._drop_pointer(pointer)
            raise

    def _resolve_report(self, doc: ReportDoc, resolve: bool) -> ReportDoc:
        if resolve and doc.pointer is not None:
            doc.report = large.unpack(self._blobs, doc.pointer)
        return doc

    def get_report(self, uid: str, sid: str, report_id: str, resolve: bool = True) -> ReportDoc:
        snap = self._session_ref(uid, sid).collection("reports").document(report_id).get()
        if not snap.exists:
            raise NotFoundError()
        return self._resolve_report(_load(ReportDoc, snap), resolve)

    def get_report_by_version(
        self, uid: str, sid: str, version: int, resolve: bool = True
    ) -> ReportDoc:
        coll = self._session_ref(uid, sid).collection("reports")
        for snap in coll.where(filter=FieldFilter("version", "==", version)).limit(1).stream():
            return self._resolve_report(_load(ReportDoc, snap), resolve)
        raise NotFoundError()

    def list_reports(self, uid: str, sid: str) -> list[ReportDoc]:
        coll = self._session_ref(uid, sid).collection("reports")
        return sorted((_load(ReportDoc, s) for s in coll.stream()), key=lambda r: r.version)

    # ---- api keys ----

    def get_api_key(self, keyid: str) -> ApiKeyDoc | None:
        snap = self._top("api_keys", keyid).get()
        return _load(ApiKeyDoc, snap) if snap.exists else None

    def create_api_key(self, uid: str, keyid: str, doc: ApiKeyDoc) -> None:
        if doc.uid != uid:
            raise ValueError("document uid does not match the caller")
        try:
            self._top("api_keys", keyid).create(doc.to_store())
        except AlreadyExists:
            raise ConflictError() from None

    def rotate_api_key(self, uid: str, keyid: str, doc: ApiKeyDoc, at: datetime) -> None:
        """Revoke every active key and create the new one in ONE transaction: concurrent calls
        leave exactly one active key."""
        if doc.uid != uid:
            raise ValueError("document uid does not match the caller")
        new_ref = self._top("api_keys", keyid)

        @firestore.transactional
        def txn_fn(txn) -> None:
            if new_ref.get(transaction=txn).exists:
                raise ConflictError()
            self._revoke_active_in(txn, uid, at)
            txn.create(new_ref, doc.to_store())

        self._contended(txn_fn, uid)

    def revoke_active_api_keys(self, uid: str, at: datetime) -> None:
        @firestore.transactional
        def txn_fn(txn) -> None:
            self._revoke_active_in(txn, uid, at)

        self._contended(txn_fn, uid)

    def _revoke_active_in(self, txn, uid: str, at: datetime) -> None:
        q = _uid_query(self._client.collection("api_keys"), uid)
        for snap in q.where(filter=FieldFilter("revoked_at", "==", None)).stream(transaction=txn):
            txn.update(snap.reference, {"revoked_at": at})

    def active_api_key(self, uid: str) -> ApiKeyDoc | None:
        q = _uid_query(self._client.collection("api_keys"), uid)
        for snap in q.where(filter=FieldFilter("revoked_at", "==", None)).limit(1).stream():
            return _load(ApiKeyDoc, snap)
        return None

    def revoke_api_key(self, uid: str, keyid: str, at: datetime) -> None:
        ref = self._top("api_keys", keyid)
        _owned(ref, uid)
        ref.update({"revoked_at": at})

    def mark_api_key_used(self, uid: str, keyid: str, at: datetime) -> None:
        ref = self._top("api_keys", keyid)
        _owned(ref, uid)
        ref.update({"last_used_at": at})

    # ---- usage + idempotency ----

    def get_usage(self, uid: str, date: str) -> UsageDoc:
        snap = self._top("usage", f"{uid}_{date}").get()
        return _load(UsageDoc, snap) if snap.exists else UsageDoc(uid=uid, date=date)

    def add_usage(self, uid: str, date: str, runs: int = 0, tokens: int = 0) -> UsageDoc:
        ref = self._top("usage", f"{uid}_{date}")
        ref.set(
            {"uid": uid, "date": date, "runs": Increment(runs), "tokens": Increment(tokens)},
            merge=True,
        )
        return _load(UsageDoc, ref.get())

    def reserve_usage(
        self, uid: str, kind: Kind, date: str, defaults: LimitDefaults, max_active: int
    ) -> ReserveUsageOutcome:
        day_ref = self._top("usage", f"{uid}_{date}")
        user_ref = self._top("users", uid)
        field = KIND_FIELD[kind]

        @firestore.transactional
        def txn_fn(txn) -> ReserveUsageOutcome:
            user = user_ref.get(transaction=txn).to_dict() or {}
            day = day_ref.get(transaction=txn).to_dict() or {}
            outcome = decide_reserve(user, day, kind, defaults, max_active)
            if outcome != "ok":
                return outcome
            txn.set(day_ref, {"uid": uid, "date": date, field: day.get(field, 0) + 1}, merge=True)
            if kind == "eval":
                txn.set(user_ref, {"active_runs": user.get("active_runs", 0) + 1}, merge=True)
            return "ok"

        return self._contended(txn_fn, uid)

    def release_usage(self, uid: str, kind: Kind, date: str, refund: bool, units: int = 1) -> None:
        day_ref = self._top("usage", f"{uid}_{date}")
        user_ref = self._top("users", uid)
        field = KIND_FIELD[kind]

        @firestore.transactional
        def txn_fn(txn) -> None:
            user = user_ref.get(transaction=txn).to_dict() or {}
            day = day_ref.get(transaction=txn).to_dict() or {}
            if kind == "eval" and user.get("active_runs", 0) > 0:
                txn.set(user_ref, {"active_runs": user["active_runs"] - 1}, merge=True)
            if refund:
                if day.get(field, 0) > 0:
                    txn.set(day_ref, {field: max(0, day[field] - units)}, merge=True)

        self._contended(txn_fn, uid)

    def release_run_slot(
        self, uid: str, sid: str, run_id: str, refund: bool, date: str | None
    ) -> bool:
        run_ref = self._run_ref(uid, sid, run_id)
        user_ref = self._top("users", uid)

        @firestore.transactional
        def txn_fn(txn) -> bool:
            run_snap = run_ref.get(transaction=txn)
            if not run_snap.exists:
                raise NotFoundError()
            run = run_snap.to_dict() or {}
            if run.get("released"):
                return False
            day_key = run.get("cap_date") or date
            user = user_ref.get(transaction=txn).to_dict() or {}
            day_ref = self._top("usage", f"{uid}_{day_key}") if day_key else None
            day = (day_ref.get(transaction=txn).to_dict() or {}) if day_ref else {}
            counted = run.get("counted", True)
            refunded = bool(day_key) and refund and counted
            txn.update(run_ref, {"released": True, "unit_kept": counted and not refunded})
            if day_key:
                if user.get("active_runs", 0) > 0:
                    txn.set(user_ref, {"active_runs": user["active_runs"] - 1}, merge=True)
                if refund and run.get("counted", True):
                    field = KIND_FIELD["eval"]
                    units = run.get("units", 1)
                    if day.get(field, 0) > 0:
                        txn.set(day_ref, {field: max(0, day[field] - units)}, merge=True)
            return True

        try:
            return self._contended(txn_fn, uid)
        except GoogleNotFound:  # the run's session was deleted under it
            raise NotFoundError() from None

    def get_usage_doc(self, uid: str, date: str) -> UsageDoc:
        day = self._top("usage", f"{uid}_{date}").get()
        return _load(UsageDoc, day) if day.exists else UsageDoc(uid=uid, date=date)

    def start_first_run(
        self, uid: str, sid: str, run_id: str, date: str, defaults: LimitDefaults, max_active: int,
        code_version: str, start_progress: int,
    ) -> StartOutcome:  # fmt: skip
        sref = self._session_ref(uid, sid)
        stref = self._top("session_status", sid)
        usage_ref = self._top("usage", f"{uid}_{date}")
        user_ref = self._top("users", uid)
        run_ref = sref.collection("runs").document(run_id)
        ratings = sref.collection("ratings")
        newest = ratings.order_by("created_at", direction=firestore.Query.DESCENDING).limit(1)

        @firestore.transactional
        def txn_fn(txn) -> StartOutcome:
            snap = sref.get(transaction=txn)
            sess = snap.to_dict() or {}
            if not snap.exists or sess.get("uid") != uid:
                raise NotFoundError()
            if sess.get("first_run_id"):
                return "already"
            if sess.get("state") != "awaiting_input" or not all(
                sess.get(f) for f in ("transcript_ready", "speaker_confirmed", "rating_submitted")
            ):
                return "not_ready"
            status = stref.get(transaction=txn).to_dict() or {}
            user = user_ref.get(transaction=txn).to_dict() or {}
            usage = usage_ref.get(transaction=txn).to_dict() or {}
            latest = [s for s in newest.get(transaction=txn) if s.id != DRAFT_ID]
            now = utcnow()
            exempt = bool(sess.get("interview_id"))  # never counted (03-failure-policy R5)
            units = sess.get("n_runs", 1)
            decided = decide_start(user, usage, defaults, max_active, exempt, units)
            if decided != "ok":
                outcome: StartOutcome = START_OUTCOME[decided]  # type: ignore[assignment]
                code = HELD_ERROR_CODE[outcome]
                txn.update(sref, {"error": {"code": code, "step": None}, "updated_at": now})
                txn.set(stref, {"error_code": code, "uid": uid, "updated_at": now}, merge=True)
                return outcome
            run = RunDoc(
                uid=uid, session_id=sid, run_id=run_id, n_runs=sess.get("n_runs", 1),
                preset=sess.get("preset"), rating_id=latest[0].id if latest else None,
                stt=sess.get("stt"), code_version=code_version, cap_date=date,
                counted=not exempt, units=units, coded_span=sess.get("coded_span"),
            )  # fmt: skip
            txn.create(run_ref, run.to_store())
            if not exempt:
                txn.set(
                    usage_ref,
                    {"uid": uid, "date": date, "runs": usage.get("runs", 0) + units},
                    merge=True,
                )
            txn.set(user_ref, {"active_runs": user.get("active_runs", 0) + 1}, merge=True)
            txn.update(
                sref,
                {"first_run_id": run_id, "state": "running", "step": None, "error": None,
                 "updated_at": now, "stage_started_at": now},
            )  # fmt: skip
            txn.set(
                stref,
                {"state": "running", "step": None, "error_code": None, "uid": uid,
                 "progress": max(status.get("progress", 0), start_progress), "updated_at": now},
                merge=True,
            )  # fmt: skip
            return "started"

        return self._contended(txn_fn, uid)

    def start_run(
        self, uid: str, sid: str, run_id: str, date: str, defaults: LimitDefaults, max_active: int,
        code_version: str, start_progress: int, allowed_states: tuple[str, ...],
        n_runs: int | None, preset: str | None, coded_span: dict | None = None,
        retry_max: int | None = None,
    ) -> StartOutcome:  # fmt: skip
        sref = self._session_ref(uid, sid)
        stref = self._top("session_status", sid)
        usage_ref = self._top("usage", f"{uid}_{date}")
        user_ref = self._top("users", uid)
        run_ref = sref.collection("runs").document(run_id)
        ratings = sref.collection("ratings")
        newest = ratings.order_by("created_at", direction=firestore.Query.DESCENDING).limit(1)

        @firestore.transactional
        def txn_fn(txn) -> StartOutcome:
            snap = sref.get(transaction=txn)
            sess = snap.to_dict() or {}
            if not snap.exists or sess.get("uid") != uid:
                raise NotFoundError()
            if sess.get("state") not in allowed_states or not (
                sess.get("transcript_ready")
                and sess.get("speaker_confirmed")
                and sess.get("clinician_speaker")
            ):
                return "not_ready"
            if retry_max is not None and not retry_allowed(sess, retry_max, "run"):
                return "not_ready"
            status = stref.get(transaction=txn).to_dict() or {}
            user = user_ref.get(transaction=txn).to_dict() or {}
            usage = usage_ref.get(transaction=txn).to_dict() or {}
            latest = [s for s in newest.get(transaction=txn) if s.id != DRAFT_ID]
            # the free first run of an interview-linked session (SP11 R5), same as start_first_run
            first = (
                (sref.collection("runs").document(sess["first_run_id"]).get(transaction=txn)
                 .to_dict() or {})
                if sess.get("first_run_id")
                else {}
            )
            # Try again after a failed free run stays free (review R1): the free rating is owed
            exempt = (
                bool(sess.get("interview_id"))
                and (not sess.get("first_run_id")
                     or (sess.get("state") == "failed" and first.get("counted") is False))
            )  # fmt: skip
            units = n_runs or sess.get("n_runs", 1)
            decided = decide_start(user, usage, defaults, max_active, exempt, units)
            if decided != "ok":
                return START_OUTCOME[decided]  # type: ignore[return-value]
            run = RunDoc(
                uid=uid, session_id=sid, run_id=run_id, n_runs=n_runs or sess.get("n_runs", 1),
                preset=preset or sess.get("preset"), rating_id=latest[0].id if latest else None,
                stt=sess.get("stt"), code_version=code_version, cap_date=date,
                counted=not exempt, units=units, coded_span=coded_span,
            )  # fmt: skip
            progress = (
                start_progress
                if sess["state"] in ("report_ready", "failed")
                else max(status.get("progress", 0), start_progress)
            )
            now_ = utcnow()
            fields = {
                "state": "running",
                "step": None,
                "error": None,
                "updated_at": now_,
                "stage_started_at": now_,
            }
            if not sess.get("first_run_id"):
                fields["first_run_id"] = run_id
            if retry_max is not None:
                fields["retry_count"] = sess.get("retry_count", 0) + 1
            txn.create(run_ref, run.to_store())
            if not exempt:
                txn.set(
                    usage_ref,
                    {"uid": uid, "date": date, "runs": usage.get("runs", 0) + units},
                    merge=True,
                )
            txn.set(user_ref, {"active_runs": user.get("active_runs", 0) + 1}, merge=True)
            txn.update(sref, fields)
            txn.set(
                stref,
                {"state": "running", "step": None, **error_status_fields(None, 0), "uid": uid,
                 "progress": progress, "updated_at": fields["updated_at"]},
                merge=True,
            )  # fmt: skip
            return "started"

        return self._contended(txn_fn, uid)

    def retry_step(
        self, uid: str, sid: str, step: str, to: str, max_retries: int, progress: int
    ) -> bool:
        sref, _ = self._owned_session(uid, sid)
        stref = self._top("session_status", sid)

        @firestore.transactional
        def txn_fn(txn) -> bool:
            snap = sref.get(transaction=txn)
            sess = snap.to_dict() or {}
            if not snap.exists or sess.get("uid") != uid:
                raise NotFoundError()
            if not retry_allowed(sess, max_retries, step):
                return False
            status = stref.get(transaction=txn).to_dict() or {}
            now = utcnow()
            txn.update(sref, {
                "state": to, "step": step, "error": None,
                f"steps.{step}": StepRecord().model_dump(),
                "retry_count": sess.get("retry_count", 0) + 1,
                "updated_at": now, "stage_started_at": now,
            })  # fmt: skip
            txn.set(
                stref,
                {"state": to, "step": step, **error_status_fields(None, 0), "uid": uid,
                 "progress": max(status.get("progress", 0), progress), "updated_at": now},
                merge=True,
            )  # fmt: skip
            return True

        return self._contended(txn_fn, uid)

    def _uid_lock(self, uid: str) -> threading.Lock:
        with self._uid_locks_guard:
            lock = self._uid_locks.get(uid)
            if lock is None:
                lock = self._uid_locks[uid] = threading.Lock()
            return lock

    def _contended(self, txn_fn, uid: str):
        # Same-user txns (usage, claims, session children) hit the same hot docs. Firestore locks
        # pessimistically and the client retry has no backoff, so a burst thrashes until all
        # attempts are exhausted: queue same-process callers per uid; retry rounds stay for
        # cross-instance contention.
        with self._uid_lock(uid):
            return self._retry_txn(txn_fn)

    def _retry_txn(self, txn_fn):
        for round_ in range(_TXN_ROUNDS):
            try:
                return txn_fn(self._client.transaction(max_attempts=_TXN_ATTEMPTS))
            except (ValueError, Aborted) as e:
                # contention only: the client's "exhausted attempts" ValueError (chained from the
                # last abort) or a raw 409 lock timeout. Any other ValueError is a real bug in
                # txn_fn: raise it at once instead of retrying under the uid lock.
                if isinstance(e, ValueError) and not _is_exhausted(e):
                    raise
                if round_ == _TXN_ROUNDS - 1:
                    raise
                time.sleep(random.uniform(0.01, 0.15))

    # ---- interviews ----

    def create_interview(self, uid: str, iid: str, doc: InterviewDoc) -> None:
        if doc.uid != uid:
            raise ValueError("document uid does not match the caller")
        try:
            self._top("interviews", iid).create(doc.to_store())
        except AlreadyExists:
            raise ConflictError() from None

    def create_interview_reserved(
        self, uid: str, iid: str, doc: InterviewDoc, defaults: LimitDefaults, max_active: int
    ) -> ReserveUsageOutcome | Literal["open_exists"]:
        if doc.uid != uid:
            raise ValueError("document uid does not match the caller")
        date = doc.reservation_date
        day_ref = self._top("usage", f"{uid}_{date}")
        user_ref = self._top("users", uid)
        iv_ref = self._top("interviews", iid)
        open_q = _uid_query(self._client.collection("interviews"), uid).where(
            filter=FieldFilter("state", "in", ["created", "live"])
        )

        @firestore.transactional
        def txn_fn(txn):
            if any(True for _ in open_q.get(transaction=txn)):
                return "open_exists"
            user = user_ref.get(transaction=txn).to_dict() or {}
            day = day_ref.get(transaction=txn).to_dict() or {}
            outcome = decide_reserve(user, day, "interview", defaults, max_active)
            if outcome != "ok":
                return outcome
            field = KIND_FIELD["interview"]
            txn.set(day_ref, {"uid": uid, "date": date, field: day.get(field, 0) + 1}, merge=True)
            txn.create(iv_ref, doc.to_store())
            return "ok"

        return self._contended(txn_fn, uid)

    def get_interview(self, uid: str, iid: str) -> InterviewDoc:
        return _load(InterviewDoc, _owned(self._top("interviews", iid), uid))

    def list_open_interviews(self, uid: str) -> list[InterviewDoc]:
        q = _uid_query(self._client.collection("interviews"), uid).where(
            filter=FieldFilter("state", "in", ["created", "live"])
        )
        return [_load(InterviewDoc, snap) for snap in q.stream()]

    def transition_interview(
        self, uid: str, iid: str, from_states: tuple[InterviewState, ...],
        to_state: InterviewState, fields: dict[str, Any] | None = None,
        refund_rule: tuple[datetime, float] | tuple[datetime, float, int] | None = None,
    ) -> InterviewDoc | None:  # fmt: skip
        ref = self._top("interviews", iid)
        _owned(ref, uid)

        @firestore.transactional
        def txn_fn(txn) -> dict | None:
            data = ref.get(transaction=txn).to_dict() or {}
            if data.get("uid") != uid:
                raise NotFoundError()
            if data.get("state") not in from_states:
                return None
            data = {**data, **(fields or {}), "state": to_state}
            if refund_rule is not None:
                data["refunded"] = interview_refundable(data, *refund_rule[:2])
                if data["refunded"] and len(refund_rule) > 2:
                    day_ref = self._top("usage", f"{uid}_{data['reservation_date']}")
                    given = (day_ref.get(transaction=txn).to_dict() or {}).get(
                        "interview_refunds", 0
                    )
                    if given >= refund_rule[2]:
                        data["refunded"] = False
                    else:
                        txn.set(
                            day_ref,
                            {"uid": uid, "date": data["reservation_date"],
                             "interview_refunds": given + 1},
                            merge=True,
                        )  # fmt: skip
            txn.set(ref, data)
            return data

        data = self._contended(txn_fn, uid)
        return None if data is None else InterviewDoc.model_validate({**data, "id": iid})

    def update_interview(self, uid: str, iid: str, fields: dict[str, Any]) -> None:
        ref = self._top("interviews", iid)
        _owned(ref, uid)
        ref.set(fields, merge=True)

    def get_idempotency(self, uid: str, key: str) -> IdempotencyDoc | None:
        ref = self._top("idempotency", _idem_id(uid, key))
        snap = _owned(ref, uid, missing_ok=True)
        return _load(IdempotencyDoc, snap) if snap is not None else None

    def put_idempotency(self, uid: str, key: str, doc: IdempotencyDoc) -> bool:
        ref = self._top("idempotency", _idem_id(uid, key))
        try:
            ref.create({**doc.to_store(), "uid": uid})
        except AlreadyExists:
            return False
        return True

    def delete_idempotency(self, uid: str, key: str) -> None:
        ref = self._top("idempotency", _idem_id(uid, key))
        if _owned(ref, uid, missing_ok=True) is not None:
            ref.delete()
