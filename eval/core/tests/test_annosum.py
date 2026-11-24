"""AnnoSUM-MI conversion with tiny synthetic fixtures (no dataset text)."""
import csv
import io
import json

import pytest
from onolys_eval import annosum
from onolys_eval.gold import Gold
from onolys_eval.manifest import DatasetManifest, load_manifest

TRAIN = ["transcript_id", "mi_quality", "topic_new", "utterance_id", "interlocutor",
         "utterance_text", "main_therapist_behaviour", "client_talk_type", "", ""]
TEST = ["transcript_id", "mi_quality", "utterance_id", "interlocutor", "utterance_text",
        "main_therapist_behaviour", "client_talk_type"]
RATE_TRAIN = ["transcript_id", "mi_quality", "Evocation", "Collaboration", "Autonomy", "Direction",
              "Empathy", "Non-Judgmental Attitude", "Competence", "Ethical Behavior",
              "Reflectiveness"]
RATE_TEST = RATE_TRAIN[:8]


def row(utt, who, text, main="", tid="5", quality="high"):
    return {"transcript_id": tid, "mi_quality": quality, "topic_new": "topic x",
            "utterance_id": str(utt), "interlocutor": who, "utterance_text": text,
            "main_therapist_behaviour": main, "client_talk_type": "neutral" if who == "client" else ""}


def basic():
    return [
        row(1, "therapist", "Synthetic open question?", "question"),
        row(0, "client", ""),
        row(2, "client", "Synthetic client one"),
        row(3, "therapist", "Synthetic reflection", "reflection"),
        row(4, "therapist", "Synthetic question two?", "question"),
        row(5, "therapist", "Synthetic input", "therapist_input"),
        row(6, "therapist", "Synthetic chat", "other"),
    ]


def build(turns, **kw):
    kw.setdefault("quality", "high")
    kw.setdefault("empathy", 4)
    return annosum.build_session("synthetic", "transcript-5", turns, retrieved_at="2026-11-24T00:00:00+00:00",
                                 sha256="a" * 64, coded_url="https://example.org/a.csv", **kw)


def test_turns_are_ordered_skip_blank_text_and_map_roles():
    turns, skipped = annosum.turns_from_rows(basic())
    assert skipped == 1 and [t["id"] for t in turns] == [f"t{i}" for i in range(1, 7)]
    assert turns[0]["role"] == "clinician" and turns[1]["role"] == "client"
    assert turns[0]["text"] == "Synthetic open question?"
    assert [t["codes"] for t in turns if t["role"] == "clinician"] == [
        ["question"], [], ["question"], [], []]


def test_mojibake_is_repaired_and_plain_text_untouched():
    original = "caf\u00e9 \u2014 yes\u2026"
    broken = original.encode("utf-8").decode("mac_roman")
    assert broken != original
    assert annosum.repair_text(broken) == original
    assert annosum.repair_text("plain ASCII, ok") == "plain ASCII, ok"
    assert annosum.repair_text(original) == original


def test_gold_labels_only_question_plus_empathy_and_quality():
    turns, _ = annosum.turns_from_rows(basic())
    transcript, gold, warnings = build(turns, quality="low", empathy=3)
    assert warnings == []
    assert all(set(t) == {"id", "speaker", "role", "text"} for t in transcript["turns"])
    assert transcript["language"] == "en"
    data = gold.model_dump(mode="json", by_alias=True)
    assert data["counts"] == {k: None for k in data["counts"]} | {"question": 2}
    assert data["globals"] == {"empathy": 3} and data["quality_label"] == "low"
    assert data.get("summaries") is None and data["label_scheme"] == annosum.LABEL_SCHEME
    codes = {u["turn_id"]: u["codes"] for u in data["utterance_codes"]}
    assert codes["t1"] == ["question"] and codes["t3"] == [] and codes["t4"] == ["question"]
    Gold.model_validate(data)


def test_missing_empathy_leaves_globals_null():
    turns, _ = annosum.turns_from_rows(basic())
    _, gold, _ = build(turns, empathy=None)
    assert gold.globals is None


def test_coded_span_limits_counts():
    turns, _ = annosum.turns_from_rows(basic())
    _, gold, _ = build(turns, span=(0, 3))
    assert gold.counts["question"] == 1
    assert gold.coded_span.model_dump() == {"start_turn": 0, "end_turn": 3}


def test_unknown_values_fail_loudly():
    bad = basic()
    bad[0]["interlocutor"] = "nurse"
    with pytest.raises(ValueError, match="interlocutor"):
        annosum.turns_from_rows(bad)
    bad = basic()
    bad[0]["main_therapist_behaviour"] = "weird"
    with pytest.raises(ValueError, match="main_therapist_behaviour"):
        annosum.turns_from_rows(bad)
    with pytest.raises(ValueError, match="mi_quality"):
        build(annosum.turns_from_rows(basic())[0], quality="medium")


def test_empathy_parsing():
    assert annosum.empathy_of({"Empathy": "5"}) == 5
    assert annosum.empathy_of({"Empathy": ""}) is None
    for value in ("0", "6", "x"):
        with pytest.raises(ValueError, match="Empathy"):
            annosum.empathy_of({"Empathy": value})


def _write(path, header, rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, header, delimiter=";", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text("﻿" + out.getvalue(), encoding="utf-8")


def _raw(tmp_path):
    raw = tmp_path / "ds" / "raw"
    raw.mkdir(parents=True)
    _write(raw / "train_dataset_MI_sessions.csv", TRAIN, basic())
    test_rows = [{**r, "transcript_id": "7", "mi_quality": "low"} for r in basic()[:3]]
    _write(raw / "test_dataset_MI_sessions.csv", TEST, test_rows)
    rating = {"transcript_id": "5", "mi_quality": "high", "Evocation": "1", "Collaboration": "2",
              "Autonomy": "", "Direction": "4", "Empathy": "5", "Non-Judgmental Attitude": "3",
              "Competence": "3", "Ethical Behavior": "3", "Reflectiveness": "2"}
    _write(raw / "train_data_MI_annotated.csv", RATE_TRAIN, [rating])
    _write(raw / "test_data_MI_annotated.csv", RATE_TEST,
           [{**rating, "transcript_id": "7", "mi_quality": "low", "Empathy": "2"}])
    record = lambda name: {"url": f"https://example.org/{name}", "sha256": "b" * 64,  # noqa: E731
                           "retrieved_at": "2026-11-24T00:00:00+00:00"}
    names = ["train_dataset_MI_sessions.csv", "test_dataset_MI_sessions.csv",
             "train_data_MI_annotated.csv", "test_data_MI_annotated.csv"]
    (raw / "fetch.json").write_text(json.dumps({"dataset_id": "ds",
                                                "files": {n: record(n) for n in names}}))
    return names


def _manifest(names, sessions):
    return DatasetManifest.model_validate({
        "dataset_id": "ds", "title": "t", "license_note": "l", "source_page": "https://example.org",
        "miti_version": None, "source_media": ["video", "transcript"], "source_format": "annosum_csv",
        "source_files": [f"https://example.org/{n}" for n in names],
        "sessions": [{"session_id": s, "title": "Synthetic", "clinician_labels": ["therapist"],
                      "code_header": None, "change_goal": "x", "change_goal_source": "curated",
                      "coded_span": None, "notes": ""} for s in sessions]})


def test_convert_dataset_writes_files_for_train_and_test_sessions(tmp_path, monkeypatch):
    names = _raw(tmp_path)
    monkeypatch.setattr("onolys_eval.publicsets.require_external_path", lambda p: p)
    status, report = annosum.convert_annosum_dataset(_manifest(names, ["transcript-5", "transcript-7"]),
                                                     tmp_path, None)
    assert status == 0, report
    gold = json.loads((tmp_path / "ds" / "transcript-5" / "gold.json").read_text())
    assert gold["quality_label"] == "high" and gold["counts"]["question"] == 2
    assert gold["globals"] == {"empathy": 5}
    assert gold["source"]["coded_url"].endswith("train_dataset_MI_sessions.csv")
    other = json.loads((tmp_path / "ds" / "transcript-7" / "gold.json").read_text())
    assert other["quality_label"] == "low" and other["globals"] == {"empathy": 2}
    assert other["source"]["coded_url"].endswith("test_dataset_MI_sessions.csv")


def test_quality_mismatch_between_files_is_an_error(tmp_path):
    _raw(tmp_path)
    raw = tmp_path / "ds" / "raw"
    _write(raw / "train_data_MI_annotated.csv", RATE_TRAIN, [
        {"transcript_id": "5", "mi_quality": "low", "Empathy": "4"}])
    with pytest.raises(ValueError, match="mi_quality"):
        annosum.read_dataset_files(raw)


def test_committed_manifest_is_valid():
    from pathlib import Path
    manifest = load_manifest(Path(__file__).resolve().parents[2] / "datasets/annosum-mi/manifest.yaml")
    assert manifest.source_format == "annosum_csv" and manifest.miti_version is None
    assert manifest.transcript_origin == "human" and len(manifest.sessions) == 131
    assert manifest.overlaps_with[0].dataset_id == "annomi"
    assert "licence request sent to authors" in manifest.license_note
