"""No old engine names survive in api/src, api/tests, api/README.md or config (SP02 D6/D11)."""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
OLD = re.compile("paudit|iaudit|eaudit|onolys_core|onolys_evaluation", re.IGNORECASE)
# Legitimate keeps (GCP project ids, Terraform-state buckets): none exist in these trees today.
ALLOW: set[str] = set()
TEXT = {".py", ".yaml", ".yml", ".json", ".md", ".toml", ".txt", ".sh", ".cfg", ".ini", ""}


def _files():
    yield ROOT / "api/README.md"
    for sub in ("api/src", "api/tests", "config"):
        for p in (ROOT / sub).rglob("*"):
            if p.is_file() and p.suffix in TEXT and "__pycache__" not in p.parts:
                yield p


def test_no_old_engine_names():
    me = Path(__file__).resolve()
    hits = []
    for p in _files():
        if p == me:
            continue
        for n, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
            for m in OLD.findall(line):
                if m.lower() not in ALLOW:
                    hits.append(f"{p.relative_to(ROOT)}:{n}: {line.strip()[:90]}")
    assert not hits, "\n".join(hits)
