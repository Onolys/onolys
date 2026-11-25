"""R6a: temporary import block for the eval allowlist secret exists; no email-like strings or secret values in it."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}")


def test_import_block_targets_allowlist_secret():
    text = (ROOT / "eval-allowlist-import.tf").read_text()
    assert "import {" in text
    assert 'id = "projects/onolys/secrets/eval-allowed-emails-eval"' in text
    assert "google_secret_manager_secret.eval_allowed_emails" in text


def test_no_email_like_strings_or_values():
    for p in [ROOT / "eval-allowlist-import.tf", Path(__file__)]:
        assert not EMAIL.search(p.read_text().replace(EMAIL.pattern, "")), p.name
