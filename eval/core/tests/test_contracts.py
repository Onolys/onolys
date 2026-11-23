"""Contract tests use synthetic content; reference manifests contain metadata only."""
import json
from copy import deepcopy
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from onolys_eval.gold import COUNT_IDS, GLOBAL_IDS, Gold, compute_summaries, load_gold
from onolys_eval.manifest import DatasetManifest, load_manifest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]


def manifest_data():
    return {
        "dataset_id": "synthetic", "title": "Synthetic", "license_note": "Test only",
        "source_page": "https://example.org", "miti_version": "4.2.1",
        "sessions": [{"session_id": "one", "title": "One",
                      "coded_url": "https://example.org/coded.pdf",
                      "uncoded_url": "https://example.org/uncoded.pdf",
                      "clinician_labels": ["I"], "code_header": "Code",
                      "change_goal": "Test goal", "change_goal_source": "curated",
                      "coded_span": None, "notes": "Synthetic"}],
    }


def gold_data():
    counts = dict.fromkeys(COUNT_IDS, 0)
    counts.update(question=2, cr=3, sr=1)
    globals_ = dict.fromkeys(GLOBAL_IDS, 3)
    return {"schema": "gold.v1", "dataset_id": "synthetic", "session_id": "one",
            "source": {"coded_url": "https://example.org/coded.pdf",
                       "uncoded_url": "https://example.org/uncoded.pdf",
                       "retrieved_at": "2026-11-23T00:00:00Z", "sha256": "a" * 64},
            "coded_span": None, "counts": counts, "globals": globals_,
            "summaries": compute_summaries(counts, globals_),
            "parse": {"method": "auto", "warnings": []}}


def test_valid_manifest_loads(tmp_path):
    import yaml
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump(manifest_data()))
    assert load_manifest(path).sessions[0].session_id == "one"


def test_gold_summary_only_loads_and_schema_is_current(tmp_path):
    data = gold_data()
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(data))
    gold = load_gold(path)
    assert gold.utterance_codes is None
    assert gold.summaries.pct_cr == .75
    assert gold.summaries.reflection_question_ratio == 2
    schema = json.loads(files("onolys_eval").joinpath("schemas/gold.v1.schema.json").read_text())
    assert schema == Gold.model_json_schema(by_alias=True)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(data)


@pytest.mark.parametrize("target,key,value", [
    ("counts", "bad", 1), ("counts", "gi", -1), ("counts", "gi", True),
    ("globals", "cct", 6), ("globals", "cct", 0), ("globals", "cct", 1.5),
    ("globals", "unknown", 3), ("parse", "unknown", "x"),
])
def test_gold_rejects_bad_scores_and_unknown_keys(target, key, value):
    data = gold_data()
    data[target][key] = value
    with pytest.raises(ValidationError):
        Gold.model_validate(data)
    schema = Gold.model_json_schema(by_alias=True)
    assert list(Draft202012Validator(schema).iter_errors(data))


def test_gold_requires_complete_scores_and_computed_summaries():
    data = gold_data()
    del data["counts"]["gi"]
    with pytest.raises(ValidationError):
        Gold.model_validate(data)
    data = gold_data()
    data["summaries"]["pct_cr"] = .9
    with pytest.raises(ValidationError, match="summaries"):
        Gold.model_validate(data)


def test_gold_accepts_optional_utterance_codes_and_zero_denominators():
    data = gold_data()
    data["utterance_codes"] = [{"turn_id": "t1", "codes": ["question"], "note": "test"}]
    assert Gold.model_validate(data).utterance_codes[0].codes == ["question"]
    data["utterance_codes"][0]["codes"] = ["not-a-code"]
    with pytest.raises(ValidationError):
        Gold.model_validate(data)
    assert compute_summaries(dict.fromkeys(COUNT_IDS, 0), data["globals"])["pct_cr"] is None


@pytest.mark.parametrize("change", [
    lambda d: d.update(dataset_id="../escape"),
    lambda d: d.update(unknown="x"),
    lambda d: d["sessions"][0].update(unknown="x"),
    lambda d: d["sessions"][0].update(session_id="bad/id"),
    lambda d: d["sessions"][0].update(change_goal=""),
    lambda d: d["sessions"][0].update(clinician_labels=[]),
    lambda d: d["sessions"].append(deepcopy(d["sessions"][0])),
    lambda d: d["sessions"][0].update(coded_span={"start_ms": 5, "end_ms": 2}),
])
def test_manifest_rejects_bad_ids_keys_duplicates_and_spans(change):
    data = manifest_data()
    change(data)
    with pytest.raises(ValidationError):
        DatasetManifest.model_validate(data)


def test_committed_casaa_manifest_lists_eight_verified_sessions():
    manifest = load_manifest(ROOT / "datasets/casaa-miti421-video2013/manifest.yaml")
    assert len(manifest.sessions) == 8
    assert {s.session_id for s in manifest.sessions} == {
        "confirmed-smoker", "rounder", "my-father-also-hit-me", "overuse-of-directing",
        "overuse-of-following", "suspiscious-smoker", "living-with-diabetes",
        "orientation-to-a-parenting-class"}
    assert all(s.audio_url is None and s.coded_span is None for s in manifest.sessions)
    assert next(s for s in manifest.sessions if s.session_id == "rounder").change_goal_source == "curated"


def test_gold_ids_follow_engine_pack():
    import yaml
    pack = yaml.safe_load(files("onolys_miti").joinpath("data/pack.yaml").read_text())
    assert set(COUNT_IDS) == {i["id"] for i in pack["items"] if i["kind"] == "count"}
    assert set(GLOBAL_IDS) == {i["id"] for i in pack["items"] if i["kind"] == "global"}
    assert set(gold_data()["summaries"]) == {i["id"] for i in pack["summaries"]}


def test_manifest_optional_audio_and_both_coded_span_shapes():
    data = manifest_data()
    data["sessions"][0].update(audio_url="https://example.org/test.mp3",
                               code_header=None, coded_span={"start_ms": 0, "end_ms": 1000})
    assert DatasetManifest.model_validate(data).sessions[0].coded_span.end_ms == 1000
    data["sessions"][0]["coded_span"] = {"start_turn": 0, "end_turn": 2}
    assert DatasetManifest.model_validate(data).sessions[0].coded_span.start_turn == 0


@pytest.mark.parametrize("path", [(), ("source",), ("summaries",)])
def test_gold_rejects_unknown_keys_at_each_level(path):
    data = gold_data()
    target = data
    for key in path:
        target = target[key]
    target["unexpected"] = "value"
    with pytest.raises(ValidationError):
        Gold.model_validate(data)


@pytest.mark.parametrize("span", [
    {"start_turn": "t1", "end_turn": "t9"},
    {"start_turn": "0", "end_turn": "2"},
    {"start_turn": -1, "end_turn": 2},
    {"start_turn": 0, "end_turn": -1},
    {"start_turn": 0, "end_turn": 0},
    {"start_turn": 2, "end_turn": 1},
    {"start_turn": 0, "end_turn": 2, "start_ms": 0, "end_ms": 10},
    {"start_turn": 0, "end_ms": 10},
])
def test_coded_span_rejects_invalid_turn_ranges_in_both_contracts(span):
    manifest = manifest_data()
    manifest["sessions"][0]["coded_span"] = span
    with pytest.raises(ValidationError):
        DatasetManifest.model_validate(manifest)
    gold = gold_data()
    gold["coded_span"] = span
    with pytest.raises(ValidationError):
        Gold.model_validate(gold)


def test_gold_accepts_zero_based_half_open_turn_range():
    data = gold_data()
    data["coded_span"] = {"start_turn": 0, "end_turn": 2}
    assert Gold.model_validate(data).coded_span.model_dump() == data["coded_span"]
