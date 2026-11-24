"""Bounded sweep pages progress past retained tombstones and legitimate active users."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from onolys_api.jobs.sweep import run_sweep
from onolys_api.repo.fake import FakeRepo
from onolys_api.repo.limits import LimitDefaults
from onolys_api.repo.models import RunDoc, SessionDoc, SessionStatusDoc

NOW = datetime(2026, 1, 3, tzinfo=UTC)
OLD = NOW - timedelta(days=1)
DATE = "2026-01-03"
pytestmark = pytest.mark.unit


@pytest.fixture(params=["fake", "firestore"])
def pair(request, blobs):
    if request.param == "fake":
        first, second = FakeRepo(blobs), FakeRepo(blobs)
        second._docs, second._claim_lock = first._docs, first._claim_lock
        return first, second
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        pytest.skip("FIRESTORE_EMULATOR_HOST not set")
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore

    from onolys_api.repo.firestore import FirestoreRepo

    project = f"demo-sweep-{uuid.uuid4().hex[:12]}"
    return tuple(FirestoreRepo(firestore.Client(project=project, credentials=AnonymousCredentials()),
                               blobs) for _ in range(2))


def session(repo, uid, sid, state, *, at=NOW, discard_code=None):
    repo.create_session(
        uid, sid, SessionDoc(uid=uid, state=state, stage_started_at=at, updated_at=at,
                            created_at=at, discard_code=discard_code),
        SessionStatusDoc(uid=uid, state=state, updated_at=at),
    )


def reserve(repo, settings, uid):
    assert repo.reserve_usage(uid, "eval", DATE, LimitDefaults.from_settings(settings), 100) == "ok"


def test_discard_tombstone_page_does_not_starve_ordinary_deletes(pair, settings, blobs):
    first, second = pair
    for i in range(2):
        session(first, "owner", f"discard{i}", "deleting", at=OLD,
                discard_code="audio_unreadable")
    session(first, "owner", "ordinary", "deleting", at=OLD + timedelta(seconds=1))
    assert run_sweep(first, blobs, settings, NOW, batch=2).deleted == 0
    assert run_sweep(second, blobs, settings, NOW, batch=2).deleted == 1
    for i in range(2):
        assert first.get_session("owner", f"discard{i}").discard_code == "audio_unreadable"


def test_active_users_cannot_starve_later_leaked_user_across_instances(pair, settings, blobs):
    first, second = pair
    for uid in ("a-live", "b-live", "z-leak"):
        reserve(first, settings, uid)
        session(first, uid, uid, "running" if uid != "z-leak" else "failed")
        first.create_run(uid, uid, "run", RunDoc(uid=uid, session_id=uid, run_id="run",
                         status="running" if uid != "z-leak" else "failed", cap_date=DATE))
    assert run_sweep(first, blobs, settings, NOW, batch=1).repaired == 0
    assert run_sweep(second, blobs, settings, NOW, batch=1).repaired == 0
    assert run_sweep(first, blobs, settings, NOW, batch=1).repaired == 1
    assert first.get_user("z-leak").active_runs == 0
    assert first.get_user("a-live").active_runs == 1
    assert first.get_user("b-live").active_runs == 1


def test_active_scan_wraps_and_keeps_tied_candidates_after_cursor_leaves(pair, settings):
    first, second = pair
    for uid in ("a", "b", "c"):
        reserve(first, settings, uid)
    assert first.list_uids_with_active_runs(1) == ["a"]
    first.release_usage("a", "eval", DATE, refund=False)
    assert second.list_uids_with_active_runs(1) == ["b"]
    assert first.list_uids_with_active_runs(1) == ["c"]
    assert second.list_uids_with_active_runs(1) == ["b"]
    assert first.list_uids_with_active_runs(0) == []


@pytest.mark.parametrize("checkpoint", [{}, {"uid": "old"}, {"active_runs": True, "uid": "a"},
                                        {"active_runs": 1, "uid": "invalid/path"}])
def test_legacy_or_invalid_checkpoint_restarts_scan(pair, settings, checkpoint):
    from onolys_api.repo.scans import ACTIVE_SCAN_PATH

    first, second = pair
    reserve(first, settings, "a")
    if isinstance(first, FakeRepo):
        first._put(ACTIVE_SCAN_PATH, checkpoint)
    else:
        first._client.document(ACTIVE_SCAN_PATH).set(checkpoint)
    assert second.list_uids_with_active_runs(1) == ["a"]
