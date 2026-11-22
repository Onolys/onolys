"""R6: no old engine/package name survives anywhere in engines/miti (src, tests, data, config).

Exception (D3): the pack hash covers pack.yaml and report.yaml byte for byte, and each carries
one old name in a comment. Editing them would change the hash, so they are allowed to contain
the old names in `#` comment lines only, nowhere else.
"""

import re
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[1]
OLD = re.compile(r"paudit|iaudit|eaudit|onolys_core|onolys_evaluation", re.IGNORECASE)
SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "dist"}
SELF = Path(__file__).resolve()
# Hash-covered data files: old names tolerated in comment lines only.
HASHED_COMMENT_ONLY = {
    "src/onolys_miti/data/pack.yaml",
    "src/onolys_miti/data/report.yaml",
}


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
                if rel in HASHED_COMMENT_ONLY and line.lstrip().startswith("#"):
                    continue
                bad.append(f"{rel}:{n}")
    assert not bad, f"old names found: {bad}"


@pytest.mark.parametrize("rel", sorted(HASHED_COMMENT_ONLY))
def test_hashed_exceptions_exist(rel):
    # keeps the allowlist honest: drop an entry once the file no longer needs it
    text = (PKG_ROOT / rel).read_text(encoding="utf-8")
    assert OLD.search(text), f"{rel} has no old name any more; remove it from the allowlist"
