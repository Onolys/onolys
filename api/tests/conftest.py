import json
from pathlib import Path

import httpx
import pytest

from onolys_api.app import create_app
from onolys_api.config import Settings
from onolys_api.repo.fake import FakeRepo
from onolys_api.storage.fake import FakeBlobStore

SCHEMA = (
    Path(__file__).resolve().parents[2] / "docs/contracts/public/public-error-response.schema.json"
)


@pytest.fixture
def schema() -> dict:
    return json.loads(SCHEMA.read_text())


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="test",
        service_mode="combined",
        auth_mode="fake",
        git_sha="abc123",
        cors_origins=("https://app.onolys.com",),
    )


@pytest.fixture
def blobs(tmp_path):
    return FakeBlobStore(tmp_path / "blobs")


@pytest.fixture
def app(settings, blobs):
    return create_app(settings, repo=FakeRepo(blobs), blobs=blobs)


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as c:
        yield c


# Test names (firestore param only) to run non-blocking because of emulator contention
# ("Aborted: 409 Transaction lock timeout"). Currently none.
FLAKY_FIRESTORE_TESTS: set[str] = set()  # same-doc txns are lock-serialized per instance; see
# test_firestore_cross_instance.py for the blocking cross-instance races


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    for item in items:
        callspec = getattr(item, "callspec", None)
        if (
            item.originalname in FLAKY_FIRESTORE_TESTS
            and callspec is not None
            and callspec.params.get("repo") == "firestore"
        ):
            item.add_marker(pytest.mark.flaky)
        if _needs_emulator(item):
            item.add_marker(pytest.mark.firestore)
    _trim_firestore_twins(items)


# Files that talk to the Firestore emulator without a [firestore] param.
EMULATOR_FILES = {
    "test_auth_emulator.py",
    "test_firestore_emulator.py",
    "test_firestore_cross_instance.py",
}


def _needs_emulator(item) -> bool:
    """CI splits on this: `-m "not firestore"` (no emulator) vs `-m firestore` (emulator job)."""
    if item.path.name in EMULATOR_FILES:
        return True
    callspec = getattr(item, "callspec", None)
    return callspec is not None and "firestore" in callspec.id.split("-")


# These files exercise HTTP/validation logic, not Firestore semantics (repo_contract covers
# those). Their [firestore] twins only add emulator time, so only tests marked
# `@pytest.mark.firestore_smoke` keep their [firestore] twin in these files.
SMOKE_FILES = {"test_rating.py", "test_error_map.py", "test_logging.py"}


def _trim_firestore_twins(items):
    kept, dropped = [], []
    for item in items:
        if (
            item.path.name in SMOKE_FILES
            and "[firestore" in item.name
            and item.get_closest_marker("firestore_smoke") is None
        ):
            dropped.append(item)
        else:
            kept.append(item)
    if dropped:
        dropped[0].config.hook.pytest_deselected(items=dropped)
        items[:] = kept
