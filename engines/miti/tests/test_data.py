"""D3/D4: MITI data copied into the package loads and keeps today's pack hash."""

import hashlib
import json
from pathlib import Path

import yaml

PKG = Path(__file__).resolve().parents[1] / "src" / "onolys_miti"
DATA = PKG / "data"
# Current pack_hash (re-pinned after dropping dead reasons_audit config; also in the golden report fixture).
KNOWN_PACK_HASH = "d98e79648859d15e"


def _hash_paths():
    # Same file order as the old pack loader; rules.py lives next to the code (R1).
    return [
        DATA / "pack.yaml",
        PKG / "rules.py",
        DATA / "rating.schema.json",
        *sorted((DATA / "prompts").glob("*")),
        DATA / "report.yaml",
    ]


def test_pack_loads():
    pack = yaml.safe_load((DATA / "pack.yaml").read_text())
    assert pack["id"] == "miti" and pack["version"] == "4.2.1"
    assert pack["items"]
    assert yaml.safe_load((DATA / "report.yaml").read_text())
    assert json.loads((DATA / "rating.schema.json").read_text())
    assert (PKG / "rules.py").is_file()


def test_pack_hash_unchanged():
    h = hashlib.sha256()
    for p in _hash_paths():
        h.update(p.read_bytes())
    assert h.hexdigest()[:16] == KNOWN_PACK_HASH


def test_golden_report_carries_same_hash():
    rep = json.loads((DATA / "fixtures/evaluation/report_no_rating.json").read_text())
    assert rep["header"]["protocol"]["pack_hash"] == KNOWN_PACK_HASH


def test_data_files_present():
    for rel in (
        "prompts/code_system.md",
        "prompts/globals_system.md",
        "prompts/tips_system.md",
        "fixtures/expected.yaml",
        "fixtures/thresholds.yaml",
        "scenarios/scenario.schema.json",
    ):
        assert (DATA / rel).is_file(), rel


def test_tips_prompt_states_concrete_change_and_example_wording():
    text = (DATA / "prompts/tips_system.md").read_text()
    assert "one concrete change" in text
    assert "praise-only" in text
    assert "example wording" in text
    assert "ready to say" in text
