"""03-failure-policy Task 4 (R4, D3, D4): one capped retry path, `POST /sessions/{id}/retry`,
re-enters whichever step failed. One repo transaction counts the retry and moves the state.

Runs on FakeRepo always and on the Firestore emulator when FIRESTORE_EMULATOR_HOST is set.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from starlette.testclient import TestClient
from test_first_run import (
    RecordingQueue,
    make_client,
    mk_settings,
    new_session,
    rate,
    repo,  # noqa: F401  (fixture)
    user_counters,
)
from test_start_run import READY, _widen
from test_worker import SID, UID, runner_with
from test_worker import repo as worker_repo  # noqa: F401  (fixture)

from onolys_api import config
from onolys_api.audio import staging_key
from onolys_api.config import MAX_SESSION_RETRIES, Settings
from onolys_api.jobs import caps
from onolys_api.jobs.machine import TRANSITIONS, advance
from onolys_api.jobs.queue import TaskPayload, task_name
from onolys_api.jobs.worker import RetryableError
from onolys_api.repo.models import SessionError

pytestmark = pytest.mark.unit
TRANSIENT = "upstream_unavailable"


def _uid() -> str:
    return f"u{uuid.uuid4().hex[:10]}"


def _hdr(uid: str) -> dict[str, str]:
    return {"Authorization": f"Bearer test:{uid}"}


def failed(repo, uid, *, step="transcribe", code=TRANSIENT, retry_count=0, ready=True, **fields):  # noqa: F811
    """A session that failed at `step` with `code`."""
    extra = dict(READY) if ready else {}
    sid = new_session(repo, uid, state="failed", ready=ready, **extra)
    repo.update_session(
        uid, sid,
        {"error": {"code": code, "step": step}, "retry_count": retry_count,
         "step": step, **fields},
        status={"error_code": code},
    )  # fmt: skip
    return sid


def refail(repo, uid, sid, step="transcribe"):  # noqa: F811
    advance(
        repo, uid, sid, to="failed", step=step,
        error=SessionError(code=TRANSIENT, step=step, kind="transient"),
    )  # fmt: skip


def retry(app, uid, sid):
    with TestClient(app) as c:
        return c.post(f"/v1/sessions/{sid}/retry", headers=_hdr(uid))


def code_of(r) -> str:
    return r.json()["details"][0]["code"]


def mk(repo, queue=None, **kw):  # noqa: F811
    return make_client(repo, mk_settings(**kw), queue or RecordingQueue())


# ---- transitions, config, queue names ----


def test_failed_may_re_enter_validating_and_transcribing():
    assert {"validating", "transcribing", "running", "deleting"} <= TRANSITIONS["failed"]


def test_one_source_for_the_retry_cap():
    assert not hasattr(Settings(), "max_session_retries")
    assert MAX_SESSION_RETRIES == 3


def test_retry_tasks_get_their_own_queue_names():
    """Cloud Tasks drops a task whose name it has seen: a retry must not reuse the old one."""

    def p(kind, **kw):
        return TaskPayload(kind=kind, uid="u", sid="s1", **kw)

    assert task_name(p("validate")) == "s1-validate"
    assert task_name(p("validate", retry=1)) != task_name(p("validate"))
    assert task_name(p("transcribe", retry=2)) not in (task_name(p("transcribe")),
                                                         task_name(p("transcribe", retry=1)))
    assert task_name(p("transcribe-poll", n=1, retry=1)) != task_name(p("transcribe-poll", n=1))


# ---- the cap ----


def test_three_retries_succeed_and_the_fourth_is_409(repo):  # noqa: F811
    uid = _uid()
    queue = RecordingQueue()
    app = mk(repo, queue)
    sid = failed(repo, uid)
    for n in (1, 2, 3):
        r = retry(app, uid, sid)
        assert r.status_code == 202, r.text
        assert repo.get_session(uid, sid).retry_count == n
        assert repo.get_session(uid, sid).state == "transcribing"
        refail(repo, uid, sid)
    r = retry(app, uid, sid)
    assert r.status_code == 409 and code_of(r) == "invalid_state", r.text
    assert repo.get_session(uid, sid).retry_count == 3
    assert repo.get_session(uid, sid).state == "failed"
    assert [c.retry for c in queue.calls] == [1, 2, 3]


def test_status_retries_left_follows_the_same_cap(repo):  # noqa: F811
    uid = _uid()
    app = mk(repo)
    sid = failed(repo, uid)
    assert retry(app, uid, sid).status_code == 202
    refail(repo, uid, sid)
    st = repo.get_status(uid, sid)
    assert (st.error_kind, st.retries_left) == ("transient", MAX_SESSION_RETRIES - 1)


def test_route_and_status_cannot_disagree_on_the_cap(repo, monkeypatch):  # noqa: F811
    monkeypatch.setattr(config, "MAX_SESSION_RETRIES", 1)
    uid = _uid()
    app = mk(repo)
    sid = failed(repo, uid)
    assert retry(app, uid, sid).status_code == 202
    refail(repo, uid, sid)
    assert repo.get_status(uid, sid).retries_left == 0
    assert retry(app, uid, sid).status_code == 409
    assert repo.get_session(uid, sid).retry_count == 1


def test_two_concurrent_retries_at_count_2_one_winner(repo):  # noqa: F811
    _widen(repo)
    queue = RecordingQueue()
    app = mk(repo, queue)
    uid = _uid()
    sid = failed(repo, uid, retry_count=2)
    barrier = threading.Barrier(2)

    def go():
        with TestClient(app) as c:
            barrier.wait()
            return c.post(f"/v1/sessions/{sid}/retry", headers=_hdr(uid))

    with ThreadPoolExecutor(2) as ex:
        rs = [f.result() for f in [ex.submit(go) for _ in range(2)]]
    assert sorted(r.status_code for r in rs) == [202, 409], [r.text for r in rs]
    assert repo.get_session(uid, sid).retry_count == 3
    assert len(queue.calls) == 1


# ---- refusals ----


@pytest.mark.parametrize("code", ["internal_error", "output_invalid", "no_speech",
                                  "audio_unreadable", "transcription_failed", "who_knows"])
def test_non_transient_failure_is_409_and_counts_nothing(repo, code):  # noqa: F811
    uid = _uid()
    queue = RecordingQueue()
    sid = failed(repo, uid, code=code)
    r = retry(mk(repo, queue), uid, sid)
    assert r.status_code == 409 and code_of(r) == "invalid_state", r.text
    assert repo.get_session(uid, sid).retry_count == 0 and not queue.calls


@pytest.mark.parametrize("state", ["awaiting_input", "running", "transcribing", "created"])
def test_not_failed_is_409(repo, state):  # noqa: F811
    uid = _uid()
    sid = new_session(repo, uid, state=state, ready=True, **READY)
    r = retry(mk(repo), uid, sid)
    assert r.status_code == 409 and code_of(r) == "invalid_state", r.text
    assert repo.get_session(uid, sid).retry_count == 0


def test_finalized_rating_is_409(repo):  # noqa: F811
    from datetime import UTC, datetime

    from onolys_api.repo.models import ReportDoc

    uid = _uid()
    sid = failed(repo, uid, step="run")
    repo.put_report(uid, sid, "r1", ReportDoc(
        run_id="x", version=1, report_schema_version="1", report={}, created_at=datetime.now(UTC)
    ))  # fmt: skip
    r = retry(mk(repo), uid, sid)
    assert r.status_code == 409 and code_of(r) == "invalid_state", r.text
    assert repo.get_session(uid, sid).retry_count == 0


def test_unknown_step_is_409(repo):  # noqa: F811
    uid = _uid()
    sid = failed(repo, uid, step="mystery")
    assert retry(mk(repo), uid, sid).status_code == 409


def test_another_users_session_is_404(repo):  # noqa: F811
    sid = failed(repo, _uid())
    assert retry(mk(repo), _uid(), sid).status_code == 404


# ---- each step re-enters the right state and enqueues the right task ----


def test_transcribe_resets_the_step_and_enqueues_transcribe(repo):  # noqa: F811
    uid = _uid()
    queue = RecordingQueue()
    sid = failed(repo, uid, steps={"transcribe": {
        "status": "failed", "attempts": 2, "error": TRANSIENT,
        "stt_operation": "op/1", "stt_started": "2026-11-24T00:00:00+00:00",
    }})  # fmt: skip
    r = retry(mk(repo, queue), uid, sid)
    assert r.status_code == 202, r.text
    assert r.json()["session"] == {"id": sid, "status": "transcribing"}
    s = repo.get_session(uid, sid)
    st = repo.get_status(uid, sid)
    assert (s.state, s.retry_count, s.error) == ("transcribing", 1, None)
    rec = s.steps["transcribe"]
    assert (rec.status, rec.attempts, rec.stt_operation, rec.stt_started, rec.error) == (
        "pending", 0, None, None, None
    )
    assert (st.state, st.error_code, st.error_kind) == ("transcribing", None, None)
    assert [(c.kind, c.sid, c.retry) for c in queue.calls] == [("transcribe", sid, 1)]


def _validate_session(repo, uid, *, staged=True, **kw):  # noqa: F811
    sid = failed(repo, uid, step="validate", ready=False, upload={
        "upload_id": "up1", "format": "mp3", "content_type": "audio/mpeg", "size_bytes": 3,
    }, steps={"validate": {"status": "failed", "attempts": 2, "error": TRANSIENT}}, **kw)  # fmt: skip
    if staged:
        repo._blobs.put_bytes(staging_key(uid, sid, "up1"), b"abc")
    return sid


def test_validate_re_enters_validating_and_enqueues_validate(repo):  # noqa: F811
    uid = _uid()
    queue = RecordingQueue()
    sid = _validate_session(repo, uid)
    r = retry(mk(repo, queue), uid, sid)
    assert r.status_code == 202, r.text
    assert r.json()["session"]["status"] == "validating"
    s = repo.get_session(uid, sid)
    assert (s.state, s.retry_count, s.error) == ("validating", 1, None)
    assert (s.steps["validate"].status, s.steps["validate"].attempts) == ("pending", 0)
    assert [(c.kind, c.retry) for c in queue.calls] == [("validate", 1)]


def test_validate_with_the_staged_copy_gone_is_409_and_counts_nothing(repo):  # noqa: F811
    uid = _uid()
    queue = RecordingQueue()
    sid = _validate_session(repo, uid, staged=False)
    r = retry(mk(repo, queue), uid, sid)
    assert r.status_code == 409 and code_of(r) == "invalid_state", r.text
    s = repo.get_session(uid, sid)
    assert (s.state, s.retry_count) == ("failed", 0) and not queue.calls


def test_run_re_enters_running_with_the_same_submission(repo):  # noqa: F811
    from onolys_api.repo.models import RunDoc

    uid = _uid()
    queue = RecordingQueue()
    sid = failed(repo, uid, step="run")
    rid = rate(repo, uid, sid)
    prior = RunDoc(uid=uid, session_id=sid, run_id="old", preset="p-old", n_runs=2,
                   status="failed", coded_span={"start_ms": 1000, "end_ms": 5000},
                   rating_id=rid, counted=True, released=True)  # fmt: skip
    repo.create_run(uid, sid, "old", prior)
    r = retry(mk(repo, queue), uid, sid)
    assert r.status_code == 202, r.text
    new_id = r.json()["run_id"]
    assert new_id != "old" and r.json()["session"] == {"id": sid, "status": "running"}
    run = repo.get_run(uid, sid, new_id)
    assert (run.preset, run.n_runs, run.units, run.rating_id) == ("p-old", 2, 2, rid)
    assert run.coded_span is not None and run.coded_span.start_ms == 1000
    s = repo.get_session(uid, sid)
    assert (s.state, s.retry_count, s.error) == ("running", 1, None)
    assert [(c.kind, c.run_id) for c in queue.calls] == [("run", new_id)]
    assert user_counters(repo, uid, caps.utc_date()) == (1, 2)  # reserved like a fresh start
    st = repo.get_status(uid, sid)
    assert (st.state, st.error_code, st.error_kind, st.retries_left) == ("running", None, None, 0)


def test_run_retry_at_the_day_cap_shows_daily_cap_reached_and_counts_nothing(repo):  # noqa: F811
    uid = _uid()
    queue = RecordingQueue()
    sid = failed(repo, uid, step="run")
    r = retry(mk(repo, queue, eval_cap_day=0), uid, sid)
    assert r.status_code == 429 and code_of(r) == "daily_cap_reached", r.text
    s = repo.get_session(uid, sid)
    assert (s.state, s.retry_count) == ("failed", 0)
    assert not queue.calls and repo.list_runs(uid, sid) == []


def test_run_retry_enqueue_failure_gives_the_slot_back_and_fails_again(repo):  # noqa: F811
    uid = _uid()
    sid = failed(repo, uid, step="run")
    r = retry(mk(repo, RecordingQueue(fail=True)), uid, sid)
    assert r.status_code == 503, r.text
    assert repo.get_session(uid, sid).state == "failed"
    assert user_counters(repo, uid, caps.utc_date()) == (0, 0)


def test_transcribe_retry_enqueue_failure_fails_the_session_again(repo):  # noqa: F811
    uid = _uid()
    sid = failed(repo, uid)
    r = retry(mk(repo, RecordingQueue(fail=True)), uid, sid)
    assert r.status_code == 503, r.text
    s = repo.get_session(uid, sid)
    assert (s.state, s.error.code, s.error.kind, s.retry_count) == (
        "failed", TRANSIENT, "transient", 1
    )


# ---- POST /runs on a failed session ----


@pytest.mark.parametrize("code", [TRANSIENT, "internal_error", "no_speech"])
def test_post_runs_on_a_failed_session_is_409(repo, code):  # noqa: F811
    uid = _uid()
    queue = RecordingQueue()
    sid = failed(repo, uid, step="run", code=code)
    with TestClient(mk(repo, queue)) as c:
        r = c.post(f"/v1/sessions/{sid}/runs", json={}, headers=_hdr(uid))
    assert r.status_code == 409 and code_of(r) == "invalid_state", r.text
    assert repo.list_runs(uid, sid) == [] and not queue.calls
    assert repo.get_session(uid, sid).retry_count == 0


# ---- the silent worker retry never touches the counter ----


def test_silent_worker_retry_does_not_touch_retry_count(worker_repo):  # noqa: F811
    def boom(ctx):
        raise RetryableError("upstream_unavailable")

    p = TaskPayload(kind="validate", uid=UID, sid=SID)
    runner_with(worker_repo, boom).handle(p, retry_count=0)
    runner_with(worker_repo, boom).handle(p, retry_count=1)
    assert worker_repo.get_session(UID, SID).retry_count == 0
