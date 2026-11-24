"""Welivita & Pu MI dataset to transcript.v1 and partial gold.v1.

Source: https://github.com/anuradha1992/Motivational-Interviewing-Dataset, file
``MI Dataset.csv`` (COLING 2022, https://aclanthology.org/2022.coling-1.293/; CC BY-NC-SA
3.0). 2,000 short forum dialogues (1,000 CounselChat threads answered by professional
counsellors, 1,000 Reddit "RED" peer-support threads), one CSV row per SENTENCE.

Labels are HUMAN: trained counsellors recruited on UpWork labelled every listener sentence
(two workers, then judges resolved conflicts; paper section 3.3). ``final agreed label`` is
the resolved label; ``-`` means the sentence stayed unresolved and is not counted. No model
predictions exist in this file. Seeker (``speaker``) is the client, listener the clinician.

A transcript turn is one dialogue turn (its sentences joined by a space); the gold codes of
a turn list the mapped code of each labeled sentence in order (a code repeats when several
sentences carry it). Counts are per sentence.

Label mapping::

    Open Question, Closed Question -> question   Simple Reflection -> sr
    Complex Reflection -> cr    Affirm -> affirm    Give Information -> gi
    Advise with Permission -> persuade_permission
    Advise without Permission, Warn, Direct -> persuade
    Emphasize Autonomy -> emphasize_autonomy       Confront -> confront

Not counted: Support, Self-Disclose, Other (no MITI 4.2.1 count). Warn and Direct count as
persuade (owner decision). No Seek Collaboration label exists, so ``seek_collab`` is ``null``. No globals, no summaries.
"""
import csv
import io
import re
from collections import Counter, OrderedDict
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

DATASET_ID = "welivita-mi"
LABEL_SCHEME = "Welivita & Pu MI labels mapped to MITI counts (partial)"
SOURCE_FILE = "MI Dataset.csv"
SOURCE_URL = ("https://raw.githubusercontent.com/anuradha1992/Motivational-Interviewing-Dataset/"
              "main/MI%20Dataset.csv")
LABELED = tuple(k for k in COUNT_IDS if k != "seek_collab")
LABEL_MAP = {
    "Open Question": "question", "Closed Question": "question", "Simple Reflection": "sr",
    "Complex Reflection": "cr", "Affirm": "affirm", "Give Information": "gi",
    "Advise with Permission": "persuade_permission", "Advise without Permission": "persuade",
    "Warn": "persuade", "Direct": "persuade",
    "Emphasize Autonomy": "emphasize_autonomy", "Confront": "confront"}
UNMAPPED_LABELS = {"Support", "Self-Disclose", "Other"}
UNRESOLVED = "-"
_ROLES = {"speaker": "client", "listener": "clinician"}
_SIDES = {"speaker": "seeker", "listener": "helper"}


def session_id_for(dialog_id: str) -> str:
    """``counsel_chat |<nbsp>1`` -> ``counsel-chat-1``; ``RED |<nbsp>115 - Sub`` -> ``red-115-sub``."""
    return re.sub(r"[^a-z0-9]+", "-", dialog_id.replace("\xa0", " ").lower()).strip("-")


def turns_from_rows(rows):
    """One dialogue's sentence rows -> ordered turns carrying ``labels`` (one per sentence)."""
    turns = []
    for row in rows:
        author = row["author"]
        if author not in _ROLES:
            raise ValueError(f"Unknown author: {author!r}")
        key = (row["turn"], author)
        if not turns or turns[-1]["key"] != key:
            if any(t["key"] == key for t in turns):
                raise ValueError(f"Turn {row['turn']} is not contiguous")
            turns.append({"key": key, "speaker": _SIDES[author], "role": _ROLES[author],
                          "sentences": [], "labels": []})
        sentence = " ".join(row["text"].split())
        if sentence:
            turns[-1]["sentences"].append(sentence)
            turns[-1]["labels"].append(row["final agreed label"].strip() if author == "listener"
                                       else None)
    out = []
    for turn in turns:
        if not turn["sentences"]:
            raise ValueError("Turn without text")
        out.append({"id": f"t{len(out) + 1}", "speaker": turn["speaker"], "role": turn["role"],
                    "text": " ".join(turn["sentences"]), "labels": turn["labels"]})
    return out


def build_session(dataset_id, session_id, turns, *, retrieved_at, sha256, coded_url):
    """Return (transcript, gold, warnings, stats). Stats count sentences by outcome."""
    counts, utterance_codes, warnings = Counter(), [], []
    stats = Counter()
    for turn in turns:
        codes = []
        if turn["role"] == "clinician":
            for label in turn["labels"]:
                if label in LABEL_MAP:
                    codes.append(LABEL_MAP[label])
                    stats["mapped"] += 1
                elif label in UNMAPPED_LABELS:
                    stats["unmapped"] += 1
                elif label == UNRESOLVED:
                    stats["unresolved"] += 1
                else:
                    warnings.append(f"unknown-label: {turn['id']}: {label!r}")
        counts.update(codes)
        utterance_codes.append({"turn_id": turn["id"], "codes": codes})
    transcript = {"language": "en", "turns": [
        {k: v for k, v in t.items() if k != "labels"} for t in turns]}
    gold = make_gold(
        dataset_id, session_id,
        source={"coded_url": coded_url, "retrieved_at": retrieved_at, "sha256": sha256},
        counts=partial_counts(counts, LABELED), utterance_codes=utterance_codes,
        warnings=warnings, label_source="Welivita & Pu human annotations (final agreed label)",
        label_scheme=LABEL_SCHEME)
    return transcript, gold, warnings, stats


def read_dialogues(path: Path):
    """Return {session_id: (dialog_id, rows)} in file order; ids must be unique."""
    text = path.read_text(encoding="utf-8-sig")
    grouped = OrderedDict()
    for row in csv.DictReader(io.StringIO(text, newline="")):
        grouped.setdefault(row["dialog_id"], []).append(row)
    out = {}
    for dialog_id, rows in grouped.items():
        key = session_id_for(dialog_id)
        if key in out:
            raise ValueError(f"Duplicate session id: {key}")
        out[key] = (dialog_id, rows)
    return out


def convert_welivita_dataset(manifest: DatasetManifest, cache: Path | None = None,
                             session_id: str | None = None):
    from .fetch import default_cache, require_external_path

    cache = require_external_path(cache if cache is not None else default_cache())
    raw = cache / manifest.dataset_id / "raw"
    files = read_provenance(raw, manifest.dataset_id)
    dialogues = read_dialogues(raw / SOURCE_FILE)
    common = source_record(files, SOURCE_FILE)

    def build(session):
        transcript, gold, warnings, _ = build_session(
            manifest.dataset_id, session.session_id,
            turns_from_rows(dialogues[session.session_id][1]), **common)
        return transcript, gold, warnings

    return convert_sessions(manifest, cache, session_id, build)


HEADER = {
    "dataset_id": DATASET_ID,
    "title": "Welivita & Pu MI dataset (2,000 forum dialogues, MI-labelled helper sentences)",
    "license_note": "CC BY-NC-SA 3.0 (non-commercial, share-alike, attribution) per the repo "
                    "README; read the paper's ethics section before use. Cite Welivita & Pu "
                    "(COLING 2022). Internal non-commercial evaluation only.",
    "source_page": "https://github.com/anuradha1992/Motivational-Interviewing-Dataset",
    "miti_version": None,
    "label_scheme": LABEL_SCHEME,
    "source_media": ["transcript"],
    "transcript_origin": "human",
    "labels_summary": "Human-labelled helper sentences mapped to 9 MITI counts (not seek_collab); "
                      "short forum threads, not counselling sessions; no globals",
    "source_format": "welivita_csv",
    "source_files": [SOURCE_URL],
}


def build_manifest(path: Path, cache: Path | None = None):
    raw = bootstrap_raw(DATASET_ID, "welivita_csv", [SOURCE_URL], cache)
    sessions = []
    for key, (dialog_id, rows) in read_dialogues(raw / SOURCE_FILE).items():
        turns = turns_from_rows(rows)
        _, _, _, stats = build_session(DATASET_ID, key, turns, retrieved_at="2026-01-01T00:00:00+00:00",
                                       sha256=None, coded_url=None)
        counsel = dialog_id.startswith("counsel_chat")
        post_id = dialog_id.replace("\xa0", " ").split("|", 1)[1].strip()
        sessions.append({
            "session_id": key,
            "title": (f"CounselChat thread {post_id}" if counsel
                      else f"Reddit RED thread {post_id}"),
            "clinician_labels": ["helper"], "code_header": None,
            "change_goal": "Not stated (forum post seeking support or advice)",
            "change_goal_source": "curated", "coded_span": None,
            "notes": (f"{'CounselChat (professional counsellor answers)' if counsel else 'Reddit peer support'}; "
                      f"{len(turns)} turns; helper sentences: {stats['mapped']} mapped, "
                      f"{stats['unmapped']} labelled but not mapped, "
                      f"{stats['unresolved']} unresolved (not counted)")})
    return write_manifest(path, HEADER, sessions)


if __name__ == "__main__":
    build_manifest(Path(__file__).resolve().parents[3] / "datasets" / DATASET_ID / "manifest.yaml")
