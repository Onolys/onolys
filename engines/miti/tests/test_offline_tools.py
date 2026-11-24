"""Offline maintenance uses real preparation, rules and rendered request content."""

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_audit_covers_every_hand_fixture_with_real_requests():
    audit = load("audit_report", ROOT / "audit_report.py")
    report = audit.build_audit()
    assert report == audit.build_audit()
    assert report["schema"] == 1
    assert report["stages"] == ["code", "globals"]
    assert "not accuracy" in report["limits"]
    expected = yaml.safe_load((audit.FIX / "expected.yaml").read_text())
    assert {r["fixture"] for r in report["fixtures"]} == set(expected["fixtures"])
    good = report["fixtures"][0]
    assert good["batch_limit"] == 25
    assert good["batch_count"] == (good["volley_count"] + 24) // 25
    assert good["request_words"]["total"] == sum(good["request_words"][s] for s in report["stages"])
    assert good["counts"] == good["target_counts"]
    assert all(d == 0 for d in good["count_drift"].values())
    assert good["persuasion_double_count_volleys"] == []
    coverage = good["coverage"]
    assert coverage["clinician_words"] >= coverage["covered_words"] > 0
    assert coverage["residual_words"] == coverage["clinician_words"] - coverage["covered_words"]
    assert sum(v["residual_words"] for v in coverage["volleys"]) == coverage["residual_words"]


def test_regen_is_byte_and_mtime_noop_on_current_goldens():
    regen = load("regen_goldens", ROOT / "tools" / "regen_goldens.py")
    paths = [*regen.GOLD.glob("*.json"), regen.GOLDEN_TEST, regen.DATA_TEST, regen.PACK_TEST, regen.REPORT]
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
    assert regen.regenerate() == []
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}


def test_regen_rejects_changed_volley_ids_before_writing(tmp_path):
    regen = load("regen_goldens", ROOT / "tools" / "regen_goldens.py")
    from onolys_engine_core.llm.fixture_client import FixtureClient

    requests = regen.golden_requests()
    response = {"volleys": [{"volley_id": "v999", "utterances": []}]}
    override = tmp_path / "responses.json"
    override.write_text(json.dumps({requests[0].call_tag: response}))
    before = {p: p.read_bytes() for p in regen.GOLD.glob("*.json")}
    with pytest.raises(ValueError, match="volley"):
        regen.regenerate(responses=override)
    assert before == {p: p.read_bytes() for p in regen.GOLD.glob("*.json")}
    assert len(FixtureClient.key_for(requests[0])) == 64


def test_regen_rekeys_changed_requests_preserving_stub_bytes(tmp_path, monkeypatch):
    from dataclasses import replace

    from onolys_engine_core.llm.fixture_client import FixtureClient

    regen = load("regen_goldens", ROOT / "tools" / "regen_goldens.py")
    for attr in ("GOLD", "GOLDEN_TEST", "DATA_TEST", "PACK_TEST", "REPORT"):
        original = getattr(regen, attr)
        target = tmp_path / attr
        if original.is_dir():
            target.mkdir()
            for path in original.glob("*.json"):
                (target / path.name).write_bytes(path.read_bytes())
        else:
            target.write_bytes(original.read_bytes())
        monkeypatch.setattr(regen, attr, target)
    old = sorted(p.read_bytes() for p in regen.GOLD.glob("*.json"))
    requests = [
        replace(r, system=r.system + " Changed instruction.") for r in regen.golden_requests()
    ]
    monkeypatch.setattr(regen, "golden_requests", lambda: requests)
    assert regen.regenerate()
    assert sorted(p.read_bytes() for p in regen.GOLD.glob("*.json")) == old
    assert {p.stem for p in regen.GOLD.glob("*.json")} == {
        FixtureClient.key_for(r) for r in requests
    }
    assert regen.regenerate() == []


def test_coverage_counts_union_including_uncoded_spans():
    from types import SimpleNamespace

    from onolys_engine_core.transcript import Turn

    from onolys_miti.coverage import coverage
    from onolys_miti.prepare import Prepared, Volley

    audit = load("audit_report", ROOT / "audit_report.py")
    turn = Turn(id="t1", speaker="A", text="one two three four")
    prepared = Prepared([], [Volley("v1", [turn])])
    # Overlap must not double-count 'two'; the last word is uncovered.
    spans = [
        SimpleNamespace(turn_id="t1", start=0, end=7),
        SimpleNamespace(turn_id="t1", start=4, end=13),
    ]
    result = audit.coverage(prepared, spans)
    assert result == coverage(prepared.volleys, spans)
    assert result["clinician_words"] == 4
    assert result["covered_words"] == 3
    assert result["residual_words"] == 1
