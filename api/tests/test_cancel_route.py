"""04-cancel Task 4: `POST /sessions/{id}/cancel` (R2, R6, R7, D6) and 409 on `cancelled`.

Runs on FakeRepo (test_first_run helpers).
"""

import uuid

import pytest
from starlette.testclient import TestClient
from test_cancel_session import SEVEN
from test_first_run import (
    RecordingQueue,
    make_client,
    mk_settings,
    new_session,
    repo,  # noqa: F401  (fixture)
    user_counters,
)
from test_isolation import CARD
from test_start_run import READY

from onolys_api.jobs import caps

pytestmark = pytest.mark.unit


def _uid() -> str:
    return f"u{uuid.uuid4().hex[:10]}"


def _hdr(uid: str) -> dict[str, str]:
    return {"Authorization": f"Bearer test:{uid}"}


def mk(repo, **kw):  # noqa: F811
    return make_client(repo, mk_settings(**kw), RecordingQueue())


def cancel(app, uid, sid):
    with TestClient(app) as c:
        return c.post(f"/v1/sessions/{sid}/cancel", headers=_hdr(uid))


@pytest.mark.parametrize("state", SEVEN)
def test_seven_states_cancel_200(repo, state):  # noqa: F811
    uid = _uid()
    sid = new_session(repo, uid, state=state, ready=state in ("awaiting_input", "running"))
    app = mk(repo)
    r = cancel(app, uid, sid)
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["counted"], bool)
    assert repo.get_session(uid, sid).state == "cancelled"
    with TestClient(app) as c:
        d = c.get(f"/v1/sessions/{sid}", headers=_hdr(uid)).json()
        lst = c.get("/v1/sessions", headers=_hdr(uid)).json()["items"][0]
    assert d["status"] == "cancelled"
    assert d["cancel"]["counted"] == r.json()["counted"]
    assert d["counted"] == r.json()["counted"]
    assert lst["status"] == "cancelled" and lst["counted"] == r.json()["counted"]


@pytest.mark.parametrize("state", ["report_ready", "failed"])
def test_finished_409(repo, state):  # noqa: F811
    uid = _uid()
    sid = new_session(repo, uid, state=state, ready=True)
    r = cancel(mk(repo), uid, sid)
    assert r.status_code == 409 and r.json()["details"][0]["code"] == "invalid_state"


def test_deleting_foreign_unknown_404(repo):  # noqa: F811
    uid = _uid()
    sid = new_session(repo, uid, state="deleting")
    app = mk(repo)
    assert cancel(app, uid, sid).status_code == 404
    live = new_session(repo, uid, state="created")
    assert cancel(app, _uid(), live).status_code == 404
    assert cancel(app, uid, "f" * 32).status_code == 404
    assert repo.get_session(uid, live).state == "created"


def test_second_cancel_same_counted_usage_unchanged(repo):  # noqa: F811
    uid = _uid()
    sid = new_session(repo, uid, state="awaiting_input", ready=True)
    app = mk(repo)
    first = cancel(app, uid, sid)
    used = user_counters(repo, uid, caps.utc_date())
    second = cancel(app, uid, sid)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"counted": True}
    assert user_counters(repo, uid, caps.utc_date()) == used
    assert used[1] == 1


def test_cancel_at_cap_succeeds(repo):  # noqa: F811
    uid = _uid()
    app = mk(repo, eval_cap_day=1)
    for _ in range(2):  # the second one is over the cap and still succeeds
        sid = new_session(repo, uid, state="awaiting_input", ready=True)
        r = cancel(app, uid, sid)
        assert r.status_code == 200 and r.json() == {"counted": True}
    assert user_counters(repo, uid, caps.utc_date())[1] == 2


def test_cancel_does_not_settle_stale(repo, monkeypatch):  # noqa: F811
    import onolys_api.routes.sessions as mod

    def boom(*a, **k):
        raise AssertionError("settle_if_stale must not run on cancel")

    monkeypatch.setattr(mod, "settle_if_stale", boom)
    uid = _uid()
    sid = new_session(repo, uid, state="validating")
    assert cancel(mk(repo), uid, sid).status_code == 200


def test_writes_409_on_cancelled_reads_work(repo):  # noqa: F811
    uid = _uid()
    sid = new_session(repo, uid, state="awaiting_input", ready=True, **READY)
    app = mk(repo)
    assert cancel(app, uid, sid).status_code == 200
    h = _hdr(uid)
    with TestClient(app) as c:
        calls = [
            c.put(f"/v1/sessions/{sid}/rating", json={"final": True, "card": CARD}, headers=h),
            c.put(f"/v1/sessions/{sid}/rating", json={"final": False, "card": CARD}, headers=h),
            c.post(
                f"/v1/sessions/{sid}/speakers/confirm", json={"clinician_speaker": "S1"}, headers=h
            ),
            c.post(f"/v1/sessions/{sid}/runs", json={}, headers=h),
            c.post(
                f"/v1/sessions/{sid}/audio",
                json={"content_type": "audio/wav", "size_bytes": 100},
                headers=h,
            ),
            c.post(f"/v1/sessions/{sid}/audio/complete", headers=h),
            c.post(f"/v1/sessions/{sid}/retry", headers=h),
        ]
        for r in calls:
            assert r.status_code == 409, (r.request.url, r.text)
            assert r.json()["details"][0]["code"] == "invalid_state"
        assert c.get(f"/v1/sessions/{sid}/transcript", headers=h).status_code == 200
        assert c.get(f"/v1/sessions/{sid}/reports", headers=h).status_code == 200
        assert c.get(f"/v1/sessions/{sid}/rating", headers=h).status_code == 200
