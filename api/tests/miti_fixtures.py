"""Engine fixtures for the real-adapter api tests, read from `onolys_miti`'s packaged data (never
from old engines) and the two seams that stand in for the LLM: the coding stage and tips."""

import json
from typing import Any

from onolys_miti import miti
from onolys_miti.report import Tip
from onolys_miti.result import MitiResult
from onolys_miti.tips import TipsArtifact
from onolys_miti.transcript import Transcript

FIXTURES = miti.DATA_DIR / "fixtures" / "evaluation"


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


TRANSCRIPT = Transcript.model_validate(load("transcript.json"))
RESULT = MitiResult.model_validate(load("miti_result.json"))
TIPS = TipsArtifact(
    valid=[Tip.model_validate(t) for t in load("report_no_rating.json")["tips"]], proposals=[]
)
SUBJECT = load("speaker_map.json")["subject"]


def patch_engine(monkeypatch, failures=(), tips_failure=None):
    """Replace the engine's coding stage and tips generator with the fixtures.

    `failures` are raised one per coding call first; returns a counter dict."""
    from onolys_miti import run, tips

    calls = {"code": 0, "tips": 0}
    pending = list(failures)

    async def fake_code(ctx, transcript, params, metrics):
        calls["code"] += 1
        if pending:
            raise pending.pop(0)
        return RESULT

    async def fake_tips(*a, **kw):
        calls["tips"] += 1
        if tips_failure is not None:
            raise tips_failure
        return TIPS, []

    monkeypatch.setattr(run, "_code", fake_code)
    monkeypatch.setattr(tips, "generate_tips", fake_tips)
    return calls
