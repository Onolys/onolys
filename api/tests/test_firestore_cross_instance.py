"""Cross-instance atomicity: several FirestoreRepo instances (one firestore.Client each) race on
the same docs, like multiple Cloud Run instances. The per-uid in-process lock cannot serialize
these, so only Firestore transactions keep the outcome correct. Needs the emulator."""

import os
import threading
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
    for r in repos:  # warm each client's gRPC channel so the race is on the claim itself
        r.get_session(uid, sid)
    barrier = threading.Barrier(len(repos))

    def claim(r):
        barrier.wait(timeout=30)
        return r.claim_step(uid, sid, "validate", now, LEASE).outcome

    with ThreadPoolExecutor(len(repos)) as ex:
        outs = list(ex.map(claim, repos))
    assert outs.count("claimed") == 1 and outs.count("busy") == len(repos) - 1


def test_cross_instance_concurrent_reservations_never_exceed_the_cap(repos):
    u = f"u-{uuid.uuid4().hex[:10]}"
    s = Settings(env="test", auth_mode="fake", eval_cap_day=1, max_active_runs=1000)

    for r in repos:  # warm each client's gRPC channel
        r.get_usage(u, "2026-11-20")
    barrier = threading.Barrier(len(repos))

    def attempt(repo):
        barrier.wait(timeout=30)
        try:
            caps.reserve_run(repo, s, u, NOON)
            return "ok"
        except ApiError as e:
            return e.details[0]["code"]

    with ThreadPoolExecutor(len(repos)) as ex:
        outs = list(ex.map(attempt, repos))
    assert outs.count("ok") == 1 and outs.count("daily_cap_reached") == len(repos) - 1
    assert repos[0].get_usage(u, "2026-11-20").runs == 1


def _running_session(repo, uid, sid):
    now = datetime.now(UTC)
    repo.create_session(
        uid, sid, SessionDoc(uid=uid, state="running", created_at=now, updated_at=now),
        SessionStatusDoc(uid=uid, state="running", progress=45, updated_at=now),
    )  # fmt: skip


def test_transition_session_cannot_overwrite_a_cancel_from_another_instance(repos):
    """M-10: the plan runs on the state read inside the transaction."""
    from onolys_api.jobs.machine import transition_plan
    from onolys_api.repo.limits import LimitDefaults

    uid, sid = f"u-{uuid.uuid4().hex[:10]}", f"s-{uuid.uuid4().hex[:10]}"
    _running_session(repos[0], uid, sid)
    assert repos[1].cancel_session(uid, sid, caps.utc_date(), LimitDefaults(10, 5))[0] == (
        "cancelled"
    )
    with pytest.raises(ApiError) as e:
        repos[0].transition_session(uid, sid, transition_plan(to="report_ready", step=None))
    assert e.value.status == 409
    assert repos[2].get_session(uid, sid).state == "cancelled"


def test_publish_report_after_a_cancel_from_another_instance_stores_nothing(repos):
    """M-11: the report is published only while the session is still `running`."""
    from onolys_api.jobs.machine import transition_plan
    from onolys_api.repo.limits import LimitDefaults
    from onolys_api.repo.models import ReportDoc, RunDoc

    uid, sid = f"u-{uuid.uuid4().hex[:10]}", f"s-{uuid.uuid4().hex[:10]}"
    _running_session(repos[0], uid, sid)
    repos[0].create_run(uid, sid, "r1", RunDoc(uid=uid, session_id=sid, run_id="r1"))
    repos[1].cancel_session(uid, sid, caps.utc_date(), LimitDefaults(10, 5))
    out = repos[0].publish_report(
        uid, sid, "r1", ReportDoc(version=0, run_id="r1", report={"k": 1}), {"stage": None},
        lambda v: transition_plan(to="report_ready", latest_report_version=v), None,
    )  # fmt: skip
    assert out is None and repos[2].list_reports(uid, sid) == []


def test_discard_failed_upload_unlinks_the_interview(repos):
    """M-4: the tombstone and the interview reset commit in one transaction."""
    from onolys_api.repo.models import InterviewDoc

    uid, sid = f"u-{uuid.uuid4().hex[:10]}", f"s-{uuid.uuid4().hex[:10]}"
    iid = f"i-{uuid.uuid4().hex[:10]}"
    repos[0].create_interview(
        uid, iid,
        InterviewDoc(uid=uid, scenario_id="s", voice="v", state="uploaded", reservation_date="d",
                     session_id=sid),
    )  # fmt: skip
    now = datetime.now(UTC)
    repos[0].create_session(
        uid, sid, SessionDoc(uid=uid, state="validating", interview_id=iid),
        SessionStatusDoc(uid=uid, updated_at=now),
    )  # fmt: skip
    repos[1].discard_failed_upload(uid, sid, "audio_too_long")
    iv = repos[2].get_interview(uid, iid)
    assert (iv.state, iv.session_id) == ("ended", None)
    with pytest.raises(Exception):  # noqa: B017  (NotFoundError: the session is gone)
        repos[2].get_session(uid, sid)
