"""R6: no old engine/package name survives anywhere in engines/miti (src, tests, data, config).

Data yaml comments are covered too (pack.yaml/report.yaml included, comments and all).
"""

import re
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
OLD = re.compile(r"paudit|iaudit|eaudit|onolys_core|onolys_evaluation|interview evidence", re.IGNORECASE)
SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "dist"}
SELF = Path(__file__).resolve()


def _files():
    for p in PKG_ROOT.rglob("*"):
        if p.is_file() and not (set(p.relative_to(PKG_ROOT).parts) & SKIP_DIRS) and p != SELF:
            yield p


def test_no_old_names_in_paths_or_content():
    bad = []
    for p in _files():
        rel = p.relative_to(PKG_ROOT).as_posix()
        if OLD.search(rel):
            bad.append(f"{rel}: path")
            continue
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(lines, 1):
            if OLD.search(line):
                bad.append(f"{rel}:{n}")
    assert not bad, f"old names found: {bad}"
