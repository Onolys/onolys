"""T04: session state atomicity (M-10, M-11, M-4, N1, LM-2). Deterministic: events between the
read and the commit; `FakeRepo`'s lock stands in for the Firestore transaction."""

import threading
import uuid
from datetime import UTC, datetime

import pytest

from onolys_api.errors import ApiError
from onolys_api.jobs import caps
from onolys_api.jobs import machine as m
from onolys_api.repo.base import NotFoundError
from onolys_api.repo.fake import FakeRepo
from onolys_api.repo.limits import LimitDefaults
from onolys_api.repo.models import (
    InterviewDoc,
    RatingDraftDoc,
    ReportDoc,
    RunDoc,
    SessionDoc,
    SessionStatusDoc,
)
from onolys_api.storage.fake import FakeBlobStore

pytestmark = pytest.mark.unit
UID, SID = "u1", "s1"
D = LimitDefaults(eval_day=10, interview_day=5)


@pytest.fixture
def repo(tmp_path):
    return FakeRepo(FakeBlobStore(tmp_path / "b"))


def make(repo, state="running", sid=SID, **fields):
    repo.create_session(
        UID, sid, SessionDoc(uid=UID, state=state, **fields),
        SessionStatusDoc(uid=UID, state=state, progress=45),
    )  # fmt: skip
    return sid


# ---- M-10: advance is one transaction ----


def test_advance_does_not_overwrite_a_cancel_that_lands_after_its_check(repo, monkeypatch):
    make(repo)
    checked, outcome, result = threading.Event(), {}, {}
    real_check = m.check_transition

    def check_then_let_the_cancel_race(current, to):
        real_check(current, to)
        checked.set()  # the check passed on `running`: now a cancel tries to get in
        threading.Event().wait(0.05)  # inside the transaction the cancel must wait for us

    monkeypatch.setattr(m, "check_transition", check_then_let_the_cancel_race)

    def cancel():
        assert checked.wait(5)
        outcome["cancel"] = repo.cancel_session(UID, SID, caps.utc_date(), D)

    t = threading.Thread(target=cancel)
    t.start()
    try:
        m.advance(repo, UID, SID, to="report_ready", step=None)
        result["advance"] = "ok"
    except ApiError as e:
        result["advance"] = e.status
    t.join(5)
    state = repo.get_session(UID, SID).state
    if outcome["cancel"][0] == "cancelled":  # the cancel won: nothing may overwrite it
        assert state == "cancelled" and result["advance"] == 409
    else:  # the advance won: the cancel must have been refused
        assert state == "report_ready" and result["advance"] == "ok"
    assert repo.get_status(UID, SID).state == state


@pytest.mark.parametrize("state", ["cancelled", "deleting"])
def test_a_change_without_a_state_move_is_refused_on_a_terminal_session(repo, state):
    make(repo, state=state)
    with pytest.raises((ApiError, NotFoundError)):
        m.advance(repo, UID, SID, step="run")
    assert repo.get_session(UID, SID).step is None


def test_marking_deleting_twice_is_a_noop(repo):
    make(repo)
    m.advance(repo, UID, SID, to="deleting")
    m.advance(repo, UID, SID, to="deleting")
    assert repo.get_session(UID, SID).state == "deleting"


def test_delete_mark_after_cancel_is_allowed(repo):
    make(repo)
    repo.cancel_session(UID, SID, caps.utc_date(), D)
    m.advance(repo, UID, SID, to="deleting")
    assert repo.get_status(UID, SID).state == "deleting"


# ---- M-11: publish_report ----


def run_doc(repo, run_id="r1"):
    repo.create_run(
        UID,
        SID,
        run_id,
        RunDoc(
            change_goal="",
            clinician_speaker="S1",
            language="en",
            transcript_sha256="test-hash",
            uid=UID,
            run_id=run_id,
            session_id=SID,
            cap_date="2026-11-20",
        ),
    )


def publish(repo, run_id="r1", report=None):
    return repo.publish_report(
        UID, SID, run_id, ReportDoc(version=0, run_id=run_id, report=report or {"k": 1}),
        {"stage": None, "run_info": {"a": 1}},
        lambda v: m.transition_plan(to="report_ready", step=None, latest_report_version=v),
        None,
    )  # fmt: skip


def test_publish_is_one_unit_report_run_session_and_slot(repo):
    make(repo)
    run_doc(repo)
    doc = publish(repo)
    assert doc is not None and doc.version == 1
    assert [r.version for r in repo.list_reports(UID, SID)] == [1]
    s, st = repo.get_session(UID, SID), repo.get_status(UID, SID)
    assert (s.state, s.latest_report_version, st.progress) == ("report_ready", 1, 100)
    run = repo.get_run(UID, SID, "r1")
    assert run.released and run.run_info == {"a": 1}


def test_publish_after_a_cancel_stores_nothing(repo):
    make(repo)
    run_doc(repo)
    repo.cancel_session(UID, SID, caps.utc_date(), D)
    assert publish(repo) is None
    assert repo.list_reports(UID, SID) == []
    assert repo.get_session(UID, SID).state == "cancelled"


def test_publish_on_a_deleting_session_stores_nothing_and_drops_the_blob(repo):
    make(repo)
    run_doc(repo)
    m.advance(repo, UID, SID, to="deleting")
    with pytest.raises(NotFoundError):
        publish(repo, report={"big": "x" * 600_000})
    assert repo.list_reports(UID, SID) == []
    assert repo._blobs.list_keys(f"{UID}/{SID}/") == []


def test_publish_twice_keeps_the_first_report(repo):
    make(repo)
    run_doc(repo)
    first = publish(repo, report={"k": 1})
    again = publish(repo, report={"k": 2})
    assert first is not None and again is not None
    assert [r.report for r in repo.list_reports(UID, SID)] == [{"k": 1}]


# ---- M-4: discard unlinks the interview ----


def test_discard_unlinks_the_interview_so_it_can_link_again(repo):
    now = datetime.now(UTC)
    iid = uuid.uuid4().hex
    repo.create_interview(
        UID, iid,
        InterviewDoc(uid=UID, scenario_id="s", voice="v", state="uploaded", reservation_date="d",
                     session_id=SID, ended_at=now),
    )  # fmt: skip
    make(repo, state="validating", interview_id=iid)
    repo.discard_failed_upload(UID, SID, "audio_too_long")
    iv = repo.get_interview(UID, iid)
    assert (iv.state, iv.session_id) == ("ended", None)
    out = repo.create_session_for_interview(
        UID, iid, "s2", SessionDoc(uid=UID, interview_id=iid), SessionStatusDoc(uid=UID),
        RatingDraftDoc(card={}, updated_at=now),
    )  # fmt: skip
    assert out == "linked"


# ---- LM-2 / N1: check + write are one transaction ----


def test_a_second_transcript_put_loses_the_created_check(repo):
    make(repo, state="created")
    plan = m.transition_plan(to="awaiting_input", step=None, only_from=("created",))
    repo.transition_session(UID, SID, plan, children=(("transcripts/current", {"n": 1}, False),))
    with pytest.raises(ApiError) as e:
        repo.transition_session(
            UID, SID, plan, children=(("transcripts/current", {"n": 2}, False),)
        )
    assert e.value.status == 409
    assert repo._get(f"sessions/{SID}/transcripts/current") == {"n": 1}
