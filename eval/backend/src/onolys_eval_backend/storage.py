"""Private eval bucket adapters. Clients are supplied, never created at import time."""

import json
from datetime import timedelta
from threading import RLock
from typing import Any, Protocol


class Bucket(Protocol):
    def read_bytes(self, path: str) -> bytes: ...
    def write_bytes(self, path: str, data: bytes, *, content_type: str) -> None: ...
    def list(self, prefix: str) -> list[str]: ...
    def read_json(self, path: str) -> Any: ...
    def write_json(self, path: str, data: Any) -> None: ...
    def signed_upload_url(
        self, path: str, content_type: str, *, expires_s: int, max_bytes: int
    ) -> dict: ...
    def size(self, path: str) -> int | None: ...
    def read_head(self, path: str, n: int) -> bytes: ...
    def delete(self, path: str) -> None: ...


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

    def delete(self, path):
        from google.api_core.exceptions import NotFound

        try:
            self.bucket.blob(path).delete()
        except NotFound:
            pass

    def signed_upload_url(self, path, content_type, *, expires_s, max_bytes):
        """V4 signed PUT for a browser upload. Signs through IAM signBlob using the runtime
        service account (needs roles/iam.serviceAccountTokenCreator on itself) and
        requires the bucket CORS policy to allow PUT from the eval origin.
        """
        import google.auth
        from google.auth.transport.requests import Request

        credentials, _ = google.auth.default()
        credentials.refresh(Request())
        headers = {
            'x-goog-content-length-range': f'1,{max_bytes}',
            'x-goog-if-generation-match': '0',
        }
        url = self.bucket.blob(path).generate_signed_url(
            version='v4',
            method='PUT',
            expiration=timedelta(seconds=expires_s),
            content_type=content_type,
            headers=headers,
            service_account_email=credentials.service_account_email,
            access_token=credentials.token,
        )
        return {'url': url, 'method': 'PUT', 'headers': {'Content-Type': content_type, **headers}}

    def size(self, path):
        blob = self.bucket.get_blob(path)
        return None if blob is None else blob.size

    def read_head(self, path, n):
        blob = self.bucket.get_blob(path)
        if blob is None:
            raise FileNotFoundError(path)
        return blob.download_as_bytes(start=0, end=n - 1)


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

    def delete(self, path):
        with self._lock:
            self._objects.pop(path, None)

    def signed_upload_url(self, path, content_type, *, expires_s, max_bytes):
        headers = {
            'x-goog-content-length-range': f'1,{max_bytes}',
            'x-goog-if-generation-match': '0',
        }
        return {
            'url': f'memory://{path}',
            'method': 'PUT',
            'headers': {'Content-Type': content_type, **headers},
        }

    def size(self, path):
        with self._lock:
            return len(self._objects[path]) if path in self._objects else None

    def read_head(self, path, n):
        return self.read_bytes(path)[:n]
