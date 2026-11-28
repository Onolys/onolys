"""The portable transcript model must work without importing an engine."""

import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_portable_model_imports_only_pydantic():
    source = Path(importlib.util.find_spec("onolys_engine_core.transcript_v1").origin)
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] == "pydantic" for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module.split(".")[0] == "pydantic"
