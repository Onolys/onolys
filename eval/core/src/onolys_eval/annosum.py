"""AnnoSUM-MI (human annotations only) to transcript.v1 and partial gold.v1.

Source: https://github.com/vsrana-ai/AnnoSUM-MI, folder ``Dataset`` (Kumar, Ntoutsi, Rajawat;
IJCNN 2025, arXiv 2511.22818). 131 of the 133 AnnoMI demonstration transcripts, split into a
train (97) and a test (34) file, semicolon-separated. ``transcript_id`` equals the AnnoMI
``transcript_id``, so session ids match ``annomi`` (``transcript-<id>``).

Only the human files are read: the dialogue files (``*_dataset_MI_sessions.csv``, AnnoMI
utterances with its ``main_therapist_behaviour``) and the expert session ratings
(``*_data_MI_annotated.csv``). The LLM summaries (``chatgpt``, ``Gemini``, ``DeepSeek``) and
their ratings are never fetched.

Mapping::

    main_therapist_behaviour == question   -> question (therapist utterances)
    Empathy rating 1-5                     -> globals.empathy
    mi_quality high/low                    -> quality_label

``main_therapist_behaviour`` is one label per utterance with no simple/complex or information
subtype, so ``sr``, ``cr``, ``gi`` and every other count stay ``null``. A question inside a
reflection or input utterance is not counted. The other ratings (Evocation, Collaboration,
Autonomy, Direction, Non-Judgmental Attitude and, in the train file only, Competence, Ethical
Behavior, Reflectiveness) are not MITI 4.2.1 globals and are not mapped. Empathy is a 1 to 5
Likert scale in the paper, so it is compared as is.

The CSV text has repairable encoding damage (UTF-8 punctuation read as Mac Roman) and one blank
utterance (transcript 3); both are handled here (blank turns skipped).
"""
import csv
import io
from collections import Counter, defaultdict
from pathlib import Path

from .manifest import DatasetManifest
from .annomi import MAX_WORDS, span_for_word_cap
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

DATASET_ID = "annosum-mi"
LABEL_SCHEME = "AnnoSUM-MI: AnnoMI question label and expert empathy rating (partial)"
BASE_URL = "https://raw.githubusercontent.com/vsrana-ai/AnnoSUM-MI/main/Dataset/"
SESSION_FILES = ("train_dataset_MI_sessions.csv", "test_dataset_MI_sessions.csv")
RATING_FILES = ("train_data_MI_annotated.csv", "test_data_MI_annotated.csv")
SOURCE_URLS = [BASE_URL + name for name in SESSION_FILES + RATING_FILES]
LABELED = ("question",)
_ROLES = {"therapist": "clinician", "client": "client"}
_MAIN = {"question", "reflection", "therapist_input", "other", ""}


def repair_text(text: str) -> str:
    """Undo UTF-8 text read as Mac Roman; leave text that does not round-trip untouched."""
    if text.isascii():
        return text
    try:
        return text.encode("mac_roman").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def empathy_of(rating) -> int | None:
    value = (rating.get("Empathy") or "").strip()
    if not value:
        return None
    if value not in {"1", "2", "3", "4", "5"}:
        raise ValueError(f"Empathy rating out of range: {value!r}")
    return int(value)


def turns_from_rows(rows):
    """One transcript's rows -> (ordered turns with ``codes``, number of blank turns skipped)."""
    turns, skipped = [], 0
    for row in sorted(rows, key=lambda r: int(r["utterance_id"])):
        side = row["interlocutor"]
        if side not in _ROLES:
            raise ValueError(f"Unknown interlocutor: {side!r}")
        main = row["main_therapist_behaviour"]
        if main not in _MAIN:
            raise ValueError(f"Unknown main_therapist_behaviour: {main!r}")
        text = repair_text(row["utterance_text"]).strip()
        if not text:
            skipped += 1
            continue
        codes = ["question"] if side == "therapist" and main == "question" else []
        turns.append({"id": f"t{len(turns) + 1}", "speaker": side, "role": _ROLES[side],
                      "text": text, "codes": codes})
    return turns, skipped


def build_session(dataset_id, session_id, turns, *, retrieved_at, sha256, coded_url,
                  quality=None, empathy=None, span=None):
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
        globals_={"empathy": empathy} if empathy is not None else None,
        coded_span={"start_turn": start, "end_turn": end} if span is not None else None,
        label_source="AnnoSUM-MI expert annotations (human; no LLM output)",
        label_scheme=LABEL_SCHEME)
    return transcript, gold, []


def _read(path: Path):
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"), newline=""),
                               delimiter=";"))


def read_dataset_files(raw: Path):
    """Return ({tid: (session file, rows)}, {tid: rating row}) in transcript-id order."""
    sessions = {}
    for name in SESSION_FILES:
        grouped = defaultdict(list)
        for row in _read(raw / name):
            grouped[row["transcript_id"]].append(row)
        for tid, rows in grouped.items():
            if tid in sessions:
                raise ValueError(f"Transcript {tid} is in both session files")
            if len({r["mi_quality"] for r in rows}) > 1:
                raise ValueError(f"Transcript {tid} has several mi_quality values")
            sessions[tid] = (name, rows)
    ratings = {}
    for name in RATING_FILES:
        for row in _read(raw / name):
            tid = row["transcript_id"]
            if tid in ratings:
                raise ValueError(f"Transcript {tid} is rated twice")
            if tid in sessions and row["mi_quality"] != sessions[tid][1][0]["mi_quality"]:
                raise ValueError(f"Transcript {tid}: mi_quality differs between session and rating files")
            ratings[tid] = row
    return dict(sorted(sessions.items(), key=lambda item: int(item[0]))), ratings


def convert_annosum_dataset(manifest: DatasetManifest, cache: Path | None = None,
                            session_id: str | None = None):
    from .fetch import default_cache, require_external_path

    cache = require_external_path(cache if cache is not None else default_cache())
    raw = cache / manifest.dataset_id / "raw"
    files = read_provenance(raw, manifest.dataset_id)
    sessions, ratings = read_dataset_files(raw)

    def build(session):
        tid = session.session_id.removeprefix("transcript-")
        name, rows = sessions[tid]
        turns, _ = turns_from_rows(rows)
        span = span_bounds(session, len(turns)) if session.coded_span else None
        return build_session(
            manifest.dataset_id, session.session_id, turns, quality=rows[0]["mi_quality"],
            empathy=empathy_of(ratings[tid]) if tid in ratings else None, span=span,
            **source_record(files, name))

    return convert_sessions(manifest, cache, session_id, build)


HEADER = {
    "dataset_id": DATASET_ID,
    "title": "AnnoSUM-MI: AnnoMI sessions with expert MITI-style ratings (131 transcripts)",
    "license_note": "No licence file in repo; internal evaluation only; licence request sent "
                    "to authors",
    "source_page": "https://github.com/vsrana-ai/AnnoSUM-MI",
    "miti_version": None,
    "label_scheme": LABEL_SCHEME,
    "source_media": ["video", "transcript"],
    "transcript_origin": "human",
    "labels_summary": "AnnoMI question label (main behaviour only) as 1 MITI count (question); "
                      "expert empathy rating 1-5 as the empathy global; high/low quality; "
                      "other ratings and all other counts not labeled",
    "source_format": "annosum_csv",
    "source_files": SOURCE_URLS,
    "overlaps_with": [{
        "dataset_id": "annomi",
        "note": "Same sessions: session ids equal AnnoMI transcript ids (transcript-<id>) for "
                "131 of AnnoMI's 133 transcripts (AnnoMI 47 and 129 are absent). Utterance ids "
                "and speakers match; 235 of 9,648 utterances carry small text edits (leading "
                "dashes dropped, minor punctuation or case changes, one blank utterance)."}],
}


def build_manifest(path: Path, cache: Path | None = None):
    """Download the human CSVs to the private cache and write the manifest YAML."""
    raw = bootstrap_raw(DATASET_ID, "annosum_csv", SOURCE_URLS, cache)
    sessions_by_id, ratings = read_dataset_files(raw)
    rows = []
    for tid, (name, session_rows) in sessions_by_id.items():
        turns, skipped = turns_from_rows(session_rows)
        span = span_for_word_cap(turns)
        topic = session_rows[0].get("topic_new", "").strip()
        empathy = empathy_of(ratings[tid]) if tid in ratings else None
        note = (f"mi_quality {session_rows[0]['mi_quality']}; {len(turns)} utterances"
                f"{f' ({skipped} blank skipped)' if skipped else ''}; "
                f"{'train' if name.startswith('train') else 'test'} split; "
                f"empathy rating {empathy if empathy is not None else 'missing'}")
        if span:
            note += f"; coded_span limits the coded text to the {MAX_WORDS}-word engine cap"
        rows.append({
            "session_id": f"transcript-{tid}", "title": f"AnnoSUM-MI session {tid}",
            "clinician_labels": ["therapist"], "code_header": None,
            "change_goal": topic or "Behavior change discussed in the session (not recorded in the test split)",
            "change_goal_source": "header" if topic else "curated",
            "coded_span": {"start_turn": span[0], "end_turn": span[1]} if span else None,
            "notes": note})
    return write_manifest(path, HEADER, rows)


if __name__ == "__main__":
    build_manifest(Path(__file__).resolve().parents[3] / "datasets" / DATASET_ID / "manifest.yaml")
