"""04-cancel Task 9: cancel vs `start_first_run` race (AC3).

One transaction wins. Run wins: cancel then reports the run's `counted` and releases the slot.
Cancel wins: the run start returns `not_ready` and nothing is reserved. The poll-vs-cancel race
is covered by `test_cancel_workers.py` (`test_cancel_mid_poll_*`, `test_backstop_*`).

Runs on FakeRepo always and on the Firestore emulator when FIRESTORE_EMULATOR_HOST is set.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_first_run import (
    new_session,
    repo,  # noqa: F401  (fixture)
    set_flags,
    user_counters,
)

from onolys_api.jobs import caps
from onolys_api.repo.limits import LimitDefaults

pytestmark = pytest.mark.unit
D = LimitDefaults(eval_day=10, interview_day=5)
READY = {"transcript_ready": True, "speaker_confirmed": True, "clinician_speaker": "S1"}


def _ready(repo, uid):  # noqa: F811
    sid = new_session(repo, uid, state="awaiting_input", ready=True, **READY)
    set_flags(repo, uid, sid, rating_submitted=True)
    return sid


def _start(repo, uid, sid, date):  # noqa: F811
    return repo.start_first_run(uid, sid, "r1", date, D, 3, "v", 10)


def test_run_wins_then_cancel_reports_counted_and_releases(repo):  # noqa: F811
    uid, date = "rc" + uuid.uuid4().hex[:8], caps.utc_date()
    sid = _ready(repo, uid)
    assert _start(repo, uid, sid, date) == "started"
    assert user_counters(repo, uid, date) == (1, 1)
    assert repo.cancel_session(uid, sid, date, D) == ("cancelled", True)
    assert user_counters(repo, uid, date) == (0, 1)  # slot released, unit kept, no second charge
    assert repo.get_session(uid, sid).state == "cancelled"


def test_cancel_wins_then_run_start_is_not_ready(repo):  # noqa: F811
    uid, date = "rc" + uuid.uuid4().hex[:8], caps.utc_date()
    sid = _ready(repo, uid)
    assert repo.cancel_session(uid, sid, date, D) == ("cancelled", True)
    assert _start(repo, uid, sid, date) == "not_ready"
    assert repo.list_runs(uid, sid) == []
    assert user_counters(repo, uid, date) == (0, 1)  # only the cancel charge


@pytest.mark.parametrize("round_", range(4))
def test_concurrent_cancel_and_first_run_have_one_consistent_winner(repo, round_):  # noqa: F811
    uid, date = "rc" + uuid.uuid4().hex[:8], caps.utc_date()
    sid = _ready(repo, uid)
    barrier = threading.Barrier(2)

    def start():
        barrier.wait()
        return _start(repo, uid, sid, date)

    def cancel():
        barrier.wait()
        return repo.cancel_session(uid, sid, date, D)

    with ThreadPoolExecutor(2) as ex:
        f_start, f_cancel = ex.submit(start), ex.submit(cancel)
        started, cancelled = f_start.result(), f_cancel.result()

    s = repo.get_session(uid, sid)
    assert s.state == "cancelled"  # cancel always lands; nothing ends up running
    assert cancelled == ("cancelled", True)  # counted either way: the run's unit or the cancel's
    assert user_counters(repo, uid, date) == (0, 1)  # exactly one unit, no leaked slot
    runs = repo.list_runs(uid, sid)
    if started == "started":  # run won: its run doc is failed/released by the cancel
        assert [(r.status, r.error, r.released) for r in runs] == [("failed", "cancelled", True)]
    else:  # cancel won
        assert started == "not_ready" and runs == []
