"""GcsBlobStore paths not covered by test_blob_store.py (mocked client; no network)."""

from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import NotFound

from onolys_api.storage.base import BlobNotFoundError
from onolys_api.storage.gcs import GcsBlobStore

pytestmark = pytest.mark.unit


def _gcs():
    client = MagicMock()
    bucket = client.bucket.return_value
    return GcsBlobStore(client, "bkt"), client, bucket


def test_bucket_name_exposed():
    s, client, _b = _gcs()
    assert s.bucket == "bkt"
    client.bucket.assert_called_once_with("bkt")


def test_download_to_creates_parent_dirs_and_downloads(tmp_path):
    s, _c, bucket = _gcs()
    dst = tmp_path / "a" / "b" / "f.wav"
    s.download_to("k", dst)
    assert dst.parent.is_dir()
    bucket.blob.assert_called_with("k")
    bucket.blob.return_value.download_to_filename.assert_called_once_with(str(dst))


def test_download_to_missing_blob_raises_blob_not_found(tmp_path):
    s, _c, bucket = _gcs()
    bucket.blob.return_value.download_to_filename.side_effect = NotFound("x")
    with pytest.raises(BlobNotFoundError):
        s.download_to("k", tmp_path / "f")


def test_upload_from_passes_path_and_content_type(tmp_path):
    s, _c, bucket = _gcs()
    src = tmp_path / "f.wav"
    src.write_bytes(b"x")
    s.upload_from("k", src, "audio/wav")
    bucket.blob.return_value.upload_from_filename.assert_called_once_with(
        str(src), content_type="audio/wav"
    )


def test_move_copies_then_deletes_source():
    s, _c, bucket = _gcs()
    src = MagicMock()
    bucket.blob.return_value = src
    s.move("a", "b")
    bucket.copy_blob.assert_called_once_with(src, bucket, "b")
    src.delete.assert_called_once_with()


def test_move_missing_source_raises_and_does_not_delete():
    s, _c, bucket = _gcs()
    src = MagicMock()
    bucket.blob.return_value = src
    bucket.copy_blob.side_effect = NotFound("x")
    with pytest.raises(BlobNotFoundError, match="a"):
        s.move("a", "b")
    src.delete.assert_not_called()


def test_size_none_when_blob_missing_else_size():
    s, _c, bucket = _gcs()
    bucket.get_blob.return_value = None
    assert s.size("k") is None
    bucket.get_blob.return_value = MagicMock(size=42)
    assert s.size("k") == 42


def test_delete_prefix_counts_only_blobs_actually_deleted():
    s, client, _b = _gcs()
    ok1, gone, ok2 = MagicMock(), MagicMock(), MagicMock()
    gone.delete.side_effect = NotFound("raced")  # deleted by someone else meanwhile
    client.list_blobs.return_value = iter([ok1, gone, ok2])
    assert s.delete_prefix("u/s/") == 2
    client.list_blobs.assert_called_once_with("bkt", prefix="u/s/")


def test_delete_returns_true_when_deleted_false_when_already_gone():
    s, _c, bucket = _gcs()
    blob = bucket.blob.return_value
    assert s.delete("k") is True
    blob.delete.assert_called_once_with()
    blob.delete.side_effect = NotFound("gone")
    assert s.delete("k") is False
