import json
import subprocess
import sys
from pathlib import Path

import pytest
from onolys_engine_core.transcript import Transcript, Turn
from pydantic import ValidationError

from onolys_miti.stt import AudioRef, SttAdapter, SttCompletion, SttParams, SttRun, Word
from onolys_miti.transcript import Span

pytestmark = pytest.mark.unit


def _run() -> SttRun:
    return SttRun(
        provider="google", model="chirp_3", language_requested="auto", adapter_version="1"
    )


def test_turn_defaults_and_required():
    t = Turn(id="t1", speaker="S1", text="hi")
    assert t.speaker == "S1" and t.start_ms is None and t.end_ms is None
    assert t.role is None
    with pytest.raises(ValidationError):
        Turn(id="t1")  # type: ignore[call-arg]


def test_transcript_roundtrip():
    tr = Transcript(
        turns=[Turn(id="t1", speaker="S1", text="hi", start_ms=0, end_ms=5)],
        language="en-US",
        duration_ms=5,
    )
    assert Transcript.model_validate(json.loads(tr.model_dump_json())) == tr
    assert "stt_run" not in Transcript(turns=[]).model_dump()


def test_span_requires_all_fields():
    assert Span(turn_id="t1", start=0, end=3).end == 3
    with pytest.raises(ValidationError):
        Span(turn_id="t1", start=0)  # type: ignore[call-arg]


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


def test_word_and_sttrun():
    w = Word(text="a", start_ms=0, end_ms=1)
    assert w.speaker is None
    with pytest.raises(ValidationError):
        Word(text="a", start_ms=0)  # type: ignore[call-arg]
    r = _run()
    assert r.location is None and r.language_detected is None
    with pytest.raises(ValidationError):
        SttRun(provider="p", model="m")  # type: ignore[call-arg]


async def test_stt_adapter_protocol_usable():
    class Fake:
        async def start(self, audio, params):
            return "h1"

        async def poll(self, handle):
            return SttCompletion(transcript=Transcript(turns=[]), run=_run())

    a: SttAdapter = Fake()
    assert await a.start(AudioRef(uri="u", mime="m"), SttParams(provider="p", model="m")) == "h1"
    assert (await a.poll("h1")).transcript == Transcript(turns=[])


def test_miti_imports_no_sibling_packages():
    """Boundary: importing the package pulls in no sibling Onolys packages."""
    forbidden = ("api", "admin", "eval")
    code = (
        "import sys, onolys_miti, onolys_miti.stt, onolys_engine_core.llm, onolys_miti.voice;"
        f"bad=[m for m in sys.modules if m.split('.')[0] in {forbidden!r}];"
        "print(bad)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


def test_extracted_llm_has_no_miti_reexports():
    import importlib.util

    import onolys_miti

    assert importlib.util.find_spec("onolys_miti.llm") is None
    for name in (
        "LLMConfig", "LLMError", "LLMUnavailable", "LiteLLMClient",
        "MetricsCollector", "StubClient", "resolve_preset",
    ):
        assert not hasattr(onolys_miti, name)
