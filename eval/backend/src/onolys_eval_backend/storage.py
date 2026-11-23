"""Private eval bucket adapters. Clients are supplied, never created at import time."""

import json
from copy import deepcopy
from threading import RLock
from typing import Any, Protocol

INLINE_OUTPUT_LIMIT = 500_000


class Bucket(Protocol):
    def read_bytes(self, path: str) -> bytes: ...
    def write_bytes(self, path: str, data: bytes, *, content_type: str) -> None: ...
    def list(self, prefix: str) -> list[str]: ...
    def read_json(self, path: str) -> Any: ...
    def write_json(self, path: str, data: Any) -> None: ...


def _encode(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


class _JSONBucket:
    def read_json(self, path: str) -> Any:
        return json.loads(self.read_bytes(path))

    def write_json(self, path: str, data: Any) -> None:
        self.write_bytes(path, _encode(data), content_type='application/json')


class GCSBucket(_JSONBucket):
    """Wrap an injected google.cloud.storage Bucket (ADC setup belongs to composition)."""

    def __init__(self, bucket):
        self.bucket = bucket

    def read_bytes(self, path: str) -> bytes:
        from google.api_core.exceptions import NotFound

        try:
            return self.bucket.blob(path).download_as_bytes()
        except NotFound as exc:
            raise FileNotFoundError(path) from exc

    def write_bytes(self, path: str, data: bytes, *, content_type: str) -> None:
        self.bucket.blob(path).upload_from_string(data, content_type=content_type)

    def list(self, prefix: str) -> list[str]:
        return sorted(blob.name for blob in self.bucket.list_blobs(prefix=prefix))


class InMemoryBucket(_JSONBucket):
    def __init__(self):
        self._objects: dict[str, bytes] = {}
        self._lock = RLock()

    def read_bytes(self, path: str) -> bytes:
        with self._lock:
            if path not in self._objects:
                raise FileNotFoundError(path)
            return self._objects[path]

    def write_bytes(self, path: str, data: bytes, *, content_type: str) -> None:
        with self._lock:
            self._objects[path] = bytes(data)

    def list(self, prefix: str) -> list[str]:
        with self._lock:
            return sorted(path for path in self._objects if path.startswith(prefix))


def store_output(bucket: Bucket, run_id: str, unit_id: str, output: dict) -> dict:
    """Store JSON inline through 500 KB, spilling larger UTF-8 payloads to SP2 layout."""
    data = _encode(output)
    if len(data) <= INLINE_OUTPUT_LIMIT:
        return {'output': deepcopy(output), 'output_ref': None}
    path = f'runs/{run_id}/{unit_id}.json'
    bucket.write_bytes(path, data, content_type='application/json')
    return {'output': None, 'output_ref': path}


def load_output(bucket: Bucket, unit: dict) -> dict | None:
    if unit.get('output_ref'):
        return bucket.read_json(unit['output_ref'])
    return deepcopy(unit.get('output'))
