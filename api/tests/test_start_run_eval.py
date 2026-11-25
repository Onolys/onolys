"""`Repo.start_run(eval=...)` (SP04 R3): an eval run starts on any ready session, outside the caps,
counted=False, no usage, the block written once; the other bookkeeping is unchanged.

Runs on FakeRepo always and on the Firestore emulator when FIRESTORE_EMULATOR_HOST is set.
"""

# ruff: noqa: F811

import uuid

import pytest
from test_first_run import new_session, repo, user_counters  # noqa: F401

from onolys_api.repo.limits import LimitDefaults
from onolys_api.repo.models import EvalRunInfo

pytestmark = pytest.mark.unit
D = LimitDefaults(eval_day=1, interview_day=5)
DATE = "2026-11-24"
INFO = EvalRunInfo(
    eval_run_id="e1",
    combo_key="miti|openai|gpt|low|high",
    repeat=0,
    engine="oneshot:miti",
    route_override={"provider": "openai", "model": "gpt", "tier": "low", "effort": "high"},
    resolved_route={"litellm_id": "openai/gpt", "effort": "high"},
    engine_version="v1",
)
STATES = ("awaiting_input",)


def ready(repo, state):
    uid = "ev-" + uuid.uuid4().hex
    sid = new_session(
        repo, uid, state=state, ready=True, speaker_confirmed=True, clinician_speaker="S1",
        change_goal="g", language="auto",
    )  # fmt: skip
    return uid, sid


def start(repo, uid, sid, rid="r1", states=STATES, max_active=5, **kw):
    return repo.start_run(uid, sid, rid, DATE, D, max_active, "v", 45, states, None, None, **kw)


@pytest.mark.parametrize("state", ["report_ready", "failed"])
def test_eval_start_on_a_finished_session(repo, state):
    uid, sid = ready(repo, state)
    assert start(repo, uid, sid, eval=INFO) == "started"
    run = repo.get_run(uid, sid, "r1")
    assert run.eval == INFO
    assert run.counted is False
    assert repo.get_session(uid, sid).state == "running"
    assert repo.get_session(uid, sid).first_run_id == "r1"


@pytest.mark.parametrize("state", ["report_ready", "failed"])
def test_prod_start_on_a_finished_session_still_refused(repo, state):
    uid, sid = ready(repo, state)
    assert start(repo, uid, sid) == "not_ready"
    assert repo.get_session(uid, sid).state == state


def test_eval_start_ignores_day_cap_and_charges_no_usage(repo):
    uid, sid = ready(repo, "report_ready")
    assert start(repo, uid, sid, "r0", states=("awaiting_input", "report_ready")) == "started"
    assert user_counters(repo, uid, DATE) == (1, 1)  # a prod run spent the whole day cap (1)
    repo.release_run_slot(uid, sid, "r0", False, DATE)
    repo.update_session(uid, sid, {"state": "report_ready"}, status={"state": "report_ready"})
    assert start(repo, uid, sid, "r1", eval=INFO) == "started"
    assert user_counters(repo, uid, DATE) == (1, 1)  # active_runs +1, usage unchanged


def test_eval_start_ignores_concurrent_limit(repo):
    uid, s1 = ready(repo, "awaiting_input")
    assert start(repo, uid, s1, "ra", max_active=1) == "started"
    s2 = new_session(
        repo, uid, state="report_ready", ready=True, speaker_confirmed=True,
        clinician_speaker="S1", change_goal="g", language="auto",
    )  # fmt: skip
    assert start(repo, uid, s2, "rb", max_active=1) == "not_ready"  # prod: state + limit
    assert start(repo, uid, s2, "rb", max_active=1, eval=INFO) == "started"
    assert user_counters(repo, uid, DATE)[0] == 2


def test_eval_block_written_once_and_slot_released_normally(repo):
    uid, sid = ready(repo, "failed")
    assert start(repo, uid, sid, eval=INFO) == "started"
    assert user_counters(repo, uid, DATE)[0] == 1
    assert repo.release_run_slot(uid, sid, "r1", True, DATE)
    # no usage was charged, so the refund of an uncounted run changes nothing
    assert user_counters(repo, uid, DATE) == (0, 0)
    assert repo.get_run(uid, sid, "r1").eval == INFO


def test_eval_start_still_refuses_a_sha_mismatch(repo):
    uid, sid = ready(repo, "report_ready")
    assert start(repo, uid, sid, "r1", eval=INFO) == "started"
    repo.release_run_slot(uid, sid, "r1", False, DATE)
    repo.update_session(uid, sid, {"state": "report_ready"}, status={"state": "report_ready"})
    repo.update_run(uid, sid, "r1", {"transcript_sha256": "different"})
    assert start(repo, uid, sid, "r2", eval=INFO) == "not_ready"
