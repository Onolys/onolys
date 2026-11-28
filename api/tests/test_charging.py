"""03-failure-policy Task 3: the charging module (`should_refund`, `release_once`), `counted` on
the failed session, interview sessions never counted.

Repo-level tests run on FakeRepo always and on the Firestore emulator when set.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor

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
from onolys_api.jobs.charging import release_once, should_refund
from onolys_api.jobs.first_run import maybe_start_first_run

pytestmark = pytest.mark.unit
READY = {"transcript_ready": True, "speaker_confirmed": True, "clinician_speaker": "S1"}


@pytest.mark.parametrize(
    ("kind", "llm_started", "expected"),
    [
        ("transient", False, True),
        ("transient", True, True),
        ("permanent_internal", False, True),
        ("permanent_internal", True, True),
        ("user_file", False, True),
        ("user_file", True, False),
    ],
)
def test_should_refund_table(kind, llm_started, expected):
    assert should_refund(kind, llm_started) is expected


def _ready(repo, uid, **fields):  # noqa: F811
    sid = new_session(repo, uid, state="awaiting_input", ready=True, **READY, **fields)
    set_flags(repo, uid, sid, rating_submitted=True)
    return sid


def _start(repo, uid, **fields):  # noqa: F811
    sid = _ready(repo, uid, **fields)
    maybe_start_first_run(repo, RecordingQueue(), uid, sid, mk_settings(max_active_runs=3))
    (run,) = repo.list_runs(uid, sid)
    return sid, run


def test_release_with_refund_reports_unit_not_kept_and_refunds_once(repo):  # noqa: F811
    uid, date = "uc" + uuid.uuid4().hex[:6], caps.utc_date()
    sid, run = _start(repo, uid)
    assert user_counters(repo, uid, date) == (1, 1)
    assert release_once(repo, uid, sid, run.run_id, True, date) is False  # not kept
    assert repo.get_run(uid, sid, run.run_id).unit_kept is False
    assert user_counters(repo, uid, date) == (0, 0)
    assert release_once(repo, uid, sid, run.run_id, True, date) is False  # double call: same answer
    assert user_counters(repo, uid, date) == (0, 0)


def test_double_release_refunds_once_with_another_run_counted(repo):  # noqa: F811
    uid, date = "ud" + uuid.uuid4().hex[:6], caps.utc_date()
    sid, run = _start(repo, uid)
    _start(repo, uid)
    assert user_counters(repo, uid, date) == (2, 2)
    with ThreadPoolExecutor(4) as pool:
        got = list(
            pool.map(lambda _: release_once(repo, uid, sid, run.run_id, True, date), range(4))
        )
    assert got == [False] * 4
    assert user_counters(repo, uid, date) == (1, 1)


def test_release_without_refund_keeps_the_unit(repo):  # noqa: F811
    uid, date = "uk" + uuid.uuid4().hex[:6], caps.utc_date()
    sid, run = _start(repo, uid)
    assert release_once(repo, uid, sid, run.run_id, False, date) is True
    assert repo.get_run(uid, sid, run.run_id).unit_kept is True
    assert user_counters(repo, uid, date) == (0, 1)
    assert release_once(repo, uid, sid, run.run_id, True, date) is True  # stored answer, no refund
    assert user_counters(repo, uid, date) == (0, 1)


def test_release_of_a_vanished_run_is_none(repo):  # noqa: F811
    uid = "uv" + uuid.uuid4().hex[:6]
    sid = _ready(repo, uid)
    assert release_once(repo, uid, sid, "nope", True, caps.utc_date()) is None


@pytest.mark.parametrize("refund", [True, False])
def test_interview_first_run_is_never_counted_nor_refunded(repo, refund):  # noqa: F811
    uid, date = "ui" + uuid.uuid4().hex[:6], caps.utc_date()
    sid, run = _start(repo, uid, interview_id="iv1")
    assert run.counted is False
    assert user_counters(repo, uid, date) == (1, 0)
    assert release_once(repo, uid, sid, run.run_id, refund, date) is False
    assert user_counters(repo, uid, date) == (0, 0)


def test_non_interview_first_run_is_counted(repo):  # noqa: F811
    uid, date = "un" + uuid.uuid4().hex[:6], caps.utc_date()
    _, run = _start(repo, uid)
    assert run.counted is True
    assert user_counters(repo, uid, date) == (1, 1)
