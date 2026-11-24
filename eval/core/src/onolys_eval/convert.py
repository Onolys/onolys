"""Position-based reference PDF conversion; source text stays in the external cache.

Overrides contain code/global corrections and optional reviewed_utterance_ids.
The latter explicitly acknowledges a checked coded/uncoded discrepancy only; it
never silences missing text, unknown codes, numbering, or count warnings.
"""
import json
import re
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import Field

from ._contracts import Contract, Nonempty
from ._formulas import compute_summaries
from .fetch import default_cache, require_external_path
from .gold import COUNT_IDS, GLOBAL_IDS, CountId, GlobalId, Gold
from .manifest import DatasetManifest, SessionManifest, load_manifest

_LABELS = {
    "GI": "gi", "PERSUADE": "persuade", "PERSUADE WITH": "persuade_permission",
    "PERSUADE WITH PERMISSION": "persuade_permission", "Q": "question", "SR": "sr",
    "CR": "cr", "AF": "affirm", "SEEK": "seek_collab",
    "EMPHASIZE": "emphasize_autonomy", "CONFRONT": "confront",
    "NC": None, "NOT CODED": None,
}
_GLOBAL_LABELS = {"CCT": "cct", "SST": "sst", "CULTIVATING": "cct", "SOFTENING": "sst",
                  "PAR": "partnership",
                  "PART": "partnership", "PARTNERSHIP": "partnership",
                  "EMP": "empathy", "EMPATHY": "empathy"}
_LABEL_PATTERN = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(k) for k in sorted(_LABELS, key=len, reverse=True))
    + r")(?!\w)", re.IGNORECASE)


def parse_codes(label: str) -> tuple[list[str], list[str]]:
    """Match longest labels first, including wrapped and multiple-code cells."""
    # Published code cells also contain teaching notes. Only explicit note
    # introducers end the assigned-code region; arbitrary unknown labels warn.
    normalized = " ".join(label.upper().split())
    normalized = re.sub(
        r"\((?:\d+|(?:HIGH|LOW) IN (?:CCT|SST)|CONT[’\']D FROM ABOVE|"
        r"SEEK CONSIDERED BUT DECLINED|COULD BE STRUCTURE|"
        r"DOES NOT MEET CRITERIA FOR SEEK|GI NOT WRONG|SR ONLY SET UP FOR Q)\)",
        " ", normalized)
    normalized = re.sub(r"\b(?:SEEK|CR|SR|AF|GI|Q) (?:CODE )?CONSIDERED.*", "", normalized)
    note = re.search(
        r"\*|[+−–-]\s*(?:CCT|SST|PARTNERSHIP|EMPATHY|SUPPORT|AFFIRM|NOT)|"
        r"A [“\"]?NO CODE|AFFIRM (?:CODES|CONSIDERED)|CONSIDERED|SUPPORTIVE|"
        r"THIS (?:COMMENT|IS|MIGHT)|AN EMPATHIC|CODE CONSIDERED|RULED OUT|"
        r"[“\"]DO YOU|REACHED BECAUSE|DID NOT MEET|NOT ENOUGH|STUCTURE|STRUCTURE",
        normalized)
    if note and _LABEL_PATTERN.search(normalized[:note.start()]):
        normalized = normalized[:note.start()]
    normalized = " ".join(re.sub(r"[/,;]", " ", normalized).split()).rstrip("- ")
    normalized = normalized.replace("EMPHA SIZE", "EMPHASIZE")
    codes = [_LABELS[m.group()] for m in _LABEL_PATTERN.finditer(normalized)]
    unknown = _LABEL_PATTERN.sub(" ", normalized).strip()
    return [c for c in codes if c is not None], [unknown] if unknown else []


@dataclass
class ParsedRow:
    number: int
    speaker: str
    text: str = ""
    label: str = ""
    codes: list[str] = field(default_factory=list)
    unknown_codes: list[str] = field(default_factory=list)


@dataclass
class ParsedDocument:
    rows: list[ParsedRow] = field(default_factory=list)
    globals: dict[str, int] = field(default_factory=dict)
    printed_counts: dict[str, int] = field(default_factory=dict)


def _lines(words):
    lines = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if not lines or abs(word["top"] - lines[-1][0]["top"]) > 3:
            lines.append([word])
        else:
            lines[-1].append(word)
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def parse_pages(pages, *, code_header="Code", layout=None) -> ParsedDocument:
    """Extract rows from pdfplumber words, preserving source utterance numbers.

    Layout settings supply column starts for PDFs without printed headers, or
    override margins. Column headers, when available, determine column positions.
    Continuation lines on later pages belong to the preceding observed row.
    """
    layout = layout or {}
    columns = {"number_x": 72., "speaker_x": 102., "text_x": 126.,
               "code_x": 447., "notes_x": 10000.}
    columns.update({k: v for k, v in layout.items() if k in columns})
    result = ParsedDocument()
    current = None
    ended = False
    for words, height in pages:
        lines = _lines(words)
        header_lines = [line for line in lines if any(
            w["text"].lower().strip(".#") in {"utt", "utterance"} and w["x0"] < 110
            for w in line
        )]
        for line in header_lines:
            header_text = " ".join(w["text"] for w in line).lower()
            if code_header and code_header.lower() in header_text:
                for start in range(len(line)):
                    if " ".join(w["text"] for w in line[start:start+len(code_header.split())]).lower() == code_header.lower():
                        columns["code_x"] = layout.get("code_x", line[start]["x0"])
            if any(w["text"].lower().strip(".#") == "content" for w in line):
                labels = [w for w in line if w["text"] in {"I", "P", "C"}]
                if labels:
                    columns["speaker_x"] = layout.get("speaker_x", labels[0]["x0"])
            for word in line:
                label = word["text"].lower().strip(".#")
                if label in {"utt", "utterance"} and word["x0"] < 110:
                    columns["number_x"] = layout.get("number_x", word["x0"])
                if label == "content":
                    columns["text_x"] = layout.get("text_x", word["x0"])
                if label == "notes":
                    columns["notes_x"] = layout.get("notes_x", word["x0"])
        for line in lines:
            top = min(w["top"] for w in line)
            if top < layout.get("header_bottom", 60) or top > height-layout.get("footer_height", 40):
                continue
            text = " ".join(w["text"] for w in line)
            if line in header_lines:
                continue
            if re.fullmatch(r"Global (?:ratings?|measures)(?: \(\d+\))?:?", text, re.IGNORECASE):
                ended = True
                continue
            # Ratings/totals are outside the table and may share one physical line.
            ratings = list(re.finditer(
                r"\b(CCT|SST|CULTIVATING|SOFTENING|PAR|PART|PARTNERSHIP|EMP|EMPATHY)\s*[:=]?\s*(-?\d+)\b",
                text, re.IGNORECASE))
            if ratings:
                ended = True
                for match in ratings:
                    result.globals[_GLOBAL_LABELS[match[1].upper()]] = int(match[2])
                continue
            total = re.fullmatch(r"(.+?)\s*[:=]\s*(\d+)\s*", text)
            if total:
                codes, unknown = parse_codes(total[1])
                if not unknown and len(codes) == 1:
                    result.printed_counts[codes[0]] = int(total[2])
                    ended = True
                    continue
            if ended:
                continue
            aliases = layout.get("number_aliases") or {}
            number_words = [w for w in line if abs(w["x0"]-columns["number_x"]) < 8
                            and (re.fullmatch(r"\d+", w["text"]) or w["text"] in aliases)]
            if number_words:
                speaker = [w["text"].strip(":") for w in line
                           if columns["speaker_x"]-5 <= w["x0"] < columns["text_x"]-5]
                printed = number_words[0]["text"]
                current = ParsedRow(aliases.get(printed, int(printed) if printed.isdigit() else 0),
                                    " ".join(speaker))
                result.rows.append(current)
            if current is None:
                continue
            body = [w["text"] for w in line
                    if columns["text_x"]-3 <= w["x0"] < columns["code_x"]-3]
            code = [w["text"] for w in line
                    if columns["code_x"]-3 <= w["x0"] < columns["notes_x"]-3]
            if body:
                current.text = " ".join(filter(None, [current.text, " ".join(body)]))
            if code:
                current.label = "\n".join(filter(None, [current.label, " ".join(code)]))
    for row in result.rows:
        row.codes, row.unknown_codes = parse_codes(row.label)
    return result


def read_pdf(path: Path, session: SessionManifest, *, coded=True) -> ParsedDocument:
    try:
        import pdfplumber
    except ImportError as error:
        raise ValueError("PDF conversion requires onolys-eval[convert]") from error
    settings = (session.pdf_layout if coded else session.uncoded_pdf_layout).model_dump(exclude_none=True)
    if not coded:
        settings.setdefault("code_x", 10000.)
    with pdfplumber.open(path) as pdf:
        return parse_pages([(p.extract_words(), p.height) for p in pdf.pages],
                           code_header=session.code_header if coded else "Code",
                           layout=settings)


class CodeOverride(Contract):
    turn_id: Nonempty
    codes: list[CountId]


class SourceNumberOverride(Contract):
    document: Literal["coded", "uncoded"] = "coded"
    row_index: Annotated[int, Field(ge=0)]
    source_number: Annotated[int, Field(ge=1)]
    number: Annotated[int, Field(ge=1)]


class Overrides(Contract):
    source_numbers: list[SourceNumberOverride] = Field(default_factory=list)
    utterance_codes: list[CodeOverride] = Field(default_factory=list)
    globals: dict[GlobalId, Annotated[int, Field(ge=1, le=5)]] = Field(default_factory=dict)
    reviewed_utterance_ids: list[Nonempty] = Field(default_factory=list)
    # Use the uncoded transcript's text for these turns (e.g. the coded PDF has inline
    # code annotations or segment markers); speaker must still agree.
    uncoded_text_turn_ids: list[Nonempty] = Field(default_factory=list)


def _normalized(text):
    return " ".join(text.split())


def build_session(manifest: DatasetManifest, session: SessionManifest,
                  coded: ParsedDocument, uncoded: ParsedDocument, source: dict,
                  overrides: dict | None = None):
    """Build strict gold, or None when absent/invalid ratings prevent valid gold.

    Invalid ratings are never replaced by guesses, including --allow-warnings.
    All other warnings remain in the written gold for downstream upload guards.
    """
    correction = Overrides.model_validate(overrides or {})
    documents = {"coded": coded, "uncoded": uncoded}
    corrected_indices = set()
    for item in correction.source_numbers:
        document = documents[item.document]
        rows = list(document.rows)
        identity = (item.document, item.row_index)
        if (identity in corrected_indices or item.row_index >= len(rows)
                or rows[item.row_index].number != item.source_number):
            raise ValueError("Invalid source number correction: inspect original row")
        corrected_indices.add(identity)
        rows[item.row_index] = replace(rows[item.row_index], number=item.number)
        documents[item.document] = replace(document, rows=rows)
    coded, uncoded = documents["coded"], documents["uncoded"]
    ids = [f"t{r.number}" for r in coded.rows]
    code_overrides = {r.turn_id: r.codes for r in correction.utterance_codes}
    referenced = (set(code_overrides) | set(correction.reviewed_utterance_ids)
                  | set(correction.uncoded_text_turn_ids))
    if referenced - set(ids):
        raise ValueError(f"Unknown override utterance IDs: {sorted(referenced-set(ids))}")
    if len(code_overrides) != len(correction.utterance_codes):
        raise ValueError("Duplicate override utterance IDs")
    warnings = []
    if (session.coded_span is not None and hasattr(session.coded_span, "end_turn")
            and session.coded_span.end_turn > len(coded.rows)):
        raise ValueError("coded_span exceeds observed transcript turns")
    if not coded.rows:
        warnings.append("empty-row: no utterances found")
    if [r.number for r in coded.rows] != list(range(1, len(coded.rows)+1)):
        warnings.append("noncontiguous-numbers: expected source numbers 1..N")
    if len(ids) != len(set(ids)):
        # Strict transcript/gold identities cannot represent duplicate source IDs.
        raise ValueError("Duplicate source utterance numbers; inspect PDF layout")
    globals_ = dict(coded.globals) | correction.globals
    for key in GLOBAL_IDS:
        if key not in globals_:
            warnings.append(f"globals-missing: {key}")
        elif not 1 <= globals_[key] <= 5:
            warnings.append(f"globals-out-of-range: {key}={globals_[key]}")
    other = {f"t{r.number}": r for r in uncoded.rows}
    if set(correction.uncoded_text_turn_ids) - set(other):
        raise ValueError(
            f"Unknown override utterance IDs: {sorted(set(correction.uncoded_text_turn_ids)-set(other))}")
    turns, utterance_codes = [], []
    counts = Counter(dict.fromkeys(COUNT_IDS, 0))
    for index, row in enumerate(coded.rows):
        turn_id = f"t{row.number}"
        if turn_id in correction.uncoded_text_turn_ids:
            row = replace(row, text=other[turn_id].text)
        if not row.text.strip():
            warnings.append(f"empty-row: {turn_id}")
        if row.unknown_codes and turn_id not in code_overrides:
            warnings.append(f"unknown-code: {turn_id}: {' '.join(row.unknown_codes)}")
        role = "clinician" if row.speaker in session.clinician_labels else "client"
        if not row.speaker:
            raise ValueError(f"Missing observed speaker label: {turn_id}")
        turns.append({"id": turn_id, "speaker": row.speaker, "role": role, "text": row.text})
        codes = code_overrides.get(turn_id, row.codes)
        utterance_codes.append({"turn_id": turn_id, "codes": codes})
        in_span = session.coded_span is None
        if session.coded_span is not None:
            if not hasattr(session.coded_span, "start_turn"):
                raise ValueError("Cannot apply a millisecond span to PDFs without timestamps")
            in_span = session.coded_span.start_turn <= index < session.coded_span.end_turn
        if role == "clinician" and in_span:
            counts.update(codes)
        mismatch = (turn_id not in other or row.speaker != other[turn_id].speaker
                    or _normalized(row.text) != _normalized(other[turn_id].text))
        if mismatch and turn_id not in correction.reviewed_utterance_ids:
            warnings.append(f"text-mismatch: {turn_id}: coded/uncoded source differs")
    for turn_id in other.keys()-set(ids):
        warnings.append(f"text-mismatch: {turn_id}: missing from coded PDF")
    for key, printed in coded.printed_counts.items():
        if counts[key] != printed:
            warnings.append(f"printed-count-mismatch: {key}: derived={counts[key]} printed={printed}")
    transcript = {"language": "en", "turns": turns}
    if any(w.startswith(("globals-missing:", "globals-out-of-range:")) for w in warnings):
        return transcript, None, warnings
    gold = Gold.model_validate({
        "schema": "gold.v1", "dataset_id": manifest.dataset_id, "session_id": session.session_id,
        "source": {"coded_url": session.coded_url, "uncoded_url": session.uncoded_url,
                   "retrieved_at": source["retrieved_at"], "sha256": source["sha256"]},
        "coded_span": session.coded_span, "counts": dict(counts), "globals": globals_,
        "summaries": compute_summaries(dict(counts), globals_), "utterance_codes": utterance_codes,
        "parse": {"method": "auto+override" if overrides else "auto", "warnings": warnings}})
    return transcript, gold, warnings


def manifest_path_for(dataset: str) -> Path:
    return Path(__file__).resolve().parents[3] / "datasets" / dataset / "manifest.yaml"


def convert_dataset(dataset: str, cache: Path | None = None, session_id: str | None = None,
                    *, dump=False, allow_warnings=False) -> int:
    manifest_path = manifest_path_for(dataset)
    manifest = load_manifest(manifest_path)
    if manifest.source_format == "mitags_csv":
        from .mitags import convert_mitags_dataset

        status, report = convert_mitags_dataset(manifest, cache, session_id)
        print("\n".join(report))
        return status
    cache = require_external_path(cache if cache is not None else default_cache())
    root = cache / manifest.dataset_id
    raw = root / "raw"
    provenance = json.loads((raw / "fetch.json").read_text())
    if provenance["dataset_id"] != manifest.dataset_id:
        raise ValueError("fetch.json dataset_id does not match manifest")
    sessions = [s for s in manifest.sessions if session_id is None or s.session_id == session_id]
    if not sessions:
        raise ValueError(f"Unknown session: {session_id}")
    status = 0
    for session in sessions:
        target = require_external_path(root / session.session_id)
        coded = read_pdf(raw / session.session_id / "coded.pdf", session)
        uncoded = read_pdf(raw / session.session_id / "uncoded.pdf", session, coded=False)
        override_path = manifest_path.parent / "overrides" / f"{session.session_id}.yaml"
        overrides = yaml.safe_load(override_path.read_text()) if override_path.exists() else None
        transcript, gold, warnings = build_session(
            manifest, session, coded, uncoded,
            provenance["files"][f"{session.session_id}/coded.pdf"], overrides)
        if dump:
            print(f"{session.session_id}\nturn\tspeaker\ttext\tparsed label\tcodes")
            for row in coded.rows:
                print(f"t{row.number}\t{row.speaker}\t{row.text}\t{row.label}\t{','.join(row.codes)}")
        for warning in warnings:
            print(f"{session.session_id}: {warning}")
        # Fail closed on unrepresentable gold; remove stale outputs from older conversions.
        if gold is None:
            for filename in ("transcript.json", "gold.json"):
                require_external_path(target / filename).unlink(missing_ok=True)
            status = 1
            continue
        target.mkdir(parents=True, exist_ok=True)
        for filename, data in (("transcript.json", transcript),
                               ("gold.json", gold.model_dump(mode="json", by_alias=True))):
            require_external_path(target / filename).write_text(json.dumps(data, indent=2)+"\n")
        print(f"{session.session_id}: converted ({len(warnings)} unresolved warnings)")
        if warnings and not allow_warnings:
            status = 1
    return status
