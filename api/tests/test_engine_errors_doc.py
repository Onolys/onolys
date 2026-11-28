"""Doc consistency of the engine errors: the public-api "Engine errors" section lists exactly the codes
`to_public` can return, and the staging results record has a line for each acceptance check."""

import re
from pathlib import Path

from onolys_api.adapters.error_map import KIND_BY_CODE, PUBLIC_MESSAGES

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_API = ROOT / "docs/reference/public-api.md"
STAGING = ROOT / "docs/reference/staging-e2e.md"


def _section(text: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert m, f"missing section: {heading}"
    return m.group(1)


def test_engine_errors_section_lists_exactly_the_to_public_codes():
    section = _section(PUBLIC_API.read_text(), "Engine errors")
    rows = [ln for ln in section.splitlines() if ln.startswith("| `")]
    documented = {re.match(r"\| `([a-z_]+)`", ln).group(1) for ln in rows}
    assert len(rows) == len(documented), "a code is listed twice"
    assert documented == set(PUBLIC_MESSAGES)


def test_engine_errors_table_lists_every_kind_by_code_code_with_its_kind():
    section = _section(PUBLIC_API.read_text(), "Engine errors")
    kinds = {}
    for ln in section.splitlines():
        m = re.match(r"\| `([a-z_]+)` \|.*\| `(transient|permanent_internal|user_file)` \|", ln)
        if m:
            kinds[m.group(1)] = m.group(2)
    assert kinds == dict(KIND_BY_CODE)


def test_engine_errors_table_links_logging_and_back():
    assert "logging.md#error_code-table" in PUBLIC_API.read_text()
    assert "public-api.md#engine-errors" in (ROOT / "docs/reference/logging.md").read_text()


def test_staging_record_has_a_result_for_each_acceptance_check():
    section = _section(STAGING.read_text(), "Acceptance sweep (SP09 AC4-AC11)")
    found = set(re.findall(r"^\| AC(\d+) \|", section, re.M))
    assert {str(n) for n in range(4, 12)} <= found
