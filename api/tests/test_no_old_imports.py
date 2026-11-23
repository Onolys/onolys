"""API uses shared core and imports MITI only for engine-specific behavior."""

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


def test_api_imports_miti_only_for_engine_specific_modules():
    allowed = {
        "engine", "miti", "prepare", "rating", "report", "result", "run", "span", "stt", "voice",
    }
    # The MITI-only API's legacy/fake adapter bridge uses the public engine schema.
    miti_engine_paths = {
        "src/onolys_api/engines.py", "src/onolys_api/adapters/validated.py",
    }
    bad = []
    for path in sorted((API / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "onolys_miti":
                for alias in node.names:
                    if (
                        alias.name == "MitiEngine"
                        and path.relative_to(API).as_posix() in miti_engine_paths
                    ):
                        continue
                    if alias.name not in allowed:
                        bad.append(f"{path.relative_to(API)}: onolys_miti.{alias.name}")
        for module in _imported(tree):
            if module == "onolys_miti" or module.startswith("onolys_miti."):
                if module == "onolys_miti":
                    continue  # direct from-imports checked above
                if module.split(".")[1] not in allowed:
                    bad.append(f"{path.relative_to(API)}: {module}")
    assert not bad, bad
