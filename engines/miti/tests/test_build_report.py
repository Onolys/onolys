"""`build_report_no_rating` assembly (PRD R3): schema validity, no-rating shape, run_info
renames, parity with the golden fixture."""

import json

import pytest
import yaml
from _report_fixtures import SCHEMA_PATH, inputs, load
from jsonschema import Draft202012Validator

from onolys_miti import miti
from onolys_miti.build import build_report_no_rating
from onolys_miti.compare import template_strings
from onolys_miti.hashes import evaluation_prompt_hashes
from onolys_miti.report import Warning
from onolys_miti.result import CodedSpan
from onolys_miti.run_info import RunInfo
from onolys_miti.tone import load_report_config, tone_rules

pytestmark = pytest.mark.unit


def doc(**over):
    return json.loads(build_report_no_rating(**{**inputs(), **over}).model_dump_json())


def test_validates_schema():
    validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    errors = list(validator.iter_errors(doc()))
    assert not errors, errors[:3]


def test_matches_golden_except_volatile_and_run_info():
    got, want = doc(), load("report_no_rating.json")
    for d in (got, want):
        for k in ("created_at", "request_id", "run_info"):
            d.pop(k)
    assert got == want


def test_run_info_renames():
    ri = doc()["run_info"]
    assert set(ri) == {"evaluation", "miti"}
    assert ri["evaluation"]["engine"] == "miti" and ri["miti"]["engine"] == "miti"
    golden = load("report_no_rating.json")["run_info"]
    assert ri["evaluation"]["pack"] == golden["evaluation"]["pack"]
    assert ri["evaluation"]["prompt_hashes"] == golden["evaluation"]["prompt_hashes"]
    assert set(ri["evaluation"]) - {"span"} == set(golden["evaluation"])


def test_layout_follows_report_yaml():
    want = yaml.safe_load((miti.DATA_DIR / "report.yaml").read_text(encoding="utf-8"))["sections"]
    got = doc()["layout"]
    assert [e["section"] for e in got] == [s["id"] for s in want]
    assert [e["title"] for e in got] == [s["label"] for s in want]


def test_disabled_section_left_out_of_layout():
    from dataclasses import replace

    cfg = load_report_config(miti.DATA_DIR / "report.yaml")
    secs = [replace(s, enabled=False) if s.id == "tips" else s for s in cfg.sections]
    r = build_report_no_rating(**inputs(), cfg=replace(cfg, sections=secs))
    assert "tips" not in [e.section for e in r.layout]


def test_no_rating_nulls_and_skipped():
    d = doc()
    assert d["aggregates"] == {"globals_compared": 0, "avg_abs_global_difference": None,
                               "within_one_share": None, "counts_flagged": None}
    assert d["reasons_audit"] == {"status": "skipped", "items": []}
    assert d["header"]["has_clinician_rating"] is False
    assert d["header"]["rating_coverage"] == {"rated": 0, "total": 14}
    assert all(r["clinician"]["value"] is None for r in d["scorecard"])
    assert all(r["diff"]["status"] == "not_rated" for r in d["scorecard"])
    assert len(d["tips"]) >= 3 and d["method"]["statement"]
    assert all(s["clinician"] is None for s in d["summaries"])


def test_explanations_are_onolys_only():
    d = doc()
    for g in d["globals"]:
        assert g["explanation"]["body"][0].startswith("Onolys scored ")
        assert g["explanation"]["clinician_support_lines"] == []
        assert g["clinician"] == {"value": None, "reason": None, "example": None}
    for b in d["behaviours"]:
        assert b["explanation"]["body"] == [f"Onolys counted {b['onolys_count']['mean']:g}."]
        assert b["clinician_count"] is None


def test_header_fields():
    kw = inputs()
    h = doc()["header"]
    assert h["stt"] == json.loads(kw["transcript"].stt_run.model_dump_json())
    assert h["preset"] == "fixture" and h["code_version"] == "fixture"
    assert h["protocol"]["pack_hash"] == miti.MITI.hash
    assert h["n_runs"] == kw["result"].n_runs
    assert h["subject_speaker"] == kw["result"].subject_speaker


def test_text_only_transcript_has_null_stt():
    kw = inputs()
    kw["transcript"] = kw["transcript"].model_copy(update={"stt_run": None})
    r = build_report_no_rating(**kw)
    assert r.header.stt is None and r.run_info.evaluation.stt is None


def test_span_reaches_header():
    kw = inputs()
    span = CodedSpan(from_s=60, to_s=1260)
    result = kw["result"].model_copy(update={"coded_span": span})
    r = build_report_no_rating(**{**kw, "result": result})
    assert r.header.coded_span.from_s == 60 and r.header.coded_span.to_s == 1260


def test_method_from_definition_and_not_official():
    cfg = load_report_config(miti.DATA_DIR / "report.yaml")
    m = doc()["method"]
    assert m["statement"] == cfg.method.statement
    assert m["not_official_miti_coding"] is True
    assert m["limits"][:-1] == cfg.method.limits
    assert "not an official coding" in m["limits"][-1]
    assert not tone_rules().lint(m["limits"][-1])


def test_extra_warnings_passed_through_and_deduped():
    w = [Warning(code="fewer_tips"), Warning(code="fewer_tips")]
    assert [x["code"] for x in doc(warnings=w)["warnings"]].count("fewer_tips") == 1


def test_tone_violating_reason_withheld_with_warning():
    kw = inputs()
    result = kw["result"]
    run = result.results[0]
    g = next(iter(run.globals))
    bad = run.globals[g].model_copy(update={"reason": "That was a mistake."})
    run2 = run.model_copy(update={"globals": {**run.globals, g: bad}})
    result = result.model_copy(update={"results": [run2, *result.results[1:]]})
    d = doc(result=result)
    assert {"code": "reason_withheld_tone", "item_id": g} in d["warnings"]
    entry = next(x for x in d["globals"] if x["item_id"] == g)
    assert "That was a mistake." not in entry["explanation"]["body"]


def test_never_truncates_instances():
    kw = inputs()
    r = build_report_no_rating(**kw)
    res = kw["result"]
    run = next(x for x in res.results if x.run_index == res.aggregate.representative_run)
    for b in r.behaviours:
        assert b.instances_total == len(b.instances)
    assert sum(b.instances_total for b in r.behaviours) == sum(
        1 for i in run.instances if i.counted)


def test_scorecard_covers_definition_items():
    d = doc()
    assert [r["item_id"] for r in d["scorecard"]][:4] == ["cct", "sst", "partnership", "empathy"]
    assert len(d["scorecard"]) == 14 and len(d["globals"]) == 4 and len(d["behaviours"]) == 10
    assert len(d["summaries"]) == 6


def test_run_info_has_no_text_and_core_shape():
    d = doc()
    RunInfo.model_validate(d["run_info"]["evaluation"])
    RunInfo.model_validate(d["run_info"]["miti"])
    blob = json.dumps(d["run_info"])
    assert inputs()["transcript"].turns[0].text not in blob
    assert d["run_info"]["evaluation"]["pack"]["hash"] == d["header"]["protocol"]["pack_hash"]


def test_prompt_hashes_cover_tips_prompt_and_engine_templates():
    h = evaluation_prompt_hashes()
    assert "tips_system.md" in h
    assert {"engine:tips_output_format", "engine:compare_templates"} <= set(h)
    assert all(len(v) == 16 for v in h.values())
    assert doc()["run_info"]["evaluation"]["prompt_hashes"] == h


def test_compare_template_hash_tracks_templates(monkeypatch):
    import onolys_miti.compare as c

    before = evaluation_prompt_hashes()["engine:compare_templates"]
    monkeypatch.setattr(c, "SCORED_ONLY", "changed {o}")
    assert template_strings() != []
    assert evaluation_prompt_hashes()["engine:compare_templates"] != before
