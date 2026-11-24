"""HLQC (High and Low Quality Counseling) archive to transcript.v1 and quality-only gold.v1.

Source: https://web.eecs.umich.edu/~mihalcea/downloads/HighLowQualityCounseling.zip
(Perez-Rosas et al., ACL 2019, https://aclanthology.org/P19-1088/). The archive holds
``labels.csv`` (``id,label`` with high/low) and ``transcripts/<id>`` text files: one turn
per line, ``T:<TAB>text`` (therapist) or ``C:<TAB>text`` (client). The text comes from
automatic video captions. There are no behaviour codes in the archive, so gold carries the
session ``quality_label`` only (counts all null, no globals, no summaries).

Parsing: a few lines deviate (``T: <TAB>``, ``C<TAB>``, and one file using ``T: text`` with a space) and are accepted. A line with no
speaker tag (a caption wrap) is appended to the previous turn and counted in the report.
Text before the first speaker tag is an error: speakers are never guessed.
"""
import csv
import io
import re
import zipfile
from pathlib import Path

from .gold import COUNT_IDS
from .manifest import DatasetManifest
from .publicsets import (
    bootstrap_raw,
    convert_sessions,
    make_gold,
    read_provenance,
    source_record,
    write_manifest,
)

DATASET_ID = "hlqc"
LABEL_SCHEME = "Session quality label (high/low) only"
SOURCE_FILE = "HighLowQualityCounseling.zip"
SOURCE_URL = "https://web.eecs.umich.edu/~mihalcea/downloads/HighLowQualityCounseling.zip"
_ROOT = "HighLowQualityCounseling/"
_ROLES = {"T": "clinician", "C": "client"}
_LINE = re.compile(r"^([TC])(?:\s*:?\s*\t|\s*:\s*)(.*)$")


def parse_transcript(text: str):
    """Return (turns, notes). Turns have id, speaker (T/C), role and text."""
    turns, appended = [], 0
    for line in text.lstrip("\ufeff").splitlines():
        if not line.strip():
            continue
        match = _LINE.match(line)
        if match is None:
            if not turns:
                raise ValueError("Text before the first speaker tag")
            turns[-1]["text"] += " " + " ".join(line.split())
            appended += 1
            continue
        speaker, body = match.groups()
        body = " ".join(body.split())
        if body:
            turns.append({"id": f"t{len(turns)+1}", "speaker": speaker, "role": _ROLES[speaker],
                          "text": body})
    notes = [f"{appended} unlabeled line(s) appended to the previous turn"] if appended else []
    return turns, notes


def read_archive(path: Path):
    """Return (labels by id, transcript text by id); macOS resource files are ignored."""
    with zipfile.ZipFile(path) as archive:
        rows = csv.DictReader(io.StringIO(archive.read(_ROOT + "labels.csv").decode("utf-8-sig")))
        labels = {row["id"]: row["label"] for row in rows}
        transcripts = {
            name.rsplit("/", 1)[1]: archive.read(name).decode("utf-8", "replace")
            for name in archive.namelist()
            if name.startswith(_ROOT + "transcripts/") and not name.endswith("/")}
    for ident, label in labels.items():
        if label not in ("high", "low") or not ident.startswith(label + "_"):
            raise ValueError(f"Label {label!r} does not match id {ident!r}")
    return labels, transcripts


def session_id_for(ident: str) -> str:
    return ident.replace("_", "-")


def build_session(dataset_id, session_id, turns, quality, *, retrieved_at, sha256, coded_url):
    transcript = {"language": "en", "turns": turns}
    gold = make_gold(
        dataset_id, session_id,
        source={"coded_url": coded_url, "retrieved_at": retrieved_at, "sha256": sha256},
        counts={key: None for key in COUNT_IDS}, utterance_codes=None, warnings=[],
        quality_label=quality, label_source="HLQC labels.csv (Perez-Rosas et al., 2019)",
        label_scheme=LABEL_SCHEME)
    return transcript, gold


def convert_hlqc_dataset(manifest: DatasetManifest, cache: Path | None = None,
                         session_id: str | None = None):
    from .fetch import default_cache, require_external_path

    cache = require_external_path(cache if cache is not None else default_cache())
    raw = cache / manifest.dataset_id / "raw"
    files = read_provenance(raw, manifest.dataset_id)
    labels, transcripts = read_archive(raw / SOURCE_FILE)
    common = source_record(files, SOURCE_FILE)
    by_session = {session_id_for(i): i for i in transcripts}
    notes = []

    def build(session):
        ident = by_session[session.session_id]
        turns, parsed_notes = parse_transcript(transcripts[ident])
        notes.extend(f"{session.session_id}: {n}" for n in parsed_notes)
        transcript, gold = build_session(manifest.dataset_id, session.session_id, turns,
                                         labels[ident], **common)
        return transcript, gold, []

    status, report = convert_sessions(manifest, cache, session_id, build)
    return status, notes + report


HEADER = {
    "dataset_id": DATASET_ID,
    "title": "HLQC: high and low quality counseling (258 transcripts)",
    "license_note": "Public download from the authors' page (web.eecs.umich.edu/~mihalcea) with no "
                    "stated license. Internal evaluation use only; owner to confirm terms before "
                    "any redistribution.",
    "source_page": "https://aclanthology.org/P19-1088/",
    "miti_version": None,
    "label_scheme": LABEL_SCHEME,
    "source_media": ["video", "transcript"],
    "transcript_origin": "auto_captions",
    "labels_summary": "Session quality label (high/low) only; no behaviour counts or globals",
    "overlaps_with": [
        {"dataset_id": "automisc-human",
         "note": "AutoMISC human-coded subset covers 10 HLQC conversations (high_001, high_099, "
                 "high_117, high_121, high_127, low_001, low_026, low_031, low_033, low_080); "
                 "its transcripts were re-parsed, so text can differ slightly."},
        {"dataset_id": "mi-tags-sample",
         "note": "The full (access-gated) MI-TAGS set reportedly includes 140 HLQC transcripts; "
                 "the public MI-TAGS sample does not."}],
    "source_format": "hlqc_zip",
    "source_files": [SOURCE_URL],
}


def build_manifest(path: Path, cache: Path | None = None):
    raw = bootstrap_raw(DATASET_ID, "hlqc_zip", [SOURCE_URL], cache)
    labels, transcripts = read_archive(raw / SOURCE_FILE)
    sessions = []
    for ident in sorted(transcripts):
        sessions.append({
            "session_id": session_id_for(ident), "title": f"HLQC {ident} ({labels[ident]} quality)",
            "clinician_labels": ["T"], "code_header": None,
            "change_goal": "Behavior change discussed in the session (the source does not record it)",
            "change_goal_source": "curated", "coded_span": None,
            "notes": f"archive id {ident}; speakers from the T:/C: line tags"})
    return write_manifest(path, HEADER, sessions)


if __name__ == "__main__":
    build_manifest(Path(__file__).resolve().parents[3] / "datasets" / DATASET_ID / "manifest.yaml")
