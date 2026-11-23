"""Shared transcript contracts must work without importing an engine."""

import ast
import importlib.util
import json
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

from onolys_engine_core.transcript import Transcript, Turn
from onolys_engine_core.transcript_v1 import TranscriptTurnV1, TranscriptV1

ROOT = Path(__file__).resolve().parents[3]


def test_core_transcript_aliases_and_packaged_schema():
    assert Transcript is TranscriptV1
    assert Turn is TranscriptTurnV1
    schema = files("onolys_engine_core").joinpath("data/transcript.v1.schema.json")
    assert json.loads(schema.read_text()) == TranscriptV1.model_json_schema()


def test_portable_model_imports_only_pydantic():
    source = Path(importlib.util.find_spec("onolys_engine_core.transcript_v1").origin)
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] == "pydantic" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module.split(".")[0] == "pydantic"


def test_transcript_and_speaker_helpers_import_without_miti():
    code = (
        "import sys; from onolys_engine_core.transcript_txt import parse_transcript_txt; "
        "from onolys_engine_core.transcript_input import inferred_clinician_speaker; "
        "tr = parse_transcript_txt('T: ' + 'example ' * 50); "
        "assert inferred_clinician_speaker(tr) == 'T'; "
        "assert not any(m.split('.')[0] == 'onolys_miti' for m in sys.modules)"
    )
    result = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_consumers_do_not_import_removed_transcript_modules():
    removed = {"transcript_v1", "transcript_input", "transcript_txt", "context", "llm", "errors"}
    for folder in ("engines/miti/src", "api/src", "eval/core/src"):
        for path in (ROOT / folder).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom) and node.module:
                    parts = node.module.split(".")
                    assert parts[:1] != ["onolys_miti"] or len(parts) < 2 or parts[1] not in removed, path
                    if parts == ["onolys_miti", "transcript"]:
                        assert all(alias.name == "Span" for alias in node.names), path


def test_miti_has_no_transcript_reexports_or_moved_files():
    import onolys_miti
    import onolys_miti.transcript as miti_transcript

    for name in ("Turn", "Transcript", "TranscriptTurnV1", "TranscriptV1"):
        assert not hasattr(onolys_miti, name)
        assert not hasattr(miti_transcript, name)
    assert miti_transcript.Span.__module__ == "onolys_miti.transcript"
    for module in ("transcript_v1", "transcript_input", "transcript_txt"):
        assert importlib.util.find_spec(f"onolys_miti.{module}") is None
    assert not files("onolys_miti").joinpath("data/transcript.v1.schema.json").is_file()
