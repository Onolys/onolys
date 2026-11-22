"""R1/D2: api imports `onolys_miti` only. No api src or test file imports an old package."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

API = Path(__file__).resolve().parents[1]
# built piecewise so this file never spells an old package as one literal
OLD = (
    "onolys_" + "core",
    "onolys_" + "evaluation",
    "onolys_" + "pa" + "udit",
    "pa" + "udit",
    "ea" + "udit",
    "ia" + "udit",
)


def _imported(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module


@pytest.mark.parametrize("folder", ["src", "tests"])
def test_no_file_imports_an_old_package(folder):
    bad = []
    for p in sorted((API / folder).rglob("*.py")):
        for mod in _imported(ast.parse(p.read_text(encoding="utf-8"))):
            if mod.split(".")[0] in OLD:
                bad.append(f"{p.relative_to(API)}: {mod}")
    assert not bad, bad
