"""AutoMISC human-coded subsets to transcript.v1 and partial gold.v1.

Source: https://github.com/cimhasgithub/AutoMISC (``main.zip``; Mahmood et al. style paper
https://aclanthology.org/2025.nlpai4health-main.4/). Only the two HUMAN-coded files are
read; the repo's automated (LLM) codes are never used:

* ``data/manual/HLQC_balanced_manual.csv``: 1,924 utterances from 10 HLQC conversations
  (5 high, 5 low quality), manual MISC 2.5 ground truth.
* ``data/manual/MIV6.3A_manual.csv``: 821 utterances from 10 conversations of a smoking
  cessation chatbot study (the counsellor is an LLM chatbot, the client a human smoker),
  consensus human annotations. The ``*_auto`` columns in this file are ignored.

Each conversation is coded in full (utterances are contiguous from 0), so counts cover the
whole session and ``coded_span`` is null. ``t2_label_GT`` is the human MISC 2.5 code. Turns
are the coded utterances (volleys are split into utterances).

Counselor code mapping (MISC 2.5 tier-2 -> gold counts)::

    OQ, CQ -> question     SR -> sr           CR -> cr        AF -> affirm
    GI -> gi               ADP, RCP -> persuade_permission
    ADW, RCW, WA, DI -> persuade   EC -> emphasize_autonomy           CO -> confront

Not counted: FI (filler), FA (facilitate), ST (structure), SU (support), RF (reframe).
WA (warn) and DI (direct) count as persuade (owner decision). MISC has no Seek
Collaboration, so ``seek_collab`` is ``null``; ``cr`` is a lower bound when RF occurs. Client codes
(N, R+, C+, ...) are ignored; a client code on a counsellor row, or the reverse, and any
unknown code are parse warnings. No globals, no summaries.
"""
import csv
import io
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from .gold import COUNT_IDS
from .manifest import DatasetManifest
from .publicsets import (
    bootstrap_raw,
    convert_sessions,
    make_gold,
    partial_counts,
    read_provenance,
    source_record,
    write_manifest,
)

DATASET_ID = "automisc-human"
LABEL_SCHEME = "MISC 2.5 (human) mapped to MITI counts"
SOURCE_FILE = "main.zip"
SOURCE_URL = "https://github.com/cimhasgithub/AutoMISC/archive/refs/heads/main.zip"
_MEMBERS = {"hlqc": "AutoMISC-main/data/manual/HLQC_balanced_manual.csv",
            "smoking": "AutoMISC-main/data/manual/MIV6.3A_manual.csv"}
LABELED = tuple(k for k in COUNT_IDS if k != "seek_collab")
COUNSELLOR_CODES = {
    "OQ": "question", "CQ": "question", "SR": "sr", "CR": "cr", "AF": "affirm", "GI": "gi",
    "ADP": "persuade_permission", "RCP": "persuade_permission", "ADW": "persuade",
    "RCW": "persuade", "WA": "persuade", "DI": "persuade", "EC": "emphasize_autonomy", "CO": "confront"}
UNMAPPED_COUNSELLOR_CODES = {"FI", "FA", "ST", "SU", "RF"}
CLIENT_CODES = {"N", "N+", "N-", "R+", "R-", "AB+", "AB-", "AC+", "AC-", "O+", "O-", "D+", "D-",
                "C+", "C-", "TS+", "TS-"}
_ROLES = {"counsellor": "clinician", "client": "client"}


def turns_from_rows(rows):
    """One conversation's utterance rows -> ordered turns carrying their human ``code``."""
    ordered = sorted(rows, key=lambda r: int(r["conv_utt_idx"]))
    numbers = [int(r["conv_utt_idx"]) for r in ordered]
    if numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        raise ValueError("Utterance indexes are not contiguous")
    turns = []
    for index, row in enumerate(ordered, 1):
        if row["speaker"] not in _ROLES:
            raise ValueError(f"Unknown speaker: {row['speaker']!r}")
        turns.append({"id": f"t{index}", "speaker": row["speaker"], "role": _ROLES[row["speaker"]],
                      "text": row["utt_text"].strip(), "code": row["t2_label_GT"].strip()})
    return turns


def build_session(dataset_id, session_id, turns, *, retrieved_at, sha256, coded_url, quality=None):
    warnings, counts, utterance_codes = [], Counter(), []
    for turn in turns:
        code, codes = turn["code"], []
        if turn["role"] == "clinician":
            if code in COUNSELLOR_CODES:
                codes = [COUNSELLOR_CODES[code]]
                counts.update(codes)
            elif code in CLIENT_CODES:
                warnings.append(f"role-mismatch: {turn['id']}: client code on counsellor turn")
            elif code not in UNMAPPED_COUNSELLOR_CODES:
                warnings.append(f"unknown-code: {turn['id']}: {code}")
        elif code in COUNSELLOR_CODES or code in UNMAPPED_COUNSELLOR_CODES:
            warnings.append(f"role-mismatch: {turn['id']}: counsellor code on client turn")
        elif code not in CLIENT_CODES:
            warnings.append(f"unknown-code: {turn['id']}: {code}")
        utterance_codes.append({"turn_id": turn["id"], "codes": codes})
    transcript = {"language": "en", "turns": [{k: v for k, v in t.items() if k != "code"}
                                              for t in turns]}
    gold = make_gold(
        dataset_id, session_id, source={"coded_url": coded_url, "retrieved_at": retrieved_at,
                                        "sha256": sha256},
        counts=partial_counts(counts, LABELED), utterance_codes=utterance_codes, warnings=warnings,
        quality_label=quality, label_source="AutoMISC manual ground truth (t2_label_GT)",
        label_scheme=LABEL_SCHEME)
    return transcript, gold, warnings


def read_archive(path: Path):
    """Return {session_id: {"rows", "origin", "conv_id", "quality"}} for the human subsets."""
    sessions = {}
    with zipfile.ZipFile(path) as archive:
        for origin, member in _MEMBERS.items():
            grouped = defaultdict(list)
            text = archive.read(member).decode("utf-8-sig")
            for row in csv.DictReader(io.StringIO(text)):
                grouped[row["conv_id"]].append(row)
            for conv_id, rows in grouped.items():
                quality = None
                if origin == "hlqc":
                    quality = conv_id.split("_")[0]
                    if quality not in ("high", "low"):
                        raise ValueError(f"Unexpected HLQC id: {conv_id}")
                key = f"{origin}-{conv_id.replace('_', '-')}"
                sessions[key] = {"rows": rows, "origin": origin, "conv_id": conv_id,
                                 "quality": quality}
    return sessions


def convert_automisc_dataset(manifest: DatasetManifest, cache: Path | None = None,
                             session_id: str | None = None):
    from .fetch import default_cache, require_external_path

    cache = require_external_path(cache if cache is not None else default_cache())
    raw = cache / manifest.dataset_id / "raw"
    files = read_provenance(raw, manifest.dataset_id)
    sessions = read_archive(raw / SOURCE_FILE)
    common = source_record(files, SOURCE_FILE)

    def build(session):
        item = sessions[session.session_id]
        return build_session(manifest.dataset_id, session.session_id, turns_from_rows(item["rows"]),
                             quality=item["quality"], **common)

    return convert_sessions(manifest, cache, session_id, build)


HEADER = {
    "dataset_id": DATASET_ID,
    "title": "AutoMISC human-coded subsets (10 HLQC + 10 smoking-chatbot conversations)",
    "license_note": "Public GitHub repo (cimhasgithub/AutoMISC); GitHub reports no license. Paper: "
                    "https://aclanthology.org/2025.nlpai4health-main.4/ (says code and annotated "
                    "datasets are released, states no data license). HLQC text is the HLQC "
                    "corpus; smoking transcripts come from a chatbot study. Internal evaluation "
                    "use only; owner to confirm terms before any redistribution.",
    "source_page": "https://github.com/cimhasgithub/AutoMISC",
    "miti_version": None,
    "label_scheme": LABEL_SCHEME,
    "source_media": ["transcript"],
    "labels_summary": "Human MISC 2.5 counsellor codes mapped to 9 MITI counts (not seek_collab); "
                      "whole conversations coded; HLQC sessions also carry the high/low quality label",
    "overlaps_with": [
        {"dataset_id": "hlqc",
         "note": "The 10 hlqc-* sessions are HLQC conversations high_001, high_099, high_117, "
                 "high_121, high_127, low_001, low_026, low_031, low_033, low_080 (same ids as in "
                 "the hlqc dataset). Transcripts were re-parsed by AutoMISC into utterances, so "
                 "turn text and count can differ from the hlqc dataset."}],
    "source_format": "automisc_zip",
    "source_files": [SOURCE_URL],
}


def build_manifest(path: Path, cache: Path | None = None):
    raw = bootstrap_raw(DATASET_ID, "automisc_zip", [SOURCE_URL], cache)
    sessions = []
    for key, item in sorted(read_archive(raw / SOURCE_FILE).items()):
        hlqc = item["origin"] == "hlqc"
        n = len(item["rows"])
        sessions.append({
            "session_id": key,
            "title": (f"HLQC {item['conv_id']} ({item['quality']} quality)" if hlqc
                      else f"Smoking cessation chatbot study {item['conv_id']}"),
            "source_media": ["video", "transcript"] if hlqc else ["transcript"],
            "clinician_labels": ["counsellor"], "code_header": None,
            "change_goal": ("Behavior change discussed in the session (the source does not record it)"
                            if hlqc else "Quit smoking"),
            "change_goal_source": "curated", "coded_span": None,
            "notes": (f"{n} human-coded utterances, whole conversation; HLQC captions" if hlqc
                      else f"{n} human-coded utterances, whole conversation; the counsellor is an "
                           "LLM chatbot and the client a human smoker (typed chat)")})
    return write_manifest(path, HEADER, sessions)


if __name__ == "__main__":
    build_manifest(Path(__file__).resolve().parents[3] / "datasets" / DATASET_ID / "manifest.yaml")
