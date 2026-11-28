"""Provider-neutral STT interface types."""

from pathlib import Path

import pytest
from onolys_engine import Transcript
from pydantic import ValidationError

from onolys_api.transcription import AudioRef, SttAdapter, SttCompletion, SttParams, SttRun, Word

pytestmark = pytest.mark.unit


def _run() -> SttRun:
    return SttRun(
        provider="google", model="chirp_3", language_requested="auto", adapter_version="1"
    )


def test_stt_params_defaults():
    p = SttParams(provider="google", model="chirp_3")
    assert (p.language, p.diarization, p.speakers_min, p.speakers_max, p.options) == (
        "auto",
        True,
        2,
        2,
        {},
    )
    with pytest.raises(ValidationError):
        SttParams(provider="google")  # type: ignore[call-arg]


def test_audio_ref_callable_and_defaults():
    a = AudioRef(uri="gs://b/x.flac", mime="audio/flac")
    assert a.local_path_fn is None and a.duration_ms is None
    b = AudioRef(uri="u", mime="audio/flac", local_path_fn=lambda: Path("/x"), duration_ms=10)
    assert b.local_path_fn() == Path("/x")


def test_word_required_fields():
    w = Word(text="a", start_ms=0, end_ms=1)
    assert w.speaker is None
    with pytest.raises(ValidationError):
        Word(text="a", start_ms=0)  # type: ignore[call-arg]


async def test_stt_adapter_protocol_usable():
    class Fake:
        async def start(self, audio, params):
            return "h1"

        async def poll(self, handle):
            return SttCompletion(transcript=Transcript(turns=[]), run=_run())

    a: SttAdapter = Fake()
    assert await a.start(AudioRef(uri="u", mime="m"), SttParams(provider="p", model="m")) == "h1"
    assert (await a.poll("h1")).transcript == Transcript(turns=[])
