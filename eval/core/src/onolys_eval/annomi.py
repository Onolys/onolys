"""AnnoMI (full CSV) to transcript.v1 and partial gold.v1.

Source: https://github.com/uccollab/AnnoMI (``AnnoMI-full.csv``; Wu et al., ICASSP 2022 and
Future Internet 15(3):110, 2023). 133 transcripts of public MI demonstration videos, one
row per (utterance, annotator). 126 transcripts have one annotator; 7 were annotated by all
ten, which ``AnnoMI-simple.csv`` collapses by majority vote. We use the same idea for every
code: a code is counted only when a strict majority of the annotators of that utterance
gave it (single-annotator transcripts: that annotator).

Mapping (therapist utterances, AnnoMI attribute -> gold count)::

    question_exists (open or closed)          -> question
    reflection_exists + subtype simple        -> sr
    reflection_exists + subtype complex       -> cr
    therapist_input_exists + subtype information -> gi

``advice`` / ``options`` / ``negotiation`` inputs are not cleanly Persuade versus Persuade
with Permission, so ``persuade`` and ``persuade_permission`` stay ``null``; affirm,
seek_collab, emphasize_autonomy and confront have no AnnoMI attribute and are ``null``.
The four mapped counts are integers (0 when absent). One utterance can carry several codes
(e.g. information and question). No globals, no summaries. ``mi_quality`` gives the
transcript's high/low ``quality_label``.
"""
import csv
import io
from collections import Counter, defaultdict
from pathlib import Path

from .manifest import DatasetManifest
from .publicsets import (
    bootstrap_raw,
    convert_sessions,
    make_gold,
    partial_counts,
    read_provenance,
    source_record,
    span_bounds,
    write_manifest,
)

DATASET_ID = "annomi"
LABEL_SCHEME = "AnnoMI codes mapped to MITI counts (partial)"
SOURCE_FILE = "AnnoMI-full.csv"
SOURCE_URL = "https://raw.githubusercontent.com/uccollab/AnnoMI/main/AnnoMI-full.csv"
LABELED = ("gi", "question", "sr", "cr")
MAX_WORDS = 6000
_ROLES = {"therapist": "clinician", "client": "client"}
_SUBTYPES = {
    "reflection_subtype": {"simple", "complex", "n/a"},
    "question_subtype": {"open", "closed", "n/a"},
    "therapist_input_subtype": {"information", "advice", "negotiation", "options", "n/a"},
}


def _codes_of(row) -> set[str]:
    """Gold codes for one annotator's row (therapist utterances only)."""
    codes = set()
    if row["interlocutor"] != "therapist":
        return codes
    for column, allowed in _SUBTYPES.items():
        if row[column] not in allowed:
            raise ValueError(f"Unknown {column}: {row[column]!r}")
    if row["question_exists"] == "True":
        codes.add("question")
    if row["reflection_exists"] == "True":
        if row["reflection_subtype"] == "simple":
            codes.add("sr")
        elif row["reflection_subtype"] == "complex":
            codes.add("cr")
    if row["therapist_input_exists"] == "True" and row["therapist_input_subtype"] == "information":
        codes.add("gi")
    return codes


def utterances_from_rows(rows):
    """One transcript's rows (any number of annotators) -> ordered turns with ``codes``."""
    by_utterance = defaultdict(list)
    for row in rows:
        if row["interlocutor"] not in _ROLES:
            raise ValueError(f"Unknown interlocutor: {row['interlocutor']!r}")
        by_utterance[int(row["utterance_id"])].append(row)
    turns = []
    for index, utterance_id in enumerate(sorted(by_utterance), 1):
        group = by_utterance[utterance_id]
        if len({r["utterance_text"] for r in group}) > 1 or \
                len({r["interlocutor"] for r in group}) > 1:
            raise ValueError(f"Utterance {utterance_id} differs between annotators")
        if len({r["annotator_id"] for r in group}) != len(group):
            raise ValueError(f"Utterance {utterance_id} has duplicate annotator rows")
        votes = Counter(code for r in group for code in _codes_of(r))
        codes = [c for c in ("gi", "question", "sr", "cr") if votes[c] * 2 > len(group)]
        side = group[0]["interlocutor"]
        turns.append({"id": f"t{index}", "speaker": side, "role": _ROLES[side],
                      "text": group[0]["utterance_text"].strip(), "codes": codes})
    return turns


def span_for_word_cap(turns):
    """Turn span limiting the coded text to the 6,000-word engine cap; None when it fits."""
    total = 0
    for index, turn in enumerate(turns):
        total += len(turn["text"].split())
        if total > MAX_WORDS:
            return (0, index)
    return None


def build_session(dataset_id, session_id, turns, *, retrieved_at, sha256, coded_url,
                  quality=None, span=None):
    """Return (transcript, gold, warnings). ``span`` limits counts to turns [start, end)."""
    if quality not in (None, "high", "low"):
        raise ValueError(f"Unknown mi_quality: {quality!r}")
    start, end = span if span is not None else (0, len(turns))
    counts = Counter(code for t in turns[start:end] for code in t["codes"])
    transcript = {"language": "en", "turns": [
        {k: v for k, v in t.items() if k != "codes"} for t in turns]}
    gold = make_gold(
        dataset_id, session_id, source={"coded_url": coded_url, "retrieved_at": retrieved_at,
                                        "sha256": sha256},
        counts=partial_counts(counts, LABELED),
        utterance_codes=[{"turn_id": t["id"], "codes": t["codes"]} for t in turns[start:end]],
        warnings=[], quality_label=quality,
        coded_span={"start_turn": start, "end_turn": end} if span is not None else None,
        label_source="AnnoMI expert annotators (AnnoMI-full.csv)", label_scheme=LABEL_SCHEME)
    return transcript, gold, []


def _read(path: Path):
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))


def _transcripts(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["transcript_id"]].append(row)
    return dict(sorted(grouped.items(), key=lambda item: int(item[0])))


def convert_annomi_dataset(manifest: DatasetManifest, cache: Path | None = None,
                           session_id: str | None = None):
    from .fetch import default_cache, require_external_path

    cache = require_external_path(cache if cache is not None else default_cache())
    raw = cache / manifest.dataset_id / "raw"
    files = read_provenance(raw, manifest.dataset_id)
    grouped = _transcripts(_read(raw / SOURCE_FILE))
    common = source_record(files, SOURCE_FILE)

    def build(session):
        tid = session.session_id.removeprefix("transcript-")
        rows = grouped[tid]
        turns = utterances_from_rows(rows)
        span = span_bounds(session, len(turns)) if session.coded_span else None
        return build_session(manifest.dataset_id, session.session_id, turns, quality=rows[0]["mi_quality"],
                             span=span, **common)

    return convert_sessions(manifest, cache, session_id, build)


HEADER = {
    "dataset_id": DATASET_ID,
    "title": "AnnoMI: expert-annotated MI demonstrations (133 transcripts, high/low quality)",
    "license_note": "Public GitHub release (uccollab/AnnoMI); the repo declares no license and "
                    "the README gives no reuse statement. Transcripts of public YouTube/Vimeo "
                    "demo videos. Internal evaluation use only; owner to confirm terms before "
                    "any redistribution.",
    "source_page": "https://github.com/uccollab/AnnoMI",
    "miti_version": None,
    "label_scheme": LABEL_SCHEME,
    "source_media": ["video", "transcript"],
    "transcript_origin": "human",
    "labels_summary": "Therapist question/reflection/information codes mapped to 4 MITI counts "
                      "(question, sr, cr, gi); persuade, affirm, seek, emphasize autonomy and "
                      "confront not labeled; high/low session quality label",
    "source_format": "annomi_csv",
    "source_files": [SOURCE_URL],
}


def build_manifest(path: Path, cache: Path | None = None):
    """Download AnnoMI-full.csv to the private cache and write the manifest YAML."""
    raw = bootstrap_raw(DATASET_ID, "annomi_csv", [SOURCE_URL], cache)
    sessions = []
    for tid, rows in _transcripts(_read(raw / SOURCE_FILE)).items():
        turns = utterances_from_rows(rows)
        span = span_for_word_cap(turns)
        first = rows[0]
        annotators = sorted({r["annotator_id"] for r in rows}, key=int)
        note = (f"mi_quality {first['mi_quality']}; video {first['video_url']}; "
                f"{len(turns)} utterances")
        note += (f"; majority vote over annotators {','.join(annotators)}"
                 if len(annotators) > 1 else f"; annotator {annotators[0]}")
        if span:
            note += f"; coded_span limits the coded text to the {MAX_WORDS}-word engine cap"
        sessions.append({
            "session_id": f"transcript-{tid}", "title": first["video_title"].strip(),
            "clinician_labels": ["therapist"], "code_header": None,
            "change_goal": first["topic"].strip() or "Behavior change discussed in the session",
            "change_goal_source": "header",
            "coded_span": {"start_turn": span[0], "end_turn": span[1]} if span else None,
            "notes": note})
    return write_manifest(path, HEADER, sessions)


if __name__ == "__main__":
    build_manifest(Path(__file__).resolve().parents[3] / "datasets" / DATASET_ID / "manifest.yaml")
