"""Dynamic response schemas and provider pricing, entirely offline."""

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from onolys_engine.llm import (
    FixtureClient,
    LiteLLMClient,
    LLMBadOutput,
    LLMConfig,
    LLMRequest,
    MetricsCollector,
    RecordingClient,
    StubClient,
)
from onolys_engine.llm.routes import Route

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Output",
    "$defs": {"Count": {"type": "integer", "minimum": 0, "default": 0}},
    "type": "object",
    "properties": {"count": {"$ref": "#/$defs/Count"}},
    "required": ["count"],
    "additionalProperties": False,
}
PROVIDER_SCHEMA = {
    "type": "object",
    "properties": {"count": {"type": "integer"}},
    "required": ["count"],
    "additionalProperties": False,
}


def request(**kwargs):
    return LLMRequest(tier="test", system="sys", user="input", call_tag="test", **kwargs)


class Out(BaseModel):
    count: int


def response(content='{"count": 2}', finish_reason="stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4),
    )


def test_request_requires_exactly_one_schema_source():
    with pytest.raises(ValueError, match="exactly one"):
        request(response_model=Out, response_schema=SCHEMA)
    with pytest.raises(ValueError, match="exactly one"):
        request()
    assert request(response_schema=SCHEMA).response_model is None


def test_provider_schema_inlines_refs_without_mutating_or_stripping_property_names():
    from onolys_engine.llm import to_provider_schema

    schema = deepcopy(SCHEMA)
    schema["properties"]["minimum"] = {"type": "string", "minLength": 1, "maxLength": 4}
    original = deepcopy(schema)
    expected = deepcopy(PROVIDER_SCHEMA)
    expected["properties"]["minimum"] = {"type": "string"}
    assert to_provider_schema(schema) == expected
    assert schema == original
    assert to_provider_schema(
        {
            "type": "object",
            "additionalProperties": {"$ref": "#/$defs/Count"},
            "$defs": SCHEMA["$defs"],
        }
    ) == {
        "type": "object",
        "additionalProperties": {"type": "integer"},
    }


def test_provider_schema_rejects_recursive_and_nonlocal_refs():
    from onolys_engine.llm import to_provider_schema

    for schema in (
        {"$ref": "https://example.com/schema"},
        {"$defs": {"Self": {"$ref": "#/$defs/Self"}}, "$ref": "#/$defs/Self"},
    ):
        with pytest.raises(ValueError, match="reference"):
            to_provider_schema(schema)


@pytest.mark.parametrize("mode", ["json_schema", "json_object"])
async def test_dynamic_response_mode_and_plain_dict(mode, monkeypatch):
    import litellm

    monkeypatch.setattr(litellm, "completion_cost", lambda **kwargs: 0.012)
    sent = []

    async def fake(**kwargs):
        sent.append(kwargs)
        return response()

    config = LLMConfig(
        llm_mode="live",
        routes={"test": Route(litellm_id="test/model", structured_output_mode=mode)},
    )
    metrics = MetricsCollector()
    result = await LiteLLMClient(config, acompletion=fake).complete_json(
        request(response_schema=SCHEMA), metrics
    )
    assert type(result.parsed) is dict and result.parsed == {"count": 2}
    fmt = sent[0]["response_format"]
    if mode == "json_object":
        assert fmt == {"type": "json_object"}
    else:
        assert fmt["json_schema"]["schema"] == PROVIDER_SCHEMA
    assert result.usage.cost_usd == 0.012
    assert metrics.records[0]["cost_usd"] == 0.012


@pytest.mark.parametrize("price", [0.0, None])
async def test_pricing_zero_or_unknown_does_not_fail_completion(price, monkeypatch):
    import litellm

    def cost(**kwargs):
        if price is None:
            raise ValueError("unpriced model")
        return price

    monkeypatch.setattr(litellm, "completion_cost", cost)

    async def fake(**kwargs):
        return response()

    metrics = MetricsCollector()
    config = LLMConfig(llm_mode="live", routes={"test": Route(litellm_id="test/model")})
    result = await LiteLLMClient(config, acompletion=fake).complete_json(
        request(response_model=Out), metrics
    )
    assert result.usage.cost_usd == price
    assert metrics.records[0]["cost_usd"] == price


async def test_dynamic_fixture_keys_recording_replay_and_stub(tmp_path):
    req = request(response_schema=SCHEMA)
    reordered = dict(reversed(list(SCHEMA.items())))
    key = FixtureClient.key_for(req)
    assert key == FixtureClient.key_for(request(response_schema=reordered))
    assert key != FixtureClient.key_for(request(response_schema={**SCHEMA, "required": []}))
    stub = StubClient()
    stub.register("test", {"count": 3})
    recorded = await RecordingClient(stub, tmp_path).complete_json(req)
    assert type(recorded.parsed) is dict
    replayed = await FixtureClient(tmp_path).complete_json(req)
    assert replayed.parsed == {"count": 3}
    assert json.loads((tmp_path / f"{key}.json").read_text()) == {"count": 3}


def test_model_fixture_key_is_unchanged():
    req = request(response_model=Out)
    old_payload = dict(
        tier="test", call_tag="test", system="sys", user="input", cache_prefix=None, schema="Out"
    )
    canonical = json.dumps(old_payload, sort_keys=True, ensure_ascii=False)
    assert (
        FixtureClient.key_for(req) == hashlib.sha256(f"test|test|{canonical}".encode()).hexdigest()
    )


async def test_dynamic_truncation_remains_nonretryable(monkeypatch):
    import litellm

    monkeypatch.setattr(litellm, "completion_cost", lambda **kwargs: None)
    calls = []

    async def fake(**kwargs):
        calls.append(kwargs)
        return response('{"count":', "length")

    config = LLMConfig(
        llm_mode="live", routes={"test": Route(litellm_id="test/model", backoff_s=0)}
    )
    with pytest.raises(LLMBadOutput, match="token limit"):
        await LiteLLMClient(config, acompletion=fake).complete_json(request(response_schema=SCHEMA))
    assert len(calls) == 1
