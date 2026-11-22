"""`POST /runs` starts a run atomically: the state check, the cap reservation, the run creation,
`first_run_id` and the move to `running` are one repo transaction (`Repo.start_run`), so two
concurrent starts, or a manual start against the auto first run, cannot both win.

Runs on FakeRepo always and on the Firestore emulator when FIRESTORE_EMULATOR_HOST is set.
"""

import threading
import time
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
    set_flags,
    user_counters,
)

from onolys_api.jobs import caps
from onolys_api.jobs.first_run import maybe_start_first_run
from onolys_api.repo.fake import FakeRepo

pytestmark = pytest.mark.unit
READY = {"transcript_ready": True, "speaker_confirmed": True, "clinician_speaker": "S1"}


class SlowReadRepo(FakeRepo):
    """Widens the read-then-write window so a non-atomic start reliably interleaves."""

    def get_session(self, uid, sid):
        s = super().get_session(uid, sid)
        time.sleep(0.05)
        return s


def _widen(r):
    if isinstance(r, FakeRepo):
        r.__class__ = SlowReadRepo


def _post(app, h, sid, barrier):
    with TestClient(app) as c:
        barrier.wait()
        return c.post(f"/v1/sessions/{sid}/runs", json={}, headers=h)


@pytest.mark.parametrize("state", ["awaiting_input", "failed"])
def test_two_concurrent_manual_starts_exactly_one_wins(repo, state):  # noqa: F811
    _widen(repo)
    queue = RecordingQueue()
    app = make_client(repo, mk_settings(max_active_runs=2), queue)
    uid = f"u{uuid.uuid4().hex[:10]}"
    h = {"Authorization": f"Bearer test:{uid}"}
    sid = new_session(repo, uid, state=state, ready=True, **READY)
    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(2) as ex:
        rs = [f.result() for f in [ex.submit(_post, app, h, sid, barrier) for _ in range(2)]]
    assert sorted(r.status_code for r in rs) == [202, 409], [r.text for r in rs]
    loser = next(r for r in rs if r.status_code == 409)
    assert loser.json()["details"][0]["code"] == "invalid_state"
    assert len(repo.list_runs(uid, sid)) == 1
    assert len(queue.runs) == 1
    assert repo.get_session(uid, sid).state == "running"
    assert user_counters(repo, uid, caps.utc_date()) == (1, 1)  # the loser holds no slot


def test_manual_start_vs_auto_first_run_exactly_one_run(repo):  # noqa: F811
    _widen(repo)
    s = mk_settings(max_active_runs=2)
    for _ in range(3):
        queue = RecordingQueue()
        app = make_client(repo, s, queue)
        uid = f"u{uuid.uuid4().hex[:10]}"
        h = {"Authorization": f"Bearer test:{uid}"}
        sid = new_session(repo, uid, state="awaiting_input", ready=True, **READY)
        set_flags(repo, uid, sid, rating_submitted=True)
        rate(repo, uid, sid)
        barrier = threading.Barrier(2)

        def auto(sid=sid, uid=uid, queue=queue, barrier=barrier):
            barrier.wait()
            maybe_start_first_run(repo, queue, uid, sid, s)

        with ThreadPoolExecutor(2) as ex:
            fa = ex.submit(auto)
            fm = ex.submit(_post, app, h, sid, barrier)
            fa.result()
            r = fm.result()
        assert r.status_code in (202, 409)
        assert len(repo.list_runs(uid, sid)) == 1
        assert len(queue.runs) == 1
        sess = repo.get_session(uid, sid)
        assert sess.first_run_id == repo.list_runs(uid, sid)[0].run_id
        assert user_counters(repo, uid, caps.utc_date()) == (1, 1)


def test_manual_start_sets_first_run_id_when_unset(repo):  # noqa: F811
    queue = RecordingQueue()
    app = make_client(repo, mk_settings(), queue)
    uid = f"u{uuid.uuid4().hex[:10]}"
    h = {"Authorization": f"Bearer test:{uid}"}
    sid = new_session(repo, uid, state="awaiting_input", ready=True, **READY)
    with TestClient(app) as c:
        r = c.post(f"/v1/sessions/{sid}/runs", json={}, headers=h)
    assert r.status_code == 202
    assert repo.get_session(uid, sid).first_run_id == r.json()["run_id"]
    # the first-run gate now finds it taken
    set_flags(repo, uid, sid, rating_submitted=True)
    maybe_start_first_run(repo, queue, uid, sid, mk_settings())
    assert len(repo.list_runs(uid, sid)) == 1


def test_refused_start_reserves_nothing(repo):  # noqa: F811
    queue = RecordingQueue()
    app = make_client(repo, mk_settings(max_active_runs=2, eval_cap_day=0), queue)
    uid = f"u{uuid.uuid4().hex[:10]}"
    h = {"Authorization": f"Bearer test:{uid}"}
    sid = new_session(repo, uid, state="failed", ready=True, **READY)
    with TestClient(app) as c:
        r = c.post(f"/v1/sessions/{sid}/runs", json={}, headers=h)
    assert r.status_code == 429 and r.json()["details"][0]["code"] == "daily_cap_reached"
    assert repo.get_session(uid, sid).state == "failed"
    assert repo.list_runs(uid, sid) == []
    assert user_counters(repo, uid, caps.utc_date()) == (0, 0)


# ---- the free first run of an interview-linked session also works through POST /runs (SP11 AC6)


def _post_run(app, uid, sid):
    with TestClient(app) as c:
        return c.post(
            f"/v1/sessions/{sid}/runs", json={}, headers={"Authorization": f"Bearer test:{uid}"}
        )


def _linked_ready(repo, uid, **fields):  # noqa: F811
    sid = new_session(repo, uid, state="awaiting_input", ready=True, **READY, **fields)
    set_flags(repo, uid, sid, rating_submitted=True)
    return sid


def test_linked_first_run_held_by_active_limit_starts_free_via_post_runs(repo):  # noqa: F811
    uid = f"u{uuid.uuid4().hex[:10]}"
    sid = _linked_ready(repo, uid, interview_id="iv1")
    full = mk_settings(eval_cap_day=0)
    held = mk_settings(eval_cap_day=0, max_active_runs=0)
    maybe_start_first_run(repo, RecordingQueue(), uid, sid, held)  # held by MAX_ACTIVE_RUNS
    assert repo.get_session(uid, sid).first_run_id is None
    queue = RecordingQueue()
    r = _post_run(make_client(repo, full, queue), uid, sid)
    assert r.status_code == 202, r.text
    sess = repo.get_session(uid, sid)
    assert sess.state == "running" and sess.first_run_id == r.json()["run_id"]
    (run,) = repo.list_runs(uid, sid)
    assert run.counted is False and len(queue.runs) == 1
    date = caps.utc_date()
    assert user_counters(repo, uid, date) == (1, 0)  # a slot, but no usage
    assert repo.get_usage_doc(uid, date).runs == 0


def test_linked_post_runs_still_obeys_the_active_limit(repo):  # noqa: F811
    uid = f"u{uuid.uuid4().hex[:10]}"
    sid = _linked_ready(repo, uid, interview_id="iv1")
    r = _post_run(make_client(repo, mk_settings(max_active_runs=0)), uid, sid)
    assert r.status_code == 429
    assert repo.list_runs(uid, sid) == []
    assert user_counters(repo, uid, caps.utc_date()) == (0, 0)


# ---- FX45 (E24): a rating is final once its report is ready; only a system failure may retry


@pytest.mark.parametrize("fields", [{}, {"interview_id": "iv1"}], ids=["upload", "interview"])
def test_post_runs_after_a_successful_report_is_refused(repo, fields):  # noqa: F811
    """The interview flow includes exactly one rating, so a linked session is no different."""
    from onolys_api.jobs.run import release_once

    uid = f"u{uuid.uuid4().hex[:10]}"
    sid = _linked_ready(repo, uid, **fields)
    app = make_client(repo, mk_settings(eval_cap_day=5), RecordingQueue())
    assert _post_run(app, uid, sid).status_code == 202
    (run,) = repo.list_runs(uid, sid)
    release_once(repo, uid, sid, run.run_id, False, caps.utc_date())  # the run finished
    repo.update_session(uid, sid, {"state": "report_ready"})
    r = _post_run(app, uid, sid)
    assert r.status_code == 409 and r.json()["details"][0]["code"] == "rating_final", r.text
    assert len(repo.list_runs(uid, sid)) == 1


def test_post_runs_on_a_failed_session_with_an_older_report_is_refused(repo):  # noqa: F811
    from datetime import UTC, datetime

    from onolys_api.repo.models import ReportDoc

    uid = f"u{uuid.uuid4().hex[:10]}"
    sid = _linked_ready(repo, uid)
    repo.put_report(uid, sid, "r1", ReportDoc(
        run_id="x", version=1, report_schema_version="1", report={}, created_at=datetime.now(UTC)
    ))  # fmt: skip
    repo.update_session(uid, sid, {"state": "failed", "error": {"code": "internal_error"}})
    r = _post_run(make_client(repo, mk_settings(), RecordingQueue()), uid, sid)
    assert r.status_code == 409 and r.json()["details"][0]["code"] == "rating_final", r.text


def test_try_again_after_a_system_failure_reuses_the_stored_rating(repo):  # noqa: F811
    uid = f"u{uuid.uuid4().hex[:10]}"
    sid = _linked_ready(repo, uid)
    rid = rate(repo, uid, sid)
    repo.update_session(uid, sid, {"state": "failed", "error": {"code": "upstream_unavailable"}})
    r = _post_run(make_client(repo, mk_settings(), RecordingQueue()), uid, sid)
    assert r.status_code == 202, r.text
    assert repo.get_run(uid, sid, r.json()["run_id"]).rating_id == rid


@pytest.mark.parametrize("code", ["no_speech", "audio_unreadable", "transcription_failed"])
def test_post_runs_after_a_bad_file_failure_is_refused(repo, code):  # noqa: F811
    uid = f"u{uuid.uuid4().hex[:10]}"
    sid = _linked_ready(repo, uid)
    repo.update_session(uid, sid, {"state": "failed", "error": {"code": code}})
    r = _post_run(make_client(repo, mk_settings(), RecordingQueue()), uid, sid)
    assert r.status_code == 409 and r.json()["details"][0]["code"] == "invalid_state", r.text
    assert repo.list_runs(uid, sid) == []


def test_unlinked_post_runs_is_unchanged_counts_and_obeys_the_cap(repo):  # noqa: F811
    uid = f"u{uuid.uuid4().hex[:10]}"
    sid = _linked_ready(repo, uid)
    assert _post_run(make_client(repo, mk_settings(eval_cap_day=0)), uid, sid).status_code == 429
    r = _post_run(make_client(repo, mk_settings()), uid, sid)
    assert r.status_code == 202
    assert repo.get_run(uid, sid, r.json()["run_id"]).counted is True
    assert user_counters(repo, uid, caps.utc_date()) == (1, 1)


def test_session_detail_exposes_interview_id(repo):  # noqa: F811
    uid = f"u{uuid.uuid4().hex[:10]}"
    linked = _linked_ready(repo, uid, interview_id="iv1")
    plain = _linked_ready(repo, uid)
    h = {"Authorization": f"Bearer test:{uid}"}
    with TestClient(make_client(repo)) as c:
        assert c.get(f"/v1/sessions/{linked}", headers=h).json()["interview_id"] == "iv1"
        assert c.get(f"/v1/sessions/{plain}", headers=h).json()["interview_id"] is None


# ---- FX42 (A5): a run costs n_runs units ---------------------------------------------------


def test_n_runs_costs_n_units_and_refunds_all(repo):  # noqa: F811
    from onolys_api.jobs.run import release_once

    uid = f"u{uuid.uuid4().hex[:10]}"
    sid = _linked_ready(repo, uid)
    app = make_client(repo, mk_settings(eval_cap_day=5), RecordingQueue())
    with TestClient(app) as c:
        r = c.post(f"/v1/sessions/{sid}/runs", json={"n_runs": 3},
                   headers={"Authorization": f"Bearer test:{uid}"})  # fmt: skip
    assert r.status_code == 202, r.text
    date = caps.utc_date()
    assert user_counters(repo, uid, date) == (1, 3)  # one slot, three units
    assert repo.get_usage_doc(uid, date).runs == 3
    release_once(repo, uid, sid, r.json()["run_id"], True, date)
    assert user_counters(repo, uid, date) == (0, 0)
    assert repo.get_usage_doc(uid, date).runs == 0


def test_n_runs_beyond_the_units_left_is_refused_and_reserves_nothing(repo):  # noqa: F811
    uid = f"u{uuid.uuid4().hex[:10]}"
    sid = _linked_ready(repo, uid)
    r = _post_run_n(make_client(repo, mk_settings(eval_cap_day=2)), uid, sid, 3)
    assert r.status_code == 429, r.text
    assert r.json()["details"][0]["code"] == "daily_cap_reached"
    assert repo.list_runs(uid, sid) == []
    assert user_counters(repo, uid, caps.utc_date()) == (0, 0)
    ok = _post_run_n(make_client(repo, mk_settings(eval_cap_day=3), RecordingQueue()), uid, sid, 3)
    assert ok.status_code == 202  # exactly the units left fit


def _post_run_n(app, uid, sid, n):
    with TestClient(app) as c:
        return c.post(f"/v1/sessions/{sid}/runs", json={"n_runs": n},
                      headers={"Authorization": f"Bearer test:{uid}"})  # fmt: skip


def test_auto_first_run_costs_the_session_n_runs(repo):  # noqa: F811
    uid = f"u{uuid.uuid4().hex[:10]}"
    sid = _linked_ready(repo, uid, n_runs=2)
    maybe_start_first_run(repo, RecordingQueue(), uid, sid, mk_settings())
    assert user_counters(repo, uid, caps.utc_date()) == (1, 2)


# ---- FX44 (A10): an interview session whose audio is not the relay's recording pays -----------


def test_linked_session_with_unmatched_audio_is_charged(repo):  # noqa: F811
    uid = f"u{uuid.uuid4().hex[:10]}"
    sid = _linked_ready(repo, uid, interview_id="iv1", free_run_void=True)
    maybe_start_first_run(repo, RecordingQueue(), uid, sid, mk_settings())
    (run,) = repo.list_runs(uid, sid)
    assert run.counted is True
    assert user_counters(repo, uid, caps.utc_date()) == (1, 1)
    # and it is held by the cap like any upload
    sid2 = _linked_ready(repo, uid, interview_id="iv2", free_run_void=True)
    maybe_start_first_run(repo, RecordingQueue(), uid, sid2, mk_settings(eval_cap_day=1))
    assert repo.get_session(uid, sid2).first_run_id is None
    r = _post_run(make_client(repo, mk_settings(eval_cap_day=1), RecordingQueue()), uid, sid2)
    assert r.status_code == 429


# ---- review R1: Try again after a failed FREE interview run stays free -------------------------


def _fail_system(repo_, uid, sid, run_id):
    from onolys_api.jobs.run import release_once

    repo_.update_run(uid, sid, run_id, {"status": "failed", "error": "upstream_unavailable"})
    release_once(repo_, uid, sid, run_id, True, caps.utc_date())  # refund: free run, nothing given
    repo_.update_session(uid, sid, {"state": "failed", "error": {"code": "upstream_unavailable"}})


def test_try_again_after_failed_free_interview_run_is_free_even_at_eval_cap(repo):  # noqa: F811
    uid = f"u{uuid.uuid4().hex[:10]}"
    date = caps.utc_date()
    sid = _linked_ready(repo, uid, interview_id="iv1", n_runs=2)
    cap1 = mk_settings(eval_cap_day=1)  # 2 units would not fit: the free run is exempt
    maybe_start_first_run(repo, RecordingQueue(), uid, sid, cap1)
    (first,) = repo.list_runs(uid, sid)
    assert first.counted is False
    _fail_system(repo, uid, sid, first.run_id)
    assert user_counters(repo, uid, date) == (0, 0)
    queue = RecordingQueue()
    r = _post_run(make_client(repo, cap1, queue), uid, sid)
    assert r.status_code == 202, r.text
    second = repo.get_run(uid, sid, r.json()["run_id"])
    assert second.counted is False and second.n_runs == 2  # same submission, still free
    assert user_counters(repo, uid, date) == (1, 0)  # takes the active slot, no usage
    assert repo.get_usage_doc(uid, date).runs == 0
    _fail_system(repo, uid, sid, second.run_id)  # fails again: still nothing to refund twice
    assert user_counters(repo, uid, date) == (0, 0)
    assert repo.get_usage_doc(uid, date).runs == 0


def test_try_again_after_failed_charged_run_is_still_charged(repo):  # noqa: F811
    uid = f"u{uuid.uuid4().hex[:10]}"
    date = caps.utc_date()
    sid = _linked_ready(repo, uid, interview_id="iv1", free_run_void=True)
    maybe_start_first_run(repo, RecordingQueue(), uid, sid, mk_settings())
    (first,) = repo.list_runs(uid, sid)
    assert first.counted is True
    _fail_system(repo, uid, sid, first.run_id)
    assert repo.get_usage_doc(uid, date).runs == 0  # refunded
    r = _post_run(make_client(repo, mk_settings(eval_cap_day=0), RecordingQueue()), uid, sid)
    assert r.status_code == 429  # a charged run is charged again


def test_session_detail_exposes_free_run(repo):  # noqa: F811
    uid = f"u{uuid.uuid4().hex[:10]}"
    free = _linked_ready(repo, uid, interview_id="iv1")
    void = _linked_ready(repo, uid, interview_id="iv2", free_run_void=True)
    plain = _linked_ready(repo, uid)
    h = {"Authorization": f"Bearer test:{uid}"}
    with TestClient(make_client(repo)) as c:
        got = [c.get(f"/v1/sessions/{s}", headers=h).json()["free_run"] for s in (free, void, plain)]
    assert got == [True, False, False]
