"""AnnoMI conversion with tiny synthetic fixtures (no dataset text)."""
import csv
import io
import json

import pytest
from onolys_eval import annomi
from onolys_eval.gold import Gold
from onolys_eval.manifest import DatasetManifest, load_manifest

HEADER = ["mi_quality", "transcript_id", "video_title", "video_url", "topic", "utterance_id",
          "interlocutor", "timestamp", "utterance_text", "annotator_id", "therapist_input_exists",
          "therapist_input_subtype", "reflection_exists", "reflection_subtype", "question_exists",
          "question_subtype", "main_therapist_behaviour", "client_talk_type"]


def row(utt, who, text, ann="0", quality="high", tid="5", question=None, reflection=None,
        inp=None):
    t = who == "therapist"
    flag = lambda v: "n/a" if not t else str(v is not None)  # noqa: E731
    sub = lambda v: v if v else "n/a"  # noqa: E731
    return dict(zip(HEADER, [
        quality, tid, "Synthetic video", "https://www.youtube.com/watch?v=xxxxxxxxxxx", "topic x",
        str(utt), who, "00:00:01", text, ann, flag(inp), sub(inp), flag(reflection), sub(reflection),
        flag(question), sub(question), "other" if t else "n/a", "neutral" if not t else "n/a"]))


def basic():
    return [
        row(1, "client", "Synthetic client one"),
        row(0, "therapist", "Synthetic open question?", question="open"),
        row(2, "therapist", "Synthetic simple reflection", reflection="simple"),
        row(3, "client", "Synthetic client two"),
        row(4, "therapist", "Synthetic info and a question?", inp="information", question="closed"),
        row(5, "therapist", "Synthetic complex reflection", reflection="complex"),
        row(6, "therapist", "Synthetic advice", inp="advice"),
        row(7, "therapist", "Synthetic chat"),
    ]


def build(rows, **kw):
    return annomi.build_session("synthetic", "transcript-5", rows, retrieved_at="2026-11-24T00:00:00+00:00",
                                sha256="a" * 64, coded_url="https://example.org/a.csv", **kw)


def test_utterances_are_ordered_by_utterance_id_with_roles():
    turns = annomi.utterances_from_rows(basic())
    assert [t["id"] for t in turns] == [f"t{i}" for i in range(1, 9)]
    assert turns[0]["role"] == "clinician" and turns[1]["role"] == "client"
    assert turns[0]["text"] == "Synthetic open question?"


def test_counts_map_question_reflections_information_and_leave_the_rest_unlabeled():
    transcript, gold, warnings = build(annomi.utterances_from_rows(basic()))
    assert warnings == []
    assert all(set(t) == {"id", "speaker", "role", "text"} for t in transcript["turns"])
    data = gold.model_dump(mode="json", by_alias=True)
    assert data["counts"] == {"gi": 1, "persuade": None, "persuade_permission": None, "question": 2,
                              "sr": 1, "cr": 1, "affirm": None, "seek_collab": None,
                              "emphasize_autonomy": None, "confront": None}
    assert data["globals"] is None and "summaries" not in data or data["summaries"] is None
    assert data["label_scheme"] == annomi.LABEL_SCHEME
    codes = {u["turn_id"]: u["codes"] for u in data["utterance_codes"]}
    assert codes["t1"] == ["question"] and codes["t5"] == ["gi", "question"] and codes["t7"] == []
    Gold.model_validate(data)


def test_quality_label_and_unknown_quality():
    _, gold, _ = build(annomi.utterances_from_rows(basic()), quality="low")
    assert gold.quality_label == "low"
    with pytest.raises(ValueError):
        build(annomi.utterances_from_rows(basic()), quality="medium")


def test_multi_annotator_transcript_uses_strict_majority_per_code():
    rows = []
    for ann, ref in (("0", "simple"), ("1", "simple"), ("2", "complex")):
        rows.append(row(0, "therapist", "Synthetic reflect", ann=ann, reflection=ref))
        rows.append(row(1, "therapist", "Synthetic split", ann=ann,
                        question="open" if ann == "0" else None))
    turns = annomi.utterances_from_rows(rows)
    assert len(turns) == 2
    assert turns[0]["codes"] == ["sr"] and turns[1]["codes"] == []


def test_multi_annotator_text_mismatch_is_an_error():
    rows = [row(0, "therapist", "Synthetic a", ann="0"), row(0, "therapist", "Synthetic b", ann="1")]
    with pytest.raises(ValueError, match="differs between annotators"):
        annomi.utterances_from_rows(rows)


def test_coded_span_limits_counts_and_utterance_codes():
    turns = annomi.utterances_from_rows(basic())
    transcript, gold, _ = build(turns, span=(0, 3))
    assert len(transcript["turns"]) == 8
    assert gold.counts["question"] == 1 and gold.counts["sr"] == 1 and gold.counts["gi"] == 0
    assert [u.turn_id for u in gold.utterance_codes] == ["t1", "t2", "t3"]
    assert gold.coded_span.model_dump() == {"start_turn": 0, "end_turn": 3}


def test_span_for_long_transcripts_stops_before_the_word_cap():
    turns = [{"id": f"t{i}", "speaker": "client", "role": "client", "text": "w " * 1000, "codes": []}
             for i in range(1, 9)]
    assert annomi.span_for_word_cap(turns) == (0, 6)
    assert annomi.span_for_word_cap(turns[:3]) is None


def test_unknown_interlocutor_and_subtype_fail_loudly():
    bad = basic()
    bad[0]["interlocutor"] = "nurse"
    with pytest.raises(ValueError, match="interlocutor"):
        annomi.utterances_from_rows(bad)
    bad = basic()
    bad[2]["reflection_subtype"] = "weird"
    with pytest.raises(ValueError, match="reflection_subtype"):
        annomi.utterances_from_rows(bad)


def test_convert_dataset_writes_files_and_manifest_roundtrip(tmp_path, monkeypatch):
    raw = tmp_path / "ds" / "raw"
    raw.mkdir(parents=True)
    out = io.StringIO()
    writer = csv.DictWriter(out, HEADER)
    writer.writeheader()
    writer.writerows(basic())
    (raw / "AnnoMI-full.csv").write_text(out.getvalue())
    (raw / "fetch.json").write_text(json.dumps({"dataset_id": "ds", "files": {"AnnoMI-full.csv": {
        "url": "https://example.org/AnnoMI-full.csv", "sha256": "b" * 64,
        "retrieved_at": "2026-11-24T00:00:00+00:00"}}}))
    monkeypatch.setattr("onolys_eval.publicsets.require_external_path", lambda p: p)
    manifest = DatasetManifest.model_validate({
        "dataset_id": "ds", "title": "t", "license_note": "l", "source_page": "https://example.org",
        "miti_version": None, "source_media": ["video", "transcript"], "source_format": "annomi_csv",
        "source_files": ["https://example.org/AnnoMI-full.csv"],
        "sessions": [{"session_id": "transcript-5", "title": "Synthetic video",
                      "clinician_labels": ["therapist"], "code_header": None, "change_goal": "topic x",
                      "change_goal_source": "header", "coded_span": None, "notes": ""}]})
    status, report = annomi.convert_annomi_dataset(manifest, tmp_path, None)
    assert status == 0, report
    gold = json.loads((tmp_path / "ds" / "transcript-5" / "gold.json").read_text())
    assert gold["quality_label"] == "high" and gold["counts"]["question"] == 2
    assert gold["source"]["sha256"] == "b" * 64


def test_committed_manifest_is_valid():
    from pathlib import Path
    manifest = load_manifest(Path(__file__).resolve().parents[2] / "datasets/annomi/manifest.yaml")
    assert manifest.source_format == "annomi_csv" and manifest.miti_version is None
    assert len(manifest.sessions) == 133
