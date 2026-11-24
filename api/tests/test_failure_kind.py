"""03-failure-policy Task 2 (R3, D2, D4): `kind` is persisted once, from `KIND_BY_CODE`, at every
failure write site; the status doc exposes `error_kind`, `retries_left`, `counted`; old failed docs
without a `kind` read as derived from the code; `BAD_FILE_CODES`/`is_system_failure` are gone.
Runs on FakeRepo, and on the Firestore emulator when FIRESTORE_EMULATOR_HOST is set."""

import re
import subprocess
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from test_first_run import RecordingQueue, make_client, mk_settings, new_session, set_flags
from test_repo_contract import T_OLD, blobs, repo, seed_state  # noqa: F401, F811  (fixtures)
from test_start_run import READY
from test_worker import SID, UID, payload, runner_with
from test_worker import repo as worker_repo  # noqa: F401  (fixture)

from onolys_api.adapters.error_map import KIND_BY_CODE, UPLOAD_FAILURE_CODES, kind_for_code
from onolys_api.config import MAX_SESSION_RETRIES, Settings
from onolys_api.jobs import machine as m
from onolys_api.jobs.stale import settle_if_stale
from onolys_api.jobs.worker import PermanentError, RetryableError
from onolys_api.repo.models import SessionError, SessionStatusDoc

pytestmark = pytest.mark.unit
SRC = Path(__file__).resolve().parents[1] / "src"
FILE_CHECK_CODES = (
    "audio_unreadable", "audio_too_large", "unsupported_audio", "audio_too_long",
    "interview_too_long",
)  # fmt: skip


def test_max_session_retries_default_is_3():
    assert MAX_SESSION_RETRIES == 3
    assert not hasattr(Settings(), "max_session_retries")  # one source: the constant, not an env


@pytest.mark.parametrize("code", FILE_CHECK_CODES)
def test_file_check_codes_are_upload_failures_not_session_kinds(code):
    assert code not in KIND_BY_CODE and code in UPLOAD_FAILURE_CODES
    assert kind_for_code(code) == "user_file"  # an old failed doc carrying it still derives


def test_kind_for_code_unknown_or_missing_is_permanent_internal():
    assert kind_for_code("who_knows") == "permanent_internal"
    assert kind_for_code(None) == "permanent_internal"
    assert kind_for_code("upstream_unavailable") == "transient"


def test_bad_file_codes_and_is_system_failure_are_gone():
    assert not hasattr(m, "BAD_FILE_CODES") and not hasattr(m, "is_system_failure")
    hits = [
        str(p) for p in SRC.rglob("*.py")
        if re.search(r"BAD_FILE_CODES|is_system_failure", p.read_text())
    ]  # fmt: skip
    assert hits == []


def test_status_fields_lists_the_new_fields():
    assert {"error_kind", "retries_left", "counted"} <= m.STATUS_FIELDS
    assert set(SessionStatusDoc.model_fields) - {"id"} == m.STATUS_FIELDS


# ---- write sites ----


def _fail_via_worker(repo, exc):
    def fn(ctx):
        raise exc

    runner_with(repo, fn).handle(payload(), retry_count=1)
    return repo.get_session(UID, SID), repo.get_status(UID, SID)


@pytest.mark.parametrize(
    "exc,code,kind",
    [
        (PermanentError("no_speech"), "no_speech", "user_file"),
        (PermanentError("audio_unreadable"), "audio_unreadable", "user_file"),
        (PermanentError("internal_error"), "internal_error", "permanent_internal"),
        (PermanentError("mystery_code"), "mystery_code", "permanent_internal"),
        (ValueError("boom"), "internal_error", "permanent_internal"),
    ],
)
def test_worker_fail_persists_kind(worker_repo, exc, code, kind):  # noqa: F811
    s, st = _fail_via_worker(worker_repo, exc)
    assert (s.error.code, s.error.kind) == (code, kind)
    assert (st.error_code, st.error_kind) == (code, kind)
    assert st.retries_left == 0 and st.counted is None


def test_worker_fail_transient_has_retries_left(worker_repo):  # noqa: F811
    def fn(ctx):
        raise RetryableError("upstream_unavailable")

    runner = runner_with(worker_repo, fn)
    runner.handle(payload(), retry_count=0)
    s = runner.handle(payload(), retry_count=1) and worker_repo.get_session(UID, SID)
    assert s.state == "failed", s.state
    st = worker_repo.get_status(UID, SID)
    assert (s.error.kind, st.error_kind) == ("transient", "transient")
    assert st.retries_left == MAX_SESSION_RETRIES == 3


def test_retries_left_counts_down_with_retry_count(worker_repo):  # noqa: F811
    worker_repo.update_session(UID, SID, {"retry_count": 2})
    s, st = _fail_via_worker(worker_repo, RetryableError("upstream_unavailable"))
    assert s.retry_count == 2 and st.retries_left == 1
    worker_repo.update_session(UID, SID, {"state": "validating", "retry_count": 5})
    m.advance(worker_repo, UID, SID, to="failed", step="validate",
              error=SessionError(code="upstream_unavailable", step="validate"))  # fmt: skip
    assert worker_repo.get_status(UID, SID).retries_left == 0  # never negative


def test_stale_write_site_persists_kind(repo):  # noqa: F811
    uid, sid = seed_state(repo, "transcribing", T_OLD)
    s = repo.get_session(uid, sid)
    done = settle_if_stale(repo, s, T_OLD + timedelta(days=1), mk_settings())
    st = repo.get_status(uid, sid)
    assert done.state == "failed" and done.error.code == "transcription_failed"
    assert (done.error.kind, st.error_kind) == ("user_file", "user_file")
    assert st.retries_left == 0
    uid, sid = seed_state(repo, "validating", T_OLD, step="validate")
    done = settle_if_stale(
        repo, repo.get_session(uid, sid), T_OLD + timedelta(days=1), mk_settings()
    )
    assert done.error.code == "internal_error"
    assert done.error.kind == repo.get_status(uid, sid).error_kind == "permanent_internal"


def test_fail_stale_session_mirrors_kind_to_status(repo):  # noqa: F811
    uid, sid = seed_state(repo, "transcribing", T_OLD)
    err = SessionError(code="upstream_unavailable", step="transcribe", kind="transient")
    assert repo.fail_stale_session(uid, sid, "transcribing", T_OLD + timedelta(minutes=30), err)
    s, st = repo.get_session(uid, sid), repo.get_status(uid, sid)
    assert s.error.kind == st.error_kind == "transient"
    assert st.retries_left == MAX_SESSION_RETRIES


async def test_compensate_write_site_persists_transient(repo):  # noqa: F811
    queue = RecordingQueue(fail=True)
    app = make_client(repo, mk_settings(max_active_runs=2), queue)
    uid = f"u{uuid.uuid4().hex[:10]}"
    sid = new_session(repo, uid, state="awaiting_input", ready=True, **READY)
    set_flags(repo, uid, sid, rating_submitted=True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            f"/v1/sessions/{sid}/runs", json={}, headers={"Authorization": f"Bearer test:{uid}"}
        )
    assert r.status_code == 503
    s, st = repo.get_session(uid, sid), repo.get_status(uid, sid)
    assert (s.state, s.error.code, s.error.kind) == ("failed", "upstream_unavailable", "transient")
    assert (st.error_kind, st.retries_left) == ("transient", MAX_SESSION_RETRIES)


# ---- reads of old docs ----


def test_old_failed_docs_without_kind_read_as_derived(repo):  # noqa: F811
    uid, sid = seed_state(repo, "transcribing", T_OLD)
    repo.update_session(
        uid, sid,
        {"state": "failed", "error": {"code": "no_speech", "step": "transcribe"}},
        status={"state": "failed", "error_code": "no_speech"},
    )  # fmt: skip
    s, st = repo.get_session(uid, sid), repo.get_status(uid, sid)
    assert s.error.kind == "user_file" and s.error.counted is None
    assert (st.error_kind, st.retries_left, st.counted) == ("user_file", 0, None)

    repo.update_session(
        uid, sid,
        {"error": {"code": "upstream_unavailable", "step": "run"}, "retry_count": 1},
        status={"error_code": "upstream_unavailable"},
    )  # fmt: skip
    st = repo.get_status(uid, sid)
    assert repo.get_session(uid, sid).error.kind == "transient"
    assert (st.error_kind, st.retries_left) == ("transient", MAX_SESSION_RETRIES)

    repo.update_session(
        uid, sid, {"error": {"code": "totally_new", "step": None}},
        status={"error_code": "totally_new"},
    )  # fmt: skip
    assert repo.get_status(uid, sid).error_kind == "permanent_internal"
    assert repo.get_session(uid, sid).error.kind == "permanent_internal"


def test_non_failed_status_has_no_error_kind(repo):  # noqa: F811
    uid, sid = seed_state(repo, "transcribing", T_OLD)
    st = repo.get_status(uid, sid)
    assert (st.error_kind, st.retries_left, st.counted) == (None, 0, None)
    assert repo.get_session(uid, sid).retry_count == 0


def test_advance_failed_then_clear_resets_status_error_fields(repo):  # noqa: F811
    uid, sid = seed_state(repo, "transcribing", T_OLD)
    m.advance(repo, uid, sid, to="failed", step="transcribe",
              error=SessionError(code="no_speech", step="transcribe", kind="user_file", counted=True))  # fmt: skip
    st = repo.get_status(uid, sid)
    assert (st.error_kind, st.counted) == ("user_file", True)
    m.advance(repo, uid, sid, to="running", step=None)
    st = repo.get_status(uid, sid)
    assert (st.error_code, st.error_kind, st.counted) == (None, None, None)
    assert st.retries_left == 0


def test_git_grep_clean():
    out = subprocess.run(
        ["grep", "-rnE", "BAD_FILE_CODES|is_system_failure", str(SRC)],
        capture_output=True, text=True,
    )  # fmt: skip
    assert out.returncode == 1, out.stdout
