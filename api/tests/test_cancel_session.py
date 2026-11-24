"""04-cancel Task 3: `Repo.cancel_session`, the atomic cancel transaction (R3, R4, D1-D3, D5, D6).

Runs on FakeRepo always and on the Firestore emulator when FIRESTORE_EMULATOR_HOST is set.
"""

import uuid
from datetime import UTC, datetime

import pytest
from test_first_run import (
    RecordingQueue,
    mk_settings,
    new_session,
    repo,  # noqa: F401  (fixture)
    set_flags,
    user_counters,
)

from onolys_api.jobs import caps
from onolys_api.jobs.charging import release_once
from onolys_api.jobs.first_run import maybe_start_first_run
from onolys_api.repo.base import NotFoundError
from onolys_api.repo.limits import LimitDefaults

pytestmark = pytest.mark.unit
D = LimitDefaults(eval_day=10, interview_day=5)
READY = {"transcript_ready": True, "speaker_confirmed": True, "clinician_speaker": "S1"}
SEVEN = ("created", "uploading", "upload_incomplete", "validating", "transcribing",
         "awaiting_input", "running")  # fmt: skip


def _uid() -> str:
    return "ux" + uuid.uuid4().hex[:8]


def _cancel(repo, uid, sid, date=None):  # noqa: F811
    return repo.cancel_session(uid, sid, date or caps.utc_date(), D)


def _running(repo, uid, **fields):  # noqa: F811
    sid = new_session(repo, uid, state="awaiting_input", ready=True, **READY, **fields)
    set_flags(repo, uid, sid, rating_submitted=True)
    maybe_start_first_run(repo, RecordingQueue(), uid, sid, mk_settings(max_active_runs=3))
    (run,) = repo.list_runs(uid, sid)
    return sid, run


@pytest.mark.parametrize(
    ("state", "op", "units"),
    [
        ("created", None, 0),
        ("uploading", None, 0),
        ("upload_incomplete", None, 0),
        ("validating", None, 0),
        ("transcribing", None, 0),
        ("transcribing", "op-1", 1),
        ("awaiting_input", None, 1),
    ],
)
def test_each_state_outcome_and_charge(repo, state, op, units):  # noqa: F811
    uid, date = _uid(), caps.utc_date()
    sid = new_session(repo, uid, state=state, ready=state == "awaiting_input")
    if op:
        repo.update_session(uid, sid, {"steps.transcribe.stt_operation": op})
    assert _cancel(repo, uid, sid, date) == ("cancelled", bool(units))
    s = repo.get_session(uid, sid)
    assert s.state == "cancelled"
    assert (s.cancel.counted, s.cancel.units) == (bool(units), units)
    assert s.stage_started_at is not None
    st = repo.get_status(uid, sid)
    assert (st.state, st.counted) == ("cancelled", bool(units))
    assert repo.get_usage(uid, date).runs == units
    # nothing deleted: the transcript blob/doc is intact
    assert len(repo.get_transcript(uid, sid, "current").transcript.turns) > 0


def test_interview_session_is_never_charged(repo):  # noqa: F811
    uid, date = _uid(), caps.utc_date()
    sid = new_session(repo, uid, state="awaiting_input", ready=True, interview_id="i" * 32)
    assert _cancel(repo, uid, sid, date) == ("cancelled", False)
    assert repo.get_usage(uid, date).runs == 0


def test_second_cancel_is_idempotent_and_returns_stored_counted(repo):  # noqa: F811
    uid, date = _uid(), caps.utc_date()
    sid = new_session(repo, uid, state="awaiting_input", ready=True)
    assert _cancel(repo, uid, sid, date) == ("cancelled", True)
    at = repo.get_session(uid, sid).cancel.at
    assert _cancel(repo, uid, sid, date) == ("cancelled", True)
    assert repo.get_usage(uid, date).runs == 1
    assert repo.get_session(uid, sid).cancel.at == at


@pytest.mark.parametrize("state", ["report_ready", "failed"])
def test_finished_states_are_invalid_and_untouched(repo, state):  # noqa: F811
    uid, date = _uid(), caps.utc_date()
    sid = new_session(repo, uid, state=state, ready=True)
    assert _cancel(repo, uid, sid, date) == ("invalid",)
    assert repo.get_session(uid, sid).state == state
    assert repo.get_usage(uid, date).runs == 0


def test_deleting_foreign_and_missing_are_not_found(repo):  # noqa: F811
    uid = _uid()
    sid = new_session(repo, uid, state="deleting")
    with pytest.raises(NotFoundError):
        _cancel(repo, uid, sid)
    other = new_session(repo, uid, state="created")
    with pytest.raises(NotFoundError):
        _cancel(repo, _uid(), other)
    with pytest.raises(NotFoundError):
        _cancel(repo, uid, uuid.uuid4().hex)


def test_over_cap_cancel_still_increments(repo):  # noqa: F811
    uid, date = _uid(), caps.utc_date()
    repo.add_usage(uid, date, runs=D.eval_day)  # at the cap
    sid = new_session(repo, uid, state="awaiting_input", ready=True)
    assert _cancel(repo, uid, sid, date) == ("cancelled", True)
    assert repo.get_usage(uid, date).runs == D.eval_day + 1


def test_running_cancel_releases_slot_without_refund_and_fails_run(repo):  # noqa: F811
    uid, date = _uid(), caps.utc_date()
    sid, run = _running(repo, uid)
    assert user_counters(repo, uid, date) == (1, 1)
    assert _cancel(repo, uid, sid, date) == ("cancelled", True)  # the run's `counted`
    assert user_counters(repo, uid, date) == (0, 1)  # slot back, unit kept, no second charge
    got = repo.get_run(uid, sid, run.run_id)
    assert (got.status, got.error, got.released, got.unit_kept) == (
        "failed",
        "cancelled",
        True,
        True,
    )
    s = repo.get_session(uid, sid)
    assert (s.state, s.cancel.counted, s.cancel.units) == ("cancelled", True, 0)
    # a late delivery of the run task is a duplicate, never claimed again
    claim = repo.claim_run(uid, sid, run.run_id, datetime.now(UTC), 60.0)
    assert claim.outcome != "claimed"
    # the data is intact
    assert len(repo.get_transcript(uid, sid, "current").transcript.turns) > 0
    assert [r.run_id for r in repo.list_runs(uid, sid)] == [run.run_id]


def test_running_exempt_interview_run_reports_not_counted(repo):  # noqa: F811
    uid, date = _uid(), caps.utc_date()
    sid, run = _running(repo, uid, interview_id="i" * 32)
    assert user_counters(repo, uid, date) == (1, 0)
    assert _cancel(repo, uid, sid, date) == ("cancelled", False)
    assert user_counters(repo, uid, date) == (0, 0)


def test_failing_run_end_after_cancel_does_no_second_release(repo):  # noqa: F811
    uid, date = _uid(), caps.utc_date()
    sid, run = _running(repo, uid)
    other_sid, _ = _running(repo, uid)  # a second live run so a double release would show
    _cancel(repo, uid, sid, date)
    assert user_counters(repo, uid, date) == (1, 2)
    assert release_once(repo, uid, sid, run.run_id, True, date) is True  # refund asked: no-op
    assert repo.release_run_slot(uid, sid, run.run_id, True, date) is False
    assert user_counters(repo, uid, date) == (1, 2)
    assert repo.get_session(uid, other_sid).state == "running"


def test_cancelled_session_cannot_start_a_run(repo):  # noqa: F811
    uid, date = _uid(), caps.utc_date()
    sid = new_session(repo, uid, state="awaiting_input", ready=True, **READY)
    set_flags(repo, uid, sid, rating_submitted=True)
    _cancel(repo, uid, sid, date)
    assert repo.start_first_run(uid, sid, "r1", date, D, 3, "v", 10) == "not_ready"
    out = repo.start_run(
        uid,
        sid,
        "r2",
        date,
        D,
        3,
        "v",
        10,
        ("awaiting_input", "report_ready", "failed"),
        None,
        None,
    )
    assert out == "not_ready"
    assert repo.list_runs(uid, sid) == []
