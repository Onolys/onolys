"""Synthetic engine-independent scoring, with no session text or external services."""
import json
from importlib.resources import files
from pathlib import Path

import pytest
import yaml
from onolys_eval.gold import COUNT_IDS, GLOBAL_IDS, compute_summaries
from onolys_eval.metrics import Scores, aggregate, compare
from onolys_miti.formula import evaluate
from pydantic import ValidationError


def scores(*, counts=None, globals=None, summaries=None):
    return Scores(counts=dict.fromkeys(COUNT_IDS, 0) | (counts or {}),
                  globals=dict.fromkeys(GLOBAL_IDS, 3) | (globals or {}),
                  summaries=summaries or {})


def test_compare_signed_absolute_and_json_contract():
    result = compare(scores(counts={"question": 2}),
                     scores(counts={"question": 5}, globals={"cct": 1}))
    assert result["schema"] == "compare.v1"
    assert result["counts"]["question"] == {"gold": 2, "ours": 5, "diff": 3, "abs_diff": 3}
    assert result["globals"]["cct"] == {"gold": 3, "ours": 1, "diff": -2, "abs_diff": 2}
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    assert any("consensus coder" in note for note in result["notes"])
    assert any("volley" in note and "row" in note for note in result["notes"])


def test_summary_recomputation_uses_pack_on_both_sides_without_mutation():
    gold = scores(counts={"question": 2, "sr": 1, "cr": 3},
                  summaries={"pct_cr": 999, "technical": 999})
    ours = scores(counts={"question": 4, "sr": 3, "cr": 1},
                  globals={"cct": 1}, summaries={"pct_cr": 999})
    pack = yaml.safe_load(files("onolys_miti").joinpath("data/pack.yaml").read_text())
    result = compare(gold, ours)
    for item in pack["summaries"]:
        for side, value in (("gold", gold), ("ours", ours)):
            expected = evaluate(item["expr"], value.counts | value.globals)
            assert result["summaries"][item["id"]][side] == expected
    assert result["summaries"]["pct_cr"]["diff"] == -.5
    assert result["summaries"]["reflection_question_ratio"]["diff"] == -1
    assert gold.summaries["pct_cr"] == 999


def test_aggregate_mae_bias_and_inclusive_within_one():
    baseline = scores(counts={"question": 2, "sr": 1, "cr": 3})
    first = compare(baseline, scores(counts={"question": 5, "sr": 1, "cr": 3},
                                     globals={"cct": 2, "empathy": 1}))
    second = compare(baseline, scores(counts={"question": 1, "sr": 1, "cr": 3},
                                      globals={"cct": 5}))
    result = aggregate([first, second])
    assert result["n"] == 2
    assert result["counts"]["question"] == {"mae": 2, "mean_bias": 1, "n": 2}
    assert result["globals"]["cct"] == {
        "mae": 1.5, "mean_bias": .5, "n": 2,
        "within_1": {"n": 1, "total": 2, "fraction": .5}}
    assert result["globals"]["partnership"]["within_1"]["fraction"] == 1
    assert result["globals"]["empathy"]["within_1"]["fraction"] == .5
    assert result["summaries"]["technical"] == {"mae": .75, "mean_bias": .25, "n": 2}
    assert json.loads(json.dumps(result, allow_nan=False)) == result


@pytest.mark.parametrize("gold,ours", [
    (scores(), scores(counts={"question": 2, "cr": 1})),
    (scores(counts={"question": 2, "cr": 1}), scores()),
    (scores(), scores()),
])
def test_nulls_skip_mae_and_bias_and_explicitly_count_pairs(gold, ours):
    invalid = compare(gold, ours)
    for key in ("pct_cr", "reflection_question_ratio"):
        assert invalid["summaries"][key]["diff"] is None
        assert invalid["summaries"][key]["abs_diff"] is None
        assert aggregate([invalid])["summaries"][key] == {"mae": None, "mean_bias": None, "n": 0}
    valid = compare(scores(counts={"question": 2, "cr": 1}),
                    scores(counts={"question": 2, "sr": 1, "cr": 1}))
    assert aggregate([invalid, valid])["summaries"]["pct_cr"] == {
        "mae": .5, "mean_bias": -.5, "n": 1}


def test_empty_aggregate_has_stable_keys_and_zero_samples():
    result = aggregate([])
    assert result["n"] == 0
    assert set(result["counts"]) == set(COUNT_IDS)
    assert set(result["globals"]) == set(GLOBAL_IDS)
    assert result["globals"]["cct"] == {
        "mae": None, "mean_bias": None, "n": 0,
        "within_1": {"n": 0, "total": 0, "fraction": None}}
    assert result["summaries"]["pct_cr"]["n"] == 0


@pytest.mark.parametrize("counts,undefined,defined", [
    ({"question": 2}, "pct_cr", "reflection_question_ratio"),
    ({"sr": 1}, "reflection_question_ratio", "pct_cr"),
])
def test_each_zero_denominator_is_skipped_independently(counts, undefined, defined):
    result = aggregate([compare(scores(counts=counts), scores(counts=counts))])
    assert result["summaries"][undefined] == {"mae": None, "mean_bias": None, "n": 0}
    assert result["summaries"][defined] == {"mae": 0, "mean_bias": 0, "n": 1}


def test_metrics_and_shared_summary_helper_do_not_read_files(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("scoring must not read files")
    monkeypatch.setattr(Path, "read_text", forbidden)
    gold = scores(counts={"question": 2, "cr": 1})
    assert compute_summaries(gold.counts, gold.globals)["pct_cr"] == 1
    assert aggregate([compare(gold, gold)])["counts"]["question"]["mae"] == 0


@pytest.mark.parametrize("group,key,value", [
    ("counts", "question", -1), ("counts", "question", True),
    ("counts", "question", 1.5), ("counts", "extra", 1),
    ("globals", "cct", 0), ("globals", "cct", 6),
    ("globals", "cct", True), ("summaries", "pct_cr", float("nan")),
    ("summaries", "pct_cr", float("inf")),
])
def test_scores_reject_invalid_scores(group, key, value):
    data = scores().model_dump()
    data[group][key] = value
    with pytest.raises(ValidationError):
        Scores(**data)


@pytest.mark.parametrize("group,key", [("counts", "question"), ("globals", "cct")])
def test_scores_require_all_authorable_keys(group, key):
    data = scores().model_dump()
    del data[group][key]
    with pytest.raises(ValidationError):
        Scores(**data)
