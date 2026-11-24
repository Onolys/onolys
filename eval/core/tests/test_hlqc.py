"""HLQC conversion with tiny synthetic fixtures (no dataset text)."""
import io
import json
import zipfile

import pytest
from onolys_eval import hlqc
from onolys_eval.manifest import DatasetManifest, load_manifest

PREFIX = "HighLowQualityCounseling/"
TEXT = "\ufeffT:\tSynthetic hello\nC:\tSynthetic reply\nT: \tSynthetic spaced tag\nC\tSynthetic no colon\n"


def make_zip(tmp_path, transcripts, labels):
    path = tmp_path / "HighLowQualityCounseling.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(PREFIX + "labels.csv", "id,label\n" + "".join(f"{k},{v}\n" for k, v in labels.items()))
        for name, text in transcripts.items():
            z.writestr(PREFIX + "transcripts/" + name, text)
        z.writestr("__MACOSX/" + PREFIX + "transcripts/._" + next(iter(transcripts)), "junk")
    return path


def test_parse_transcript_handles_bom_tag_variants_and_continuations():
    turns, notes = hlqc.parse_transcript(TEXT + "orphan:\tSynthetic continuation\n\n")
    assert [(t["speaker"], t["role"]) for t in turns] == [
        ("T", "clinician"), ("C", "client"), ("T", "clinician"), ("C", "client")]
    assert turns[2]["text"] == "Synthetic spaced tag"
    assert turns[3]["text"] == "Synthetic no colon orphan: Synthetic continuation"
    assert notes == ["1 unlabeled line(s) appended to the previous turn"]


def test_parse_accepts_space_separated_tags():
    turns, notes = hlqc.parse_transcript("T: Synthetic one\nC: Synthetic two\n")
    assert [t["text"] for t in turns] == ["Synthetic one", "Synthetic two"] and notes == []


def test_parse_rejects_text_before_any_speaker_tag():
    with pytest.raises(ValueError, match="before the first speaker"):
        hlqc.parse_transcript("loose text\nT:\tSynthetic\n")


def test_session_gold_is_quality_only():
    turns, _ = hlqc.parse_transcript(TEXT)
    transcript, gold = hlqc.build_session(
        "synthetic", "low-007", turns, "low", retrieved_at="2026-11-24T00:00:00+00:00",
        sha256="a" * 64, coded_url="https://example.org/h.zip")
    data = gold.model_dump(mode="json", by_alias=True)
    assert data["quality_label"] == "low" and set(data["counts"].values()) == {None}
    assert data["globals"] is None and data["utterance_codes"] is None
    assert data["label_scheme"] == hlqc.LABEL_SCHEME and data["parse"]["warnings"] == []
    assert transcript["turns"][0] == {"id": "t1", "speaker": "T", "role": "clinician",
                                      "text": "Synthetic hello"}


def test_read_archive_skips_macos_junk_and_reports_missing_transcripts(tmp_path):
    path = make_zip(tmp_path, {"high_001": TEXT, "low_002": TEXT},
                    {"high_001": "high", "low_002": "low", "high_003": "high"})
    labels, transcripts = hlqc.read_archive(path)
    assert sorted(transcripts) == ["high_001", "low_002"]
    assert labels == {"high_001": "high", "low_002": "low", "high_003": "high"}


def test_label_must_match_file_name_prefix(tmp_path):
    path = make_zip(tmp_path, {"high_001": TEXT}, {"high_001": "low"})
    with pytest.raises(ValueError, match="does not match"):
        hlqc.read_archive(path)


def test_convert_dataset_writes_sessions(tmp_path):
    raw = tmp_path / "ds" / "raw"
    raw.mkdir(parents=True)
    make_zip(raw, {"high_001": TEXT, "low_002": TEXT}, {"high_001": "high", "low_002": "low"})
    (raw / "fetch.json").write_text(json.dumps({"dataset_id": "ds", "files": {
        "HighLowQualityCounseling.zip": {"url": "https://example.org/HighLowQualityCounseling.zip",
                                         "sha256": "c" * 64, "retrieved_at": "2026-11-24T00:00:00+00:00"}}}))
    session = {"clinician_labels": ["T"], "code_header": None, "change_goal": "x",
               "change_goal_source": "curated", "coded_span": None, "notes": ""}
    manifest = DatasetManifest.model_validate({
        "dataset_id": "ds", "title": "t", "license_note": "l", "source_page": "https://example.org",
        "miti_version": None, "source_media": ["video", "transcript"], "source_format": "hlqc_zip",
        "source_files": ["https://example.org/HighLowQualityCounseling.zip"],
        "sessions": [{**session, "session_id": "high-001", "title": "HLQC high_001"},
                     {**session, "session_id": "low-002", "title": "HLQC low_002"}]})
    status, report = hlqc.convert_hlqc_dataset(manifest, tmp_path, None)
    assert status == 0, report
    gold = json.loads((tmp_path / "ds" / "low-002" / "gold.json").read_text())
    assert gold["quality_label"] == "low" and gold["source"]["sha256"] == "c" * 64


def test_committed_manifest_is_valid():
    from pathlib import Path
    manifest = load_manifest(Path(__file__).resolve().parents[2] / "datasets/hlqc/manifest.yaml")
    assert manifest.transcript_origin == "auto_captions" and manifest.miti_version is None
    assert len(manifest.sessions) == 258
    assert {m.dataset_id for m in manifest.overlaps_with} >= {"automisc-human"}
