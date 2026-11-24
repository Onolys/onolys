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
    uncoded_url: HttpURL
    coded_url: HttpURL
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


class DatasetManifest(Contract):
    dataset_id: Identifier
    title: Nonempty
    license_note: Nonempty
    source_page: HttpURL
    miti_version: Literal["4.2.1"]
    # What the ORIGINAL source offers (we always store transcript.v1 regardless).
    source_media: list[SourceMedia] = Field(min_length=1)
    transcript_origin: TranscriptOrigin | None = None
    labels_summary: Nonempty | None = None
    overlaps_with: list[DatasetOverlap] = Field(default_factory=list)
    sessions: list[SessionManifest] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_sessions(self):
        _unique_media(self.source_media)
        ids = [session.session_id for session in self.sessions]
        if len(ids) != len(set(ids)):
            raise ValueError("session_id must be unique within a dataset")
        return self


def load_manifest(path: str | Path) -> DatasetManifest:
    """Read a YAML manifest and reject invalid fields before any dataset I/O."""
    return DatasetManifest.model_validate(yaml.safe_load(Path(path).read_text()))
