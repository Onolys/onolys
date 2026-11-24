"""Welivita & Pu MI dataset with tiny synthetic fixtures (no dataset text)."""
import csv
import io
import json

import pytest
from onolys_eval import welivita
from onolys_eval.manifest import DatasetManifest, load_manifest

HEADER = ["dialog_id", "turn_count", "turn", "author", "text", "ann1", "ann2",
          "stage I agreed label", "judge 1 annotation", "stage II agreed label",
          "judge 2 annotation", "final agreed label"]
CC = "counsel_chat |\xa07"
RED = "RED |\xa0123 - SomeSub"


def sentence(dialog, turn, author, text, label="N/A"):
    return dict(zip(HEADER, [dialog, "2", str(turn), author, text, "x", "y", "x", "-", "x", "-", label]))


def dialogue(dialog=CC):
    return [
        sentence(dialog, 1, "speaker", "Synthetic seeker text.\n  More text."),
        sentence(dialog, 2, "listener", "Synthetic one.", "Open Question"),
        sentence(dialog, 2, "listener", "Synthetic two.", "Closed Question"),
        sentence(dialog, 2, "listener", "Synthetic three.", "Advise without Permission"),
        sentence(dialog, 2, "listener", "Synthetic four.", "Advise with Permission"),
        sentence(dialog, 2, "listener", "Synthetic five.", "Support"),
        sentence(dialog, 2, "listener", "Synthetic six.", "-"),
        sentence(dialog, 3, "speaker", "Synthetic reply."),
        sentence(dialog, 4, "listener", "Synthetic seven.", "Complex Reflection"),
        sentence(dialog, 4, "listener", "Synthetic eight.", "Complex Reflection"),
        sentence(dialog, 4, "listener", "Synthetic nine.", "Give Information"),
    ]


COMMON = dict(retrieved_at="2026-11-24T00:00:00+00:00", sha256="a" * 64,
              coded_url="https://example.org/mi.csv")


def test_session_ids_from_dialog_ids():
    assert welivita.session_id_for(CC) == "counsel-chat-7"
    assert welivita.session_id_for(RED) == "red-123-somesub"


def test_turns_join_sentences_and_map_roles():
    turns = welivita.turns_from_rows(dialogue())
    assert [(t["id"], t["speaker"], t["role"]) for t in turns] == [
        ("t1", "seeker", "client"), ("t2", "helper", "clinician"), ("t3", "seeker", "client"),
        ("t4", "helper", "clinician")]
    assert turns[0]["text"] == "Synthetic seeker text. More text."
    assert turns[1]["text"].startswith("Synthetic one. Synthetic two.")
    assert turns[1]["labels"][0] == "Open Question" and turns[0]["labels"] == [None]


def test_non_contiguous_turn_and_unknown_author_are_errors():
    rows = dialogue()
    rows.append(sentence(CC, 1, "speaker", "Synthetic late."))
    with pytest.raises(ValueError, match="not contiguous"):
        welivita.turns_from_rows(rows)
    with pytest.raises(ValueError, match="author"):
        welivita.turns_from_rows([sentence(CC, 1, "bot", "x")])


def test_gold_maps_labels_and_skips_unmapped_and_unresolved():
    transcript, gold, warnings, stats = welivita.build_session(
        "synthetic", "counsel-chat-7", welivita.turns_from_rows(dialogue()), **COMMON)
    assert warnings == [] and stats == {"mapped": 7, "unmapped": 1, "unresolved": 1}
    assert gold.counts == {"gi": 1, "persuade": 1, "persuade_permission": 1, "question": 2, "sr": 0,
                           "cr": 2, "affirm": 0, "seek_collab": None, "emphasize_autonomy": 0,
                           "confront": 0}
    codes = {u.turn_id: u.codes for u in gold.utterance_codes}
    assert codes["t2"] == ["question", "question", "persuade", "persuade_permission"]
    assert codes["t1"] == [] and codes["t4"] == ["cr", "cr", "gi"]
    assert gold.globals is None and gold.summaries is None and gold.quality_label is None
    assert all(set(t) == {"id", "speaker", "role", "text"} for t in transcript["turns"])


def test_unknown_label_is_a_warning():
    rows = dialogue()
    rows[1]["final agreed label"] = "Brand New Label"
    _, _, warnings, _ = welivita.build_session(
        "synthetic", "counsel-chat-7", welivita.turns_from_rows(rows), **COMMON)
    assert any("unknown-label: t2" in w for w in warnings)


def _csv_text(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, HEADER, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def test_read_dialogues_groups_in_file_order(tmp_path):
    path = tmp_path / "MI Dataset.csv"
    path.write_text("﻿" + _csv_text(dialogue(CC) + dialogue(RED)), encoding="utf-8")
    dialogues = welivita.read_dialogues(path)
    assert list(dialogues) == ["counsel-chat-7", "red-123-somesub"]
    assert len(dialogues["counsel-chat-7"][1]) == 11


def test_convert_dataset_writes_sessions(tmp_path):
    raw = tmp_path / "ds" / "raw"
    raw.mkdir(parents=True)
    (raw / "MI Dataset.csv").write_text(_csv_text(dialogue(CC) + dialogue(RED)), encoding="utf-8")
    (raw / "fetch.json").write_text(json.dumps({"dataset_id": "ds", "files": {"MI Dataset.csv": {
        "url": "https://example.org/MI%20Dataset.csv", "sha256": "e" * 64,
        "retrieved_at": "2026-11-24T00:00:00+00:00"}}}))
    base = {"clinician_labels": ["helper"], "code_header": None, "change_goal": "x",
            "change_goal_source": "curated", "coded_span": None, "notes": ""}
    manifest = DatasetManifest.model_validate({
        "dataset_id": "ds", "title": "t", "license_note": "l", "source_page": "https://example.org",
        "miti_version": None, "source_media": ["transcript"], "source_format": "welivita_csv",
        "source_files": ["https://example.org/MI%20Dataset.csv"],
        "sessions": [{**base, "session_id": "counsel-chat-7", "title": "a"},
                     {**base, "session_id": "red-123-somesub", "title": "b"}]})
    status, report = welivita.convert_welivita_dataset(manifest, tmp_path, None)
    assert status == 0, report
    gold = json.loads((tmp_path / "ds" / "red-123-somesub" / "gold.json").read_text())
    assert gold["counts"]["question"] == 2 and gold["counts"]["seek_collab"] is None
    assert gold["source"]["sha256"] == "e" * 64


def test_committed_manifest_is_valid():
    from pathlib import Path
    manifest = load_manifest(Path(__file__).resolve().parents[2] / "datasets/welivita-mi/manifest.yaml")
    assert manifest.source_format == "welivita_csv" and manifest.transcript_origin == "human"
    assert manifest.source_media == ["transcript"] and "CC BY-NC-SA" in manifest.license_note
    assert len(manifest.sessions) == 2000
