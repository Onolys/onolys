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


@pytest.mark.parametrize("guard_state", ["current", "cancelled", "stale", "terminal", "missing"])
def test_scheduler_guard_is_checked_in_start_transaction(repo, guard_state):
    uid, sid = ready(repo, "report_ready")
    group_id = uuid.uuid4().hex
    info = INFO.model_copy(update={"eval_run_id": group_id})
    group = {"tick_owner": "current", "status": "running", "cancel_requested": False}
    if guard_state == "cancelled":
        group["cancel_requested"] = True
    elif guard_state == "stale":
        group["tick_owner"] = "replacement"
    elif guard_state == "terminal":
        group["status"] = "cancelled"
    if guard_state != "missing":
        if hasattr(repo, "_put"):
            repo._put(f"eval_runs/{group_id}", group)
        else:
            repo._top("eval_runs", group_id).set(group)
    try:
        outcome = start(repo, uid, sid, eval=info, eval_guard="current")
        assert outcome == ("started" if guard_state == "current" else "not_ready")
        assert repo.get_session(uid, sid).state == (
            "running" if guard_state == "current" else "report_ready"
        )
        assert len(repo.list_runs(uid, sid)) == int(guard_state == "current")
        assert user_counters(repo, uid, DATE) == (int(guard_state == "current"), 0)
    finally:
        if not hasattr(repo, "_put"):
            repo._top("eval_runs", group_id).delete()


def test_firestore_scheduler_guard_reads_group_in_run_transaction(monkeypatch):
    """No emulator: assert the real Firestore adapter uses the RunDoc transaction for its gate."""
    from unittest.mock import Mock

    from google.cloud import firestore

    from onolys_api.repo.firestore import FirestoreRepo

    repo = FirestoreRepo(Mock(), Mock())
    session_ref, group_ref, transaction = Mock(), Mock(), Mock()
    group_ref.get.return_value.to_dict.return_value = {
        "tick_owner": "owner", "status": "running", "cancel_requested": True,
    }
    monkeypatch.setattr(firestore, "transactional", lambda fn: fn)
    monkeypatch.setattr(repo, "_session_ref", lambda *a: session_ref)
    monkeypatch.setattr(repo, "_top", lambda name, key: group_ref if name == "eval_runs" else Mock())
    monkeypatch.setattr(repo, "_contended", lambda fn, uid: fn(transaction))
    assert start(repo, "u", "s", eval=INFO, eval_guard="owner") == "not_ready"
    group_ref.get.assert_called_once_with(transaction=transaction)
    session_ref.get.assert_not_called()
    transaction.create.assert_not_called()


@pytest.mark.parametrize("backend", ["fake", "firestore_transaction"])
@pytest.mark.parametrize("change", [None, "transcript", "speaker", "goal", "language", "span", "pin", "prod", "first_hash"])
def test_imported_eval_pin_survives_first_run_deletion_and_rejects_input_changes(
    monkeypatch, backend, change,
):
    """Exercise the actual Firestore start transaction offline as well as the fake."""
    import hashlib
    import json
    from unittest.mock import Mock

    from google.cloud import firestore

    from onolys_api.repo.fake import FakeRepo
    from onolys_api.repo.firestore import FirestoreRepo
    from onolys_api.storage.fake import FakeBlobStore

    fake = FakeRepo(FakeBlobStore())
    uid, sid = ready(fake, "report_ready")
    session_path = f"sessions/{sid}"
    transcript_path = f"{session_path}/transcripts/current"
    session = fake._get(session_path)
    transcript = fake._get(transcript_path)
    payload = {
        "transcript_sha256": transcript["sha256"], "language": transcript["language"],
        "clinician_speaker": session["clinician_speaker"],
        "change_goal": session["change_goal"] or "", "coded_span": session["coded_span"],
    }
    pin = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    session.update(first_run_id="deleted", eval={
        "dataset_session_id": "one", "source": "dataset", "input_sha256": pin,
    })
    group_path = "eval_runs/e1"
    fake._put(group_path, {"tick_owner": "owner", "status": "running"})
    if change == "transcript":
        transcript["sha256"] = "replaced"
    elif change == "speaker":
        session["clinician_speaker"] = "S2"
    elif change == "goal":
        session["change_goal"] = "other goal"
    elif change == "language":
        transcript["language"] = "fr"
    elif change == "span":
        session["coded_span"] = {"start_turn": 0, "end_turn": 1}
    elif change == "pin":
        session["eval"].pop("input_sha256")
    elif change == "first_hash":
        fake._put(f"{session_path}/runs/deleted", {"transcript_sha256": "different"})
    fake._put(session_path, session)
    fake._put(transcript_path, transcript)
    if backend == "fake":
        target, transaction, refs = fake, None, {}
    else:
        target = FirestoreRepo(Mock(), Mock())
        transaction, refs = Mock(), {}

        def ref(path):
            if path not in refs:
                doc = refs[path] = Mock()
                doc.get.return_value.exists = path in fake._docs
                doc.get.return_value.to_dict.return_value = fake._get(path)
                doc.collection.side_effect = lambda name: collection(f"{path}/{name}")
            return refs[path]

        def collection(path):
            col = Mock()
            col.document.side_effect = lambda key: ref(f"{path}/{key}")
            col.order_by.return_value.limit.return_value.get.return_value = []
            return col

        monkeypatch.setattr(firestore, "transactional", lambda fn: fn)
        monkeypatch.setattr(target, "_session_ref", lambda *_: ref(session_path))
        monkeypatch.setattr(target, "_top", lambda name, key: ref(f"{name}/{key}"))
        monkeypatch.setattr(target, "_contended", lambda fn, _: fn(transaction))
    kwargs = {} if change == "prod" else {"eval": INFO, "eval_guard": "owner"}
    assert start(target, uid, sid, states=("report_ready",), **kwargs) == (
        "started" if change is None else "not_ready"
    )
    if transaction is not None:
        for path in (session_path, transcript_path):
            refs[path].get.assert_called_once_with(transaction=transaction)
        if change != "prod":
            refs[group_path].get.assert_called_once_with(transaction=transaction)
        assert transaction.create.call_count == int(change is None)
        if change is not None:
            transaction.update.assert_not_called()
            transaction.set.assert_not_called()
    else:
        assert (fake._get(f"{session_path}/runs/r1") is not None) == (change is None)
