"""Server-only eval persistence, including atomic upload, run and slot primitives.

Records are JSON-compatible mappings so engine provenance, typed Scores/run_info
serialized with model_dump(mode='json'), stages and future provider metadata survive
unchanged. Routers own input validation and executors own state-machine decisions.
"""

from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol

Record = dict


_CANCELLABLE = {'queued', 'running'}


def _utc_iso():
    return datetime.now(UTC).isoformat()


class EvalRepository(Protocol):
    def create_upload(self, upload_id: str, data: Record) -> None: ...
    def get_upload(self, upload_id: str) -> Record | None: ...
    def update_upload(self, upload_id: str, updates: Record) -> None: ...
    def transition_upload(
        self, upload_id: str, expected: str, updates: Record, *, match: Record | None = None
    ) -> bool: ...
    def create_group(self, run_id: str, data: Record) -> None: ...
    def get_run(self, run_id: str) -> Record | None: ...
    def delete_run(self, run_id: str) -> None: ...
    def list_runs(self, limit: int = 100) -> dict[str, Record]: ...
    def list_runs_page(
        self, limit: int = 100, after: tuple[str, str] | None = None
    ) -> tuple[dict[str, Record], bool]: ...
    def update_run(self, run_id: str, updates: Record) -> None: ...
    def cancel_run(self, run_id: str, at: str | None = None) -> bool: ...
    # Scheduler (05 R6): the `eval_slots/{provider}` doc, `{holders: {run_id: eval_run_id}}`.
    def claim_slot(self, provider: str, run_id: str, eval_run_id: str, cap: int) -> bool: ...
    def release_slot(self, provider: str, run_id: str) -> None: ...
    def get_slots(self, provider: str) -> Record: ...
    def update_slot(self, provider: str, fields: Record) -> None: ...
    def advance_tick(self, run_id: str, n: int, at: str) -> bool: ...


class InMemoryEvalRepository:
    """Thread-safe fake with detached snapshots and atomic multi-document callbacks."""

    def __init__(self):
        self._uploads: dict[str, Record] = {}
        self._runs: dict[str, Record] = {}
        self._slots: dict[str, Record] = {}
        self._lock = RLock()

    def create_upload(self, upload_id, data):
        with self._lock:
            if upload_id in self._uploads:
                raise ValueError('Upload already exists')
            self._uploads[upload_id] = deepcopy(data)

    def get_upload(self, upload_id):
        with self._lock:
            return deepcopy(self._uploads.get(upload_id))

    def update_upload(self, upload_id, updates):
        with self._lock:
            self._uploads[upload_id].update(deepcopy(updates))

    def transition_upload(self, upload_id, expected, updates, *, match=None):
        with self._lock:
            saved = self._uploads.get(upload_id)
            if (saved is None or saved['status'] != expected
                    or any(saved.get(key) != value for key, value in (match or {}).items())):
                return False
            saved.update(deepcopy(updates))
            return True

    def create_group(self, run_id, data):
        """The rollup doc alone (05 R4): refs are embedded, there is no units subcollection."""
        with self._lock:
            if run_id in self._runs:
                raise ValueError('Run already exists')
            self._runs[run_id] = deepcopy(data)

    def get_run(self, run_id):
        with self._lock:
            return deepcopy(self._runs.get(run_id))

    def delete_run(self, run_id):
        """The group doc alone (05 R8 step 4); idempotent."""
        with self._lock:
            self._runs.pop(run_id, None)

    def list_runs(self, limit=100):
        if limit < 1:
            raise ValueError('limit must be positive')
        with self._lock:
            return deepcopy(dict(sorted(self._runs.items(),
                                        key=lambda item: item[1]['created_at'],
                                        reverse=True)[:limit]))

    def list_runs_page(self, limit=100, after=None):
        """Newest first by (created_at, id). `after` is the last (created_at, id) seen."""
        if limit < 1:
            raise ValueError('limit must be positive')
        with self._lock:
            rows = sorted(((r['created_at'], rid) for rid, r in self._runs.items()), reverse=True)
            if after is not None:
                rows = [row for row in rows if row < tuple(after)]
            page = rows[:limit]
            return {rid: deepcopy(self._runs[rid]) for _, rid in page}, len(rows) > limit

    def update_run(self, run_id, updates):
        with self._lock:
            self._runs[run_id].update(deepcopy(updates))

    def cancel_run(self, run_id, at=None):
        """Flags only (the tick marks cells). Idempotent; `cancelled_at` set once; no-op if over."""
        with self._lock:
            if run_id not in self._runs:
                return False
            run = self._runs[run_id]
            if run.get('status') in _CANCELLABLE:
                run['cancel_requested'] = True
                run.setdefault('cancelled_at', None)
                run['cancelled_at'] = run['cancelled_at'] or at or _utc_iso()
            return True

    # The lock is the in-memory equivalent of a Firestore transaction: read, decide, write.
    def claim_slot(self, provider, run_id, eval_run_id, cap):
        with self._lock:
            holders = self._slots.setdefault(provider, {}).setdefault('holders', {})
            if run_id in holders:
                return True  # idempotent: a re-claim after a crash is the same slot
            if len(holders) >= cap:
                return False
            holders[run_id] = eval_run_id
            return True

    def release_slot(self, provider, run_id):
        with self._lock:
            self._slots.get(provider, {}).get('holders', {}).pop(run_id, None)

    def get_slots(self, provider):
        with self._lock:
            return deepcopy(self._slots.get(provider, {'holders': {}}))

    def update_slot(self, provider, fields):
        """Merge non-holder fields (cooldown_until, overload_streak) into the slots doc."""
        with self._lock:
            self._slots.setdefault(provider, {}).setdefault('holders', {})
            self._slots[provider].update(deepcopy(fields))

    def advance_tick(self, run_id, n, at):
        """Compare-and-set `tick_seq` n -> n+1: of duplicate deliveries of tick n only one wins."""
        with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.get('tick_seq') != n:
                return False
            run.update({'tick_seq': n + 1, 'last_tick_at': at})
            return True


class FirestoreEvalRepository:
    """Inject a Firestore client targeting database='staging' at service composition."""

    def __init__(self, client):
        self.client = client
        self.uploads = client.collection('eval_uploads')
        self.runs = client.collection('eval_runs')
        self.slots = client.collection('eval_slots')

    @staticmethod
    def _read(ref):
        snapshot = ref.get()
        return snapshot.to_dict() if snapshot.exists else None

    def create_upload(self, upload_id, data):
        from google.api_core.exceptions import AlreadyExists

        try:
            self.uploads.document(upload_id).create(data)
        except AlreadyExists as exc:
            raise ValueError('Upload already exists') from exc

    def get_upload(self, upload_id):
        return self._read(self.uploads.document(upload_id))

    def update_upload(self, upload_id, updates):
        self._update(self.uploads.document(upload_id), updates)

    def transition_upload(self, upload_id, expected, updates, *, match=None):
        from google.cloud import firestore

        ref = self.uploads.document(upload_id)

        @firestore.transactional
        def apply(transaction):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return False
            saved = snapshot.to_dict()
            if (saved['status'] != expected
                    or any(saved.get(key) != value for key, value in (match or {}).items())):
                return False
            transaction.update(ref, updates)
            return True

        return apply(self.client.transaction())

    def create_group(self, run_id, data):
        from google.api_core.exceptions import AlreadyExists

        try:
            self.runs.document(run_id).create(data)
        except AlreadyExists as exc:
            raise ValueError('Run already exists') from exc

    def get_run(self, run_id):
        return self._read(self.runs.document(run_id))

    def delete_run(self, run_id):
        self.runs.document(run_id).delete()

    def list_runs(self, limit=100):
        if limit < 1:
            raise ValueError('limit must be positive')
        query = self.runs.order_by('created_at', direction='DESCENDING').limit(limit)
        return {doc.id: doc.to_dict() for doc in query.stream()}

    def list_runs_page(self, limit=100, after=None):
        if limit < 1:
            raise ValueError('limit must be positive')
        query = (self.runs.order_by('created_at', direction='DESCENDING')
                 .order_by('__name__', direction='DESCENDING'))
        if after is not None:
            # Value cursor remains stable even when the last document was deleted.
            query = query.start_after({
                'created_at': after[0], '__name__': self.runs.document(after[1]),
            })
        docs = list(query.limit(limit + 1).stream())
        return {doc.id: doc.to_dict() for doc in docs[:limit]}, len(docs) > limit

    @staticmethod
    def _update(ref, updates):
        from google.api_core.exceptions import NotFound

        try:
            ref.update(updates)
        except NotFound as exc:
            raise KeyError(ref.id) from exc

    def update_run(self, run_id, updates):
        self._update(self.runs.document(run_id), updates)

    def cancel_run(self, run_id, at=None):
        from google.cloud import firestore

        ref = self.runs.document(run_id)

        @firestore.transactional
        def cancel(transaction):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists:
                return False
            run = snapshot.to_dict()
            if run.get('status') in _CANCELLABLE:
                stamp = run.get('cancelled_at') or at or _utc_iso()
                transaction.update(ref, {'cancel_requested': True, 'cancelled_at': stamp})
            return True

        return cancel(self.client.transaction())

    def claim_slot(self, provider, run_id, eval_run_id, cap):
        from google.cloud import firestore

        ref = self.slots.document(provider)

        @firestore.transactional
        def claim(transaction):
            snapshot = ref.get(transaction=transaction)
            holders = (snapshot.to_dict() or {}).get('holders', {}) if snapshot.exists else {}
            if run_id in holders:
                return True
            if len(holders) >= cap:
                return False
            if snapshot.exists:
                transaction.update(ref, {f'holders.{run_id}': eval_run_id})
            else:
                transaction.set(ref, {'holders': {run_id: eval_run_id}})
            return True

        return claim(self.client.transaction())

    def release_slot(self, provider, run_id):
        from google.api_core.exceptions import NotFound
        from google.cloud import firestore

        try:
            self.slots.document(provider).update({f'holders.{run_id}': firestore.DELETE_FIELD})
        except NotFound:
            pass

    def get_slots(self, provider):
        return self._read(self.slots.document(provider)) or {'holders': {}}

    def update_slot(self, provider, fields):
        self.slots.document(provider).set(fields, merge=True)

    def advance_tick(self, run_id, n, at):
        from google.cloud import firestore

        ref = self.runs.document(run_id)

        @firestore.transactional
        def advance(transaction):
            snapshot = ref.get(transaction=transaction)
            if not snapshot.exists or snapshot.to_dict().get('tick_seq') != n:
                return False
            transaction.update(ref, {'tick_seq': n + 1, 'last_tick_at': at})
            return True

        return advance(self.client.transaction())
