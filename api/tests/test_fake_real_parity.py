"""The fake and the real adapter (fixture LLM) agree on shape: top-level keys, stage sequence,
artifact names and report schema validity."""

import json

import miti_fixtures as fx
import pytest
from jsonschema import Draft202012Validator
from onolys_engine_core.context import RunContext
from onolys_miti import miti
from onolys_miti.run_info import SpanInfo

from onolys_api.adapters import FakeEvaluation
from onolys_api.adapters.real import RealEvaluation

pytestmark = pytest.mark.unit

REPORT = Draft202012Validator(json.loads((miti.DATA_DIR / "report.schema.json").read_text()))
PARAMS = {"change_goal": "cut back", "seed": "sess-1", "language": "en",
          "n_runs": 1, "preset": "default", "code_version": "abc"}  # fmt: skip


async def _run(evaluation):
    ev: list = []
    ctx = RunContext(llm=object(), metrics=None, request_id="req-1")
    out = await evaluation.run(
        ctx, fx.TRANSCRIPT, {"subject": fx.SUBJECT}, PARAMS, lambda s, st: ev.append((s, st))
    )
    return out, ev


async def test_fake_and_real_agree_on_shape(monkeypatch):
    fx.patch_engine(monkeypatch)
    real = RealEvaluation(llm_factory=lambda routes: object())
    (fo, fev), (ro, rev) = await _run(FakeEvaluation()), await _run(real)
    assert set(fo.report) - {"request_id"} == set(ro.report) - {"request_id"}
    assert fev == rev == [("code", "started"), ("code", "done"), ("tips", "started"),
                          ("tips", "done"), ("assemble", "started"), ("assemble", "done")]  # fmt: skip
    assert set(fo.artifacts) == set(ro.artifacts) == {"code", "tips"}
    assert not list(REPORT.iter_errors(fo.report)) and not list(REPORT.iter_errors(ro.report))
    assert set(fo.report["run_info"]) == set(ro.report["run_info"]) == {"evaluation", "miti"}
    assert set(fo.report["run_info"]["miti"]) == set(ro.report["run_info"]["miti"])
    # The patched engine returns a fixture result without a span, so compare the fake's span to
    # what the real engine emits (SpanInfo).
    fspan = fo.report["run_info"]["miti"]["span"]
    assert set(fspan) == set(SpanInfo.model_fields)
    assert fspan["mode"] == "whole" and fspan["seed"] == PARAMS["seed"]
