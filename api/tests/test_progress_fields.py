"""05-processing-screen Task 3: the progress fields on the status doc and the detail route."""

from datetime import UTC, datetime, timedelta

import pytest

from onolys_api import progress as p
from onolys_api.jobs import machine as m
from onolys_api.repo.fake import FakeRepo
from onolys_api.repo.models import SessionDoc, SessionError, SessionStatusDoc
from onolys_api.storage.fake import FakeBlobStore

UID, SID = "u1", "s1"
T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def repo(tmp_path):
    r = FakeRepo(FakeBlobStore(tmp_path / "b"))
    r.create_session(UID, SID, SessionDoc(uid=UID), SessionStatusDoc(uid=UID))
    return r


@pytest.fixture
def clock(monkeypatch):
    """A controllable `utcnow` for `advance`."""
    now = [T0]
    monkeypatch.setattr(m, "utcnow", lambda: now[0])
    return now


def walk(repo, *states):
    for s in states:
        m.advance(repo, UID, SID, to=s, error=SessionError(code="x") if s == "failed" else None)


def st(repo):
    return repo.get_status(UID, SID)


# ---- expected duration ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "audio_s,want",
    [(0, 30), (10, 30), (50, 30), (100, 40), (2900, 600), (3000, 600), (10_000, 600), (None, 30)],
)
def test_transcription_expected_is_clamped(audio_s, want):
    assert p.stage_expected_s("transcribing", "transcribe", audio_s) == want


def test_expected_for_other_states_comes_from_the_one_table():
    assert p.stage_expected_s("running", "tips", 99) == p.STAGE_EXPECTED_S["tips"]
    assert p.stage_expected_s("running", None, None) == p.STAGE_EXPECTED_S["code"]
    assert p.stage_expected_s("awaiting_input", None, None) is None
    assert p.stage_expected_s("report_ready", None, None) is None


def test_the_weights_and_progress_table_are_unchanged():
    assert m.STATE_PROGRESS == {
        "created": 0, "uploading": 5, "validating": 10, "transcribing": 20,
        "awaiting_input": 40, "running": 45, "report_ready": 100,
    }  # fmt: skip
    assert m.STAGE_WEIGHTS == {"code": 40, "tips": 8, "assemble": 3}


# ---- progress_next ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state,step,want",
    [
        ("created", None, 5), ("uploading", None, 10), ("validating", "validate", 20),
        ("transcribing", "transcribe", 40), ("awaiting_input", None, 45),
        ("running", None, 85), ("running", "code", 85), ("running", "tips", 93),
        ("running", "assemble", 99),  # the last stage caps at 99, not 96
        ("report_ready", None, None), ("failed", None, None), ("cancelled", None, None),
    ],
)  # fmt: skip
def test_progress_next_per_state_and_stage(state, step, want):
    assert p.progress_next(state, step) == want


def test_advance_writes_progress_next_and_expected(repo):
    walk(repo, "uploading")
    s = st(repo)
    assert (s.progress_next, s.stage_expected_s) == (10, p.STAGE_EXPECTED_S["uploading"])
    walk(repo, "validating", "transcribing")
    assert st(repo).progress_next == 40
    walk(repo, "awaiting_input", "running")
    assert st(repo).progress_next == 85
    m.advance(repo, UID, SID, step="assemble")
    assert st(repo).progress_next == 99
    m.advance(repo, UID, SID, to="report_ready")
    s = st(repo)
    assert (s.progress_next, s.stage_expected_s) == (None, None)


def test_stage_done_moves_progress_next_to_the_next_stage(repo):
    walk(repo, "uploading", "validating", "transcribing", "awaiting_input", "running")
    m.advance(repo, UID, SID, step="code", stage_done="code")
    assert st(repo).progress_next == 93
    m.advance(repo, UID, SID, step="tips", stage_done="tips")
    assert st(repo).progress_next == 99


def test_transcribing_expected_uses_audio_s(repo):
    walk(repo, "uploading", "validating")
    repo.update_session(UID, SID, {}, status={"audio_s": 400.0})
    walk(repo, "transcribing")
    assert st(repo).stage_expected_s == 100  # 20 + 0.2 x 400


# ---- started_at / stage_started_at / waited_ms ------------------------------------------------


def test_started_at_is_the_first_upload_only(repo, clock):
    assert st(repo).started_at is None
    walk(repo, "uploading")
    assert st(repo).started_at == T0
    clock[0] = T0 + timedelta(seconds=30)
    walk(repo, "uploading")  # a fresh signed URL
    s = st(repo)
    assert s.started_at == T0 and s.stage_started_at == T0 + timedelta(seconds=30)
    assert repo.get_session(UID, SID).stage_started_at == s.stage_started_at  # one value, mirrored


def test_rerun_restarts_started_at_and_waited_ms(repo, clock):
    walk(repo, "uploading", "validating", "transcribing", "awaiting_input")
    clock[0] = T0 + timedelta(seconds=10)
    walk(repo, "running")
    assert st(repo).waited_ms == 10_000
    clock[0] = T0 + timedelta(seconds=100)
    walk(repo, "report_ready")
    clock[0] = T0 + timedelta(seconds=200)
    walk(repo, "running")  # re-run
    s = st(repo)
    assert s.started_at == clock[0] and s.waited_ms == 0
    assert s.stage_started_at == clock[0]


def test_retry_of_a_failed_run_keeps_started_at(repo, clock):
    walk(repo, "uploading", "validating", "transcribing", "awaiting_input", "running", "failed")
    clock[0] = T0 + timedelta(seconds=50)
    walk(repo, "running")
    assert st(repo).started_at == T0


def test_waited_ms_accumulates_only_while_awaiting_input(repo, clock):
    walk(repo, "uploading", "validating", "transcribing")
    clock[0] = T0 + timedelta(seconds=60)  # time in transcribing is not waiting
    walk(repo, "awaiting_input")
    assert st(repo).waited_ms == 0
    clock[0] = T0 + timedelta(seconds=60 + 90)
    walk(repo, "running")
    assert st(repo).waited_ms == 90_000
    clock[0] = T0 + timedelta(seconds=1000)
    walk(repo, "report_ready")
    assert st(repo).waited_ms == 90_000


def test_repo_transaction_start_updates_the_same_fields(repo, clock):
    """`start_first_run` bypasses `advance`: it must leave `awaiting_input` the same way."""
    from onolys_api.repo.base import LimitDefaults

    walk(repo, "uploading", "validating", "transcribing", "awaiting_input")
    repo.update_session(
        UID, SID,
        {"transcript_ready": True, "speaker_confirmed": True, "rating_submitted": True},
    )  # fmt: skip
    wait_start = repo.get_session(UID, SID).stage_started_at
    out = repo.start_first_run(
        UID,
        SID,
        "r1",
        "2026-01-01",
        LimitDefaults(eval_day=50, interview_day=5),
        5,
        "v",
        m.RUN_START_PROGRESS,
    )
    assert out == "started"
    s = st(repo)
    assert s.waited_ms >= 0 and s.stage_started_at > wait_start - timedelta(seconds=1)
    assert (s.progress_next, s.stage_expected_s) == (85, p.STAGE_EXPECTED_S["code"])
    assert s.started_at == T0


def test_cancel_clears_the_stage_numbers(repo):
    from onolys_api.repo.base import LimitDefaults

    walk(repo, "uploading")
    repo.cancel_session(UID, SID, "2026-01-01", LimitDefaults(eval_day=50, interview_day=5))
    s = st(repo)
    assert s.state == "cancelled" and (s.progress_next, s.stage_expected_s) == (None, None)
    assert s.stage_started_at is not None
