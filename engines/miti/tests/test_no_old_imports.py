"""R1/D4: onolys_miti imports no old package (static scan plus a clean-interpreter import)."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[1] / "src" / "onolys_miti"
# built piecewise so the naming guard (which greps for these words) stays clean
OLD = (
    *(c + "udit" for c in ("pa", "ia", "ea")),
    "onolys_" + "core",
    "onolys_" + "evaluation",
    "onolys_" + "pa" + "udit",
)


def _imported(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module


def test_no_source_file_imports_an_old_package():
    bad = []
    for p in SRC.rglob("*.py"):
        for mod in _imported(ast.parse(p.read_text(encoding="utf-8"))):
            if mod.split(".")[0] in OLD:
                bad.append(f"{p.relative_to(SRC)}: {mod}")
    assert not bad, bad


def test_importing_the_passes_loads_no_old_package():
    code = (
        "import sys\n"
        "import onolys_miti.code_pass, onolys_miti.globals_pass, onolys_miti.prepare\n"
        "import onolys_miti.score, onolys_miti.result, onolys_miti.formula, onolys_miti.miti\n"
        f"old = {OLD!r}\n"
        "print(sorted(m for m in sys.modules if m.split('.')[0] in old))\n"
    )
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"
