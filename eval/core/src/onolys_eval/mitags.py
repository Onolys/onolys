"""MI-TAGS sample CSVs to transcript.v1 and gold.v1 (MITI 4.2 codes, 4 globals).

Inputs (https://github.com/Advanced-Reality-Lab/MI-TAGS, sample files):

* ``sample_global_mitis.csv``: one row per (video, annotator) with the four global
  scores and the whole session as ``Tagged Text`` lines ``T: [Code] text`` (``Only
  Text`` is the same session without tags; it is only used as a consistency check).
* ``sample_utterances.csv``: one row per utterance (``Video Title``, ``Turn``,
  ``Speaker``, ``Text``, ``Code``, ``Annotator``). The public sample holds isolated
  utterances, so it only yields a session if a manifest session title matches.

Code mapping (clinician turns, MITI 4.2 -> gold counts)::

    Giving Information -> gi          Persuade -> persuade
    Persuade with Permission -> persuade_permission
    Question -> question              Simple Reflection -> sr
    Complex Reflection -> cr          Affirm -> affirm
    Seeking/Seek Collaboration -> seek_collab
    Emphasize/Emphasizing Autonomy -> emphasize_autonomy
    Confront -> confront

``Structure Statement`` is deliberately not counted (the Onolys MITI 4.2.1 pack does not
code structuring statements). Client tags (Neutral, Change Talk, Counter-Change Talk,
Sustain Talk) are CLEAR tags, not MITI behaviour codes, and are ignored.

Counts of gi, persuade, question, sr, cr, affirm and confront are always integers
(0 when absent). persuade_permission, seek_collab and emphasize_autonomy never appear
in the sample tag vocabulary, so they are ``null`` (not labeled) unless the session
actually contains such a tag. Summaries are omitted (partial gold).
"""
import csv
import io
import re
from collections import Counter
from pathlib import Path

from .fetch import default_cache, require_external_path
from .gold import COUNT_IDS, GLOBAL_IDS, Gold
from .manifest import DatasetManifest
from .publicsets import convert_sessions, read_provenance, source_record

LABEL_SCHEME = "MITI 4.2"
_CLINICIAN_CODES = {
    "giving information": "gi", "persuade": "persuade",
    "persuade with permission": "persuade_permission", "question": "question",
    "simple reflection": "sr", "complex reflection": "cr", "affirm": "affirm",
    "seeking collaboration": "seek_collab", "seek collaboration": "seek_collab",
    "emphasize autonomy": "emphasize_autonomy", "emphasizing autonomy": "emphasize_autonomy",
    "confront": "confront",
}
_IGNORED_TAGS = {"structure statement", "neutral", "change talk", "counter-change talk",
                 "sustain talk"}
_ALWAYS_LABELED = ("gi", "persuade", "question", "sr", "cr", "affirm", "confront")
_GLOBAL_COLUMNS = {"Empathy": "empathy", "SofteningSustainTalk": "sst",
                   "CultivatingChangeTalk": "cct", "Partnership": "partnership"}
_ROLES = {"T": "clinician", "C": "client"}
_LINE = re.compile(r"^([TC]): \[([^\]]*)\]\s?(.*)$")


def _tag_key(tag: str) -> str:
    return " ".join(tag.lower().split())


def _norm(text: str) -> str:
    return " ".join(text.split())


def parse_tagged_text(tagged: str):
    """Split ``T: [Code] text`` lines into turns (with their raw ``tag``)."""
    turns, warnings = [], []
    for line in tagged.splitlines():
        match = _LINE.match(line)
        if match is None:
            if not line.strip():
                continue
            if not turns:
                raise ValueError("Tagged text does not start with a tagged turn")
            turns[-1]["text"] += " " + line.strip()
            warnings.append(f"unparsed-line: appended to t{len(turns)}")
            continue
        speaker, tag, text = match.groups()
        turns.append({"id": f"t{len(turns)+1}", "speaker": speaker, "role": _ROLES[speaker],
                      "text": text.strip(), "tag": tag.strip()})
    return turns, warnings


def turns_from_utterance_rows(rows):
    """Order one video's utterance rows by ``Turn``; one annotator only."""
    if len({row["Annotator"] for row in rows}) > 1:
        raise ValueError("Multiple annotators for one video; choose one explicitly")
    ordered = sorted(rows, key=lambda row: int(row["Turn"]))
    numbers = [int(row["Turn"]) for row in ordered]
    if len(set(numbers)) != len(numbers):
        raise ValueError("Duplicate Turn numbers for one video")
    turns = []
    for index, row in enumerate(ordered, 1):
        speaker = row["Speaker"].strip()
        if speaker not in _ROLES:
            raise ValueError(f"Unknown speaker label: {speaker!r}")
        turns.append({"id": f"t{index}", "speaker": speaker, "role": _ROLES[speaker],
                      "text": row["Text"].strip(), "tag": row["Code"].strip()})
    return turns, []


def pick_global_row(rows, title):
    matches = [row for row in rows if row["Video Title"] == title]
    if not matches:
        raise ValueError(f"Video title not found: {title}")
    if len(matches) > 1:
        raise ValueError(f"Multiple annotator rows for {title}; choose one explicitly")
    return matches[0]


def build_session_from_turns(dataset_id, session_id, turns, scores, warnings, *,
                             retrieved_at, sha256, coded_url, annotator):
    """Return (transcript, gold-or-None, warnings); never invents missing ratings."""
    warnings = list(warnings)
    counts, utterance_codes = Counter(), []
    for turn in turns:
        key = _tag_key(turn["tag"])
        codes = []
        if key in _CLINICIAN_CODES:
            if turn["role"] != "clinician":
                warnings.append(f"role-mismatch: {turn['id']}: clinician code on client turn")
            else:
                codes = [_CLINICIAN_CODES[key]]
                counts.update(codes)
        elif key not in _IGNORED_TAGS:
            warnings.append(f"unknown-code: {turn['id']}: {turn['tag']}")
        utterance_codes.append({"turn_id": turn["id"], "codes": codes})
    transcript = {"language": "en", "turns": [{k: v for k, v in t.items() if k != "tag"}
                                              for t in turns]}
    globals_ = None
    if scores is not None:
        globals_ = {}
        for key in GLOBAL_IDS:
            value = scores.get(key)
            if not isinstance(value, int) or not 1 <= value <= 5:
                warnings.append(f"globals-out-of-range: {key}={value}")
            globals_[key] = value
        if any(w.startswith("globals-out-of-range:") for w in warnings):
            return transcript, None, warnings
    observed = {code for code in counts}
    full = {key: (counts[key] if key in _ALWAYS_LABELED or key in observed else None)
            for key in COUNT_IDS}
    gold = Gold.model_validate({
        "schema": "gold.v1", "dataset_id": dataset_id, "session_id": session_id,
        "source": {"coded_url": coded_url, "retrieved_at": retrieved_at, "sha256": sha256},
        "coded_span": None, "counts": full, "globals": globals_,
        "utterance_codes": utterance_codes,
        "parse": {"method": "auto", "warnings": warnings},
        "label_source": f"MI-TAGS sample, annotator {annotator}", "label_scheme": LABEL_SCHEME})
    return transcript, gold, warnings


def build_session_from_global_row(dataset_id, session_id, row, *, retrieved_at, sha256, coded_url):
    turns, warnings = parse_tagged_text(row["Tagged Text"])
    plain = [line for line in row["Only Text"].splitlines() if line.strip()]
    expected = [f"{t['speaker']}: {t['text']}" for t in turns]
    if [_norm(line) for line in plain] != [_norm(line) for line in expected]:
        warnings.append("text-mismatch: Only Text differs from Tagged Text")
    scores = {}
    for column, key in _GLOBAL_COLUMNS.items():
        try:
            scores[key] = int(row[column])
        except ValueError:
            scores[key] = None
    return build_session_from_turns(
        dataset_id, session_id, turns, scores, warnings, retrieved_at=retrieved_at,
        sha256=sha256, coded_url=coded_url, annotator=row["Annotator"])


def _read(path: Path):
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))


def convert_mitags_dataset(manifest: DatasetManifest, cache: Path | None = None,
                           session_id: str | None = None):
    """Write transcript.json and gold.json per manifest session; return (status, report)."""
    cache = require_external_path(cache if cache is not None else default_cache())
    raw = cache / manifest.dataset_id / "raw"
    files = read_provenance(raw, manifest.dataset_id)
    globals_rows, utterance_rows, global_file, utterance_file = [], [], None, None
    for name in sorted(files):
        rows = _read(raw / name)
        if rows and "Tagged Text" in rows[0]:
            globals_rows, global_file = rows, name
        elif rows and "Turn" in rows[0]:
            utterance_rows, utterance_file = rows, name
    used = set()

    def build(session):
        if any(row["Video Title"] == session.title for row in globals_rows):
            return build_session_from_global_row(
                manifest.dataset_id, session.session_id,
                pick_global_row(globals_rows, session.title), **source_record(files, global_file))
        rows = [r for r in utterance_rows if r["Video Title"] == session.title]
        if not rows:
            raise ValueError(f"Video title not found: {session.title}")
        turns, warnings = turns_from_utterance_rows(rows)
        used.update(id(r) for r in rows)
        return build_session_from_turns(
            manifest.dataset_id, session.session_id, turns, None, warnings,
            annotator=rows[0]["Annotator"], **source_record(files, utterance_file))

    status, report = convert_sessions(manifest, cache, session_id, build)
    left = [r for r in utterance_rows if id(r) not in used]
    if left:
        titles = {r["Video Title"] for r in left}
        report.append(f"{len(left)} utterance rows from {len(titles)} videos not converted "
                      "(isolated sample utterances, not sessions)")
    return status, report
