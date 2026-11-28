"""docs/reference/logging.md matches the code: every public error code is in its table,
the runbook points at the session id, and relative links resolve."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from onolys_api.adapters.error_map import PUBLIC_MESSAGES
from onolys_api.logs import API_FIELDS

ROOT = Path(__file__).resolve().parents[2]
LOGGING_MD = ROOT / "docs/reference/logging.md"
INFRA_MD = ROOT / "docs/reference/infra.md"
DOCS = [
    LOGGING_MD,
    INFRA_MD,
    ROOT / "docs/implementation/logging-and-phi.md",
    ROOT / "docs/reference/README.md",
]
pytestmark = pytest.mark.unit


def _table_codes(text: str) -> set[str]:
    """First-column backticked codes of the table under '## `error_code` table'."""
    section = text.split("## `error_code` table", 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"^\|\s*`([a-z_]+)`\s*\|", section, re.M))


def test_error_code_table_lists_every_public_message_code():
    codes = _table_codes(LOGGING_MD.read_text())
    assert set(PUBLIC_MESSAGES) <= codes, sorted(set(PUBLIC_MESSAGES) - codes)


def test_field_list_covers_allowlist_names():
    text = LOGGING_MD.read_text()
    # base allowlist read in a clean interpreter: engines add their own fields at import time
    base = json.loads(
        subprocess.check_output(
            [
                sys.executable,
                "-c",
                "import json;from onolys_engine_core.safe_log import ALLOWED_FIELDS as A;"
                "print(json.dumps(sorted(A)))",
            ],
            text=True,
        )
    )
    missing = sorted(f for f in {*base, *API_FIELDS} if f"`{f}`" not in text)
    assert not missing, missing


def test_runbook_reference_is_session_id():
    section = INFRA_MD.read_text().split("## Runbook: a user reports a failed session", 1)[1]
    section = section.split("\n## ", 1)[0]
    assert "session id" in section.split("\n\n", 1)[1][:600].lower()
    assert "shows a **reference id** (the `request_id`)" not in section
    assert "logging.md" in section
    assert "t10b-1795181702" in section  # verified 2026-11-20 REST example kept


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_relative_links_resolve(doc):
    for target in re.findall(r"\]\((?!https?:|#|mailto:)([^)#\s]+)", doc.read_text()):
        assert (doc.parent / target).exists(), f"{doc.name}: {target}"
