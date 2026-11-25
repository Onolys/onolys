"""Offline fakes for the compare calculations: a scenario-backed EvalRunSource and a price book.

Stdlib only, so eval/core and eval/backend tests can both import it. Scenario files are
`eval/fixtures/compare/<name>.json`, produced by `builder.py`.
"""
import json
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIOS = (
    "counts_golden", "annomi_partial", "lines", "twelve_sessions", "cancelled_partial",
    "provider_skipped", "no_labels_hlqc", "no_labels_phac", "no_completed", "running",
)


class SourceNotFound(LookupError):
    """Same name and base as onolys_eval.summary.source.SourceNotFound (stdlib-only copy)."""


def load_scenario(name: str, root: Path | None = None) -> dict:
    return json.loads(((root or HERE) / f"{name}.json").read_text())


@dataclass(frozen=True)
class FakeCost:
    cost_usd: float | None
    is_estimate: bool = True


class FakePriceBook:
    """Mirrors `onolys_eval_backend.costs.PriceBook.estimate`: reported `cost_usd` wins (even 0),
    an unknown model gives `cost_usd=None`, never 0."""

    def __init__(self, models: dict[str, dict]):
        self.models = dict(models)

    def estimate(self, usage, model: str) -> FakeCost:
        usage = usage or {}
        if usage.get("cost_usd") is not None:
            return FakeCost(float(usage["cost_usd"]), False)
        entry = self.models.get(model) or {}
        if entry.get("input_usd_per_million") is None or entry.get("output_usd_per_million") is None:
            return FakeCost(None)
        cost = (usage.get("input_tokens", 0) * entry["input_usd_per_million"]
                + usage.get("output_tokens", 0) * entry["output_usd_per_million"]) / 1_000_000
        return FakeCost(cost)


class FakeEvalRunSource:
    """Satisfies `onolys_eval.summary.source.EvalRunSource` over one or more scenario dicts.

    `calls` records every read so tests can assert bounded reads and caching."""

    def __init__(self, *scenarios: dict):
        self._by_id = {s["eval_run"]["eval_run_id"]: s for s in scenarios}
        self.calls: list[tuple] = []

    @classmethod
    def from_names(cls, *names: str) -> "FakeEvalRunSource":
        return cls(*(load_scenario(n) for n in names))

    def _scenario(self, eval_run_id: str) -> dict:
        try:
            return self._by_id[eval_run_id]
        except KeyError:
            raise SourceNotFound(eval_run_id) from None

    def _find(self, key: str, getter):
        for scenario in self._by_id.values():
            found = getter(scenario)
            if found is not None:
                return found
        raise SourceNotFound(key)

    def eval_run(self, eval_run_id):
        self.calls.append(("eval_run", eval_run_id))
        return self._scenario(eval_run_id)["eval_run"]

    def cells(self, eval_run_id):
        self.calls.append(("cells", eval_run_id))
        return self._scenario(eval_run_id)["cells"]

    def run_doc(self, uid, sid, run_id):
        self.calls.append(("run_doc", uid, sid, run_id))
        doc = self._find(run_id, lambda s: s["run_docs"].get(run_id))
        if doc["uid"] != uid or doc["session_id"] != sid:
            raise SourceNotFound(run_id)
        return doc

    def report(self, uid, sid, run_id):
        self.calls.append(("report", uid, sid, run_id))
        self.run_doc(uid, sid, run_id)
        return self._find(run_id, lambda s: s["reports"].get(run_id))

    def transcript(self, uid, sid):
        self.calls.append(("transcript", uid, sid))
        if uid != "synthetic-uid":
            raise SourceNotFound(sid)
        return self._find(sid, lambda s: s["transcripts"].get(sid))

    def gold(self, sha256):
        self.calls.append(("gold", sha256))
        return self._find(sha256, lambda s: s["gold"].get(sha256))
