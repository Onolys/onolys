"""Shared helpers for public-corpus converters that emit partial gold.v1.

Each converter module (annomi, hlqc, automisc, welivita) parses its raw files from the
private cache, builds ``transcript.v1`` + ``gold.v1`` per manifest session and writes
them next to the raw files. Nothing here touches the repository tree.
"""
import json
from collections import Counter
from pathlib import Path

import yaml

from .fetch import default_cache, fetch_dataset, require_external_path
from .gold import COUNT_IDS, Gold
from ._contracts import TimeSpan
from .manifest import DatasetManifest

ROLE_BY_SIDE = {"clinician": "clinician", "client": "client"}


def partial_counts(counter: Counter, labeled) -> dict:
    """Integers for labeled ids (0 when absent), null (not labeled) for the rest."""
    return {key: (int(counter[key]) if key in labeled else None) for key in COUNT_IDS}


def span_bounds(session, turn_count: int) -> tuple[int, int]:
    span = session.coded_span
    if span is None:
        return 0, turn_count
    if isinstance(span, TimeSpan):
        raise ValueError(f"{session.session_id}: time spans are not supported for text corpora")
    if not 0 <= span.start_turn < span.end_turn <= turn_count:
        raise ValueError(f"{session.session_id}: coded_span outside the transcript")
    return span.start_turn, span.end_turn


def make_gold(dataset_id, session_id, *, source, counts, utterance_codes, warnings,
              label_source, label_scheme, coded_span=None, quality_label=None) -> Gold:
    data = {
        "schema": "gold.v1", "dataset_id": dataset_id, "session_id": session_id,
        "source": source, "coded_span": coded_span, "counts": counts, "globals": None,
        "utterance_codes": utterance_codes, "parse": {"method": "auto", "warnings": warnings},
        "label_source": label_source, "label_scheme": label_scheme}
    if quality_label is not None:
        data["quality_label"] = quality_label
    return Gold.model_validate(data)


def read_provenance(raw: Path, dataset_id: str) -> dict:
    provenance = json.loads((raw / "fetch.json").read_text())
    if provenance["dataset_id"] != dataset_id:
        raise ValueError("fetch.json dataset_id does not match manifest")
    return provenance["files"]


def source_record(files: dict, name: str) -> dict:
    record = files[name]
    return {"coded_url": record["url"], "retrieved_at": record["retrieved_at"],
            "sha256": record["sha256"]}


def convert_sessions(manifest: DatasetManifest, cache: Path | None, session_id: str | None,
                     build):
    """Write transcript.json/gold.json per session; ``build(session)`` -> (transcript, gold, warnings)."""
    cache = require_external_path(cache if cache is not None else default_cache())
    root = cache / manifest.dataset_id
    sessions = [s for s in manifest.sessions if session_id in (None, s.session_id)]
    if not sessions:
        raise ValueError(f"Unknown session: {session_id}")
    status, report = 0, []
    for session in sessions:
        target = require_external_path(root / session.session_id)
        transcript, gold, warnings = build(session)
        for warning in warnings:
            report.append(f"{session.session_id}: {warning}")
        if gold is None:
            for filename in ("transcript.json", "gold.json"):
                require_external_path(target / filename).unlink(missing_ok=True)
            status = 1
            continue
        target.mkdir(parents=True, exist_ok=True)
        for filename, data in (("transcript.json", transcript),
                               ("gold.json", gold.model_dump(mode="json", by_alias=True))):
            require_external_path(target / filename).write_text(json.dumps(data, indent=2) + "\n")
        if warnings:
            status = 1
    report.append(f"{len(sessions)} sessions processed")
    return status, report


def bootstrap_raw(dataset_id: str, source_format: str, source_files: list[str],
                  cache: Path | None = None) -> Path:
    """Download the dataset-level files before the full manifest exists."""
    stub = DatasetManifest.model_validate({
        "dataset_id": dataset_id, "title": "stub", "license_note": "stub",
        "source_page": "https://example.org", "miti_version": None, "source_media": ["transcript"],
        "source_format": source_format, "source_files": source_files,
        "sessions": [{"session_id": "stub", "title": "stub", "clinician_labels": ["x"],
                      "code_header": None, "change_goal": "stub",
                      "change_goal_source": "curated", "coded_span": None, "notes": ""}]})
    return fetch_dataset(stub, cache)


def write_manifest(path: Path, header: dict, sessions: list[dict]) -> DatasetManifest:
    """Validate and write a manifest YAML (metadata only, never dataset text)."""
    manifest = DatasetManifest.model_validate({**header, "sessions": sessions})
    data = manifest.model_dump(mode="json")
    for key in ("label_scheme", "transcript_origin", "labels_summary"):
        if data.get(key) is None:
            data.pop(key, None)
    if data.get("language") == "en":
        data.pop("language")
    for key in ("overlaps_with", "source_files"):
        if not data[key]:
            data.pop(key)
    for session in data["sessions"]:
        for key in ("pdf_layout", "uncoded_pdf_layout"):
            session.pop(key, None)
        for key in ("uncoded_url", "coded_url", "audio_url", "source_media"):
            if session.get(key) is None:
                session.pop(key, None)
    # Stable, readable key order: header fields first, sessions last.
    order = [k for k in data if k not in ("source_format", "source_files", "overlaps_with",
                                          "sessions")]
    top = {k: data[k] for k in order}
    for key in ("source_format", "source_files", "overlaps_with", "sessions"):
        if key in data:
            top[key] = data[key]
    path.write_text(yaml.safe_dump(top, sort_keys=False, allow_unicode=True, width=10_000))
    return manifest
