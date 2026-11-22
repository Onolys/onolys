"""R2/R3/D1/D2/D10: the engine seam. The run passes `seed` (the session id), never a coded span,
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


async def test_span_not_passed(env):  # noqa: F811
    cap = Capture()
    swap_eval(env, cap)
    sid = await env.finished()
    assert env.repo.get_session(env.uid, sid).coded_span is not None  # the card did set a span
    assert cap.seen["params"]["seed"] == sid
    assert "coded_span" not in cap.seen["params"]


async def test_real_adapter_forwards_seed_and_drops_a_caller_span():
    seen = {}

    async def run_miti(rctx, transcript, speaker_map, params, progress_cb=None):
        seen.update(params)
        raise RuntimeError("stop")

    from onolys_miti import RunContext

    ev = RealEvaluation(run_miti=run_miti, llm_factory=lambda routes: object())
    ctx = RunContext(llm=None, metrics=None, request_id="r1")
    params = {"seed": "sess-1", "coded_span": {"from_s": 1, "to_s": 2}, "preset": None}
    with pytest.raises(RuntimeError):
        await ev.run(ctx, None, {"subject": "S1"}, params)
    assert seen["seed"] == "sess-1" and "coded_span" not in seen


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
        return rep

    assert body(rated) == body(unrated)
