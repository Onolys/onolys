"""The shared engine package must remain independent of MITI."""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "onolys_engine_core"


def _imports_miti(source: str) -> bool:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            modules = [node.module or ""]
        else:
            continue
        if any(module.split(".")[0] == "onolys_miti" for module in modules):
            return True
    return False


@pytest.mark.parametrize(
    "source",
    [
        "import onolys_miti",
        "import onolys_miti.context as context",
        "from onolys_miti import errors",
        "from onolys_miti.errors import InputError",
    ],
)
def test_boundary_scanner_detects_miti_imports(source):
    assert _imports_miti(source)


def test_core_imports_no_miti_modules():
    sources = sorted(SRC.rglob("*.py"))
    assert sources, "the shared engine package must exist"
    bad = [str(path.relative_to(SRC)) for path in sources if _imports_miti(path.read_text())]
    assert not bad, bad
