import json
import subprocess
import sys

import pytest
from onolys_engine_core.transcript import Transcript, Turn
from pydantic import ValidationError

from onolys_miti.run_info import SttRun
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


def test_sttrun_required_fields():
    r = _run()
    assert r.location is None and r.language_detected is None
    with pytest.raises(ValidationError):
        SttRun(provider="p", model="m")  # type: ignore[call-arg]


def test_miti_imports_no_sibling_packages():
    """Boundary: importing the package pulls in no sibling Onolys packages."""
    forbidden = ("api", "admin", "eval")
    code = (
        "import sys, onolys_miti, onolys_engine_core.llm;"
        f"bad=[m for m in sys.modules if m.split('.')[0] in {forbidden!r}];"
        "print(bad)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"

