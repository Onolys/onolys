"""Shared inputs for the report tests: the synthetic transcript, speaker map and engine result in
`data/fixtures/evaluation/`, and the no-rating report built from them (the golden)."""

import json
from pathlib import Path
from typing import Any

from onolys_engine_core.transcript import Transcript

from onolys_miti import miti
from onolys_miti.hashes import evaluation_prompt_hashes
from onolys_miti.report import Tip
from onolys_miti.result import MitiResult
from onolys_miti.tips import TipsArtifact

FIXTURES = miti.DATA_DIR / "fixtures" / "evaluation"
SCHEMA_PATH = Path(miti.DATA_DIR) / "report.schema.json"
REPORT_NAMES = ("report_full", "report_partial", "report_no_rating")
CREATED_AT = "2026-11-20T00:00:00Z"


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def inputs() -> dict[str, Any]:
    """Keyword arguments for `build_report_no_rating` that rebuild `report_no_rating.json`."""
    golden = load("report_no_rating.json")
    result = MitiResult.model_validate(load("miti_result.json"))
    route = next(iter(result.run_info.routes.values())).litellm_id
    return {
        "transcript": Transcript.model_validate(load("transcript.json")),
        "params": {"n_runs": 1, "preset": "fixture", "code_version": "fixture",
                   "stt_run": golden["header"]["stt"]},
        "result": result,
        "tips": TipsArtifact(valid=[Tip.model_validate(t) for t in golden["tips"]],
                             proposals=[]),
        "models": {"tips": route},
        "prompt_hashes": evaluation_prompt_hashes(),
        "request_id": "req-fixture-no_rating",
        "created_at": CREATED_AT,
    }
