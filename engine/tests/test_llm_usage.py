"""Billable provider responses survive parsing failures and transport retries."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from onolys_engine.llm import (
    LiteLLMClient,
    LLMBadOutput,
    LLMConfig,
    LLMRequest,
    LLMUnavailable,
    MetricsCollector,
)
from onolys_engine.llm.routes import Route


class Out(BaseModel):
    count: int


def response(content, *, price=0.01, finish_reason="stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)
        ],
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=4,
            cache_read_input_tokens=3,
            cache_creation_input_tokens=2,
        ),
        price=price,
    )


def setup(monkeypatch, *outcomes, dynamic=False, retry=True):
    import litellm

    def cost(completion_response):
        if completion_response.price is None:
            raise ValueError("unpriced model")
        return completion_response.price

    monkeypatch.setattr(litellm, "completion_cost", cost)
    calls = []
    pending = iter(outcomes)

    async def fake(**kwargs):
        calls.append(kwargs)
        outcome = next(pending)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    config = LLMConfig(
        llm_mode="live",
        routes={"test": Route(litellm_id="test/model", max_retries=1, backoff_s=0)},
    )
    schema = {"response_schema": {"type": "object"}} if dynamic else {"response_model": Out}
    req = LLMRequest(tier="test", system="sys", user="input", retry=retry, **schema)
    return LiteLLMClient(config, acompletion=fake), req, MetricsCollector(), calls


def assert_usage(usage, *, responses, price):
    assert usage.input_tokens == 10 * responses
    assert usage.output_tokens == 4 * responses
    assert usage.cache_read_tokens == 3 * responses
    assert usage.cache_write_tokens == 2 * responses
    assert usage.cost_usd == price


def assert_record(metrics, *, responses, price, attempts, ok):
    assert len(metrics.records) == 1
    record = metrics.records[0]
    assert record["input_tokens"] == 10 * responses
    assert record["output_tokens"] == 4 * responses
    assert record["cache_read_tokens"] == 3 * responses
    assert record["cache_write_tokens"] == 2 * responses
    assert record["cost_usd"] == price
    assert record["attempts"] == attempts
    assert record["ok"] is ok


@pytest.mark.parametrize(
    ("bad", "dynamic"),
    [
        ("PRIVATE invalid JSON", False),
        ('{"count": []}', False),
        ("PRIVATE invalid JSON", True),
        ("[]", True),
    ],
)
async def test_invalid_then_valid_sums_every_received_response(monkeypatch, bad, dynamic):
    client, req, metrics, calls = setup(
        monkeypatch, response(bad), response('{"count": 2}'), dynamic=dynamic
    )
    result = await client.complete_json(req, metrics)
    assert result.attempts == len(calls) == 2
    assert_usage(result.usage, responses=2, price=0.02)
    assert_record(metrics, responses=2, price=0.02, attempts=2, ok=True)
    assert "PRIVATE" not in json.dumps(metrics.records)


@pytest.mark.parametrize("prices", [(None, 0.01), (0.01, None)])
async def test_any_unpriced_received_response_makes_total_unknown(monkeypatch, prices):
    client, req, metrics, _ = setup(
        monkeypatch,
        response("invalid", price=prices[0]),
        response('{"count": 2}', price=prices[1]),
    )
    result = await client.complete_json(req, metrics)
    assert_usage(result.usage, responses=2, price=None)
    assert_record(metrics, responses=2, price=None, attempts=2, ok=True)


@pytest.mark.parametrize("last_price", [0.01, None])
async def test_final_bad_output_preserves_all_billable_usage(monkeypatch, last_price):
    client, req, metrics, calls = setup(
        monkeypatch, response("PRIVATE malformed"), response('{"count": []}', price=last_price)
    )
    with pytest.raises(LLMBadOutput) as exc:
        await client.complete_json(req, metrics)
    assert len(calls) == 2
    assert_record(
        metrics, responses=2, price=0.02 if last_price is not None else None, attempts=2, ok=False
    )
    assert metrics.records[0]["error_kind"] == "bad_output"
    assert "PRIVATE" not in str(exc.value) + json.dumps(metrics.records)


@pytest.mark.parametrize("retry_first", [False, True])
async def test_truncation_preserves_usage_without_retrying_it(monkeypatch, retry_first):
    outcomes = [response("invalid")] if retry_first else []
    outcomes.append(response('PRIVATE {"count":', finish_reason="length"))
    client, req, metrics, calls = setup(monkeypatch, *outcomes)
    with pytest.raises(LLMBadOutput, match="token limit") as exc:
        await client.complete_json(req, metrics)
    attempts = 2 if retry_first else 1
    assert len(calls) == attempts
    assert exc.value.no_retry is True
    assert_record(metrics, responses=attempts, price=0.01 * attempts, attempts=attempts, ok=False)


async def test_retry_disabled_retains_failed_response_usage(monkeypatch):
    client, req, metrics, calls = setup(monkeypatch, response("invalid"), retry=False)
    with pytest.raises(LLMBadOutput):
        await client.complete_json(req, metrics)
    assert len(calls) == 1
    assert_record(metrics, responses=1, price=0.01, attempts=1, ok=False)


async def test_provider_exception_before_response_does_not_poison_known_price(monkeypatch):
    client, req, metrics, calls = setup(
        monkeypatch, ConnectionError("offline"), response('{"count": 2}')
    )
    result = await client.complete_json(req, metrics)
    assert result.attempts == len(calls) == 2
    assert_usage(result.usage, responses=1, price=0.01)
    assert_record(metrics, responses=1, price=0.01, attempts=2, ok=True)


@pytest.mark.parametrize("received", [False, True])
async def test_final_provider_exception_preserves_only_received_usage(monkeypatch, received):
    first = response("invalid") if received else ConnectionError("offline")
    client, req, metrics, calls = setup(monkeypatch, first, ConnectionError("offline"))
    with pytest.raises(LLMUnavailable):
        await client.complete_json(req, metrics)
    assert len(calls) == 2
    assert_record(
        metrics, responses=int(received), price=0.01 if received else None, attempts=2, ok=False
    )
    assert metrics.records[0]["error_kind"] == "unavailable"


@pytest.mark.parametrize("price", [0.01, None])
async def test_cancellation_during_retry_retains_only_received_usage(monkeypatch, price):
    client, req, metrics, calls = setup(
        monkeypatch, response("PRIVATE malformed response", price=price)
    )
    first_call = client._acompletion
    retry_started = asyncio.Event()

    async def provider(**kwargs):
        if not calls:
            return await first_call(**kwargs)
        calls.append(kwargs)
        retry_started.set()
        await asyncio.Future()  # No response or usage has arrived for this attempt.

    client._acompletion = provider
    task = asyncio.create_task(client.complete_json(req, metrics))
    await asyncio.wait_for(retry_started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()
    assert len(calls) == 2
    assert_record(metrics, responses=1, price=price, attempts=2, ok=False)
    assert metrics.records[0]["error_kind"] == "cancelled"
    assert "PRIVATE" not in json.dumps(metrics.records)
