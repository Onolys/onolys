"""MIDAS (Spanish MI) conversion with tiny synthetic fixtures (no dataset text)."""
import json

import pytest
from onolys_eval import midas
from onolys_eval.gold import Gold
from onolys_eval.manifest import DatasetManifest, load_manifest


def turn(number, speaker, text, tags=(), translated="Synthetic translation"):
    return {"speaker": speaker, "turn": text, "translated_turn": translated, "turn_number": number,
            "tag_positions": [{"tag": t, "start_pos": 0, "end_pos": 5} for t in tags]}


def basic():
    return [
        turn(1, "patient", "Texto  sintetico\tdos"),
        turn(0, "counselor", "Pregunta sintetica uno. Otra pregunta sintetica?", ["question", "question"]),
        turn(2, "counselor", "Reflexion sintetica", ["reflection"]),
        turn(3, "patient", "Respuesta sintetica"),
        turn(4, "counselor", "Pregunta final?", ["question", "empty"]),
    ]


COMMON = dict(retrieved_at="2026-11-24T00:00:00+00:00", sha256="a" * 64,
              coded_url="https://example.org/Spanish_MI.json")


def test_session_ids_are_valid_identifiers():
    assert midas.session_id_for("6uqC49iSopg_c.html") == "6uqc49isopg-c"
    assert midas.session_id_for("h-nEe_-KCxU_bad.html") == "h-nee-kcxu-bad"
    assert midas.session_id_for("voBvNMYEB.html") == "vobvnmyeb"


def test_turns_are_ordered_normalised_and_roles_mapped():
    turns, stats = midas.turns_from_conversation("k.html", basic())
    assert [t["id"] for t in turns] == [f"t{i}" for i in range(1, 6)]
    assert [(t["speaker"], t["role"]) for t in turns[:2]] == [("counselor", "clinician"),
                                                              ("patient", "client")]
    assert turns[1]["text"] == "Texto sintetico dos"
    assert [t["codes"] for t in turns] == [["question", "question"], [], [], [], ["question"]]
    assert stats == {"reflection": 1, "empty": 1, "bad_span": 0}


def test_out_of_range_spans_are_counted_and_reported():
    entries = basic()
    entries[1]["tag_positions"][0]["end_pos"] = 999
    entries[1]["tag_positions"][1]["end_pos"] = 0
    turns, stats = midas.turns_from_conversation("k.html", entries)
    assert turns[0]["codes"] == ["question", "question"] and stats["bad_span"] == 2


@pytest.mark.parametrize("speaker", ["unclear"])
def test_unclear_speaker_makes_roles_undetermined(speaker):
    entries = basic() + [turn(5, speaker, "x")]
    with pytest.raises(midas.UndeterminedRoles, match="unclear"):
        midas.turns_from_conversation("k.html", entries)


def test_tag_on_a_patient_turn_makes_roles_undetermined():
    entries = basic()
    entries[0]["tag_positions"] = [{"tag": "question", "start_pos": 0, "end_pos": 3}]
    with pytest.raises(midas.UndeterminedRoles, match="patient"):
        midas.turns_from_conversation("k.html", entries)


def test_unknown_speaker_tag_and_numbering_fail_loudly():
    with pytest.raises(ValueError, match="speaker"):
        midas.turns_from_conversation("k.html", [turn(0, "nurse", "x")])
    with pytest.raises(ValueError, match="tag"):
        midas.turns_from_conversation("k.html", [turn(0, "counselor", "x", ["advice"])])
    with pytest.raises(ValueError, match="turn_number"):
        midas.turns_from_conversation("k.html", [turn(0, "counselor", "x"), turn(2, "patient", "y")])
    with pytest.raises(ValueError, match="empty text"):
        midas.turns_from_conversation("k.html", [turn(0, "counselor", "  ")])


def test_gold_labels_only_questions_and_transcript_is_spanish():
    turns, _ = midas.turns_from_conversation("k.html", basic())
    transcript, gold, warnings = midas.build_session("synthetic", "k", turns, **COMMON)
    assert warnings == [] and transcript["language"] == "es"
    assert all(set(t) == {"id", "speaker", "role", "text"} for t in transcript["turns"])
    assert "translated" not in json.dumps(transcript)
    data = gold.model_dump(mode="json", by_alias=True)
    assert data["counts"] == {k: None for k in data["counts"]} | {"question": 3}
    assert data["globals"] is None and data.get("summaries") is None
    assert data["label_scheme"] == midas.LABEL_SCHEME
    assert [u["codes"] for u in data["utterance_codes"]] == [["question", "question"], [], [], [], ["question"]]
    Gold.model_validate(data)


def test_usable_conversations_skip_and_report_reasons():
    data = {"ok.html": basic(), "bad_one.html": basic() + [turn(5, "unclear", "x")],
            "Ok.html": basic()}
    with pytest.raises(ValueError, match="Duplicate session id"):
        midas.usable_conversations(data)
    del data["Ok.html"]
    usable, skipped = midas.usable_conversations(data)
    assert list(usable) == ["ok"] and list(skipped) == ["bad_one.html"]
    assert "unclear" in skipped["bad_one.html"]


def _manifest(sessions):
    return DatasetManifest.model_validate({
        "dataset_id": "ds", "title": "t", "license_note": "l", "source_page": "https://example.org",
        "miti_version": None, "source_media": ["video", "transcript"], "language": "es",
        "source_format": "midas_json", "source_files": ["https://example.org/Spanish_MI.json"],
        "sessions": [{"session_id": s, "title": "Synthetic", "clinician_labels": ["counselor"],
                      "code_header": None, "change_goal": "x", "change_goal_source": "curated",
                      "coded_span": None, "notes": ""} for s in sessions]})


def _raw(tmp_path):
    raw = tmp_path / "ds" / "raw"
    raw.mkdir(parents=True)
    (raw / "Spanish_MI.json").write_text(json.dumps({"ok.html": basic(), "bad.html": [turn(0, "unclear", "x")]}))
    (raw / "fetch.json").write_text(json.dumps({"dataset_id": "ds", "files": {"Spanish_MI.json": {
        "url": "https://example.org/Spanish_MI.json", "sha256": "b" * 64,
        "retrieved_at": "2026-11-24T00:00:00+00:00"}}}))


def test_convert_dataset_writes_files(tmp_path, monkeypatch):
    _raw(tmp_path)
    monkeypatch.setattr("onolys_eval.publicsets.require_external_path", lambda p: p)
    status, report = midas.convert_midas_dataset(_manifest(["ok"]), tmp_path, None)
    assert status == 0, report
    gold = json.loads((tmp_path / "ds" / "ok" / "gold.json").read_text())
    transcript = json.loads((tmp_path / "ds" / "ok" / "transcript.json").read_text())
    assert gold["counts"]["question"] == 3 and gold["source"]["sha256"] == "b" * 64
    assert transcript["language"] == "es"


def test_convert_rejects_a_session_with_undetermined_roles(tmp_path, monkeypatch):
    _raw(tmp_path)
    monkeypatch.setattr("onolys_eval.publicsets.require_external_path", lambda p: p)
    with pytest.raises(ValueError, match="bad"):
        midas.convert_midas_dataset(_manifest(["bad"]), tmp_path, None)


def test_committed_manifest_is_valid():
    from pathlib import Path
    manifest = load_manifest(Path(__file__).resolve().parents[2] / "datasets/midas-es/manifest.yaml")
    assert manifest.source_format == "midas_json" and manifest.language == "es"
    assert manifest.miti_version is None and manifest.transcript_origin == "human"
    assert manifest.source_media == ["video", "transcript"]
    assert manifest.label_scheme == "ITEM2 (Spanish MITI adaptation): questions and reflections"
    assert "licence request sent to authors" in manifest.license_note
    assert len(manifest.sessions) == 57
