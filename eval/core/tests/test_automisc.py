"""AutoMISC human-coded subsets with tiny synthetic fixtures (no dataset text)."""
import csv
import io
import json
import zipfile

import pytest
from onolys_eval import automisc
from onolys_eval.manifest import DatasetManifest, load_manifest

HEADER = ["corp_conv_idx", "conv_id", "speaker", "corp_vol_idx", "conv_vol_idx", "vol_text",
          "corp_utt_idx", "conv_utt_idx", "utt_text", "t1_label_GT", "t2_label_GT"]


def rows(conv, labels):
    """labels: list of (speaker, code); utterances numbered in order."""
    out = []
    for i, (speaker, code) in enumerate(labels):
        out.append(dict(zip(HEADER, ["0", conv, speaker, str(i), str(i), f"Synthetic volley {i}",
                                     str(i), str(i), f"Synthetic utterance {i}", "x", code])))
    return out


LABELS = [("counsellor", "OQ"), ("client", "N"), ("counsellor", "CQ"), ("client", "R+"),
          ("counsellor", "SR"), ("counsellor", "CR"), ("counsellor", "AF"), ("counsellor", "GI"),
          ("counsellor", "ADP"), ("counsellor", "ADW"), ("counsellor", "RCW"), ("counsellor", "EC"),
          ("counsellor", "CO"), ("counsellor", "FI"), ("counsellor", "ST"), ("counsellor", "SU"),
          ("counsellor", "RF"), ("counsellor", "WA"), ("counsellor", "DI"), ("counsellor", "FA")]


def test_turns_preserve_order_and_roles():
    turns = automisc.turns_from_rows(rows("c1", LABELS[:3])[::-1])
    assert [t["id"] for t in turns] == ["t1", "t2", "t3"]
    assert [t["role"] for t in turns] == ["clinician", "client", "clinician"]
    assert turns[0]["text"] == "Synthetic utterance 0" and turns[0]["code"] == "OQ"


def test_noncontiguous_or_unknown_speaker_is_an_error():
    bad = rows("c1", LABELS[:3])
    bad[1]["conv_utt_idx"] = "5"
    with pytest.raises(ValueError, match="contiguous"):
        automisc.turns_from_rows(bad)
    bad = rows("c1", LABELS[:2])
    bad[0]["speaker"] = "bot"
    with pytest.raises(ValueError, match="speaker"):
        automisc.turns_from_rows(bad)


def test_gold_maps_misc_codes_to_miti_counts():
    turns = automisc.turns_from_rows(rows("c1", LABELS))
    transcript, gold, warnings = automisc.build_session(
        "synthetic", "smoking-c1", turns, retrieved_at="2026-11-24T00:00:00+00:00", sha256="a" * 64,
        coded_url="https://example.org/a.zip")
    assert warnings == []
    assert all(set(t) == {"id", "speaker", "role", "text"} for t in transcript["turns"])
    assert gold.counts == {"gi": 1, "persuade": 4, "persuade_permission": 1, "question": 2, "sr": 1,
                           "cr": 1, "affirm": 1, "seek_collab": None, "emphasize_autonomy": 1,
                           "confront": 1}
    codes = {u.turn_id: u.codes for u in gold.utterance_codes}
    assert codes["t1"] == ["question"] and codes["t2"] == [] and codes["t10"] == ["persuade"]
    assert codes["t18"] == ["persuade"] and codes["t19"] == ["persuade"]  # WA, DI
    assert gold.quality_label is None and gold.label_scheme == automisc.LABEL_SCHEME


def test_quality_label_and_wrong_side_or_unknown_codes_warn():
    turns = automisc.turns_from_rows(rows("c1", [("counsellor", "SR"), ("client", "SR"),
                                                 ("counsellor", "ZZ")]))
    _, gold, warnings = automisc.build_session(
        "synthetic", "hlqc-high-001", turns, quality="high", retrieved_at="2026-11-24T00:00:00+00:00",
        sha256="a" * 64, coded_url="https://example.org/a.zip")
    assert gold.quality_label == "high" and gold.counts["sr"] == 1
    assert any(w.startswith("role-mismatch: t2") for w in warnings)
    assert any(w.startswith("unknown-code: t3") for w in warnings)


def _archive(tmp_path, hlqc_rows, smoking_rows):
    path = tmp_path / "main.zip"
    with zipfile.ZipFile(path, "w") as z:
        for name, data in (("HLQC_balanced_manual.csv", hlqc_rows), ("MIV6.3A_manual.csv", smoking_rows)):
            out = io.StringIO()
            writer = csv.DictWriter(out, HEADER)
            writer.writeheader()
            writer.writerows(data)
            z.writestr(f"AutoMISC-main/data/manual/{name}", "﻿" + out.getvalue())
    return path


def test_read_archive_groups_sessions_and_assigns_ids(tmp_path):
    path = _archive(tmp_path, rows("low_031", LABELS[:3]), rows("abc123", LABELS[:3]))
    sessions = automisc.read_archive(path)
    assert sorted(sessions) == ["hlqc-low-031", "smoking-abc123"]
    assert sessions["hlqc-low-031"]["quality"] == "low" and sessions["smoking-abc123"]["quality"] is None


def test_convert_dataset_writes_sessions(tmp_path):
    raw = tmp_path / "ds" / "raw"
    raw.mkdir(parents=True)
    _archive(raw, rows("high_001", LABELS[:4]), rows("abc123", LABELS[:4]))
    (raw / "fetch.json").write_text(json.dumps({"dataset_id": "ds", "files": {"main.zip": {
        "url": "https://example.org/main.zip", "sha256": "d" * 64,
        "retrieved_at": "2026-11-24T00:00:00+00:00"}}}))
    base = {"clinician_labels": ["counsellor"], "code_header": None, "change_goal": "x",
            "change_goal_source": "curated", "coded_span": None, "notes": ""}
    manifest = DatasetManifest.model_validate({
        "dataset_id": "ds", "title": "t", "license_note": "l", "source_page": "https://example.org",
        "miti_version": None, "source_media": ["transcript"], "source_format": "automisc_zip",
        "source_files": ["https://example.org/main.zip"],
        "sessions": [{**base, "session_id": "hlqc-high-001", "title": "a"},
                     {**base, "session_id": "smoking-abc123", "title": "b"}]})
    status, report = automisc.convert_automisc_dataset(manifest, tmp_path, None)
    assert status == 0, report
    gold = json.loads((tmp_path / "ds" / "hlqc-high-001" / "gold.json").read_text())
    assert gold["quality_label"] == "high" and gold["counts"]["question"] == 2


def test_committed_manifest_is_valid():
    from pathlib import Path
    manifest = load_manifest(Path(__file__).resolve().parents[2] / "datasets/automisc-human/manifest.yaml")
    assert manifest.source_format == "automisc_zip" and len(manifest.sessions) == 20
    assert {s.session_id.split("-")[0] for s in manifest.sessions} == {"hlqc", "smoking"}
