"""Pack definitions loaded once; evaluating scores performs no I/O."""
from collections.abc import Mapping
from importlib.resources import files

import yaml
from onolys_miti.formula import evaluate

# Keep the pack as the only source of arithmetic rules. Import-time resource loading
# is separate from the pure scoring functions used by gold conversion and metrics.
_SUMMARIES = yaml.safe_load(
    files("onolys_miti").joinpath("data/pack.yaml").read_text()
)["summaries"]
SUMMARY_FORMULAS = tuple((item["id"], item["expr"]) for item in _SUMMARIES)
SUMMARY_REFERENCES = {item["id"]: item["reference"] for item in _SUMMARIES if item.get("reference")}



def compute_summaries(counts: Mapping[str, int | float], globals: Mapping[str, int]
                      ) -> dict[str, float | None]:
    """Evaluate the shared pack formulas, preserving undefined ratios as null."""
    values = {**counts, **globals}
    return {key: evaluate(expr, values) for key, expr in SUMMARY_FORMULAS}
