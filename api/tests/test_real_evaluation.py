"""SP09 R2/D5/AC1: the real `Evaluation` adapter is one call into `run_miti`.
Unit tests stub `run_miti` and the LLM client; no live calls."""

import re
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from onolys_engine_core.context import RunContext
from onolys_engine_core.errors import InputError
from onolys_miti.transcript import Transcript

from onolys_api.adapters import real
from onolys_api.adapters.base import EvaluationOutput
from onolys_api.adapters.real import RealEvaluation

pytestmark = pytest.mark.unit

PARAMS = {
    "change_goal": "cut back",
    "seed": "sess-1",
    "language": "en",
    "n_runs": 3,
    "preset": "default",
    "code_version": "abc123",
    "stub_title": "ignored",
}
SPEAKERS = {"subject": "A"}


class Engine:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def __call__(self, *args, **kw):
        self.calls.append((args, kw))
        return SimpleNamespace(
            report=SimpleNamespace(model_dump_json=lambda: '{"schema_version": "1"}'),
            artifacts=SimpleNamespace(model_dump_json=lambda: '{"code": {"x": 1}}'),
        )


def make(engine: Engine, llm=None) -> RealEvaluation:
    return RealEvaluation(run_miti=engine, llm_factory=lambda routes: llm or "llm")


def ctx() -> RunContext:
    return RunContext(llm=None, metrics=None, request_id="req-9", deadline=time.monotonic() + 900)


def transcript() -> Transcript:
    return Transcript(language="en", turns=[], duration_ms=0)


async def test_one_call_with_exact_params():
    engine = Engine()
    cb = lambda stage, status: None  # noqa: E731
    out = await make(engine).run(ctx(), transcript(), SPEAKERS, PARAMS, cb)
    assert len(engine.calls) == 1
    (args, kw) = engine.calls[0]
    c, tr, speakers, params, got_cb = args
    assert speakers == SPEAKERS and got_cb is cb and kw == {}
    assert params == {**{k: v for k, v in PARAMS.items() if k != "stub_title"}, "coded_span": None}
    assert c.request_id == "req-9" and c.llm == "llm" and c.metrics is not None
    assert isinstance(out, EvaluationOutput)
    assert out.report == {"schema_version": "1"} and out.artifacts == {"code": {"x": 1}}


async def test_no_progress_cb_passes_none():
    engine = Engine()
    await make(engine).run(ctx(), transcript(), SPEAKERS, PARAMS)
    assert engine.calls[0][0][4] is None


async def test_deadline_is_capped_at_eight_minutes():
    engine = Engine()
    before = time.monotonic()
    await make(engine).run(ctx(), transcript(), SPEAKERS, PARAMS)
    deadline = engine.calls[0][0][0].deadline
    assert before + 470 < deadline <= time.monotonic() + 480


async def test_shorter_ctx_deadline_wins():
    engine = Engine()
    c = RunContext(llm=None, metrics=None, request_id="r", deadline=time.monotonic() + 60)
    await make(engine).run(c, transcript(), SPEAKERS, PARAMS)
    assert engine.calls[0][0][0].deadline <= time.monotonic() + 60


async def test_unknown_preset_is_input_error_and_no_engine_call():
    engine = Engine()
    ev = RealEvaluation(run_miti=engine)  # real resolve
    with pytest.raises(InputError):
        await ev.run(ctx(), transcript(), SPEAKERS, {**PARAMS, "preset": "no-such-preset"})
    assert engine.calls == []


async def test_default_llm_factory_builds_litellm_client_from_routes():
    from onolys_miti.llm import LiteLLMClient

    engine = Engine()
    ev = RealEvaluation(run_miti=engine)
    await ev.run(ctx(), transcript(), SPEAKERS, PARAMS)
    assert isinstance(engine.calls[0][0][0].llm, LiteLLMClient)


def test_adapter_names_no_model_or_provider():
    src = Path(real.__file__).read_text().lower()
    code = "\n".join(line for line in src.splitlines() if not line.lstrip().startswith("#"))
    # strip the STT section's registry keys (provider keys are data, SP09 T2); check Evaluation part
    part = code[code.index("class realevaluation") :]
    assert not re.search(
        r"claude|anthropic|gemini|gpt|openai|vertex|sonnet|haiku|opus|litellm_id", part
    )


@pytest.mark.parametrize(
    "coded_span",
    [{"start_ms": 0, "end_ms": 600_000}, {"start_turn": 0, "end_turn": 2}],
    ids=["milliseconds", "turns"],
)
async def test_a_caller_coded_span_reaches_the_engine_unchanged(coded_span):
    engine = Engine()
    params = {**PARAMS, "coded_span": coded_span}
    await make(engine).run(ctx(), transcript(), SPEAKERS, params)
    assert engine.calls[0][0][3]["coded_span"] == coded_span


async def test_session_stt_provenance_passes_outside_transcript():
    from onolys_miti.stt import SttRun

    engine = Engine()
    run = SttRun(provider="fixture", model="fixture", language_requested="en",
                 adapter_version="fixture-1").model_dump()
    await make(engine).run(ctx(), transcript(), SPEAKERS, {**PARAMS, "stt_run": run})
    args, _ = engine.calls[0]
    assert args[3]["stt_run"] == run
    assert "stt_run" not in args[1].model_dump()
