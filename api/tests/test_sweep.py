"""Recovery: stale settlement + slot release in ONE transaction, transient stale
failures, `active_runs` self-repair on a refused start, the server-side sweep and unique delete-task names. Fake repo, fake clock, no sleeps."""

from datetime import UTC, datetime, timedelta

import pytest

from onolys_api.app import create_app
from onolys_api.config import MAX_SESSION_RETRIES
from onolys_api.jobs import caps
from onolys_api.jobs.queue import TaskPayload, task_name
from onolys_api.jobs.stale import settle_if_stale
from onolys_api.jobs.sweep import run_sweep
from onolys_api.repo.fake import FakeRepo
from onolys_api.repo.limits import LimitDefaults
from onolys_api.repo.models import RunDoc, SessionDoc, SessionStatusDoc, StepRecord

pytestmark = pytest.mark.unit
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
LATE = T0 + timedelta(days=2)
DATE = "2026-01-01"
UID = "alice"
A = {"Authorization": f"Bearer test:{UID}"}


def sid_of(n: int) -> str:
    return f"{n:032x}"


@pytest.fixture
def repo(blobs):
    return FakeRepo(blobs)


def seed(repo, settings, n=1, state="running", run_status="running", at=T0, slot=True, **extra):
    """A session in `state` since `at`; for `running` also a run holding the user's cap slot."""
    sid = sid_of(n)
    steps = {"transcribe": StepRecord(status="pending", stt_started=at, stt_limit_s=60.0)}
    repo.create_session(
        UID, sid,
        SessionDoc(uid=UID, state=state, step="transcribe", steps=steps, created_at=at,
                   updated_at=at, stage_started_at=at, **extra),
        SessionStatusDoc(uid=UID, state=state, progress=50, updated_at=at),
    )  # fmt: skip
    if run_status:
        if slot:
            ok = repo.reserve_usage(UID, "eval", DATE, LimitDefaults.from_settings(settings), 9)
            assert ok == "ok"
        repo.create_run(
            UID, sid, f"run{n}",
            RunDoc(change_goal="", clinician_speaker="S1", language="en", transcript_sha256="test-hash", uid=UID, session_id=sid, run_id=f"run{n}", status=run_status, cap_date=DATE),
        )  # fmt: skip
    return sid


def active(repo) -> int:
    return repo.get_user(UID).active_runs


# ---- the stale fail releases the slot in the same transaction ----


def test_stale_fail_releases_the_slot_even_when_a_separate_release_would_raise(
    repo, settings, monkeypatch
):
    sid = seed(repo, settings)

    def boom(*a, **kw):
        raise RuntimeError("firestore down")

    monkeypatch.setattr(repo, "release_run_slot", boom)  # the old second step
    settle_if_stale(repo, repo.get_session(UID, sid), LATE, settings)
    assert repo.get_session(UID, sid).state == "failed"
    run = repo.get_run(UID, sid, "run1")
    assert (run.status, run.released, run.error) == ("failed", True, "run_failed")
    assert active(repo) == 0


# ---- a stale failure is a lost task: transient, retryable, honest copy ----


@pytest.mark.parametrize("state,step", [("transcribing", "transcribe"), ("validating", "validate"),
                                        ("running", "run")])  # fmt: skip
def test_stale_failures_are_transient_and_retryable(repo, settings, state, step):
    sid = seed(repo, settings, state=state, run_status="running" if state == "running" else None)
    settle_if_stale(repo, repo.get_session(UID, sid), LATE, settings)
    s, st = repo.get_session(UID, sid), repo.get_status(UID, sid)
    assert s.state == "failed" and s.error.step == step
    assert (s.error.code, s.error.kind) == ("deadline_exceeded", "transient")
    assert (st.error_kind, st.retries_left) == ("transient", MAX_SESSION_RETRIES)


# ---- refused start repairs a leaked slot ----


def leak(repo, settings, n=1):
    """A failed session whose run still holds the slot (a release that never happened)."""
    sid = seed(repo, settings, n=n, state="failed", run_status="failed")
    return sid


def test_reconcile_frees_a_leaked_slot_but_keeps_a_live_run(repo, settings):
    seed(repo, settings, n=1)  # live: running session, running run
    leak(repo, settings, n=2)
    assert active(repo) == 2
    assert repo.reconcile_active_runs(UID) == 1
    assert active(repo) == 1
    assert repo.get_run(UID, sid_of(2), "run2").released is True
    assert repo.get_run(UID, sid_of(1), "run1").released is False
    assert repo.reconcile_active_runs(UID) == 0  # idempotent


def test_a_refused_start_reconciles_and_retries_once(repo, settings):
    leak(repo, settings)
    calls = []

    def start():
        calls.append(1)
        return "concurrent" if active(repo) >= 1 else "started"

    assert caps.start_with_repair(repo, UID, start) == "started"
    assert len(calls) == 2


def test_a_refused_start_with_a_live_run_stays_refused(repo, settings):
    seed(repo, settings)
    calls = []

    def start():
        calls.append(1)
        return "concurrent"

    assert caps.start_with_repair(repo, UID, start) == "concurrent"
    assert len(calls) == 1 and active(repo) == 1


# ---- the sweep ----


def test_sweep_settles_stale_sessions_resumes_deletes_and_repairs_leaks(repo, settings, blobs):
    stale = seed(repo, settings, n=1)  # running, stale
    fresh = seed(repo, settings, n=2, at=LATE - timedelta(seconds=10))  # not stale yet
    leak(repo, settings, n=3)
    gone = seed(repo, settings, n=4, state="deleting", run_status=None)
    young = seed(repo, settings, n=5, state="deleting", run_status=None,
                 at=LATE - timedelta(seconds=10))  # fmt: skip
    blobs.put_bytes(f"{UID}/{gone}/audio.wav", b"x", "audio/wav")

    out = run_sweep(repo, blobs, settings, LATE)

    assert repo.get_session(UID, stale).state == "failed"
    assert repo.get_session(UID, fresh).state == "running"
    assert repo.get_run(UID, sid_of(3), "run3").released is True
    assert repo.get_run(UID, stale, "run1").released is True
    assert active(repo) == 1  # only the fresh run's slot is left
    with pytest.raises(Exception, match="not found"):
        repo.get_session(UID, gone)
    assert not blobs.list_keys(f"{UID}/{gone}/")
    assert repo.get_session(UID, young).state == "deleting"  # inside the grace window
    assert (out.settled, out.deleted) == (1, 1) and out.repaired >= 1

    again = run_sweep(repo, blobs, settings, LATE)  # idempotent
    assert (again.settled, again.deleted, again.repaired) == (0, 0, 0)


def test_sweep_batch_is_bounded(repo, settings, blobs):
    for n in range(1, 6):
        seed(repo, settings, n=n, state="deleting", run_status=None)
    assert run_sweep(repo, blobs, settings, LATE, batch=2).deleted == 2
    assert run_sweep(repo, blobs, settings, LATE, batch=2).deleted == 2
    assert run_sweep(repo, blobs, settings, LATE, batch=2).deleted == 1


def test_sweep_leaves_a_failed_upload_tombstone_alone(repo, settings, blobs):
    sid = seed(repo, settings, state="deleting", run_status=None, discard_code="audio_unreadable")
    assert run_sweep(repo, blobs, settings, LATE).deleted == 0
    assert repo.get_session(UID, sid).state == "deleting"


async def test_sweep_endpoint(settings, blobs, repo, client_for):
    app, client = client_for
    sid = seed(repo, settings, state="deleting", run_status=None)
    app.state.clock = lambda: LATE
    r = await client.post("/tasks/sweep")
    assert r.status_code == 200 and r.json()["deleted"] == 1
    assert (await client.post("/tasks/sweep")).json() == {"settled": 0, "deleted": 0, "repaired": 0}
    assert repo.paths(sid) == []  # nothing of it is left


@pytest.fixture
async def client_for(settings, blobs, repo):
    import httpx

    app = create_app(settings, repo=repo, blobs=blobs)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as c:
        yield app, c


# ---- a repeated DELETE is not deduped by Cloud Tasks ----


def test_delete_task_names_are_unique_per_enqueue():
    first = TaskPayload(kind="delete", uid=UID, sid=sid_of(1))
    again = TaskPayload(kind="delete", uid=UID, sid=sid_of(1), n=1_767_268_800)
    assert task_name(first) != task_name(again)
    assert task_name(first) == f"{sid_of(1)}-delete"  # an old in-flight task keeps its name


async def test_a_second_failed_delete_enqueues_a_new_task(settings, blobs, repo, client_for):
    app, client = client_for
    sid = seed(repo, settings, state="created", run_status=None)
    blobs.delete_prefix = lambda p: (_ for _ in ()).throw(RuntimeError("gcs down"))
    app.state.clock = lambda: T0
    assert (await client.delete(f"/v1/sessions/{sid}", headers=A)).status_code == 503
    app.state.clock = lambda: T0 + timedelta(minutes=20)
    assert (await client.delete(f"/v1/sessions/{sid}", headers=A)).status_code == 503
    assert len({task_name(p) for p in app.state.queue.pending}) == 2
