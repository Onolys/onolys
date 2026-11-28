"""Shared transcript contracts must work without importing an engine."""

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


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

