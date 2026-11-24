"""Dataset metadata contract. No source text, recordings, or gold data belong here."""
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, model_validator

from ._contracts import CodedSpan, Contract, HttpURL, Identifier, Nonempty


class PDFLayout(Contract):
    """Per-source coordinate quirks; omitted values use detected column headers."""
    number_x: float | None = None
    speaker_x: float | None = None
    text_x: float | None = None
    code_x: float | None = None
    notes_x: float | None = None
    header_bottom: float | None = None
    footer_height: float | None = None
    # Misprinted utterance-number tokens in the number column, e.g. {"Q": 2}.
    number_aliases: dict[str, int] | None = None


SourceMedia = Literal["audio", "video", "transcript"]
TranscriptOrigin = Literal["human", "auto_captions", "translated", "stt_ours"]


def _unique_media(media):
    if media is not None and len(set(media)) != len(media):
        raise ValueError("source_media must be unique")
    return media


class DatasetOverlap(Contract):
    """Another dataset that shares interviews with this one."""
    dataset_id: Identifier
    note: Nonempty


class SessionManifest(Contract):
    session_id: Identifier
    title: Nonempty
    # Required for PDF datasets; CSV datasets list their files at dataset level.
    uncoded_url: HttpURL | None = None
    coded_url: HttpURL | None = None
    audio_url: HttpURL | None = None
    # Per-session override of the dataset-level original source media.
    source_media: list[SourceMedia] | None = Field(default=None, min_length=1)
    clinician_labels: list[Nonempty] = Field(min_length=1)
    # Some PDFs have a code column but no printed column header.
    code_header: Nonempty | None
    change_goal: Nonempty
    change_goal_source: Literal["header", "curated"]
    coded_span: CodedSpan
    notes: str
    pdf_layout: PDFLayout = Field(default_factory=PDFLayout)
    uncoded_pdf_layout: PDFLayout = Field(default_factory=PDFLayout)

    @model_validator(mode="after")
    def unique_labels(self):
        _unique_media(self.source_media)
        if len(set(self.clinician_labels)) != len(self.clinician_labels):
            raise ValueError("clinician_labels must be unique")
        return self


SourceFormat = Literal[
    "pdf", "mitags_csv", "annomi_csv", "hlqc_zip"]


class DatasetManifest(Contract):
    dataset_id: Identifier
    title: Nonempty
    license_note: Nonempty
    source_page: HttpURL
    # null = labels are not MITI-coded (e.g. MISC or AnnoMI codes mapped to MITI).
    miti_version: Literal["4.2.1", "4.2", "4.0"] | None
    # Human-readable label scheme, e.g. "MITI 4.2", "MISC 2.5 mapped to MITI", "none".
    label_scheme: Nonempty | None = None
    # What the ORIGINAL source offers (we always store transcript.v1 regardless).
    source_media: list[SourceMedia] = Field(min_length=1)
    transcript_origin: TranscriptOrigin | None = None
    labels_summary: Nonempty | None = None
    overlaps_with: list[DatasetOverlap] = Field(default_factory=list)
    # "pdf": per-session coded/uncoded PDFs. Other formats: dataset-level source_files
    # (CSV/zip) read by that format's converter module.
    source_format: SourceFormat = "pdf"
    source_files: list[HttpURL] = Field(default_factory=list)
    sessions: list[SessionManifest] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_sessions(self):
        _unique_media(self.source_media)
        if self.source_format == "pdf":
            if any(s.coded_url is None or s.uncoded_url is None for s in self.sessions):
                raise ValueError("pdf datasets need coded_url and uncoded_url for every session")
        elif not self.source_files:
            raise ValueError("csv datasets need source_files")
        ids = [session.session_id for session in self.sessions]
        if len(ids) != len(set(ids)):
            raise ValueError("session_id must be unique within a dataset")
        return self


def load_manifest(path: str | Path) -> DatasetManifest:
    """Read a YAML manifest and reject invalid fields before any dataset I/O."""
    return DatasetManifest.model_validate(yaml.safe_load(Path(path).read_text()))
