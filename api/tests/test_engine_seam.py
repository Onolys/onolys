"""R2/R3/D1/D2/D10: the engine seam. The run passes `seed` (the session id), the optional caller span,
and never a rating: a run with or without a submitted card gives the same report."""

import inspect

import pytest
from test_run import env, swap_eval  # noqa: F401,F811

from onolys_api.adapters import FakeEvaluation
from onolys_api.adapters.base import Evaluation
from onolys_api.adapters.real import RealEvaluation

pytestmark = pytest.mark.integration


class Capture(FakeEvaluation):
    async def run(self, ctx, transcript, speaker_map, params, progress_cb=None):
        self.seen = {"params": dict(params), "map": speaker_map}
        return await super().run(ctx, transcript, speaker_map, params, progress_cb)


async def test_absent_span_passes_whole_session(env):  # noqa: F811
    cap = Capture()
    swap_eval(env, cap)
    sid = await env.finished()
    assert env.repo.get_session(env.uid, sid).coded_span is None  # card span is ignored
    assert cap.seen["params"]["seed"] == sid
    assert cap.seen["params"]["coded_span"] is None


async def test_real_adapter_forwards_seed_and_caller_span():
    seen = {}

    async def run_miti(rctx, transcript, speaker_map, params, progress_cb=None):
        seen.update(params)
        raise RuntimeError("stop")

    from onolys_engine_core.context import RunContext

    ev = RealEvaluation(run_miti=run_miti, llm_factory=lambda routes: object())
    ctx = RunContext(llm=None, metrics=None, request_id="r1")
    params = {"seed": "sess-1", "coded_span": {"start_turn": 0, "end_turn": 2}, "preset": None}
    with pytest.raises(RuntimeError):
        await ev.run(ctx, None, {"subject": "S1"}, params)
    assert seen["seed"] == "sess-1" and seen["coded_span"] == params["coded_span"]


def test_seam_has_no_pack_or_rating():
    for fn in (Evaluation.run, RealEvaluation.run, FakeEvaluation.run):
        names = list(inspect.signature(fn).parameters)
        assert names == ["self", "ctx", "transcript", "speaker_map", "params", "progress_cb"]


async def test_rating_ignored(env):  # noqa: F811
    cap = Capture()
    swap_eval(env, cap)
    rated = await env.finished("same")
    with_card = dict(cap.seen)
    unrated = await env.start("same", rate=False)
    assert (await env.c.post(f"/v1/sessions/{unrated}/runs", json={}, headers=env.h)).status_code == 202
    env.drain()
    assert "rating" not in with_card["params"] and "rating" not in cap.seen["params"]

    def body(sid):
        rep = dict(env.repo.get_report_by_version(env.uid, sid, 1).report)
        rep.pop("request_id", None)
        rep["header"] = {**rep["header"], "change_goal": ""}  # only the card carries a goal
        for info in rep["run_info"].values():
            (info.get("span") or {}).pop("seed", None)  # the seed is the session id
        return rep

    assert body(rated) == body(unrated)


@pytest.mark.parametrize("span", [{"start_turn": 0, "end_turn": 2},
                                 {"start_ms": 0, "end_ms": 10000}])
async def test_caller_span_reaches_worker_and_report(env, span):  # noqa: F811
    cap = Capture()
    swap_eval(env, cap)
    sid = await env.finished(coded_span=span)
    assert cap.seen["params"]["coded_span"] == span
    report = env.repo.get_report_by_version(env.uid, sid, 1).report
    assert report["header"]["coded_span"] == span
    assert report["run_info"]["miti"]["span"]["mode"] == "explicit"
    for key, value in span.items():
        assert report["run_info"]["miti"]["span"][key] == value
