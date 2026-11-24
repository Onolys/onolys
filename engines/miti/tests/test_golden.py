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
    """Freeze exact request hashes, including prompt wording.

    The globals response was intentionally reused as deterministic synthetic stub data
    after the concise-prose instruction changed. It is not a new live-model recording.
    """
    expected = {
        "8340f9e78d95ffa99a37a4ac7015423258eb01f2d2b22d5871e83b9d78645623",
        "ec02bc75849e82d47f8619a2d9a4fc1648c6d2f7e644cce3ad2d271a08d66f26",
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


def adapter_bytes(payload: dict) -> bytes:
    """Canonical UTF-8 JSON; normalize only the generated created_at timestamps.

    Keep every report, artifact and run_info field, including provenance shape and
    stable prompt/pack hashes, fixed request ids and fixed build metadata.
    Transcript timestamps stay intact.
    """
    def normalize(value):
        if isinstance(value, dict):
            return {
                key: "<volatile>" if key == "created_at"
                else normalize(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    return (json.dumps(normalize(payload), sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False) + "\n").encode("utf-8")


async def _adapter_run() -> dict:
    # Local offline adapter evidence requires the API package. Engine-only CI
    # skips this adapter check; the existing engine golden checks still run.
    real = pytest.importorskip("onolys_api.adapters.real")
    config = pytest.importorskip("onolys_api.config")
    transcript = Transcript.model_validate(json.loads((FIX / "good_practice.json").read_text()))
    adapter = real.RealEvaluation(
        settings=config.Settings(env="test"), llm_factory=lambda routes: GoldenClient(),
    )
    out = await adapter.run(
        RunContext(llm=None, metrics=None, request_id="req-golden"), transcript, SMAP,
        {**PARAMS, "code_version": "fixture-build"},
    )
    return out.model_dump(mode="json")


async def test_adapter_fixture_bytes_match_manual_alignment():
    """Current deterministic manual-alignment baseline after SP02 Task 2.

    Historical SP01 assertion and adapter_pre_input_locks.json are preserved at
    commit ce65eef. Task 2 intentionally changes the pack fingerprint only for
    this fixture: its volley groupings and coding output remain unchanged.

    Compare the entire EvaluationOutput (report, artifacts and run_info), not just
    the report or a fresh result generated by the current implementation. Only
    generated created_at timestamps are normalized; request ids and build metadata
    remain exact. This local offline adapter evidence requires the API installed,
    so engine-only CI skips it while existing engine goldens still run.
    """
    expected = (Path(__file__).parent / "fixtures" / "adapter_manual_alignment.json").read_bytes()
    assert adapter_bytes(await _adapter_run()) == expected
