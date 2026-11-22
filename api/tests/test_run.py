"""Task 12: the `run` task, progress, partial failure, versioned reports, `POST /runs`
(PRD R4 Run, R5, R6, R7, D2, D12, D17, D18, AC2, AC15, AC16). Stub flow over HTTP, in-memory queue.
"""

import json
import os
import time
import uuid
from dataclasses import replace

import httpx
import pytest
from audio_helpers import MAGIC, StubTools
from cards import valid_card

from onolys_api.adapters import AdapterError, Adapters, FakeEvaluation, FakeStt
from onolys_api.app import create_app
from onolys_api.jobs import caps
from onolys_api.jobs.run import release_once
from onolys_api.repo.fake import FakeRepo

pytestmark = pytest.mark.integration
CARD = valid_card()
ROUTES = (
    "cheap: &s {litellm_id: anthropic/x, api_key_env: K}\nmid: *s\nstrong: *s\n"
    "paudit_code: {alias: mid}\npaudit_globals: {alias: mid}\ntips: {alias: mid}\n"
    "presets:\n  default: {routes: {}}\n  fast: {routes: {}}\n"
)


def spy(repo):
    """Record every `session_status` progress/step write on any repo, in order."""
    repo.progress, repo.steps = [], []
    orig = repo.update_session

    def update_session(uid, sid, fields, status=None):
        if status and "progress" in status:
            repo.progress.append(status["progress"])
        if status and "step" in status:
            repo.steps.append(status["step"])
        orig(uid, sid, fields, status=status)

    repo.update_session = update_session
    return repo


class BigEval(FakeEvaluation):
    async def run(self, *a, **kw):
        out = await super().run(*a, **kw)
        out.report["method"]["limits"] = ["x" * 1000] * 700  # ~700 KB
        return out


class FlakyEval(FakeEvaluation):
    """First call raises a retryable provider error."""

    async def run(self, *a, **kw):
        if self.calls == 0:
            self.calls += 1
            raise AdapterError("upstream_unavailable")
        return await super().run(*a, **kw)


class Env:
    def __init__(self, app, client, repo, blobs, stt, evaluation) -> None:
        self.app, self.c, self.repo, self.blobs = app, client, repo, blobs
        self.stt, self.evaluation = stt, evaluation
        self.uid = f"u{uuid.uuid4().hex[:10]}"
        self.h = {"Authorization": f"Bearer test:{self.uid}"}
        self.hb = {"Authorization": f"Bearer test:{self.uid}-other"}

    @property
    def q(self):
        return self.app.state.queue

    def drain(self):
        self.q.drain()

    async def new_session(self, title=None, **body):
        uid_h = self.h
        r = await self.c.post("/v1/sessions", json={"title": title, **body}, headers=uid_h)
        sid = r.json()["session"]["id"]
        up = (
            await self.c.post(
                f"/v1/sessions/{sid}/audio",
                json={"content_type": "audio/wav", "size_bytes": len(MAGIC["wav"])},
                headers=uid_h,
            )
        ).json()
        put = await self.c.put(
            up["upload_url"].removeprefix("http://localhost:8000"),
            content=MAGIC["wav"],
            headers=up["required_headers"],
        )
        assert put.status_code == 200
        await self.c.post(f"/v1/sessions/{sid}/audio/complete", headers=uid_h)
        self.drain()
        return sid

    async def start(self, title=None, rate=True, **body):
        """Session through to a running first run (not yet drained)."""
        sid = await self.new_session(title, **body)
        await self.c.post(
            f"/v1/sessions/{sid}/speakers/confirm", json={"clinician_speaker": "S1"}, headers=self.h
        )
        if rate:
            await self.c.put(
                f"/v1/sessions/{sid}/rating", json={"final": True, "card": CARD}, headers=self.h
            )
        return sid

    async def finished(self, title=None, **kw):
        sid = await self.start(title, **kw)
        self.drain()
        return sid

    def counters(self):
        uid = self.uid
        u = self.repo.get_user(uid)
        return (u.active_runs if u else 0), self.repo.get_usage(uid, caps.utc_date()).runs


@pytest.fixture(params=["fake", "firestore"])
async def env(request, settings, blobs, tmp_path):
    routes = tmp_path / "routes.yaml"
    routes.write_text(ROUTES)
    (tmp_path / "stt_providers.yaml").write_text(
        "providers:\n  base: {provider: p1, model: m1}\ndefault: base\nby_language: {}\n"
    )
    if request.param == "fake":
        repo = FakeRepo(blobs)
    else:
        if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
            pytest.skip("FIRESTORE_EMULATOR_HOST not set")
        from google.auth.credentials import AnonymousCredentials
        from google.cloud import firestore

        from onolys_api.repo.firestore import FirestoreRepo

        repo = FirestoreRepo(
            firestore.Client(project="demo-onolys", credentials=AnonymousCredentials()), blobs
        )
    spy(repo)
    stt, ev = FakeStt(), FakeEvaluation()
    app = create_app(
        replace(settings, extra_presets=("fast",), routes_file=str(routes)),
        repo=repo,
        blobs=blobs,
        audio_tools=StubTools(),
        adapters=Adapters(stt=stt, evaluation=ev),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield Env(app, c, repo, blobs, stt, ev)


def swap_eval(env, evaluation):
    env.app.state.adapters = Adapters(stt=env.stt, evaluation=evaluation)  # read lazily by `run`


async def test_full_stub_flow_reaches_report_ready_with_progress_table(env):
    sid = await env.start()
    s = env.repo.get_session(env.uid, sid)
    assert s.state == "running"
    env.repo.progress.clear()
    env.repo.steps.clear()
    env.drain()

    s = env.repo.get_session(env.uid, sid)
    assert s.state == "report_ready" and s.latest_report_version == 1 and s.error is None
    st = env.repo.get_status(env.uid, sid)
    assert (st.state, st.progress, st.latest_report_version) == ("report_ready", 100, 1)
    p = env.repo.progress
    assert p == sorted(p), "progress never goes backwards"
    # fake order: paudit +25, eaudit +15, tips +8, compare +4, assemble +3 (capped at 99), done 100
    assert [45 + 25, 45 + 25 + 15, 45 + 25 + 15 + 8, 97, 99, 100] == [
        x for x in dict.fromkeys(p) if x >= 70
    ]
    assert {"paudit", "eaudit", "tips", "compare", "assemble"} <= set(env.repo.steps)

    (run,) = env.repo.list_runs(env.uid, sid)
    assert run.status == "done" and run.error is None
    assert (run.preset, run.code_version, run.stt.provider) == ("default", "abc123", "p1")
    assert run.rating_id and run.run_info
    assert run.artifacts_prefix
    for name in ("paudit", "eaudit", "tips"):
        assert env.blobs.exists(f"{env.uid}/{sid}/runs/{run.run_id}/{name}.json")
    assert env.counters() == (0, 1)  # released once, no refund (the LLM was called)

    r = await env.c.get(f"/v1/sessions/{sid}/reports/1", headers=env.h)
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 1 and body["run_id"] == run.run_id
    assert body["report_schema_version"] == body["report"]["schema_version"]
    assert body["report"]["header"]["preset"] == "default"
    assert body["report"]["header"]["code_version"] == "abc123"


async def test_a_ready_report_is_final_post_runs_is_refused(env):
    sid = await env.finished()
    v1 = (await env.c.get(f"/v1/sessions/{sid}/reports/1", headers=env.h)).json()
    r = await env.c.post(f"/v1/sessions/{sid}/runs", json={"preset": "fast"}, headers=env.h)
    assert r.status_code == 409 and r.json()["details"][0]["code"] == "rating_final"
    assert env.repo.get_session(env.uid, sid).state == "report_ready"
    assert (await env.c.get(f"/v1/sessions/{sid}/reports/1", headers=env.h)).json() == v1
    assert (await env.c.get(f"/v1/sessions/{sid}/reports/2", headers=env.h)).status_code == 404
    assert len(env.repo.list_runs(env.uid, sid)) == 1 and env.counters() == (0, 1)
    lst = (await env.c.get(f"/v1/sessions/{sid}/reports", headers=env.h)).json()
    assert [(x["version"], x["run_id"]) for x in lst["items"]] == [(1, v1["run_id"])]
    assert {"version", "report_id", "run_id", "created_at"} <= set(lst["items"][0])
    one = (await env.c.get(f"/v1/runs/{v1['run_id']}", headers=env.h)).json()
    assert (one["status"], one["n_runs"], one["code_version"]) == ("done", 1, "abc123")
    assert one["stt"]["provider"] == "p1" and one["rating_id"] and one["run_info"]


async def test_no_rating_run_has_skipped_reasons_audit(env):
    sid = await env.start(rate=False)
    assert env.repo.get_session(env.uid, sid).state == "awaiting_input"
    r = await env.c.post(f"/v1/sessions/{sid}/runs", json={}, headers=env.h)
    assert r.status_code == 202
    env.drain()
    rep = env.repo.get_report_by_version(env.uid, sid, 1).report
    assert rep["reasons_audit"]["status"] == "skipped"
    assert env.repo.get_run(env.uid, sid, r.json()["run_id"]).rating_id is None


async def test_paudit_failure_fails_run_and_session_and_refunds_the_system_failure(env):
    sid = await env.finished("[fail:paudit]")
    s = env.repo.get_session(env.uid, sid)
    assert s.state == "failed" and s.error.code and s.latest_report_version is None
    st = env.repo.get_status(env.uid, sid)
    assert st.state == "failed" and st.error_code == s.error.code and st.progress == 70
    (run,) = env.repo.list_runs(env.uid, sid)
    assert run.status == "failed" and run.error == s.error.code
    assert env.repo.list_reports(env.uid, sid) == []
    assert env.counters() == (0, 0)  # system failure after the LLM call: slot and unit refunded
    assert (await env.c.get(f"/v1/sessions/{sid}/reports/1", headers=env.h)).status_code == 404


async def test_try_again_after_a_failure_reuses_transcript_and_stored_rating(env):
    sid = await env.finished("[fail:paudit]")
    rating_id = env.repo.latest_rating(env.uid, sid).id

    # the stub title still says fail:paudit: swap in an evaluation that ignores it
    class Ok(FakeEvaluation):
        async def run(self, ctx, pack, transcript, speaker_map, params, rating, progress_cb=None):
            return await super().run(
                ctx,
                pack,
                transcript,
                speaker_map,
                {**params, "stub_title": ""},
                rating,
                progress_cb,
            )

    swap_eval(env, Ok())
    r = await env.c.post(f"/v1/sessions/{sid}/runs", json={"preset": "fast"}, headers=env.h)
    assert r.status_code == 202
    assert env.counters() == (1, 1)  # the retry takes a fresh unit
    assert env.repo.get_status(env.uid, sid).progress == 45  # a retry restarts at 45
    env.drain()
    assert env.repo.get_session(env.uid, sid).state == "report_ready"
    assert env.repo.get_session(env.uid, sid).latest_report_version == 1
    assert env.stt.start_calls == 1  # the transcript is reused, Stt not called again
    run = env.repo.get_run(env.uid, sid, r.json()["run_id"])
    assert run.rating_id == rating_id  # the same submission
    rep = env.repo.get_report_by_version(env.uid, sid, 1).report
    assert rep["header"]["preset"] == "fast"
    assert env.counters() == (0, 1)  # the failed run was refunded; only the retry is counted


async def test_eaudit_failure_ships_report_with_warning(env):
    sid = await env.finished("[fail:eaudit]")
    assert env.repo.get_session(env.uid, sid).state == "report_ready"
    rep = env.repo.get_report_by_version(env.uid, sid, 1).report
    assert rep["reasons_audit"]["status"] == "failed"
    assert {"code": "reasons_audit_failed"} in rep["warnings"]
    assert env.repo.get_status(env.uid, sid).progress == 100


async def test_tips_failure_ships_report_with_warning(env):
    sid = await env.finished("[fail:tips]")
    assert env.repo.get_session(env.uid, sid).state == "report_ready"
    rep = env.repo.get_report_by_version(env.uid, sid, 1).report
    assert rep["tips"] == [] and {"code": "tips_failed"} in rep["warnings"]


async def test_report_over_500kb_is_served_unchanged_from_gcs(env):
    swap_eval(env, BigEval())
    sid = await env.finished()
    doc = env.repo.get_report_by_version(env.uid, sid, 1, resolve=False)
    assert doc.pointer is not None and doc.report is None and doc.pointer.size_bytes > 500 * 1024
    assert env.blobs.exists(doc.pointer.key)
    served = (await env.c.get(f"/v1/sessions/{sid}/reports/1", headers=env.h)).json()["report"]
    assert served == json.loads(env.blobs.get_bytes(doc.pointer.key))
    assert len(served["method"]["limits"]) == 700


async def test_retried_run_reruns_everything_and_yields_one_report(env):
    flaky = FlakyEval()
    swap_eval(env, flaky)
    sid = await env.finished()
    assert flaky.calls == 2  # first attempt failed (retryable), the retry ran again
    assert len(env.repo.list_reports(env.uid, sid)) == 1
    (run,) = env.repo.list_runs(env.uid, sid)
    assert run.status == "done" and run.attempts == 2
    assert env.repo.get_session(env.uid, sid).state == "report_ready"
    assert env.counters() == (0, 1)


async def test_retryable_failure_on_last_attempt_fails_and_releases_once(env):
    class AlwaysDown(FakeEvaluation):
        async def run(self, *a, **kw):
            raise AdapterError("upstream_unavailable")

    swap_eval(env, AlwaysDown())
    sid = await env.finished()
    s = env.repo.get_session(env.uid, sid)
    assert s.state == "failed" and s.error.code == "upstream_unavailable"
    assert env.counters()[0] == 0


async def test_retry_within_the_task_refunds_once_never_twice(env):
    """Attempt 1 calls the evaluation and fails retryably; attempt 2 then dies before calling it.
    Both are system failures: the unit is refunded exactly once (A20, owner decision)."""

    class SpendThenBreak(FakeEvaluation):
        async def run(self, *a, **kw):
            env.repo.update_session(env.uid, sid, {"clinician_speaker": None})
            raise AdapterError("upstream_unavailable")

    swap_eval(env, SpendThenBreak())
    sid = await env.start()
    env.drain()
    s = env.repo.get_session(env.uid, sid)
    assert s.state == "failed" and s.error.code == "internal_error"
    (run,) = env.repo.list_runs(env.uid, sid)
    assert run.llm_started is True and run.released is True
    assert env.counters() == (0, 0)  # refunded once (a double refund would clamp or go negative)
    for _ in range(2):  # a redelivered release is a no-op
        release_once(env.repo, env.uid, sid, run.run_id, True, run.cap_date)
    assert env.counters() == (0, 0)


class Capture(FakeEvaluation):
    async def run(self, ctx, pack, transcript, speaker_map, params, rating, progress_cb=None):
        self.seen = {"ctx": ctx, "params": params, "rating": rating, "map": speaker_map}
        return await super().run(ctx, pack, transcript, speaker_map, params, rating, progress_cb)


async def test_evaluation_gets_rating_card_coded_span_language_and_a_deadline(env):
    cap = Capture()
    swap_eval(env, cap)
    sid = await env.finished()
    (run,) = env.repo.list_runs(env.uid, sid)
    sess = env.repo.get_session(env.uid, sid)
    assert cap.seen["rating"] == env.repo.get_rating(env.uid, sid, run.rating_id).card
    assert cap.seen["rating"] is not None and sess.coded_span is not None
    assert cap.seen["params"]["coded_span"] == sess.coded_span.model_dump()
    tr = env.repo.get_transcript(env.uid, sid, "current").transcript
    assert cap.seen["params"]["language"] == (tr.language or sess.language)
    assert cap.seen["map"] == {"subject": "S1"}
    left = cap.seen["ctx"].deadline - time.monotonic()
    assert 0 < left <= 600  # derived from the task's remaining time, not unbounded


async def test_run_without_a_usable_rating_passes_no_card(env):
    cap = Capture()
    swap_eval(env, cap)
    sid = await env.start(rate=False)  # never rated: run has no rating_id
    assert (await env.c.post(f"/v1/sessions/{sid}/runs", json={}, headers=env.h)).status_code == 202
    env.drain()
    assert cap.seen["rating"] is None and cap.seen["params"]["coded_span"] is None
    # a final "no rating" revision: the run keeps its rating_id but passes no card
    sid2 = await env.start(rate=False)
    r = await env.c.put(
        f"/v1/sessions/{sid2}/rating",
        json={"final": True, "no_rating": True, "card": {"change_goal": "g"}},
        headers=env.h,
    )
    assert r.status_code in (200, 202)
    env.drain()
    (run2,) = env.repo.list_runs(env.uid, sid2)
    assert run2.rating_id and cap.seen["rating"] is None


async def test_out_of_schema_report_fails_the_run_and_stores_nothing(env):
    class BadReport(FakeEvaluation):
        async def run(self, *a, **kw):
            out = await super().run(*a, **kw)
            out.report.pop("schema_version", None)
            out.report["unexpected"] = {"x": 1}
            out.report["method"] = "not-an-object"
            return out

    swap_eval(env, BadReport())
    sid = await env.finished()
    s = env.repo.get_session(env.uid, sid)
    assert s.state == "failed" and s.error.code == "internal_error"
    assert env.repo.list_reports(env.uid, sid) == []


async def test_slot_is_kept_while_a_retry_is_pending_and_released_after(env):
    seen = {}

    class DownOnce(FakeEvaluation):
        async def run(self, *a, **kw):
            if self.calls == 0:
                self.calls += 1
                raise AdapterError("upstream_unavailable")
            (run,) = env.repo.list_runs(env.uid, sid)
            seen["released"], seen["counters"] = run.released, env.counters()
            return await super().run(*a, **kw)

    swap_eval(env, DownOnce())
    sid = await env.start()
    env.drain()
    assert seen == {"released": False, "counters": (1, 1)}  # attempt 1 left it held
    assert env.counters() == (0, 1)


async def test_retry_after_the_report_was_stored_only_finishes_the_bookkeeping(env):
    ev = Capture()
    swap_eval(env, ev)
    orig, boom = env.repo.update_run, []

    def update_run(uid, sid, run_id, fields):
        if "artifacts_prefix" in fields and not boom:  # report stored, then the worker dies
            boom.append(1)
            raise AdapterError("upstream_unavailable")
        orig(uid, sid, run_id, fields)

    env.repo.update_run = update_run
    sid = await env.finished()
    assert ev.calls == 1  # the retry did not evaluate again
    assert len(env.repo.list_reports(env.uid, sid)) == 1
    s = env.repo.get_session(env.uid, sid)
    assert s.state == "report_ready" and s.latest_report_version == 1
    (run,) = env.repo.list_runs(env.uid, sid)
    assert run.stage is None and run.status == "done" and env.counters() == (0, 1)


async def test_redelivered_run_task_is_a_noop(env):
    sid = await env.finished()
    (run,) = env.repo.list_runs(env.uid, sid)
    from onolys_api.jobs.queue import TaskPayload

    res = env.app.state.runner.handle(
        TaskPayload(kind="run", uid=env.uid, sid=sid, run_id=run.run_id)
    )
    assert res.outcome == "duplicate"
    assert len(env.repo.list_reports(env.uid, sid)) == 1 and env.counters() == (0, 1)


async def test_bad_file_failure_is_not_refunded_after_the_llm_call(env):
    class BadFile(FakeEvaluation):
        async def run(self, *a, **kw):
            raise AdapterError("no_speech")

    swap_eval(env, BadFile())
    sid = await env.finished()
    s = env.repo.get_session(env.uid, sid)
    assert s.state == "failed" and s.error.code == "no_speech"
    assert env.counters() == (0, 1)  # user-side failure: the unit stays spent


async def test_failure_before_the_llm_is_refunded(env):
    sid = await env.start()
    # break an input the handler needs before it calls the evaluation
    env.repo.update_session(env.uid, sid, {"clinician_speaker": None})
    env.drain()
    assert env.repo.get_session(env.uid, sid).state == "failed"
    assert env.counters() == (0, 0)  # refunded: runs back to 0, slot freed


async def test_post_runs_state_and_input_checks(env):
    sid = await env.new_session()
    r = await env.c.post(f"/v1/sessions/{sid}/runs", json={}, headers=env.h)
    assert r.status_code == 409  # speaker not confirmed yet
    sid2 = await env.start()  # running
    r = await env.c.post(f"/v1/sessions/{sid2}/runs", json={}, headers=env.h)
    assert r.status_code == 409 and r.json()["details"][0]["code"] == "invalid_state"
    fresh = (await env.c.post("/v1/sessions", json={}, headers=env.h)).json()["session"]["id"]
    assert (
        await env.c.post(f"/v1/sessions/{fresh}/runs", json={}, headers=env.h)
    ).status_code == 409
    done = await env.finished()  # FX45: a ready report is final
    r = await env.c.post(f"/v1/sessions/{done}/runs", json={}, headers=env.h)
    assert r.status_code == 409 and r.json()["details"][0]["code"] == "rating_final"
    for bad in ({"n_runs": 0}, {"n_runs": 6}, {"preset": "nope"}):
        sid3 = await env.start(rate=False)
        r = await env.c.post(f"/v1/sessions/{sid3}/runs", json=bad, headers=env.h)
        assert r.status_code == 422, bad


async def test_post_runs_cap_429_and_releases(env):
    sid = await env.start(rate=False)
    env.app.state.settings = replace(env.app.state.settings, eval_cap_day=0)
    r = await env.c.post(f"/v1/sessions/{sid}/runs", json={}, headers=env.h)
    assert r.status_code == 429 and r.json()["details"][0]["code"] == "daily_cap_reached"
    assert env.repo.get_session(env.uid, sid).state == "awaiting_input"
    assert env.repo.list_runs(env.uid, sid) == [] and env.counters() == (0, 0)


async def test_cap_held_first_run_starts_with_post_runs(env):
    env.app.state.settings = replace(env.app.state.settings, eval_cap_day=0)
    sid = await env.start()
    s = env.repo.get_session(env.uid, sid)
    assert s.state == "awaiting_input" and s.error.code == "daily_cap_reached"
    env.app.state.settings = replace(env.app.state.settings, eval_cap_day=20)
    r = await env.c.post(f"/v1/sessions/{sid}/runs", json={}, headers=env.h)
    assert r.status_code == 202
    s = env.repo.get_session(env.uid, sid)
    assert s.state == "running" and s.error is None and s.first_run_id == r.json()["run_id"]
    env.drain()
    assert env.repo.get_session(env.uid, sid).state == "report_ready"


async def test_run_and_report_reads_are_owner_scoped(env):
    sid = await env.finished()
    (run,) = env.repo.list_runs(env.uid, sid)
    for path in (
        f"/v1/sessions/{sid}/runs",
        f"/v1/runs/{run.run_id}",
        f"/v1/sessions/{sid}/reports",
        f"/v1/sessions/{sid}/reports/1",
    ):
        assert (await env.c.get(path, headers=env.hb)).status_code == 404, path
    assert (
        await env.c.post(f"/v1/sessions/{sid}/runs", json={}, headers=env.hb)
    ).status_code == 404
    assert (await env.c.get("/v1/runs/" + "0" * 32, headers=env.h)).status_code == 404


async def test_no_report_text_in_session_status(env):
    sid = await env.finished()
    st = env.repo.get_status(env.uid, sid).model_dump(mode="json")
    assert set(st) <= {
        "id", "uid", "state", "step", "progress", "error_code", "latest_report_version",
        "updated_at", "transcript_ready", "speaker_confirmed", "rating_submitted", "has_rating",
    }  # fmt: skip
