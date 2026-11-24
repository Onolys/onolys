"""MIDAS (Spanish MI) to transcript.v1 and partial gold.v1.

Source: https://github.com/MichiganNLP/MIDAS, file ``Spanish_MI.json`` (Gunal et al., NAACL
2025, arXiv 2502.08458). 74 Spanish-language MI conversations from YouTube (outer key = the
video id plus a variant suffix and ``.html``). Per turn: ``speaker`` (counselor, patient,
sometimes ``unclear``), ``turn`` (Spanish text), ``translated_turn`` (Google Translate, never
used), ``turn_number`` and ``tag_positions`` (character spans with a tag).

Transcripts were made with Amazon Transcribe, speakers labeled manually and the text reviewed
by two native Spanish speakers (paper section 3.1). Three Spanish-speaking MI counselors
annotated COUNSELOR turns for questions and reflections with ITEM2 (the Spanish MITI), one
span per instance (paper section 3.2). The source has no open/closed or simple/complex split.

Mapping::

    tag question    -> question (one per span)
    tag reflection  -> not mapped (no simple/complex split, so sr and cr stay null)
    tag empty       -> ignored (one span in the file; not a label)

No other counts, no globals, no summaries. Conversations whose speaker roles cannot be
determined are skipped, never guessed: any turn with speaker ``unclear``, or a counselor tag
on a patient turn (the role label is then wrong). Spans are counted as given; the few with
character positions outside their turn text are still counted (positions are not used).
"""
import json
import re
from collections import Counter
from pathlib import Path

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

DATASET_ID = "midas-es"
LABEL_SCHEME = "ITEM2 (Spanish MITI adaptation): questions and reflections"
SOURCE_FILE = "Spanish_MI.json"
SOURCE_URL = "https://raw.githubusercontent.com/MichiganNLP/MIDAS/main/Spanish_MI.json"
LABELED = ("question",)
_ROLES = {"counselor": "clinician", "patient": "client"}
_TAGS = {"question", "reflection", "empty"}


class UndeterminedRoles(ValueError):
    """The conversation's speaker roles cannot be trusted; it must not be converted."""


def session_id_for(key: str) -> str:
    """``6uqC49iSopg_c.html`` -> ``6uqc49isopg-c`` (lowercase identifier)."""
    return re.sub(r"[^a-z0-9]+", "-", key.removesuffix(".html").lower()).strip("-")


def turns_from_conversation(key: str, entries):
    """One conversation -> (ordered turns with ``codes``, stats of unmapped/odd spans)."""
    ordered = sorted(entries, key=lambda e: e["turn_number"])
    if [e["turn_number"] for e in ordered] != list(range(len(ordered))):
        raise ValueError(f"{key}: turn_number is not 0..n-1")
    turns, stats = [], Counter(reflection=0, empty=0, bad_span=0)
    for entry in ordered:
        speaker = entry["speaker"]
        if speaker == "unclear":
            raise UndeterminedRoles(f"{key}: speaker unclear on turn {entry['turn_number']}")
        if speaker not in _ROLES:
            raise ValueError(f"{key}: unknown speaker {speaker!r}")
        text = " ".join(entry["turn"].split())
        if not text:
            raise ValueError(f"{key}: empty text on turn {entry['turn_number']}")
        codes = []
        for span in entry["tag_positions"]:
            tag = span["tag"]
            if tag not in _TAGS:
                raise ValueError(f"{key}: unknown tag {tag!r}")
            if speaker == "patient":
                raise UndeterminedRoles(
                    f"{key}: counselor tag on patient turn {entry['turn_number']}")
            if not 0 <= span["start_pos"] < span["end_pos"] <= len(entry["turn"]):
                stats["bad_span"] += 1
            if tag == "question":
                codes.append("question")
            else:
                stats[tag] += 1
        turns.append({"id": f"t{len(turns) + 1}", "speaker": speaker, "role": _ROLES[speaker],
                      "text": text, "codes": codes})
    return turns, dict(stats)


def usable_conversations(data: dict):
    """Return ({session_id: (key, turns, stats)}, {key: skip reason}) in file order."""
    usable, skipped = {}, {}
    for key, entries in data.items():
        session_id = session_id_for(key)
        if session_id in usable:
            raise ValueError(f"Duplicate session id: {session_id}")
        try:
            turns, stats = turns_from_conversation(key, entries)
        except UndeterminedRoles as error:
            skipped[key] = str(error)
            continue
        usable[session_id] = (key, turns, stats)
    return usable, skipped


def build_session(dataset_id, session_id, turns, *, retrieved_at, sha256, coded_url):
    """Return (transcript, gold, warnings)."""
    counts = Counter(code for t in turns for code in t["codes"])
    transcript = {"language": "es", "turns": [
        {k: v for k, v in t.items() if k != "codes"} for t in turns]}
    gold = make_gold(
        dataset_id, session_id,
        source={"coded_url": coded_url, "retrieved_at": retrieved_at, "sha256": sha256},
        counts=partial_counts(counts, LABELED),
        utterance_codes=[{"turn_id": t["id"], "codes": t["codes"]} for t in turns],
        warnings=[], label_source="MIDAS human annotations (three MI counselors, ITEM2)",
        label_scheme=LABEL_SCHEME)
    return transcript, gold, []


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def convert_midas_dataset(manifest: DatasetManifest, cache: Path | None = None,
                          session_id: str | None = None):
    from .fetch import default_cache, require_external_path

    cache = require_external_path(cache if cache is not None else default_cache())
    raw = cache / manifest.dataset_id / "raw"
    files = read_provenance(raw, manifest.dataset_id)
    usable, skipped = usable_conversations(_load(raw / SOURCE_FILE))
    common = source_record(files, SOURCE_FILE)

    def build(session):
        if session.session_id not in usable:
            reasons = [v for k, v in skipped.items() if session_id_for(k) == session.session_id]
            raise ValueError(f"{session.session_id}: not a usable conversation"
                             f"{' (' + reasons[0] + ')' if reasons else ''}")
        return build_session(manifest.dataset_id, session.session_id,
                             usable[session.session_id][1], **common)

    return convert_sessions(manifest, cache, session_id, build)


HEADER = {
    "dataset_id": DATASET_ID,
    "title": "MIDAS: Spanish-language MI conversations from YouTube (ITEM2 questions and reflections)",
    "license_note": "No licence file in repo; internal evaluation only; licence request sent "
                    "to authors",
    "source_page": "https://github.com/MichiganNLP/MIDAS",
    "miti_version": None,
    "label_scheme": LABEL_SCHEME,
    "source_media": ["video", "transcript"],
    "transcript_origin": "human",
    "language": "es",
    "labels_summary": "Counselor questions as 1 MITI count (question); reflections annotated "
                      "but not split into simple/complex, so sr and cr not labeled; no other "
                      "counts, no globals; Spanish transcripts",
    "source_format": "midas_json",
    "source_files": [SOURCE_URL],
}


def build_manifest(path: Path, cache: Path | None = None):
    """Download Spanish_MI.json to the private cache and write the manifest YAML."""
    raw = bootstrap_raw(DATASET_ID, "midas_json", [SOURCE_URL], cache)
    usable, skipped = usable_conversations(_load(raw / SOURCE_FILE))
    rows = []
    for session_id, (key, turns, stats) in usable.items():
        video = key.removesuffix(".html")
        video_id = video[:11]  # YouTube ids are 11 characters; a suffix marks a variant
        questions = sum(len(t["codes"]) for t in turns)
        rows.append({
            "session_id": session_id, "title": f"MIDAS Spanish MI conversation {video}",
            "clinician_labels": ["counselor"], "code_header": None,
            "change_goal": "Behavior change discussed in the session (the source does not record it)",
            "change_goal_source": "curated", "coded_span": None,
            "notes": (f"source key {key}; video id {video_id} "
                      f"(https://www.youtube.com/watch?v={video_id}, may no longer be "
                      f"public); {len(turns)} turns; {questions} questions labeled, "
                      f"{stats['reflection']} reflections not mapped")})
    manifest = write_manifest(path, HEADER, rows)
    print(f"{len(rows)} sessions written; {len(skipped)} skipped (undetermined roles)")
    return manifest


if __name__ == "__main__":
    build_manifest(Path(__file__).resolve().parents[3] / "datasets" / DATASET_ID / "manifest.yaml")
