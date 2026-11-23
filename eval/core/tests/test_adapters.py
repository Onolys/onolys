"""Lean report projection against the engine's synthetic golden fixture."""
import json
from importlib.resources import files

import pytest
from onolys_eval.adapters import miti_lean_scores
from onolys_eval.metrics import compare
from onolys_miti.report import Report
from pydantic import ValidationError


@pytest.fixture
def report():
    return json.loads(files("onolys_miti").joinpath(
        "data/fixtures/evaluation/report_no_rating.json").read_text())


@pytest.mark.parametrize("typed", [False, True])
def test_golden_report_maps_exact_authorable_values(report, typed):
    validated = Report.model_validate(report)
    result = miti_lean_scores(validated if typed else report)
    assert result.model_dump() == {
        "counts": {"gi": 1, "persuade": 0, "persuade_permission": 1,
                   "question": 6, "sr": 2, "cr": 4, "affirm": 2,
                   "seek_collab": 2, "emphasize_autonomy": 2, "confront": 0},
        "globals": {"cct": 4, "sst": 4, "partnership": 5, "empathy": 4},
        "summaries": {},
    }


def test_fractional_multirun_mean_is_preserved_for_comparison(report):
    report["behaviours"][3]["onolys_count"]["mean"] = 2.5
    result = miti_lean_scores(report)
    assert result.counts["question"] == 2.5
    comparison = compare(result, result)
    assert comparison["summaries"]["reflection_question_ratio"]["ours"] == 6 / 2.5


def test_projection_ignores_derived_scores_evidence_metadata_and_tips(report):
    expected = miti_lean_scores(report)
    # None of these fields may contribute values to metrics.
    for field in ("scorecard", "summaries", "tips", "header", "run_info"):
        report[field] = {"unscored": "synthetic sentinel"}
    for entry in report["behaviours"]:
        entry["clinician_count"] = 999
        entry["instances"] = []
        entry["instances_total"] = 999
        entry["onolys_count"]["values"] = [999]
    for entry in report["globals"]:
        entry["clinician"]["value"] = 1
    actual = miti_lean_scores(report)
    assert actual == expected
    assert compare(expected, actual)["summaries"]["pct_cr"]["ours"] == 4 / 6


@pytest.mark.parametrize("section,key", [("behaviours", "onolys_count"),
                                        ("globals", "onolys")])
def test_missing_nested_field_fails_loudly(report, section, key):
    del report[section][0][key]
    with pytest.raises(KeyError, match=key):
        miti_lean_scores(report)


@pytest.mark.parametrize("section", ["behaviours", "globals"])
def test_missing_or_duplicate_item_fails_loudly(report, section):
    removed = report[section].pop()
    with pytest.raises(ValidationError):
        miti_lean_scores(report)
    report[section].extend([removed, removed])
    with pytest.raises(ValueError, match="duplicate"):
        miti_lean_scores(report)


@pytest.mark.parametrize("section", ["behaviours", "globals"])
def test_unknown_item_and_missing_section_fail_loudly(report, section):
    report[section][0]["item_id"] = "unknown"
    with pytest.raises(ValidationError):
        miti_lean_scores(report)
    del report[section]
    with pytest.raises(KeyError, match=section):
        miti_lean_scores(report)


@pytest.mark.parametrize("value", [None, True, -1.0, float("nan"), float("inf")])
def test_unrepresentable_count_is_rejected_without_rounding(report, value):
    report["behaviours"][0]["onolys_count"]["mean"] = value
    with pytest.raises(ValidationError):
        miti_lean_scores(report)


def test_missing_global_score_does_not_default(report):
    report["globals"][0]["onolys"]["score"] = None
    with pytest.raises(ValidationError):
        miti_lean_scores(report)
