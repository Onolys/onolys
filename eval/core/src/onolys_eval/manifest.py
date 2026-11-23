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


class SessionManifest(Contract):
    session_id: Identifier
    title: Nonempty
    uncoded_url: HttpURL
    coded_url: HttpURL
    audio_url: HttpURL | None = None
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
        if len(set(self.clinician_labels)) != len(self.clinician_labels):
            raise ValueError("clinician_labels must be unique")
        return self


class DatasetManifest(Contract):
    dataset_id: Identifier
    title: Nonempty
    license_note: Nonempty
    source_page: HttpURL
    miti_version: Literal["4.2.1"]
    sessions: list[SessionManifest] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_sessions(self):
        ids = [session.session_id for session in self.sessions]
        if len(ids) != len(set(ids)):
            raise ValueError("session_id must be unique within a dataset")
        return self


def load_manifest(path: str | Path) -> DatasetManifest:
    """Read a YAML manifest and reject invalid fields before any dataset I/O."""
    return DatasetManifest.model_validate(yaml.safe_load(Path(path).read_text()))
