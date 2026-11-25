"""Rough LLM-only cost estimates. Unknown prices stay unknown; STT is excluded."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

import yaml


@dataclass(frozen=True)
class CostEstimate:
    cost_usd: float | None
    is_estimate: bool
    source: str | None = None
    rate_as_of: str | None = None


class PriceBook:
    def __init__(self, models: Mapping[str, dict]):
        self.models = dict(models)

    @classmethod
    def from_yaml(cls, path: str | Path | None = None) -> 'PriceBook':
        if path is None:
            resource = files('onolys_eval_backend').joinpath('prices.yaml')
            # Editable source checkouts keep the hand-maintained file at backend root.
            text = (resource.read_text() if resource.is_file()
                    else Path(__file__).resolve().parents[2].joinpath('prices.yaml').read_text())
        else:
            text = Path(path).read_text()
        data = yaml.safe_load(text) or {}
        return cls(data.get('models', {}))

    def estimate(self, usage, model: str) -> CostEstimate:
        """Prefer reported provider cost, including zero, over token estimates.

        input_tokens already includes cached input. Cache counters are intentionally
        not added again. A mixed-model total must not be priced as one model: callers
        should pass per-model usage, or leave mixed/unknown models unpriced.
        """
        if hasattr(usage, 'model_dump'):
            usage = usage.model_dump()
        usage = usage or {}
        reported = usage.get('cost_usd')
        if reported is not None:
            return CostEstimate(float(reported), False, 'usage.cost_usd')
        entry = self.models.get(model) or {}
        input_rate = entry.get('input_usd_per_million')
        output_rate = entry.get('output_usd_per_million')
        if input_rate is None or output_rate is None:
            return CostEstimate(None, True, entry.get('source'), entry.get('rate_as_of'))
        rates = (float(input_rate), float(output_rate))
        if any(not math.isfinite(rate) or rate < 0 for rate in rates):
            raise ValueError('Prices must be finite and non-negative')
        cost = (usage.get('input_tokens', 0) * rates[0]
                + usage.get('output_tokens', 0) * rates[1]) / 1_000_000
        return CostEstimate(cost, True, entry.get('source'), str(entry.get('rate_as_of', '')))


def estimate_route_cost(prices: PriceBook, run_doc: Mapping) -> CostEstimate:
    """Price saved usage with this RunDoc's pinned route; provider cost (even 0) wins."""
    usage = (run_doc.get('run_info') or {}).get('usage') or {}
    route = ((run_doc.get('eval') or {}).get('resolved_route') or {})
    return prices.estimate(usage, route.get('litellm_id', ''))
