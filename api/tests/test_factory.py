"""Storage seam factory: which Repo/BlobStore a Settings + env combination builds."""

from unittest.mock import MagicMock

import pytest
from onolys_api import factory
from onolys_api.config import Settings
from onolys_api.repo.fake import FakeRepo
from onolys_api.storage.fake import FakeBlobStore
from onolys_api.storage.gcs import GcsBlobStore

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in (
        "FAKE_BLOB_DIR",
        "FAKE_BLOB_BASE_URL",
        "BLOB_SIGNER_EMAIL",
        "FIRESTORE_EMULATOR_HOST",
    ):
        monkeypatch.delenv(k, raising=False)


def test_local_blobs_are_fake_with_defaults():
    b = factory.build_blobs(Settings(env="test"))
    assert isinstance(b, FakeBlobStore)
    assert b.signed_read_url("k").startswith("http://localhost:8000")


def test_local_blobs_honor_dir_and_base_url_env(monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_BLOB_DIR", str(tmp_path / "blobs"))
    monkeypatch.setenv("FAKE_BLOB_BASE_URL", "http://fake.test:9/")
    b = factory.build_blobs(Settings(env="local"))
    b.put_bytes("k", b"abc")
    assert (tmp_path / "blobs").exists()
    assert b.signed_read_url("k").startswith("http://fake.test:9/")


def test_cloud_blobs_are_gcs_with_signer_from_env(monkeypatch):
    from google.cloud import storage

    client_cls = MagicMock()
    monkeypatch.setattr(storage, "Client", client_cls)
    monkeypatch.setenv("BLOB_SIGNER_EMAIL", "sig@p.iam.gserviceaccount.com")
    b = factory.build_blobs(Settings(env="staging", gcp_project="proj", audio_bucket="bkt"))
    assert isinstance(b, GcsBlobStore) and b.bucket == "bkt"
    client_cls.assert_called_once_with(project="proj")
    assert b._signer_email == "sig@p.iam.gserviceaccount.com"


def test_local_env_with_bucket_configured_uses_gcs_without_signer(monkeypatch):
    from google.cloud import storage

    client_cls = MagicMock()
    monkeypatch.setattr(storage, "Client", client_cls)
    b = factory.build_blobs(Settings(env="local", audio_bucket="bkt"))
    assert isinstance(b, GcsBlobStore)
    client_cls.assert_called_once_with(project=None)  # empty project -> ADC default
    assert b._signer_email is None


def test_local_repo_is_fake_without_emulator():
    blobs = FakeBlobStore()
    assert isinstance(factory.build_repo(Settings(env="test"), blobs), FakeRepo)


@pytest.mark.parametrize(
    ("env", "emulator"), [("test", "127.0.0.1:1"), ("staging", None), ("prod", "127.0.0.1:1")]
)
def test_repo_is_firestore_with_emulator_or_cloud_env(monkeypatch, env, emulator):
    import onolys_api.repo.firestore as fs

    if emulator:
        monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", emulator)
    client = object()
    seen = {}

    def fake_make(settings):
        seen["settings"] = settings
        return client

    monkeypatch.setattr(fs, "make_firestore_client", fake_make)
    blobs = FakeBlobStore()
    settings = Settings(env=env, gcp_project="p")
    repo = factory.build_repo(settings, blobs)
    assert isinstance(repo, fs.FirestoreRepo)
    assert repo._client is client and repo._blobs is blobs
    assert seen["settings"] is settings
