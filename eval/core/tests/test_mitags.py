"""MI-TAGS CSV conversion with tiny synthetic fixtures (no dataset text)."""
import csv
import io
import json

import pytest
from onolys_eval import mitags
from onolys_eval.gold import Gold
from onolys_eval.manifest import DatasetManifest
from test_contracts import manifest_data

GLOBAL_HEADER = ["id", "Video Title", "Annotator", "Empathy", "SofteningSustainTalk",
                 "CultivatingChangeTalk", "Partnership", "Only Text", "Tagged Text", "Only Tags"]
UTT_HEADER = ["id", "Video Title", "Turn", "Speaker", "Text", "Code", "Annotator", "Normalized Turn"]
TAGGED = ("T: [Question] Synthetic question?\nC: [Neutral] Synthetic answer\n"
          "T: [Structure Statement] Synthetic setup\nT: [Complex Reflection] Synthetic reflection\n"
          "C: [Change Talk] Synthetic change\nT: [Giving Information] Synthetic info\n"
          "T: [Affirm] Synthetic praise")
PLAIN = ("T: Synthetic question?\nC: Synthetic answer\nT: Synthetic setup\nT: Synthetic reflection\n"
         "C: Synthetic change\nT: Synthetic info\nT: Synthetic praise")


def to_csv(header, rows):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue()


def global_row(title="Synthetic Video", annotator="A1", scores=("3", "2", "4", "5"),
               tagged=TAGGED, plain=PLAIN):
    return dict(zip(GLOBAL_HEADER, ["1", title, annotator, *scores, plain, tagged, ""]))


def test_parse_tagged_text_roles_codes_and_text():
    turns, warnings = mitags.parse_tagged_text(TAGGED)
    assert warnings == []
    assert [t["id"] for t in turns] == [f"t{i}" for i in range(1, 8)]
    assert turns[0] == {"id": "t1", "speaker": "T", "role": "clinician",
                        "text": "Synthetic question?", "tag": "Question"}
    assert turns[1]["role"] == "client" and turns[1]["tag"] == "Neutral"


def test_session_gold_counts_mapping_globals_and_unlabeled_codes():
    transcript, gold, warnings = mitags.build_session_from_global_row(
        "synthetic", "synthetic-video", global_row(), retrieved_at="2026-11-24T00:00:00+00:00",
        sha256="a" * 64, coded_url="https://example.org/g.csv")
    assert warnings == []
    assert [t["text"] for t in transcript["turns"]][:2] == ["Synthetic question?", "Synthetic answer"]
    assert all(set(t) == {"id", "speaker", "role", "text"} for t in transcript["turns"])
    data = gold.model_dump(mode="json", by_alias=True)
    assert data["counts"] == {"gi": 1, "persuade": 0, "persuade_permission": None, "question": 1,
                              "sr": 0, "cr": 1, "affirm": 1, "seek_collab": None,
                              "emphasize_autonomy": None, "confront": 0}
    assert data["globals"] == {"cct": 4, "sst": 2, "partnership": 5, "empathy": 3}
    assert data["label_scheme"] == "MITI 4.2" and data["source"]["coded_url"] == "https://example.org/g.csv"
    assert (data["utterance_codes"][2]["turn_id"], data["utterance_codes"][2]["codes"]) == ("t3", [])
    assert data["utterance_codes"][3]["codes"] == ["cr"]
    Gold.model_validate(data)


def test_optional_codes_are_counted_when_present():
    tagged = "T: [Seeking Collaboration] a\nT: [Emphasize Autonomy] b\nT: [Persuade with Permission] c"
    _, gold, _ = mitags.build_session_from_global_row(
        "synthetic", "s", global_row(tagged=tagged, plain="T: a\nT: b\nT: c"),
        retrieved_at="2026-11-24T00:00:00+00:00", sha256=None, coded_url=None)
    assert (gold.counts["seek_collab"], gold.counts["emphasize_autonomy"],
            gold.counts["persuade_permission"]) == (1, 1, 1)


def test_unknown_tags_and_text_mismatch_warn_and_bad_globals_give_no_gold():
    tagged = "T: [Mystery] a\nC: [Whatever] b"
    _, gold, warnings = mitags.build_session_from_global_row(
        "synthetic", "s", global_row(tagged=tagged, plain="T: a\nC: different"),
        retrieved_at="2026-11-24T00:00:00+00:00", sha256=None, coded_url=None)
    assert any(w.startswith("unknown-code:") for w in warnings)
    assert any(w.startswith("text-mismatch:") for w in warnings)
    assert gold.parse.warnings == warnings
    _, none, warnings = mitags.build_session_from_global_row(
        "synthetic", "s", global_row(scores=("9", "2", "4", "5")),
        retrieved_at="2026-11-24T00:00:00+00:00", sha256=None, coded_url=None)
    assert none is None and any(w.startswith("globals-out-of-range:") for w in warnings)


def test_utterance_rows_build_session_in_turn_order_without_globals():
    rows = [["9", "Vid", "2", "C", "answer", "Neutral", "A1", "0.5"],
            ["8", "Vid", "1", "T", "question?", "Question", "A1", "0.1"],
            ["7", "Vid", "3", "T", "reflect", "Simple Reflection", "A1", "0.9"]]
    parsed = list(csv.DictReader(io.StringIO(to_csv(UTT_HEADER, rows))))
    turns, warnings = mitags.turns_from_utterance_rows(parsed)
    assert warnings == [] and [t["text"] for t in turns] == ["question?", "answer", "reflect"]
    _, gold, _ = mitags.build_session_from_turns(
        "synthetic", "vid", turns, None, [], retrieved_at="2026-11-24T00:00:00+00:00",
        sha256=None, coded_url=None, annotator="A1")
    assert gold.globals is None and gold.counts["question"] == 1 and gold.counts["sr"] == 1


def test_duplicate_turns_or_annotators_are_rejected():
    rows = [["1", "Vid", "1", "T", "a", "Question", "A1", "0"],
            ["2", "Vid", "1", "T", "b", "Question", "A2", "0"]]
    parsed = list(csv.DictReader(io.StringIO(to_csv(UTT_HEADER, rows))))
    with pytest.raises(ValueError, match="annotator"):
        mitags.turns_from_utterance_rows(parsed)
    with pytest.raises(ValueError, match="annotator"):
        mitags.pick_global_row([global_row(annotator=a) for a in ("A1", "A2")], "Synthetic Video")


def test_convert_dataset_end_to_end_and_cli(tmp_path, monkeypatch):
    raw = tmp_path / "cache/mi-tags-synth/raw"
    raw.mkdir(parents=True)
    (raw / "sample_global_mitis.csv").write_text(to_csv(GLOBAL_HEADER, [list(global_row().values())]))
    (raw / "sample_utterances.csv").write_text(to_csv(UTT_HEADER, [
        ["1", "Other video", "1", "T", "lonely", "Question", "A1", "0"]]))
    (raw / "fetch.json").write_text(json.dumps({"dataset_id": "mi-tags-synth", "files": {
        "sample_global_mitis.csv": {"url": "https://example.org/g.csv", "sha256": "b" * 64,
                                    "retrieved_at": "2026-11-24T00:00:00+00:00"},
        "sample_utterances.csv": {"url": "https://example.org/u.csv", "sha256": "c" * 64,
                                  "retrieved_at": "2026-11-24T00:00:00+00:00"}}}))
    data = manifest_data()
    data.update(dataset_id="mi-tags-synth", miti_version="4.2", source_format="mitags_csv",
                source_files=["https://example.org/g.csv", "https://example.org/u.csv"])
    data["sessions"] = [{"session_id": "synthetic-video", "title": "Synthetic Video",
                         "clinician_labels": ["T"], "code_header": None, "change_goal": "Goal",
                         "change_goal_source": "curated", "coded_span": None, "notes": "n"}]
    manifest = DatasetManifest.model_validate(data)
    status, report = mitags.convert_mitags_dataset(manifest, tmp_path / "cache")
    assert status == 0
    gold = json.loads((tmp_path / "cache/mi-tags-synth/synthetic-video/gold.json").read_text())
    assert gold["source"]["sha256"] == "b" * 64 and gold["counts"]["question"] == 1
    assert any("1 utterance rows" in line for line in report)
    transcript = json.loads((tmp_path / "cache/mi-tags-synth/synthetic-video/transcript.json").read_text())
    assert transcript["language"] == "en" and len(transcript["turns"]) == 7
    # unknown manifest title is an error, never a guess
    manifest.sessions[0].title = "Missing"
    with pytest.raises(ValueError, match="not found"):
        mitags.convert_mitags_dataset(manifest, tmp_path / "cache")


def test_committed_mi_tags_manifest():
    from onolys_eval.manifest import load_manifest
    from test_contracts import ROOT
    m = load_manifest(ROOT / "datasets/mi-tags-sample/manifest.yaml")
    assert m.miti_version == "4.2" and m.source_format == "mitags_csv" and len(m.source_files) == 2
    assert m.source_media == ["video", "transcript"]
    assert m.overlaps_with and m.overlaps_with[0].dataset_id == "casaa-miti421-video2013"
