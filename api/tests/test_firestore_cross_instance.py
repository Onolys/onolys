"""Cross-instance atomicity: several FirestoreRepo instances (one firestore.Client each) race on
the same docs, like multiple Cloud Run instances. The per-uid in-process lock cannot serialize
these, so only Firestore transactions keep the outcome correct. Needs the emulator."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from onolys_api.config import Settings
from onolys_api.errors import ApiError
from onolys_api.jobs import caps
from onolys_api.repo.models import SessionDoc, SessionStatusDoc
from onolys_api.storage.fake import FakeBlobStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("FIRESTORE_EMULATOR_HOST"), reason="FIRESTORE_EMULATOR_HOST not set"
    ),
]

NOON = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
LEASE = 540.0


@pytest.fixture
def repos(tmp_path):
    """Three independent repo instances (own client, own in-process lock table)."""
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore

    from onolys_api.repo.firestore import FirestoreRepo

    blobs = FakeBlobStore(tmp_path / "blobs", bucket="test-bucket")
    return [
        FirestoreRepo(
            firestore.Client(project="demo-onolys", credentials=AnonymousCredentials()), blobs
        )
        for _ in range(3)
    ]


def test_cross_instance_concurrent_claims_one_wins(repos):
    uid, sid = f"u-{uuid.uuid4().hex[:10]}", f"s-{uuid.uuid4().hex[:10]}"
    now = datetime.now(UTC)
    repos[0].create_session(
        uid, sid, SessionDoc(uid=uid, created_at=now, updated_at=now),
        SessionStatusDoc(uid=uid, updated_at=now),
    )  # fmt: skip
    with ThreadPoolExecutor(len(repos)) as ex:
        outs = list(ex.map(lambda r: r.claim_step(uid, sid, "validate", now, LEASE).outcome, repos))
    assert outs.count("claimed") == 1 and outs.count("busy") == len(repos) - 1


def test_cross_instance_concurrent_reservations_never_exceed_the_cap(repos):
    u = f"u-{uuid.uuid4().hex[:10]}"
    s = Settings(env="test", auth_mode="fake", eval_cap_day=1, max_active_runs=1000)

    def attempt(repo):
        try:
            caps.reserve_run(repo, s, u, NOON)
            return "ok"
        except ApiError as e:
            return e.details[0]["code"]

    with ThreadPoolExecutor(len(repos)) as ex:
        outs = list(ex.map(attempt, repos))
    assert outs.count("ok") == 1 and outs.count("daily_cap_reached") == len(repos) - 1
    assert repos[0].get_usage(u, "2026-11-20").runs == 1
