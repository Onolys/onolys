"""Cancel logging. Real stderr JSON lines, ids from the engine context."""

import pytest
from starlette.testclient import TestClient
from test_cancel_route import _hdr, _uid, mk
from test_cancel_session import SEVEN
from test_first_run import new_session, repo  # noqa: F401  (fixture)
from test_logging_e2e import stderr_lines  # noqa: F401  (fixture)
from test_worker import payload, runner_with
from test_worker import repo as worker_repo  # noqa: F401  (fixture)

from onolys_api.jobs.worker import Cancelled
from onolys_api.logs import API_FIELDS

pytestmark = pytest.mark.unit
CONTENT = {"transcript", "text", "message_text", "email", "uid", "token", "error"}


def _events(lines, *names):
    return [d for d in lines if d.get("event") in names or d.get("message") in names]


def test_from_state_and_counted_are_allowed_fields():
    assert {"from_state", "counted"} <= API_FIELDS


@pytest.mark.parametrize("state,counted", [("validating", False), ("transcribing", True)])
def test_cancel_logs_requested_and_cancelled_with_session_id(repo, stderr_lines, state, counted):  # noqa: F811
    assert state in SEVEN
    uid = _uid()
    sid = new_session(repo, uid, state=state)
    if state == "transcribing":
        repo.update_session(uid, sid, {"steps": {"transcribe": {"stt_operation": "op1"}}})
    with TestClient(mk(repo)) as c:
        r = c.post(f"/v1/sessions/{sid}/cancel", headers=_hdr(uid))
    assert r.status_code == 200 and r.json() == {"counted": counted}
    out = stderr_lines()
    (req,) = _events(out, "session_cancel_requested")
    (done,) = _events(out, "session_cancelled")
    assert req["session_id"] == sid and req["from_state"] == state
    assert done["session_id"] == sid and done["from_state"] == state
    assert done["counted"] is counted
    assert req["request_id"] == done["request_id"]
    for d in (req, done):
        assert not CONTENT & d.keys(), d
    assert not _events(out, "session_cancel_failed")


def test_repeat_cancel_logs_requested_but_cancelled_only_once(repo, stderr_lines):  # noqa: F811
    uid = _uid()
    sid = new_session(repo, uid, state="validating")
    with TestClient(mk(repo)) as c:
        for _ in range(2):
            assert c.post(f"/v1/sessions/{sid}/cancel", headers=_hdr(uid)).status_code == 200
    out = stderr_lines()
    assert len(_events(out, "session_cancel_requested")) == 2
    assert len(_events(out, "session_cancelled")) == 1


def test_forced_txn_failure_logs_class_name_only(repo, stderr_lines, monkeypatch):  # noqa: F811
    uid = _uid()
    sid = new_session(repo, uid, state="validating")

    def boom(*a, **k):
        raise RuntimeError("SECRET-CONTENT-9921 transcript text")

    monkeypatch.setattr(repo, "cancel_session", boom)
    with TestClient(mk(repo), raise_server_exceptions=False) as c:
        r = c.post(f"/v1/sessions/{sid}/cancel", headers=_hdr(uid))
    assert r.status_code == 500
    out = stderr_lines()
    (failed,) = _events(out, "session_cancel_failed")
    assert failed["session_id"] == sid and failed["exc_class"] == "RuntimeError"
    assert failed["severity"] == "ERROR"
    assert "SECRET-CONTENT-9921" not in str(out)
    assert not _events(out, "session_cancelled")


def test_worker_abort_logs_task_cancelled_with_step(worker_repo, stderr_lines):  # noqa: F811
    repo = worker_repo  # noqa: F811
    repo.cancel_session("u1", "s1", "2026-11-24", _defaults())
    stderr_lines()  # drop the cancel's own lines

    def abort(ctx):
        raise Cancelled()

    res = runner_with(repo, abort).handle(payload())
    assert (res.status_code, res.outcome) == (200, "cancelled")
    (line,) = _events(stderr_lines(), "task_cancelled")
    assert line["session_id"] == "s1" and line["step"] == "validate"
    assert line["request_id"] == "req-1"
    assert not CONTENT & line.keys()


def _defaults():
    from onolys_api.repo.limits import LimitDefaults

    return LimitDefaults(eval_day=10, interview_day=5)
