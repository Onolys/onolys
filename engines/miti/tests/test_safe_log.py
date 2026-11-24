import logging

import pytest
from onolys_engine_core.json_logging import render

from onolys_miti.stt import AudioRef, SttParams, Word
from onolys_miti.stt.base import transcribe
from onolys_miti.stt.fixture import FixtureStt, uri_hash

pytestmark = pytest.mark.unit

SENTINEL = "ZZ-SENTINEL-PHI-ZZ"
URI = "gs://secret-bucket/patient-0042.flac"


async def test_full_fixture_stt_call_logs_no_text_or_uri(caplog):
    words = [
        Word(text=SENTINEL, start_ms=0, end_ms=400, speaker="a"),
        Word(text="other", start_ms=500, end_ms=900, speaker="b"),
    ]
    audio = AudioRef(uri=URI, mime="audio/flac", duration_ms=900)
    stt = FixtureStt({uri_hash(URI): words}, polls_before_ready=1)
    with caplog.at_level(logging.DEBUG, logger="miti"):
        await transcribe(
            stt, audio, SttParams(provider="fixture", model="fx", language="en"), interval_s=0
        )
    all_fields = [getattr(r, "fields", {}) for r in caplog.records]
    merged: dict = {}
    for f in all_fields:
        merged.update(f)
    blob = caplog.text + "\n".join(render(r) for r in caplog.records)
    assert "stt_provider" in merged and any(f.get("stt_model") == "fx" for f in all_fields)
    assert merged["audio_ms"] == 900 and merged["speakers"] == 2
    assert "job_id" in merged
    for banned in (SENTINEL, "other", URI, "secret-bucket", "patient-0042"):
        assert banned not in blob
