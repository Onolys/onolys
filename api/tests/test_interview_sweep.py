"""SP10 Task 6: delayed `interview-sweep` task and the single refund routine (R5, D11, D12, AC6)."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from test_interviews import SCENARIO, A, SpyRepo

from onolys_api.app import create_app
from onolys_api.config import Settings
from onolys_api.jobs.interview_sweep import enqueue_sweep, hard_ceiling_s, sweep_delay_s
from onolys_api.jobs.queue import InMemoryQueue
from onolys_api.storage.fake import FakeBlobStore

pytestmark = pytest.mark.unit
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


class RecordingQueue(InMemoryQueue):
    def __init__(self):
        super().__init__()
        self.delays: list[float] = []

    def enqueue(self, payload, delay_s=0.0):
        self.delays.append(delay_s)
        super().enqueue(payload, delay_s)


@pytest.fixture
def repo(tmp_path):
    return SpyRepo(FakeBlobStore(tmp_path / "b"))


@pytest.fixture
def app(tmp_path, repo):
    a = create_app(
        Settings(
            env="test", auth_mode="fake", service_mode="combined", ai_cap_day=5, ai_cap_month=10,
            voice_url="wss://voice.example",
        ),
        repo=repo,
        blobs=FakeBlobStore(tmp_path / "b2"),
    )  # fmt: skip
    a.state.now = [NOW]
    a.state.clock = lambda: a.state.now[0]
    a.state.queue = RecordingQueue()
    a.state.runner.queue = a.state.queue
    a.state.queue.bind(lambda p, retry: a.state.runner.handle(p, retry).status_code)
    return a


@pytest.fixture
async def api(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as c:
        yield c


async def create(api):
    r = await api.post("/v1/interviews", headers=A, json={"scenario_id": SCENARIO})
    assert r.status_code == 201
    return r.json()["interview_id"]


def releases(repo):
    return [c[-1] for c in repo.calls if c[0] == "release"]


async def test_create_enqueues_one_sweep_at_max_plus_reconnect_plus_60(api, app):
    iid = await create(api)
    q = app.state.queue
    assert q.delays == [600 + 60 + 60] == [sweep_delay_s(app.state.settings)]
    assert [(p.kind, p.uid, p.sid) for p in q.pending] == [("interview-sweep", "alice", iid)]


async def test_sweep_abandons_stuck_interview_and_refunds_when_short(api, app, repo):
    iid = await create(api)
    repo.update_interview("alice", iid, {"state": "live", "duration_s": 20})
    app.state.queue.drain()
    assert repo.get_interview("alice", iid).state == "abandoned"
    assert releases(repo) == [True]
    assert repo.get_usage_docs("alice", "2026-11-21")[0].interviews == 0


async def _setup_live(api, app, repo, at_s, **fields):
    """A `live` interview whose sweep fires `at_s` seconds after create."""
    iid = await create(api)
    repo.update_interview("alice", iid, {"state": "live", "duration_s": 200.0, **fields})
    app.state.now[0] = NOW + timedelta(seconds=at_s)
    app.state.queue.pending.clear()
    return iid


async def test_sweep_rechecks_a_connected_interview_with_a_fresh_checkpoint(api, app, repo):
    iid = await _setup_live(api, app, repo, 720, seen_at=NOW + timedelta(seconds=700))
    from onolys_api.jobs.queue import TaskPayload

    sweep = TaskPayload(kind="interview-sweep", uid="alice", sid=iid)
    assert app.state.runner.handle(sweep).status_code == 200
    assert repo.get_interview("alice", iid).state == "live" and releases(repo) == []
    nxt = app.state.queue.pending
    assert [(p.kind, p.sid, p.n) for p in nxt] == [("interview-sweep", iid, 1)]
    assert app.state.queue.delays[-1] == 120


async def test_sweep_rechecks_a_disconnected_interview_inside_the_reconnect_window(api, app, repo):
    iid = await _setup_live(
        api, app, repo, 720, seen_at=NOW + timedelta(seconds=650),
        disconnected_at=NOW + timedelta(seconds=700),
    )  # fmt: skip
    from onolys_api.jobs.queue import TaskPayload

    app.state.runner.handle(TaskPayload(kind="interview-sweep", uid="alice", sid=iid))
    assert repo.get_interview("alice", iid).state == "live"
    assert len(app.state.queue.pending) == 1


async def test_sweep_abandons_a_live_interview_whose_checkpoint_went_stale(api, app, repo):
    iid = await _setup_live(api, app, repo, 720, seen_at=NOW + timedelta(seconds=300))
    from onolys_api.jobs.queue import TaskPayload

    app.state.runner.handle(TaskPayload(kind="interview-sweep", uid="alice", sid=iid))
    assert repo.get_interview("alice", iid).state == "abandoned"
    assert app.state.queue.pending == [] and releases(repo) == [False]


async def test_sweep_abandons_a_disconnected_interview_past_the_reconnect_window(api, app, repo):
    iid = await _setup_live(
        api, app, repo, 900, seen_at=NOW + timedelta(seconds=300),
        disconnected_at=NOW + timedelta(seconds=300),
    )  # fmt: skip
    from onolys_api.jobs.queue import TaskPayload

    app.state.runner.handle(TaskPayload(kind="interview-sweep", uid="alice", sid=iid))
    assert repo.get_interview("alice", iid).state == "abandoned"


async def test_sweep_rechecks_a_not_yet_connected_interview_then_abandons_at_the_ceiling(
    api, app, repo
):
    from onolys_api.jobs.queue import TaskPayload

    iid = await create(api)
    app.state.queue.pending.clear()
    app.state.now[0] = NOW + timedelta(seconds=720)
    app.state.runner.handle(TaskPayload(kind="interview-sweep", uid="alice", sid=iid))
    assert repo.get_interview("alice", iid).state == "created"
    assert len(app.state.queue.pending) == 1
    app.state.now[0] = NOW + timedelta(seconds=hard_ceiling_s(app.state.settings))
    app.state.runner.handle(TaskPayload(kind="interview-sweep", uid="alice", sid=iid, n=1))
    assert repo.get_interview("alice", iid).state == "abandoned"
    assert releases(repo) == [True]  # never connected: refundable


async def test_sweep_hard_ceiling_beats_a_fresh_checkpoint(api, app, repo):
    from onolys_api.jobs.queue import TaskPayload

    at = hard_ceiling_s(app.state.settings)
    iid = await _setup_live(api, app, repo, at, seen_at=NOW + timedelta(seconds=at - 5))
    app.state.runner.handle(TaskPayload(kind="interview-sweep", uid="alice", sid=iid, n=5))
    assert repo.get_interview("alice", iid).state == "abandoned"


async def test_sweep_keeps_the_unit_at_or_above_threshold(api, app, repo):
    iid = await create(api)
    repo.update_interview("alice", iid, {"state": "live", "duration_s": 30})
    app.state.queue.drain()
    assert repo.get_interview("alice", iid).state == "abandoned"
    assert releases(repo) == [False]
    assert repo.get_usage_docs("alice", "2026-11-21")[0].interviews == 1


async def test_sweep_is_idempotent_on_redelivery(api, app, repo):
    await create(api)
    payload = app.state.queue.pending[0]
    app.state.now[0] = NOW + timedelta(seconds=hard_ceiling_s(app.state.settings))
    for _ in range(3):
        assert app.state.runner.handle(payload).status_code == 200
    assert releases(repo) == [True]


async def test_sweep_is_a_noop_on_an_already_ended_interview(api, app, repo):
    iid = await create(api)
    repo.update_interview("alice", iid, {"duration_s": 300})
    await api.post(f"/v1/interviews/{iid}/end", headers=A)
    before = list(repo.calls)
    app.state.queue.drain()
    assert repo.get_interview("alice", iid).state == "ended"
    assert repo.calls == before  # no release, no write


async def test_sweep_of_a_deleted_or_missing_interview_is_2xx(api, app):
    await create(api)
    payload = app.state.queue.pending[0].model_copy(update={"sid": "nope"})
    res = app.state.runner.handle(payload)
    assert (res.status_code, res.outcome) == (200, "gone")


@pytest.mark.parametrize("path", ["end", "discard", "lazy", "sweep"])
@pytest.mark.parametrize("duration,refund", [(None, True), (29.9, True), (30, False), (400, False)])
async def test_refund_once_under_threshold_across_all_four_paths(
    api, app, repo, path, duration, refund
):
    iid = await create(api)
    if duration is not None:
        repo.update_interview("alice", iid, {"duration_s": duration})
    if path == "end":
        await api.post(f"/v1/interviews/{iid}/end", headers=A)
    elif path == "discard":
        await api.post(f"/v1/interviews/{iid}/end", headers=A, json={"discard": True})
    elif path == "lazy":
        await create(api)  # abandons the first
    elif path == "sweep":
        app.state.now[0] = NOW + timedelta(seconds=hard_ceiling_s(app.state.settings))
    for _ in range(2):  # the sweep (after any path) never refunds a second time
        res = app.state.runner.handle(app.state.queue.pending[0])
        assert res.status_code == 200
    first = [c for c in repo.calls if c[0] == "release"]
    assert [c[-1] for c in first] == [refund]


async def test_enqueue_failure_fails_create_with_refund_and_no_interview(api, app, repo):
    def boom(payload, delay_s=0.0):
        raise RuntimeError("queue down")

    app.state.queue.enqueue = boom
    r = await api.post("/v1/interviews", headers=A, json={"scenario_id": SCENARIO})
    assert r.status_code == 500
    assert [c[0] for c in repo.calls] == ["reserve", "release"] and releases(repo) == [True]
    assert repo.get_usage_docs("alice", "2026-11-21")[0].interviews == 0
    assert repo.list_open_interviews("alice") == []


def test_no_queue_configured_skips_scheduling(repo):
    enqueue_sweep(None, Settings(env="test"), "alice", "i1")  # must not raise
