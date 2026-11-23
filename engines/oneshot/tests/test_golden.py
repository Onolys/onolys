"""Replay actual provider replies for synthetic sessions; recording is opt-in."""

import os
from pathlib import Path

import pytest
from onolys_engine_core.context import RunContext
from onolys_engine_core.llm import LLMConfig, MetricsCollector, make_client
from onolys_engine_core.transcript_v1 import TranscriptV1
from onolys_engine_core.validate import validate_output

from onolys_oneshot import OneshotEngine

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("name,mode", [("good_practice", "json_object"), ("short_session", "json_schema")])
async def test_recorded_miti_reply(name, mode, monkeypatch):
    # Pins render mode/preset so ambient deployment configuration cannot change keys.
    monkeypatch.setenv("MITI_LLM_RESPONSE_FORMAT", mode)
    monkeypatch.delenv("ROUTES_FILE", raising=False)
    monkeypatch.setenv("DEFAULT_PRESET", "claude")
    transcript = TranscriptV1.model_validate_json((FIXTURES / "transcripts" / f"{name}.json").read_text())
    recording = os.environ.get("MITI_LLM_RECORD") == "1"
    client = make_client(LLMConfig(
        llm_mode="live" if recording else "fixture",
        fixture_dir=str(FIXTURES / "recorded"), preset="claude",
    ))
    ctx = RunContext(llm=client, metrics=MetricsCollector(), request_id="synthetic-golden")
    engine = OneshotEngine()
    result = await engine.run(ctx, transcript, {"config": "miti", "change_goal": "Walk more regularly", "language": "en", "preset": "claude"})
    assert validate_output(result.output, engine.output_schema()) == []
    if not recording:
        assert result.run_info.model == "fixture"
    assert result.run_info.usage.calls == 1
    # This is a structural regression check, not a clinical accuracy claim.
    assert set(result.output) == {"counts", "globals", "tips"}
