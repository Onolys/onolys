"""Exercise the locked LiteLLM/OpenAI adapter at an offline HTTP boundary."""

import json
from functools import partial

import httpx
import pytest

from onolys_engine.llm import LiteLLMClient, LLMConfig, LLMRequest
from onolys_engine.llm.routes import Route

pytestmark = pytest.mark.unit

COMBOS = [
    (model, effort)
    for model in ("gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna")
    for effort in ("none", "low", "medium", "high", "xhigh", "max")
    if (model, effort) != ("gpt-6.1-sol", "none")
]


@pytest.mark.parametrize("model,effort", COMBOS)
@pytest.mark.parametrize("cap", [4096, 8192])
@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
async def test_openai_wire_effort_json_token_cap_and_billable_reasoning(monkeypatch, model, effort, cap, mode):
    import litellm

    bodies = []

    async def send(self, request, **kwargs):
        assert request.url.host == "offline.invalid"
        bodies.append(json.loads(request.content))
        return httpx.Response(200, request=request, json={
            "id": "synthetic", "object": "chat.completion", "created": 1, "model": model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": '{"ok":true}'}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 90, "total_tokens": 190,
                      "completion_tokens_details": {"reasoning_tokens": 80},
                      "prompt_tokens_details": {"cached_tokens": 20}},
        })

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    route = Route(
        litellm_id=f"openai/{model}", api_key_env="OPENAI_API_KEY", max_output_tokens=64000,
        supports_temperature=False, structured_output_mode=mode,
        extra_params={"reasoning_effort": effort}, max_retries=0,
    )
    call = partial(litellm.acompletion, api_key="synthetic-offline-key", api_base="https://offline.invalid/v1")
    client = LiteLLMClient(LLMConfig(llm_mode="live", routes={"mid": route}), acompletion=call)
    result = await client.complete_json(LLMRequest(
        tier="mid", system="Return JSON.", user="Synthetic test.", response_schema={}, max_tokens=cap,
    ))
    assert len(bodies) == 1
    body = bodies[0]
    assert body["model"] == model
    assert body["reasoning_effort"] == effort
    assert body["max_completion_tokens"] == cap
    assert "max_tokens" not in body and "temperature" not in body
    assert body["response_format"]["type"] == mode
    if mode == "json_schema":
        assert body["response_format"]["json_schema"]["strict"] is True
    assert result.parsed == {"ok": True}
    # Completion usage already includes reasoning: count it once, alongside visible tokens.
    assert result.usage.output_tokens == 90
    assert result.usage.input_tokens == 100 and result.usage.cache_read_tokens == 20
