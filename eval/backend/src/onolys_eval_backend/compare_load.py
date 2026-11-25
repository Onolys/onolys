"""Read one eval group into bounded, hash-checked SP06 projections. No writes or providers."""
import json
import re
from dataclasses import dataclass
from typing import Any

from onolys_api.repo.base import NotFoundError
from onolys_api.storage.base import BlobNotFoundError
from onolys_eval.summary.gold_view import GoldProjection, project_gold
from onolys_eval.summary.operations import final_attempts
from onolys_eval.summary.run_report import ParsedRun, parse_report
from onolys_eval.summary.source import EvalRunSource, SourceNotFound
from onolys_eval.summary.transcript_view import TranscriptChanged, TurnView, project_transcript

from onolys_eval_backend import eval_view
from onolys_eval_backend.compare_cache import CompareCache
from onolys_eval_backend.costs import CostEstimate, PriceBook, estimate_route_cost
from onolys_eval_backend.eval_scheduler import plan_cells
from onolys_eval_backend.eval_sessions import canonical_sha256


class GoldHashMismatch(ValueError):
    """Stored gold does not match the group's pinned content hash."""


class ReadLimitExceeded(ValueError):
    """The group exceeds the configured bounded compare input size."""


def _plain(doc):
    return doc.model_dump(mode="json") if hasattr(doc, "model_dump") else doc


class ServiceEvalRunSource:
    """SP05 adapter; a fresh instance per request keeps its group snapshot isolated."""
    def __init__(self, services, max_runs: int = 499, max_attempts: int = 4990):
        self.services = services
        self.max_runs, self.max_attempts = max_runs, max_attempts
        self._groups: dict[str, dict] = {}
        self._cells: dict[str, list[dict]] = {}

    def eval_run(self, eval_run_id: str) -> dict[str, Any]:
        services = self.services
        doc = services.repository.get_run(eval_run_id)
        if not doc:
            raise SourceNotFound(eval_run_id)
        sessions_raw = doc.get("sessions") or {}
        planned = (len(sessions_raw) * len(doc.get("combos") or [])
                   * sum(e != "human" for e in doc.get("engines") or []) * doc["repeats"])
        attempts = sum(len(s.get("runs") or []) for s in sessions_raw.values())
        if planned > self.max_runs or attempts > self.max_attempts:
            raise ReadLimitExceeded(eval_run_id)
        self._groups[eval_run_id] = doc
        self._cells.pop(eval_run_id, None)
        cells = self.cells(eval_run_id)
        sessions = []
        for sid, entry in sorted((doc.get("sessions") or {}).items(),
                                 key=lambda kv: kv[1].get("order", 0)):
            ref = next((c.get("gold_ref") for c in cells if c["sid"] == sid), None)
            sessions.append({"session_id": sid, "uid": services.config.eval_owner_uid,
                             "dataset_session_id": entry.get("dataset_session_id"),
                             "gold_sha256": ref.get("sha256") if ref else None,
                             "transcript_sha256": entry.get("transcript_sha256")})
        combos = {}
        resolved = (doc.get("saved_config") or {}).get("resolved_combos") or {}
        for cell in plan_cells(doc):
            ck = f"{cell['engine']}|{cell['combo_key']}"
            route = resolved.get(cell["combo_key"]) or {}
            model = route.get("litellm_id", "")
            combos[ck] = {**cell["combo"], "combo_key": ck, "engine": cell["engine"],
                          "litellm_id": model, "provider": model.split("/")[0]}
        return {"eval_run_id": eval_run_id, "name": doc.get("name"),
                "dataset_id": (doc.get("input") or {}).get("dataset_id"),
                "status": doc["status"],
                "cancelled_at": doc.get("cancelled_at"), "sessions": sessions,
                "progress": {key: doc.get(key) or 0
                             for key in ("done_units", "total_units", "skipped_units")},
                "combos": list(combos.values()), "repeats": doc["repeats"],
                "provider_skips": eval_view.provider_skips(doc),
                "runs": [{**c, "session_id": c["sid"]} for c in cells]}

    def cells(self, eval_run_id: str) -> list[dict[str, Any]]:
        if eval_run_id not in self._groups:
            self.eval_run(eval_run_id)
        if eval_run_id not in self._cells:
            self._cells[eval_run_id] = [
                {**c, "combo_key": f"{c['engine']}|{c['combo_key']}"} if c.get("engine") else c
                for c in eval_view.list_cells(
                    self.services, eval_run_id, self._groups[eval_run_id])]
        return self._cells[eval_run_id]

    def _read(self, method, *args):
        try:
            return _plain(method(*args))
        except (NotFoundError, BlobNotFoundError, FileNotFoundError) as exc:
            raise SourceNotFound(args[-1]) from exc

    def run_doc(self, uid: str, sid: str, run_id: str) -> dict[str, Any]:
        return self._read(self.services.repo.get_run, uid, sid, run_id)

    def report(self, uid: str, sid: str, run_id: str) -> dict[str, Any]:
        return self._read(self.services.repo.get_report, uid, sid, run_id)

    def transcript(self, uid: str, sid: str) -> dict[str, Any]:
        return self._read(self.services.repo.get_transcript, uid, sid, "current")

    def gold(self, sha256: str) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise GoldHashMismatch(sha256)
        return json.loads(self._read(self.services.blobs.get_bytes, f"gold/{sha256}.json"))


@dataclass(frozen=True)
class LoadedSession:
    gold: GoldProjection
    turns: tuple[TurnView, ...]
    transcript_changed: bool = False

    def require_turns(self) -> tuple[TurnView, ...]:
        if self.transcript_changed:
            raise TranscriptChanged("transcript_changed")
        return self.turns


@dataclass(frozen=True)
class LoadedRun:
    cell: dict[str, Any]
    doc: dict[str, Any]
    parsed: ParsedRun
    turns: tuple[TurnView, ...]
    cost: CostEstimate


@dataclass(frozen=True)
class CompareProjection:
    group: dict[str, Any]
    sessions: dict[str, LoadedSession]
    runs: tuple[LoadedRun, ...]  # final done attempts only, including unparseable
    attempts: tuple[dict[str, Any], ...]  # all cells for time, cost, failures and exclusions


class CompareLoader:
    def __init__(self, source: EvalRunSource, prices: PriceBook,
                 cache: CompareCache | None = None, max_runs: int = 499,
                 max_attempts: int = 4990):
        self.source, self.prices = source, prices
        self.cache = cache if cache is not None else CompareCache()
        self.max_runs, self.max_attempts = max_runs, max_attempts

    def load(self, eval_run_id: str) -> CompareProjection:
        group = self.source.eval_run(eval_run_id)
        cells = self.source.cells(eval_run_id)
        final = final_attempts(cells)
        if len(final) > self.max_runs or len(cells) > self.max_attempts \
                or len(group["sessions"]) > self.max_runs:
            raise ReadLimitExceeded(eval_run_id)
        cached = self.cache.get(eval_run_id, cells, group["status"])
        if cached is not None:
            return cached
        entries = {s["session_id"]: s for s in group["sessions"]}
        if any(c["sid"] not in entries for c in cells):
            raise SourceNotFound("cell outside eval run")
        sessions, transcripts, golds = {}, {}, {}
        for sid, entry in entries.items():
            sha = entry.get("gold_sha256")
            if sha and sha not in golds:
                gold = self.source.gold(sha)
                if canonical_sha256(gold) != sha:
                    raise GoldHashMismatch(sha)
                golds[sha] = project_gold(gold)
            human = golds[sha] if sha else GoldProjection(None, {}, {}, None, None)
            sessions[sid] = LoadedSession(human, ())
        runs = []
        for cell in final:
            if cell["status"] != "done" or not cell.get("run_id"):
                continue
            sid, rid = cell["sid"], cell["run_id"]
            uid = entries[sid]["uid"]
            doc = self.source.run_doc(uid, sid, rid)
            engine = (doc.get("eval") or {}).get("engine", "")
            try:
                report = self.source.report(uid, sid, rid)
            except SourceNotFound:
                report = {}
            parsed = parse_report(engine, report)
            if sid not in transcripts:
                transcripts[sid] = self.source.transcript(uid, sid)
            try:
                turns = project_transcript(doc, transcripts[sid])
            except TranscriptChanged:
                turns = ()
                sessions[sid] = LoadedSession(sessions[sid].gold, (), True)
            else:
                if not sessions[sid].transcript_changed:
                    sessions[sid] = LoadedSession(sessions[sid].gold, turns)
            runs.append(LoadedRun(dict(cell), doc, parsed, turns,
                                  estimate_route_cost(self.prices, doc)))
        projection = CompareProjection(group, sessions, tuple(runs), tuple(dict(c) for c in cells))
        self.cache.put(eval_run_id, cells, group["status"], projection)
        return projection

    def session_turns(self, projection: CompareProjection, sid: str) -> tuple[TurnView, ...]:
        """Reverify saved transcripts on line reads, including after a terminal cache hit."""
        entry = next((s for s in projection.group["sessions"] if s["session_id"] == sid), None)
        if entry is None:
            raise SourceNotFound(sid)
        mine = [r for r in projection.runs if r.cell["sid"] == sid]
        if not mine:
            return ()
        transcript = self.source.transcript(entry["uid"], sid)
        turns = ()
        for run in mine:
            turns = project_transcript(run.doc, transcript)
        return turns
