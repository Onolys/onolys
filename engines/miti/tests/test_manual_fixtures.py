"""Hand-coded synthetic examples check deterministic rules, never model accuracy."""

import importlib.util
from pathlib import Path

import pytest
import yaml

from onolys_miti import miti
from onolys_miti.score import apply_rules, count_instances

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fixture_audit", ROOT / "audit_report.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
FIXTURES = yaml.safe_load((audit.FIX / "expected.yaml").read_text())["fixtures"]


@pytest.mark.parametrize("name", ["batch_edge", "sparse_evidence"])
def test_hand_counts_match_manual_targets(name):
    expected = FIXTURES[name]
    transcript, _, prepared = audit.load_fixture(expected)
    source = audit.hand_instances(prepared, expected["utterances"])
    final, warnings = apply_rules(source, miti.MITI.data["rules"])
    actual = count_instances(final, audit.code_pass.count_codes())
    assert actual == expected["counts"]
    assert warnings == []
    assert set(expected["counts"]) == set(audit.code_pass.count_codes())
    assert set(expected["summaries"]) == {s["id"] for s in miti.MITI.data["summaries"]}
    turns = {t.id: t.text for t in transcript.turns}
    for global_spec in expected["globals"].values():
        assert global_spec["range"][0] <= global_spec["score"] <= global_spec["range"][1]
        for evidence in global_spec["evidence"]:
            assert evidence["quote"] in turns[evidence["turn_id"]]
    assert all("p." in reason or "pp." in reason
               for reason in expected["count_reasons"].values())
    for inst in source:
        turn = next(t for v in prepared.volleys for t in v.turns if t.id == inst.turn_id)
        assert turn.text[inst.start:inst.end] == inst.quote


def test_batch_edge_has_permission_across_25_26_and_facilitative_ack():
    expected = FIXTURES["batch_edge"]
    transcript, params, prepared = audit.load_fixture(expected)
    assert 1400 <= sum(len(t.text.split()) for t in transcript.turns) <= 1700
    batches = [r for r in audit.render_requests(prepared, params) if r.tier == "miti_code"]
    assert [r.unit for r in batches] == ["v1-v25", "v26-v27"]
    assert prepared.volleys[0].turns[0].id == "b01a"
    assert [t.id for t in prepared.volleys[0].turns] == ["b01a", "b01b"]
    assert prepared.volleys[24].turns[0].text == "May I offer a suggestion about fitting a short walk into your lunch break?"
    assert prepared.volleys[25].prev_other.text == "yeah"
    assert prepared.volleys[25].turns[0].id == "b26"


def test_sparse_evidence_has_hand_set_high_sst_without_sustain_talk():
    expected = FIXTURES["sparse_evidence"]
    assert expected["globals"]["sst"]["range"] == [4, 5]
    assert expected["globals"]["sst"]["score"] == 5
    assert "p.38" in expected["globals"]["sst"]["reason"]
    assert expected["globals"]["sst"]["evidence"] == []
    assert set(expected["globals"]) == {"cct", "sst", "partnership", "empathy"}


def test_audit_all_fixtures_have_no_persuasion_double_or_count_drift():
    rows = {r["fixture"]: r for r in audit.build_audit()["fixtures"]}
    assert {"batch_edge", "sparse_evidence"} <= rows.keys()
    assert rows["batch_edge"]["batch_count"] == 2
    assert rows["sparse_evidence"]["counts"] == FIXTURES["sparse_evidence"]["counts"]
    assert rows["batch_edge"]["summaries_with_hand_globals"]["total_mina"] == 0
    assert rows["batch_edge"]["summary_drift"]["total_mina"] == 0
    assert len(rows) == 5
    for row in rows.values():
        assert row["counts"] == row["target_counts"]
        assert all(d == 0 for d in row["count_drift"].values())
        assert row["persuasion_double_count_volleys"] == []


def test_generated_six_thousand_word_portion_has_disjoint_batches():
    import json

    from onolys_engine_core.transcript import Transcript, Turn

    from onolys_miti.prepare import prepare

    # Size stress belongs here, not in a large committed transcript fixture.
    turns = [
        Turn(id=f"large{i}", speaker="B" if i % 2 == 0 else "A",
             text=" ".join(["synthetic"] * 50), start_ms=i * 12_000,
             end_ms=(i + 1) * 12_000)
        for i in range(120)
    ]
    transcript = Transcript(turns=turns, language="en")
    params = {"speaker_map": {"subject": "A", "other": "B"}, "change_goal": "walk at lunch"}
    prepared = prepare(transcript, params, coded_span={"start_ms": 0, "end_ms": 1_440_000})
    assert sum(len(t.text.split()) for t in turns) == 6000
    assert prepared.duration_ms == 24 * 60_000
    batches = [json.loads(r.user)["volleys"] for r in audit.render_requests(prepared, params)
               if r.tier == "miti_code"]
    assert [len(b) for b in batches] == [25, 25, 10]
    batch_turns = [{t["turn_id"] for v in b for t in v["clinician_turns"]} for b in batches]
    assert all(a.isdisjoint(b) for i, a in enumerate(batch_turns) for b in batch_turns[i + 1:])
    assert set.union(*batch_turns) == {t.id for t in turns if t.speaker == "A"}
