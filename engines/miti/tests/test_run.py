"""`run_miti` (PRD R2, R7, D6): stages, n_runs averaging, deadline, coding vs tips failure.

The client is a handler-based fixture client: code and globals replies come from the recorded
good_practice replies (data/fixtures/golden), tips replies are built here."""

import asyncio
import copy
import json
import logging
import re
import time

import jsonschema
import pytest

from onolys_miti import miti
from onolys_miti.context import RunContext
from onolys_miti.llm import LLMBadOutput, LLMResult, LLMUnavailable, MetricsCollector, Usage
from onolys_miti.result import MitiResult
from onolys_miti.run import AllRunsFailed, MitiOutput, aggregate, run_miti
from onolys_miti.transcript import Transcript

pytestmark = pytest.mark.unit

FIX = miti.DATA_DIR / "fixtures"
GOLD = FIX / "golden" / "good_practice"
PARAMS = {"change_goal": "walk more during the working week"}
SMAP = {"subject": "A", "other": "B"}
STAGES = ["code", "tips", "assemble"]


def _recorded(key):
    for f in GOLD.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        if key in d:
            return d
    raise AssertionError(key)


CODE, GLOBALS = _recorded("volleys"), _recorded("globals")


def transcript(whole=True):
    d = json.loads((FIX / "good_practice.json").read_text(encoding="utf-8"))
    if whole:  # 1205 s is just past the 20-minute cap; trim so the whole session is coded
        d["turns"][-1]["end_ms"] = 1195000
    return Transcript.model_validate(d)


def tip(item, turn, quote):
    return {
        "item_id": item,
        "observation": "Onolys reads this as a closed prompt.",
        "quote": {"turn_id": turn, "text": quote},
        "alternative": f"Try option {item} in plain words.",
        "why_it_matters": "Open wording invites more of the client's own reasons.",
    }


TIPS = [
    tip("cct", "t4", "What makes walking more important to you right now?"),
    tip("sst", "t9", "Where would a walk fit best in your week?"),
    tip("partnership", "t15", "Would it be helpful if I shared some ideas"),
]


def code_reply(req, run_idx):
    asked = {v["volley_id"] for v in json.loads(req.user)["volleys"]}
    out = copy.deepcopy(CODE)
    out["volleys"] = [v for v in out["volleys"] if v["volley_id"] in asked]
    return req.response_model.model_validate(out)


def globals_reply(req, run_idx):
    return req.response_model.model_validate(copy.deepcopy(GLOBALS))


def tips_reply(req, run_idx):
    return req.response_model.model_validate({"tips": TIPS})


class FakeClient:
    """Fixture client: one handler per route; the run index comes from the call tag."""

    def __init__(self, code=code_reply, glob=globals_reply, tips=tips_reply):
        self.h = {"miti_code": code, "miti_globals": glob, "tips": tips}
        self.requests = []

    async def complete_json(self, req, metrics=None):
        self.requests.append(req)
        run_idx = int(re.search(r":r(\d+)", req.call_tag).group(1))
        parsed = self.h[req.tier](req, run_idx)
        if metrics is not None:
            metrics.record(req, "fake", Usage(input_tokens=10, output_tokens=5), 0.0, 1, True)
        return LLMResult(parsed=parsed, model="fake")


def bad(req, run_idx):
    raise LLMBadOutput("truncated")


def make_ctx(client, **kw):
    return RunContext(llm=client, metrics=MetricsCollector(), request_id="req-1", **kw)


class Rec:
    def __init__(self):
        self.events = []

    def __call__(self, stage, status):
        self.events.append((stage, status))

    def seq(self, stage):
        return [s for st, s in self.events if st == stage]


async def go(client=None, params=None, cb=None, tr=None, **ctx_kw):
    client = client or FakeClient()
    return await run_miti(
        make_ctx(client, **ctx_kw), tr or transcript(), SMAP, {**PARAMS, **(params or {})}, cb
    )


def codes(out):
    return [w.code for w in out.report.warnings]


async def test_happy_path_stage_events_and_output():
    cb = Rec()
    out = await go(cb=cb)
    assert isinstance(out, MitiOutput)
    assert cb.events == [(s, st) for s in STAGES for st in ("started", "done")]
    assert isinstance(out.artifacts.code, MitiResult)
    assert out.artifacts.tips is not None and len(out.artifacts.tips.valid) == 3
    assert len(out.report.tips) == 3 and "tips_failed" not in codes(out)
    assert out.report.header.has_clinician_rating is False
    assert out.report.reasons_audit.status == "skipped"
    assert out.report.request_id == "req-1"
    ri = out.report.run_info
    assert ri.evaluation.engine == "miti" and ri.miti.engine == "miti"
    assert set(ri.miti.routes) <= {"miti_code", "miti_globals"}
    assert ri.miti.pack.hash == miti.MITI.hash


async def test_report_validates_against_schema():
    out = await go()
    schema = json.loads((miti.DATA_DIR / "report.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(json.loads(out.report.model_dump_json()), schema)
    MitiResult.model_validate_json(out.artifacts.code.model_dump_json())


async def test_stages_are_emitted_in_order_with_assemble_last():
    cb = Rec()
    await go(cb=cb)
    assert cb.events[0] == ("code", "started") and cb.events[-1] == ("assemble", "done")
    assert cb.events.index(("code", "done")) < cb.events.index(("tips", "started"))
    assert cb.events.index(("tips", "done")) < cb.events.index(("assemble", "started"))


async def test_raising_callback_is_ignored(caplog):
    caplog.set_level(logging.INFO)

    def boom(stage, status):
        raise ValueError("cb exploded")

    assert isinstance(await go(cb=boom), MitiOutput)
    assert "cb exploded" not in caplog.text


async def test_no_callback_ok():
    assert isinstance(await go(cb=None), MitiOutput)


async def test_whole_session_records_span_without_window():
    out = await go()
    res = out.artifacts.code
    assert res.coded_span is None
    assert res.run_info.span.mode == "whole" and res.run_info.span.seed == "req-1"
    assert out.report.run_info.miti.span.mode == "whole"
    assert "coded_window" not in codes(out)


async def test_long_session_codes_one_seeded_window():
    a = await go(tr=transcript(whole=False))
    b = await go(tr=transcript(whole=False), params={"n_runs": 2})
    for out in (a, b):
        assert out.artifacts.code.run_info.span.mode == "random_window"
        assert "coded_window" in codes(out)
    assert a.artifacts.code.coded_span == b.artifacts.code.coded_span  # one window for all runs
    span = a.artifacts.code.coded_span
    assert span is not None and span.to_s - span.from_s == 1200
    other = await go(tr=transcript(whole=False), params={"seed": "another-session"})
    assert other.artifacts.code.run_info.span.seed == "another-session"


async def test_caller_cannot_pass_coded_span():
    out = await go(params={"coded_span": {"from_s": 100, "to_s": 200}})
    assert out.artifacts.code.coded_span is None
    assert "coded_span" not in out.report.header.params


async def test_n1_aggregate_equals_single_run():
    out = await go()
    res = out.artifacts.code
    assert res.n_runs == 1 and len(res.results) == 1
    only = res.results[0]
    for k, v in only.counts.items():
        s = res.aggregate.counts[k]
        assert s.mean == s.min == s.max == v and s.values == [v]


async def test_n3_averages_with_one_failed_run():
    def code(req, run_idx):
        if run_idx == 1:
            raise LLMBadOutput("truncated")
        return code_reply(req, run_idx)

    out = await go(FakeClient(code=code), {"n_runs": 3})
    res = out.artifacts.code
    assert [r.run_index for r in res.results] == [0, 2]
    assert res.n_runs == 3 and res.run_info.n_runs == 3
    failed = [w for w in res.warnings if w.code == "run_failed"]
    assert len(failed) == 1 and "1" in (failed[0].detail or "")
    for st in res.aggregate.counts.values():
        assert len(st.values) == 2
        assert (
            st.mean == sum(st.values) / 2 and st.min == min(st.values) and st.max == max(st.values)
        )
    assert "run_failed" in codes(out)


async def test_n3_aggregate_values_differ_per_run():
    def code(req, run_idx):
        r = code_reply(req, run_idx)
        if run_idx == 1:  # run 1 codes nothing
            for v in r.volleys:
                for u in v.utterances:
                    u.code = None
        return r

    res = (await go(FakeClient(code=code), {"n_runs": 3})).artifacts.code
    q = res.aggregate.counts["question"]
    assert len(q.values) == 3 and q.values[1] == 0 and q.min == 0 and q.max == q.values[0]
    assert q.mean == pytest.approx(sum(q.values) / 3)
    assert res.aggregate.representative_run in (0, 2)


async def test_later_runs_wait_for_warm_call():
    client = FakeClient()
    await go(client, {"n_runs": 2})
    tags = [r.call_tag for r in client.requests if r.tier == "miti_code"]
    assert tags[0].startswith("miti_code:r0:")
    assert {t.split(":")[1] for t in tags} == {"r0", "r1"}


async def test_all_runs_failed_raises_and_no_report():
    cb = Rec()
    with pytest.raises(AllRunsFailed) as e:
        await go(FakeClient(glob=bad), {"n_runs": 2}, cb=cb)
    assert e.value.code == "run_failed"
    assert cb.seq("code") == ["started", "failed"]
    assert cb.seq("tips") == [] and cb.seq("assemble") == []


async def test_coding_failure_chains_cause_and_skips_tips():
    client = FakeClient(code=lambda r, i: (_ for _ in ()).throw(LLMUnavailable("down")))
    with pytest.raises(AllRunsFailed) as e:
        await go(client)
    assert isinstance(e.value.__cause__, LLMUnavailable)
    assert not [r for r in client.requests if r.tier == "tips"]


async def test_tips_failure_degrades_to_warning():
    cb = Rec()
    out = await go(FakeClient(tips=bad), cb=cb)
    assert out.report.tips == [] and "tips_failed" in codes(out)
    assert cb.seq("tips") == ["started", "failed"]
    assert cb.seq("assemble") == ["started", "done"]
    assert out.artifacts.code.results


async def test_deadline_past_raises_timeout():
    cb = Rec()
    with pytest.raises(TimeoutError):
        await go(cb=cb, deadline=time.monotonic() - 1)
    assert ("assemble", "done") not in cb.events


async def test_deadline_mid_run_cancels():
    async def slow(req, run_idx):
        await asyncio.sleep(5)

    class Slow(FakeClient):
        async def complete_json(self, req, metrics=None):
            await asyncio.sleep(5)

    cb = Rec()
    with pytest.raises(TimeoutError):
        await go(Slow(), cb=cb, deadline=time.monotonic() + 0.2)
    assert cb.seq("code")[-1] == "failed"


async def test_future_deadline_is_not_hit():
    assert isinstance(await go(deadline=time.monotonic() + 60), MitiOutput)


async def test_language_warning():
    out = await go(params={"language": "de"})
    assert out.artifacts.code.language == "de"
    assert "language_not_validated" in [w.code for w in out.artifacts.code.warnings]


async def test_invalid_n_runs():
    from onolys_miti.errors import InputError

    with pytest.raises(InputError):
        await go(params={"n_runs": -1})


async def test_usage_and_call_log_cover_all_calls():
    client = FakeClient()
    ctx = make_ctx(client)
    out = await run_miti(ctx, transcript(), SMAP, dict(PARAMS), None)
    code_calls = out.artifacts.code.run_info.usage.calls
    assert code_calls == len([r for r in client.requests if r.tier != "tips"])
    assert out.report.run_info.evaluation.usage.calls == 1  # the tips call
    assert len(ctx.metrics.records) == len(client.requests)  # one call log for the whole run


async def test_logs_hold_no_transcript_text(caplog):
    caplog.set_level(logging.DEBUG)
    await go()
    with pytest.raises(AllRunsFailed):
        await go(FakeClient(code=bad))
    assert caplog.records
    for needle in ("walk more", "What makes walking", "kids", "blocking"):
        assert needle not in caplog.text


def test_prompt_hashes_change_with_engine_template(monkeypatch):
    from onolys_miti import code_pass
    from onolys_miti.run import prompt_hashes

    before = prompt_hashes()
    assert {"code_system.md", "globals_system.md"} <= set(before)
    monkeypatch.setattr(code_pass, "_OUTPUT_FORMAT", "changed instructions")
    after = prompt_hashes()
    assert {k for k in before if before[k] != after[k]} == {"engine:code_output_format"}


def _fake_runs(counts, scores):
    from onolys_miti.result import GlobalScore, RunResult

    return [
        RunResult(
            run_index=i,
            instances=[],
            counts={"a": a},
            globals={
                "g1": GlobalScore(score=g, source="model", raw_score=g, reason="r", evidence=[])
            },
            summaries={},
            warnings=[],
        )
        for i, (a, g) in enumerate(zip(counts, scores, strict=True))
    ]


def test_representative_run_closest_to_mean():
    assert aggregate(_fake_runs([0, 4, 5], [3, 3, 3])).representative_run == 1
    assert aggregate(_fake_runs([2, 2, 2], [1, 3, 5])).representative_run == 1
    assert aggregate(_fake_runs([1, 3], [3, 3])).representative_run == 0  # tie: lowest index


def test_public_reexports():
    import onolys_miti as m

    for name in (
        "run_miti",
        "MitiOutput",
        "AllRunsFailed",
        "RunContext",
        "SttParams",
        "LiteLLMClient",
        "GoogleChirp3",
        "resolve_preset",
        "Transcript",
    ):
        assert hasattr(m, name), name
