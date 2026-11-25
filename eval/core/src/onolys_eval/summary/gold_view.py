"""Gold projection (SP06 R3): allowed fields only, plus the per-dataset label coverage table.

Pure. Never carries `source` (URLs, hashes) or `parse` warnings. Missing or null counts/globals
mean "not labeled" and are omitted from the projection. Coverage is derived from the dataset
converters' own label constants where they exist, so it cannot drift from what gold holds.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .. import annomi, annosum, automisc, midas, mitags, welivita
from ..gold import COUNT_IDS, GLOBAL_IDS, Gold


@dataclass(frozen=True)
class LabelCoverage:
    counts: tuple[str, ...]
    globals: tuple[str, ...]
    line_labels: bool


_MITI = LabelCoverage(tuple(COUNT_IDS), tuple(GLOBAL_IDS), True)
# Per dataset: what human gold labels (SP06 R3). No dataset here has a second human coder.
LABEL_COVERAGE: dict[str, LabelCoverage] = {
    "casaa-miti421-video2013": _MITI,
    "casaa-miti-practice": _MITI,
    "mi-tags-sample": LabelCoverage(tuple(mitags._ALWAYS_LABELED), tuple(GLOBAL_IDS), True),
    "automisc-human": LabelCoverage(tuple(automisc.LABELED), (), True),
    "welivita-mi": LabelCoverage(tuple(welivita.LABELED), (), True),
    "annomi": LabelCoverage(tuple(annomi.LABELED), (), True),
    "annosum-mi": LabelCoverage(tuple(annosum.LABELED), ("empathy",), True),
    "midas-es": LabelCoverage(tuple(midas.LABELED), (), True),
    "hlqc": LabelCoverage((), (), False),
    "phac-en": LabelCoverage((), (), False),
    "phac-fr": LabelCoverage((), (), False),
}


def label_coverage(dataset_id: str) -> LabelCoverage | None:
    """Coverage for a dataset, or None when the dataset is not in the table (never guessed)."""
    return LABEL_COVERAGE.get(dataset_id)


@dataclass(frozen=True)
class LineLabel:
    turn_id: str
    codes: tuple[str, ...]
    note: str | None


@dataclass(frozen=True)
class GoldProjection:
    coded_span: Mapping[str, int] | None
    counts: Mapping[str, int]  # labeled only
    globals: Mapping[str, int]  # labeled only
    quality_label: str | None
    utterance_codes: tuple[LineLabel, ...] | None  # None = no line labels

    def to_dict(self) -> dict[str, Any]:
        return {
            "coded_span": None if self.coded_span is None else dict(self.coded_span),
            "counts": dict(self.counts),
            "globals": dict(self.globals),
            "quality_label": self.quality_label,
            "utterance_codes": None if self.utterance_codes is None else [
                {"turn_id": u.turn_id, "codes": list(u.codes), "note": u.note}
                for u in self.utterance_codes],
        }


def project_gold(doc: Mapping[str, Any]) -> GoldProjection:
    """Project a stored gold.v1 JSON document. Raises ValidationError if it is not gold.v1."""
    gold = Gold.model_validate(doc)
    span = gold.coded_span.model_dump() if gold.coded_span is not None else None
    return GoldProjection(
        coded_span=span,
        counts={k: v for k, v in gold.counts.items() if v is not None},
        globals={k: v for k, v in (gold.globals or {}).items() if v is not None},
        quality_label=gold.quality_label,
        utterance_codes=None if gold.utterance_codes is None else tuple(
            LineLabel(u.turn_id, tuple(u.codes), u.note) for u in gold.utterance_codes))
