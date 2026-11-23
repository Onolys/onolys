"""Shared validation retries are bounded, accounted for, and safe to disclose."""

import pytest

from onolys_engine_core.context import RunContext
from onolys_engine_core.engine import Engine, EngineResult, RunInfo, RunUsage
from onolys_engine_core.llm.errors import LLMBadOutput
from onolys_engine_core.transcript_v1 import TranscriptV1
from onolys_engine_core.validated_run import OutputInvalid, run_validated

SCHEMA = {
    "type": "object", "required": ["answer"], "additionalProperties": False,
    "properties": {"answer": {"type": "integer"}},
}
INSTRUCTION = (
    "Your last answer did not match the schema. Return the complete JSON object; "
    "every required field present, no extra fields, exact enum values"
)


class StubEngine(Engine):
    name = "stub"
    version = "1"
    accepts_feedback = True

    def __init__(self, replies, schema=SCHEMA):
        self.replies = iter(replies)
        self.seen = []
        self.schema = schema

    def output_schema(self):
        return self.schema

    async def run(self, ctx, transcript, params, progress_cb=None):
        self.seen.append((ctx.feedback, transcript, params, progress_cb))
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return reply


def result(output, cost=0.01, **usage):
    return EngineResult(output=output, artifacts={"kept": True}, run_info=RunInfo(
        usage=RunUsage(input_tokens=11, output_tokens=7, calls=1, cost_usd=cost,
                       cache_read_tokens=3, cache_write_tokens=2, **usage),
        engine="stub",
    ))


def context():
    return RunContext(llm=object(), metrics=object(), request_id="test")


async def test_bad_then_good_retries_with_feedback_and_sums_usage():
    bad, good = result({"answer": "PRIVATE_VALUE"}), result({"answer": 2}, cost=0.02)
    engine, ctx, transcript, params = StubEngine([bad, good]), context(), TranscriptV1(turns=[]), {}
    def progress(*_):
        return None

    got = await run_validated(engine, ctx, transcript, params, progress)
    assert got.output == good.output and got.artifacts == good.artifacts
    assert got.run_info.engine == "stub"
    assert got.run_info.validation == {"attempts": 2}
    assert got.run_info.usage.model_dump() == {
        "input_tokens": 22, "output_tokens": 14, "calls": 2, "cost_usd": 0.03,
        "cache_read_tokens": 6, "cache_write_tokens": 4,
    }
    assert engine.seen[0] == (None, transcript, params, progress)
    assert INSTRUCTION in engine.seen[1][0] and "$.answer" in engine.seen[1][0]
    assert "PRIVATE_VALUE" not in engine.seen[1][0]
    assert ctx.feedback is None
    assert bad.run_info.usage.input_tokens == good.run_info.usage.input_tokens == 11
    assert "validation" not in good.run_info.model_dump()


@pytest.mark.parametrize("prices", [(None, 0.02), (0.01, None), (None, None)])
async def test_unknown_attempt_price_stays_unknown(prices):
    engine = StubEngine([result({}, prices[0]), result({"answer": 1}, prices[1])])
    got = await run_validated(engine, context(), TranscriptV1(turns=[]), {})
    assert got.run_info.usage.cost_usd is None
    assert got.run_info.usage.calls == 2


async def test_good_first_returns_without_retry_and_records_attempt_count():
    good = result({"answer": 1})
    engine = StubEngine([good])
    got = await run_validated(engine, context(), TranscriptV1(turns=[]), {})
    assert len(engine.seen) == 1
    assert got.output == good.output and got.run_info.usage == good.run_info.usage
    assert got.run_info.validation == {"attempts": 1}


@pytest.mark.parametrize("accepts_feedback,attempts", [(True, 2), (False, 1)])
async def test_invalid_output_is_bounded_safe_and_carries_all_attempt_usage(accepts_feedback, attempts):
    schema = {"additionalProperties": {"type": "integer"}}
    private = {f"PATIENT_SECRET_{i}": "PRIVATE_VALUE" for i in range(30)}
    engine, ctx = StubEngine([result(private), result(private)], schema), context()
    engine.accepts_feedback = accepts_feedback
    with pytest.raises(OutputInvalid) as caught:
        await run_validated(engine, ctx, TranscriptV1(turns=[]), {})
    error = caught.value
    assert error.code == "output_invalid" and error.retryable is False
    assert error.attempts == attempts and len(engine.seen) == attempts
    assert len(error.first_issues) == 10
    assert error.validation["attempts"] == attempts
    assert len(error.validation["first_issues"]) == 10
    assert error.usage.calls == attempts and error.usage.input_tokens == 11 * attempts
    assert error.usage.cost_usd == 0.01 * attempts
    public = str(error) + repr(error) + repr(vars(error)) + repr(engine.seen)
    assert "PATIENT_SECRET" not in public and "PRIVATE_VALUE" not in public
    assert ctx.feedback is None


@pytest.mark.parametrize("failure", [RuntimeError("engine failed"), LLMBadOutput("length")])
@pytest.mark.parametrize("after_invalid", [False, True])
async def test_engine_exceptions_propagate_without_retry_and_restore_feedback(failure, after_invalid):
    replies = [result({}), failure] if after_invalid else [failure]
    engine, ctx = StubEngine(replies), context()
    ctx.feedback = "caller feedback"
    with pytest.raises(type(failure)) as caught:
        await run_validated(engine, ctx, TranscriptV1(turns=[]), {})
    assert caught.value is failure
    assert len(engine.seen) == 1 + after_invalid
    assert ctx.feedback == "caller feedback"


async def test_reusing_context_does_not_reuse_validation_feedback():
    engine, ctx = StubEngine([result({}), result({"answer": 1}), result({"answer": 2})]), context()
    for _ in range(2):
        await run_validated(engine, ctx, TranscriptV1(turns=[]), {})
    assert engine.seen[0][0] is engine.seen[2][0] is None
    assert INSTRUCTION in engine.seen[1][0]


async def test_missing_attempt_usage_keeps_known_tokens_and_unknown_total_price():
    missing = EngineResult(output={}, run_info=RunInfo())
    engine = StubEngine([missing, result({"answer": 1})])
    got = await run_validated(engine, context(), TranscriptV1(turns=[]), {})
    assert got.run_info.usage.calls == 1
    assert got.run_info.usage.cost_usd is None
