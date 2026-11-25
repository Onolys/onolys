"""The one-time allowlist import was retired: its source secret was deleted from onolys."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_stale_import_of_deleted_allowlist_secret_is_gone():
    assert not (ROOT / "eval-allowlist-import.tf").exists()
    for path in ROOT.glob("*.tf"):
        text = path.read_text()
        assert "projects/onolys/secrets/eval-allowed-emails-eval" not in text, path.name
        assert not any(ln.startswith("import {") for ln in text.splitlines()), path.name
