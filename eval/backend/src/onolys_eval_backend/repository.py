"""Server-only eval persistence, including atomic run/unit mutation primitives.

Records are JSON-compatible mappings so engine provenance, typed Scores/run_info
serialized with model_dump(mode='json'), stages and future provider metadata survive
unchanged. Routers own input validation and executors own state-machine decisions.
"""

from collections.abc import Callable, Mapping
from copy import deepcopy
from threading import RLock
from typing import Protocol

Record = dict
# None aborts without writes. Otherwise patch run and unit together. Firestore may
# retry callbacks: they must be pure, with no bucket writes, LLM calls or enqueues.
UnitMutation = Callable[[Record, Record], tuple[Record, Record] | None]


class EvalRepository(Protocol):
    def create_upload(self, upload_id: str, data: Record) -> None: ...
    def get_upload(self, upload_id: str) -> Record | None: ...
    def update_upload(self, upload_id: str, updates: Record) -> None: ...
    def create_run(self, run_id: str, data: Record, units: Mapping[str, Record]) -> None: ...
    def get_run(self, run_id: str) -> Record | None: ...
    def list_runs(self, limit: int = 100) -> dict[str, Record]: ...
    def get_unit(self, run_id: str, unit_id: str) -> Record | None: ...
    def list_units(self, run_id: str) -> dict[str, Record]: ...
    def update_run(self, run_id: str, updates: Record) -> None: ...
    def update_unit(self, run_id: str, unit_id: str, updates: Record) -> None: ...
    def transact_unit(self, run_id: str, unit_id: str, mutate: UnitMutation) -> bool: ...
    def cancel_run(self, run_id: str) -> bool: ...


class InMemoryEvalRepository:
    """Thread-safe fake with detached snapshots and atomic multi-document callbacks."""

    def __init__(self):
        self._uploads: dict[str, Record] = {}
        self._runs: dict[str, Record] = {}
        self._units: dict[str, dict[str, Record]] = {}
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

    def create_run(self, run_id, data, units):
        with self._lock:
            if run_id in self._runs:
                raise ValueError('Run already exists')
            self._runs[run_id] = deepcopy(data)
            self._units[run_id] = deepcopy(dict(units))

    def get_run(self, run_id):
        with self._lock:
            return deepcopy(self._runs.get(run_id))

    def list_runs(self, limit=100):
        if limit < 1:
            raise ValueError('limit must be positive')
        with self._lock:
            return deepcopy(dict(sorted(self._runs.items(),
                                        key=lambda item: item[1]['created_at'],
                                        reverse=True)[:limit]))

    def get_unit(self, run_id, unit_id):
        with self._lock:
            return deepcopy(self._units.get(run_id, {}).get(unit_id))

    def list_units(self, run_id):
        with self._lock:
            return deepcopy(self._units.get(run_id, {}))

    def update_run(self, run_id, updates):
        with self._lock:
            self._runs[run_id].update(deepcopy(updates))

    def update_unit(self, run_id, unit_id, updates):
        with self._lock:
            self._units[run_id][unit_id].update(deepcopy(updates))

    def transact_unit(self, run_id, unit_id, mutate):
        with self._lock:
            run, unit = self.get_run(run_id), self.get_unit(run_id, unit_id)
            if run is None or unit is None:
                return False
            changes = mutate(run, unit)
            if changes is None:
                return False
            run_updates, unit_updates = deepcopy(changes)
            self._runs[run_id].update(run_updates)
            self._units[run_id][unit_id].update(unit_updates)
            return True

    def cancel_run(self, run_id):
        with self._lock:
            if run_id not in self._runs:
                return False
            self._runs[run_id]['cancel_requested'] = True
            return True


class FirestoreEvalRepository:
    """Inject a Firestore client targeting database='staging' at service composition."""

    def __init__(self, client):
        self.client = client
        self.uploads = client.collection('eval_uploads')
        self.runs = client.collection('eval_runs')

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

    def create_run(self, run_id, data, units):
        # One atomic commit avoids publishing a run with missing units.
        from google.api_core.exceptions import AlreadyExists

        ref = self.runs.document(run_id)
        batch = self.client.batch()
        batch.create(ref, data)
        for unit_id, unit in units.items():
            batch.create(ref.collection('units').document(unit_id), unit)
        try:
            batch.commit()
        except AlreadyExists as exc:
            raise ValueError('Run already exists') from exc

    def get_run(self, run_id):
        return self._read(self.runs.document(run_id))

    def list_runs(self, limit=100):
        if limit < 1:
            raise ValueError('limit must be positive')
        query = self.runs.order_by('created_at', direction='DESCENDING').limit(limit)
        return {doc.id: doc.to_dict() for doc in query.stream()}

    def _unit(self, run_id, unit_id):
        return self.runs.document(run_id).collection('units').document(unit_id)

    def get_unit(self, run_id, unit_id):
        return self._read(self._unit(run_id, unit_id))

    def list_units(self, run_id):
        return {doc.id: doc.to_dict()
                for doc in self.runs.document(run_id).collection('units').stream()}

    @staticmethod
    def _update(ref, updates):
        from google.api_core.exceptions import NotFound

        try:
            ref.update(updates)
        except NotFound as exc:
            raise KeyError(ref.id) from exc

    def update_run(self, run_id, updates):
        self._update(self.runs.document(run_id), updates)

    def update_unit(self, run_id, unit_id, updates):
        self._update(self._unit(run_id, unit_id), updates)

    def transact_unit(self, run_id, unit_id, mutate):
        from google.cloud import firestore

        run_ref, unit_ref = self.runs.document(run_id), self._unit(run_id, unit_id)

        @firestore.transactional
        def apply(transaction):
            # All reads precede writes, as required by Firestore transactions.
            run = run_ref.get(transaction=transaction)
            unit = unit_ref.get(transaction=transaction)
            if not run.exists or not unit.exists:
                return False
            changes = mutate(run.to_dict(), unit.to_dict())
            if changes is None:
                return False
            run_updates, unit_updates = changes
            if run_updates:
                transaction.update(run_ref, run_updates)
            if unit_updates:
                transaction.update(unit_ref, unit_updates)
            return True

        return apply(self.client.transaction())

    def cancel_run(self, run_id):
        from google.cloud import firestore

        ref = self.runs.document(run_id)

        @firestore.transactional
        def cancel(transaction):
            if not ref.get(transaction=transaction).exists:
                return False
            transaction.update(ref, {'cancel_requested': True})
            return True

        return cancel(self.client.transaction())
