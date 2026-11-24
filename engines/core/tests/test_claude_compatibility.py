"""Characterize the locked provider adapter without sending a real HTTP request."""

import json

import pytest

from onolys_engine_core.llm import LiteLLMClient, LLMConfig, LLMRequest, LLMUnavailable
from onolys_engine_core.llm.routes import Route

pytestmark = pytest.mark.unit


async def test_locked_claude_adapter_sends_adaptive_thinking_and_low_effort(monkeypatch):
    import litellm
    from litellm.llms.custom_httpx.http_handler import AsyncHTTPHandler

    sent = []

    async def fake_post(self, url, *args, **kwargs):
        sent.append(kwargs.get("data") or kwargs.get("json"))
        raise RuntimeError("synthetic HTTP boundary")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-key")
    monkeypatch.setattr(AsyncHTTPHandler, "post", fake_post)
    route = Route(
        litellm_id="anthropic/claude-sonnet-5-5", api_key_env="ANTHROPIC_API_KEY",
        supports_temperature=False, extra_params={"reasoning_effort": "low"}, max_retries=0,
    )
    client = LiteLLMClient(LLMConfig(llm_mode="live", routes={"mid": route}), acompletion=litellm.acompletion)
    request = LLMRequest(tier="mid", system="Return JSON.", user='{"ok":true}', response_schema={})
    with pytest.raises(LLMUnavailable):
        await client.complete_json(request)
    assert len(sent) == 1
    body = json.loads(sent[0]) if isinstance(sent[0], str | bytes) else sent[0]
    assert body["thinking"]["type"] == "adaptive"
    assert body["output_config"]["effort"] == "low"
    assert "temperature" not in body
