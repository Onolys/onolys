"""Lean report projection against the engine's synthetic golden fixture."""
import json
from importlib.resources import files
from pathlib import Path

import pytest
from onolys_eval.adapters import miti_lean_scores, oneshot_scores
from onolys_eval.metrics import Scores, compare
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


@pytest.fixture
def oneshot_output():
    # Actual recorded provider reply for the synthetic good-practice session.
    recording = (Path(__file__).resolve().parents[3] / "engines/oneshot/tests/fixtures/recorded"
                 / "78eccc44b0064774023ebe2e5bf374016f16e816a4013df04b34f49a4a440b15.json")
    return json.loads(recording.read_text())


def test_recorded_oneshot_projects_to_hand_built_scores(oneshot_output):
    expected = Scores(
        counts={"gi": 1, "persuade": 0, "persuade_permission": 1,
                "question": 6, "sr": 5, "cr": 1, "affirm": 2,
                "seek_collab": 2, "emphasize_autonomy": 2, "confront": 0},
        globals={"cct": 4, "sst": 4, "partnership": 4, "empathy": 4},
    )
    assert oneshot_scores(oneshot_output) == expected
    oneshot_output["tips"] = []
    assert oneshot_scores(oneshot_output) == expected


@pytest.mark.parametrize("sr,cr,question", [(5, 1, 4), (0, 0, 0), (2, 4, 0)])
def test_lean_and_oneshot_share_scores_and_summary_formulas(
    report, oneshot_output, sr, cr, question,
):
    oneshot_output["counts"].update(sr=sr, cr=cr, question=question)
    for entry in report["behaviours"]:
        entry["onolys_count"]["mean"] = oneshot_output["counts"][entry["item_id"]]
    for entry in report["globals"]:
        entry["onolys"]["score"] = oneshot_output["globals"][entry["item_id"]]
    lean, oneshot = miti_lean_scores(report), oneshot_scores(oneshot_output)
    assert lean == oneshot
    # Supplied summaries cannot override the common formula used for gold and engines.
    gold = Scores(counts=oneshot.counts, globals=oneshot.globals,
                  summaries={"pct_cr": 999, "reflection_question_ratio": 999})
    assert compare(gold, lean) == compare(gold, oneshot)
    summaries = compare(gold, oneshot)["summaries"]
    for key, expected in {
        "pct_cr": cr / (sr + cr) if sr + cr else None,
        "reflection_question_ratio": (sr + cr) / question if question else None,
    }.items():
        assert summaries[key] == {"gold": expected, "ours": expected,
                                  "diff": 0 if expected is not None else None,
                                  "abs_diff": 0 if expected is not None else None}


@pytest.mark.parametrize("section", [None, "counts", "globals", "tip"])
@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_oneshot_missing_or_extra_fields_fail_clearly(oneshot_output, section, mutation):
    target = (oneshot_output["tips"][0] if section == "tip" else
              oneshot_output[section] if section else oneshot_output)
    if mutation == "missing":
        key = next(iter(target))
        del target[key]
        message = "Field required" if section in {None, "tip"} else "at least"
    else:
        target["unexpected"] = 99
        message = "Extra inputs" if section in {None, "tip"} else "Input should be"
    with pytest.raises(ValidationError, match=message):
        oneshot_scores(oneshot_output)


@pytest.mark.parametrize("value", [None, True, -1, 1.5, 2.0, "2", float("nan"), float("inf")])
def test_oneshot_counts_are_strict_integers_without_rounding(oneshot_output, value):
    oneshot_output["counts"]["question"] = value
    with pytest.raises(ValidationError, match="counts.question"):
        oneshot_scores(oneshot_output)


@pytest.mark.parametrize("value", [None, True, 0, 6, 2.5, "4"])
def test_oneshot_globals_are_strict_ratings(oneshot_output, value):
    oneshot_output["globals"]["empathy"] = value
    with pytest.raises(ValidationError, match="globals.empathy"):
        oneshot_scores(oneshot_output)


@pytest.mark.parametrize("field,value", [("rank", 0), ("rank", True),
                                         ("item_id", "unknown"),
                                         ("observation", None)])
def test_oneshot_tips_are_validated_even_though_unscored(oneshot_output, field, value):
    oneshot_output["tips"][0][field] = value
    with pytest.raises(ValidationError, match="tips.0"):
        oneshot_scores(oneshot_output)
