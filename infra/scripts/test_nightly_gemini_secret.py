"""Offline guards: the live (paid) Gemini check and its legacy identity are gone.

Use only the standard library so this runs in the minimal infra CI environment.
The live test stays runnable manually: api/tests/test_live_real_mode.py -m live.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
REMOVED = (
    "api-real-mode",
    "NIGHTLY_LEGACY_GEMINI",
    "NIGHTLY_WIF_PROVIDER",
    "NIGHTLY_GEMINI_SA",
    "test_live_real_mode",
    "-m live",
)


def test_nightly_workflow_has_no_live_gemini_job():
    text = (ROOT / ".github/workflows/nightly.yml").read_text()
    for needle in REMOVED:
        assert needle not in text, needle
    jobs = re.search(r"^jobs:\n(.*)", text, re.M | re.S)[1]
    assert re.findall(r"^  ([\w-]+):", jobs, re.M) == [
        "full-offline", "api-nightly", "web-campaigns", "api-emulator-matrix", "browser-matrix",
    ]
    assert "id-token" not in text


def test_no_workflow_consumes_nightly_identity():
    for path in (ROOT / ".github/workflows").glob("*.y*ml"):
        text = path.read_text()
        assert "NIGHTLY_WIF_PROVIDER" not in text, path
        assert "NIGHTLY_GEMINI_SA" not in text, path


def test_nightly_identity_terraform_is_removed():
    assert not (ROOT / "infra/nightly.tf").exists()
    for path in (ROOT / "infra").glob("*.tf"):
        text = path.read_text()
        for needle in ("nightly_gemini", "github-nightly", "workload_identity_pool.nightly", "nightly_wif_provider"):
            assert needle not in text, (path, needle)


def test_live_test_file_stays_for_manual_runs():
    assert (ROOT / "api/tests/test_live_real_mode.py").exists()
