"""The admin image holds python, admin/auth and admin/backend only: no engines, protocols, config
or contract copies, and the sync targets the admin package."""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = (ROOT / "admin" / "backend" / "Dockerfile").read_text()
COPY_LINES = [ln for ln in DOCKERFILE.splitlines() if re.match(r"^\s*COPY\b", ln)]


@pytest.mark.parametrize("forbidden", ["protocols", "config", "docs/contracts"])
def test_no_forbidden_copies(forbidden):
    assert not [ln for ln in COPY_LINES if re.search(rf"(^|\s){re.escape(forbidden)}", ln)]


def test_no_engine_source_copies():
    # Only pyproject manifests of engines (needed to resolve the workspace lock) may be copied.
    for ln in COPY_LINES:
        if "engines/" in ln:
            assert ln.rstrip().endswith("pyproject.toml engines/" + ln.split("engines/")[1].split("/")[0] + "/pyproject.toml"), ln


def test_admin_sources_are_copied():
    assert any(re.search(r"COPY\s+admin/auth\s+admin/auth\s*$", ln) for ln in COPY_LINES)
    assert any(re.search(r"COPY\s+admin/backend\s+admin/backend\s*$", ln) for ln in COPY_LINES)


def test_uv_sync_targets_admin_package():
    syncs = re.findall(r"^RUN\s+uv sync.*$", DOCKERFILE, re.M)
    assert syncs and all("--package onolys-admin-backend" in s and "--frozen" in s for s in syncs)


def test_no_engine_env_vars():
    for var in ("ROUTES_FILE", "PAUDIT_PROTOCOLS_DIR", "IAUDIT_CONTRACTS_DIR"):
        assert var not in re.sub(r"^#.*$", "", DOCKERFILE, flags=re.M)


def test_safe_defaults_and_workdir():
    assert re.search(r"ENV=prod ADMIN_AUTH=on", DOCKERFILE)
    assert re.search(r"^WORKDIR\s+/app\s*$", DOCKERFILE, re.M)
