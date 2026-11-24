"""PHAC HTML transcript conversion with tiny synthetic pages (no dataset text)."""
import json

import pytest
from onolys_eval import phac
from onolys_eval.manifest import DatasetManifest, load_manifest

EN = """<html><h1>x</h1><div><h2>Transcript - Synthetic</h2>
<p>(Music playing.)</p>
<p><strong>Text on screen:</strong><br>Synthetic title</p>
<p>DR. SYNTH: Synthetic narrator explains that this is a reflection.</p>
<p><strong>Text on screen:</strong><br>Reflect</p>
<p>DOCTOR: Synthetic question &amp; more?</p>
<p>PATIENT:&nbsp;Synthetic answer.</p>
<p>DOCTOR:<br>
Synthetic wrapped body.</p>
<p>Production of this video was made possible by synthetic funders.</p>
</div><div>after</div></html>"""
FR = """<div><h2>Transcription - Synthetique</h2>
<p>(Musique.)</p><p><strong>Texte à l’écran :</strong><br>Demander</p>
<p>DR SYNTH : Narration synthetique.</p>
<p>MÉDECIN\xa0: Question synthetique?</p><p>PATIENTE : Reponse synthetique.</p>
<p>La production de cette publication a ete rendue possible.</p></div>"""
COMMON = dict(retrieved_at="2026-11-24T00:00:00+00:00", sha256="a" * 64,
              coded_url="https://example.org/p.html")


def test_en_roles_and_exclusions():
    turns, excluded, warnings = phac.parse_transcript(EN, "en")
    assert [(t["id"], t["speaker"], t["role"]) for t in turns] == [
        ("t1", "DOCTOR", "clinician"), ("t2", "PATIENT", "client"), ("t3", "DOCTOR", "clinician")]
    assert turns[0]["text"] == "Synthetic question & more?"
    assert turns[1]["text"] == "Synthetic answer." and turns[2]["text"] == "Synthetic wrapped body."
    assert warnings == []
    cats = [c for c, _ in excluded]
    assert cats.count("on-screen cue") == 2 and "stage direction" in cats
    assert "narrator (DR. SYNTH)" in cats and "credit" in cats
    # narrator / cue text never leaks into turns
    assert not any("narrator" in t["text"] or "Reflect" in t["text"] for t in turns)


def test_fr_labels_with_nbsp():
    turns, excluded, warnings = phac.parse_transcript(FR, "fr")
    assert [(t["speaker"], t["role"]) for t in turns] == [
        ("MÉDECIN", "clinician"), ("PATIENTE", "client")]
    assert warnings == [] and {c for c, _ in excluded} == {
        "stage direction", "on-screen cue", "narrator (DR SYNTH)", "credit"}


def test_unlabeled_paragraph_warns_and_is_not_a_turn():
    page = EN.replace("<p>Production", "<p>Loose synthetic line.</p><p>Production")
    turns, _, warnings = phac.parse_transcript(page, "en")
    assert len(turns) == 3 and warnings == ["unlabeled-paragraph: Loose synthetic line."]


def test_errors_without_section_or_both_roles():
    with pytest.raises(ValueError, match="No transcript section"):
        phac.parse_transcript("<div><p>DOCTOR: x</p></div>", "en")
    with pytest.raises(ValueError, match="lacks a clinician or a client"):
        phac.parse_transcript("<div><h2>Transcript</h2><p>DOCTOR: x</p></div>", "en")


def test_gold_is_empty_and_language_is_set():
    turns, _, _ = phac.parse_transcript(FR, "fr")
    transcript, gold = phac.build_session("synthetic", "smoking", "fr", turns, **COMMON)
    data = gold.model_dump(mode="json", by_alias=True)
    assert transcript["language"] == "fr"
    assert data["counts"] == {} and data["globals"] is None and data["utterance_codes"] is None
    assert data["label_scheme"] == "none" and data["label_source"] == "no human labels"
    assert data["parse"]["warnings"] == []


def test_urls():
    assert phac.page_url("fr", "smoking").endswith(
        "/videos-aide-changement-comportement/entrevue-motivationnelle-tabagisme.html")
    assert phac.page_url("en", "eating").endswith("/motivational-interviewing-unhealthy-eating.html")
    assert phac.video_url("fr", "physical-inactivity").endswith("/cd-mc/physi-fra.mp4")
    assert phac.video_url("en", "alcohol").endswith("/cd-mc/alcohol-eng.mp4")


def test_convert_dataset_writes_sessions(tmp_path):
    raw = tmp_path / "ds" / "raw"
    raw.mkdir(parents=True)
    name = phac.page_name("fr", "smoking")
    (raw / name).write_text(FR, encoding="utf-8")
    (raw / "fetch.json").write_text(json.dumps({"dataset_id": "ds", "files": {name: {
        "url": phac.page_url("fr", "smoking"), "sha256": "e" * 64,
        "retrieved_at": "2026-11-24T00:00:00+00:00"}}}))
    manifest = DatasetManifest.model_validate({
        "dataset_id": "ds", "title": "t", "license_note": "l", "source_page": "https://example.org",
        "miti_version": None, "language": "fr", "source_media": ["video", "transcript"],
        "source_format": "phac_html", "source_files": [phac.page_url("fr", "smoking")],
        "sessions": [{"session_id": "smoking", "title": "a", "clinician_labels": ["MÉDECIN"],
                      "code_header": None, "change_goal": "x", "change_goal_source": "curated",
                      "coded_span": None, "notes": ""}]})
    status, report = phac.convert_phac_dataset(manifest, tmp_path, None)
    assert status == 0, report
    transcript = json.loads((tmp_path / "ds" / "smoking" / "transcript.json").read_text())
    gold = json.loads((tmp_path / "ds" / "smoking" / "gold.json").read_text())
    assert transcript["language"] == "fr" and len(transcript["turns"]) == 2
    assert gold["counts"] == {} and gold["source"]["sha256"] == "e" * 64
    assert any("narrator (DR SYNTH)" in line for line in report)


def test_manifest_language_default_and_validation():
    base = {"dataset_id": "ds", "title": "t", "license_note": "l", "source_page": "https://e.org",
            "miti_version": None, "source_media": ["transcript"], "source_format": "phac_html",
            "source_files": ["https://e.org/a.html"],
            "sessions": [{"session_id": "s", "title": "a", "clinician_labels": ["x"],
                          "code_header": None, "change_goal": "x", "change_goal_source": "curated",
                          "coded_span": None, "notes": ""}]}
    assert DatasetManifest.model_validate(base).language == "en"
    assert DatasetManifest.model_validate({**base, "language": "pt-BR"}).language == "pt-BR"
    with pytest.raises(ValueError):
        DatasetManifest.model_validate({**base, "language": "French"})


@pytest.mark.parametrize("ident,language", [("phac-en", "en")])
def test_committed_manifests_are_valid(ident, language):
    from pathlib import Path
    manifest = load_manifest(Path(__file__).resolve().parents[2] / f"datasets/{ident}/manifest.yaml")
    assert manifest.language == language and manifest.label_scheme == "none"
    assert manifest.miti_version is None and manifest.transcript_origin == "human"
    assert manifest.source_media == ["video", "transcript"]
    assert manifest.labels_summary == "No human labels (transcript only)"
    assert [s.session_id for s in manifest.sessions] == [
        "alcohol", "eating", "physical-inactivity", "smoking"]
    assert "canada.ca/en/transparency/terms.html" in manifest.license_note
