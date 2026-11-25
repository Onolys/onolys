"""Read-side interface the compare calculations depend on (SP06 R1).

The protocol lives in core because the pure summary code is typed against it and must be
testable with no cloud: the backend implements it over SP05's `eval_view`/Firestore/GCS, tests
implement it over synthetic fixtures (`eval/fixtures/compare/fakes.py`). Methods return the plain
documents (dicts) of the prod pipeline, never storage pointers. An unknown id raises
`SourceNotFound`.
"""
from typing import Any, Protocol, runtime_checkable


class SourceNotFound(LookupError):
    """The eval run, session, run, report, transcript or gold document does not exist."""


@runtime_checkable
class EvalRunSource(Protocol):
    def eval_run(self, eval_run_id: str) -> dict[str, Any]:
        """Grouping doc: {eval_run_id, name, dataset_id, status, cancelled_at,
        sessions[{session_id, uid, dataset_session_id, gold_sha256, transcript_sha256}],
        combos[{combo_key, engine, provider, litellm_id, effort}], repeats,
        provider_skips[{provider, after_failures, skipped_at}],
        runs[{session_id, run_id, combo_key, repeat, attempt, status, reason}]}."""

    def cells(self, eval_run_id: str) -> list[dict[str, Any]]:
        """`eval_view.list_cells` shape, all attempts, ordered session -> plan -> attempt:
        {sid, dataset_session_id, engine, combo_key, repeat, attempt, run_id, status, started,
        ended, error, run_info{usage, cost_usd_est}, gold_ref}."""

    def run_doc(self, uid: str, sid: str, run_id: str) -> dict[str, Any]:
        """RunDoc (store form, ISO timestamps) incl. `eval` provenance."""

    def report(self, uid: str, sid: str, run_id: str) -> dict[str, Any]:
        """ReportDoc with the pointer resolved (`report` always inline)."""

    def transcript(self, uid: str, sid: str) -> dict[str, Any]:
        """TranscriptDoc with the transcript inline."""

    def gold(self, sha256: str) -> dict[str, Any]:
        """Gold JSON stored at eval bucket `gold/<sha256>`."""


@runtime_checkable
class PriceLookup(Protocol):
    def estimate(self, usage: dict[str, Any], model: str) -> Any:
        """Object with `.cost_usd: float | None` (None = unknown price, never 0)."""
