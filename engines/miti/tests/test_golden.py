"""Golden parity (PRD R4, D6): `run_miti` on good_practice, code and globals replayed from the
recorded fixtures (`data/fixtures/golden/good_practice`, keyed by the real request content), tips
answered with the golden report's own tips, must equal `report_no_rating.json` after masking the
volatile keys. The report also validates against the report schema and the API's local copy."""

import json
from dataclasses import replace
from pathlib import Path

import jsonschema
import pytest
from onolys_engine_core.context import RunContext
from onolys_engine_core.llm import LLMResult, MetricsCollector
from onolys_engine_core.llm.fixture_client import FixtureClient
from onolys_engine_core.transcript import Transcript

from onolys_miti import miti
from onolys_miti.run import run_miti

pytestmark = pytest.mark.unit

FIX = miti.DATA_DIR / "fixtures"
GOLD = FIX / "golden" / "good_practice"
GOLDEN_REPORT = json.loads((FIX / "evaluation" / "report_no_rating.json").read_text("utf-8"))
SMAP = {"subject": "A", "other": "B"}
PARAMS = {"n_runs": 1, "change_goal": "walk more during the working week"}
# Run provenance and environment, not coding output: differs by preset, host, stt and build.
VOLATILE_TOP = ("created_at", "request_id", "run_info")
VOLATILE_HEADER = ("code_version", "params", "models", "preset", "stt")


class GoldenClient:
    """Code and globals come from the recorded fixtures, tips from the golden report."""

    def __init__(self):
        self.fixtures = FixtureClient(GOLD)

    async def complete_json(self, req, metrics=None):
        if req.tier != "tips":
            return await self.fixtures.complete_json(req, metrics)
        tips = [
            {**t, "quote": {"turn_id": t["quote"]["turn_id"], "text": t["quote"]["text"]}}
            for t in GOLDEN_REPORT["tips"]
        ]
        return LLMResult(parsed=req.response_model.model_validate({"tips": tips}), model="fake")


def masked(report: dict) -> dict:
    out = {k: v for k, v in report.items() if k not in VOLATILE_TOP}
    out["header"] = {k: v for k, v in report["header"].items() if k not in VOLATILE_HEADER}
    return out


async def _run() -> dict:
    d = json.loads((FIX / "good_practice.json").read_text(encoding="utf-8"))
    ctx = RunContext(llm=GoldenClient(), metrics=MetricsCollector(), request_id="req-golden")
    out = await run_miti(ctx, Transcript.model_validate(d), SMAP, PARAMS)
    return json.loads(out.report.model_dump_json())


async def test_run_miti_matches_golden_report_after_masking():
    got = await _run()
    assert masked(got) == masked(GOLDEN_REPORT)


async def test_golden_report_validates_against_report_schema():
    schema = json.loads((miti.DATA_DIR / "report.schema.json").read_text("utf-8"))
    jsonschema.validate(await _run(), schema)
    jsonschema.validate(GOLDEN_REPORT, schema)


async def test_golden_report_against_api_local_schema():
    """The API's stand-in schema predates the rename: it still requires two old `run_info` keys
    and not `run_info.miti`. Until SP02 refreshes the copy, exactly those two "required property"
    errors on `run_info` are allowed; after it, none. Anything else is a real regression."""
    path = Path(__file__).resolve().parents[3] / "api/src/onolys_api/schemas/report.local.schema.json"
    if not path.is_file():
        pytest.skip("api checkout not present")
    validator = jsonschema.Draft202012Validator(json.loads(path.read_text("utf-8")))
    errors = list(validator.iter_errors(await _run()))
    if errors:  # pre-SP02: only the two old-key `run_info` required-property errors
        assert [list(e.absolute_path) for e in errors] == [["run_info"], ["run_info"]]
        assert all(e.message.endswith("is a required property") for e in errors)
        assert not any("'miti'" in e.message for e in errors)
        assert all(e.validator == "required" for e in errors)


async def test_fixture_keys_match_existing_golden_filenames(monkeypatch):
    """Freeze request hashes before extracting the shared LLM implementation."""
    expected = {
        "8340f9e78d95ffa99a37a4ac7015423258eb01f2d2b22d5871e83b9d78645623",
        "c24dfc214fee7fdb4aa02911ec86b49e7e4dca8b2b4c3f1feba40db6033602a2",
    }
    seen = set()
    original = FixtureClient.complete_json

    async def capture(self, req, metrics=None):
        key = self.key_for(req)
        assert key == self.key_for(replace(req))
        seen.add(key)
        return await original(self, req, metrics)

    monkeypatch.setattr(FixtureClient, "complete_json", capture)
    await _run()
    assert seen == expected == {path.stem for path in GOLD.glob("*.json")}
