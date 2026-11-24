import importlib.util
import json
import logging
from pathlib import Path

import pytest

from onolys_engine_core.llm import LiteLLMClient, LLMConfig, LLMRequest, LLMUnavailable
from onolys_engine_core.llm.routes import Route

pytestmark = pytest.mark.unit


async def test_provider_warning_redacts_credentials_prompts_and_caps_message(caplog, monkeypatch):
    secret = "private-provider-credential"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    request = LLMRequest(tier="mid", system="private system prompt", user="private user prompt", response_schema={})
    error = RuntimeError(f"provider unavailable key={secret} Authorization: Bearer another-token {request.user} {request.system} " + "x" * 400)
    error.status_code = 503

    async def fail(**kwargs):
        raise error

    route = Route(litellm_id="anthropic/claude-sonnet-5-5", api_key_env="ANTHROPIC_API_KEY", max_retries=0)
    client = LiteLLMClient(LLMConfig(llm_mode="live", routes={"mid": route}), acompletion=fail)
    with caplog.at_level(logging.WARNING, logger="miti"), pytest.raises(LLMUnavailable):
        await client.complete_json(request)
    record, = [r for r in caplog.records if r.name == "miti"]
    text = record.getMessage()
    assert record.levelno == logging.WARNING
    assert "provider=anthropic" in text and "model=claude-sonnet-5-5" in text
    assert "status_code=503" in text and "exc_class=RuntimeError" in text
    assert secret not in text and "another-token" not in text
    assert request.user not in text and request.system not in text
    assert "provider unavailable" in text
    assert len(json.loads(text.split("message=", 1)[1])) <= 300


def load_probe():
    path = Path(__file__).resolve().parents[1] / "scripts" / "probe_llm.py"
    spec = importlib.util.spec_from_file_location("probe_llm", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_probe_claude_kwargs_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "routes.yaml"
    path.write_text("mid:\n  litellm_id: anthropic/claude-sonnet-5-5\n  api_key_env: ANTHROPIC_API_KEY\n  supports_temperature: false\n  max_output_tokens: 16000\n  extra_params: {reasoning_effort: low}\n")
    monkeypatch.setenv("ROUTES_FILE", str(path))
    probe = load_probe()
    route, request, kwargs = probe.build_probe("mid")
    assert kwargs == {
        "model": "anthropic/claude-sonnet-5-5",
        "messages": [{"role": "system", "content": "Return only a JSON object."}, {"role": "user", "content": 'Return {"ok": true}.'}],
        "response_format": {"type": "json_object"},
        "max_tokens": 16000,
        "timeout": 180,
        "drop_params": True,
        "num_retries": 0,
        "reasoning_effort": "low",
    }
    assert route.api_key_env == "ANTHROPIC_API_KEY"
    assert request.tier == "mid"


async def test_probe_suppresses_debug_and_prints_safe_error(tmp_path, monkeypatch, capsys, caplog):
    import litellm

    path = tmp_path / "routes.yaml"
    path.write_text("mid: {litellm_id: anthropic/claude-test, api_key_env: ANTHROPIC_API_KEY}")
    monkeypatch.setenv("ROUTES_FILE", str(path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-api-key")
    probe = load_probe()

    def debug():
        print("secret-api-key")
        logging.getLogger("LiteLLM").warning("secret-api-key")

    async def fail(**kwargs):
        print("secret-api-key")
        raise RuntimeError("API failed secret-api-key")

    monkeypatch.setattr(litellm, "_turn_on_debug", debug)
    monkeypatch.setattr(litellm, "acompletion", fail)
    monkeypatch.setattr(litellm, "get_model_info", lambda model: {"max_tokens": 1})
    assert await probe.run_probe("mid") == 1
    logging.getLogger("LiteLLM").warning("deferred secret-api-key")
    output = capsys.readouterr()
    assert "secret-api-key" not in caplog.text
    assert "secret-api-key" not in output.out + output.err
    assert "RuntimeError" in output.out and "API failed" in output.out


async def test_provider_warning_drops_echoed_message_transcript(caplog, monkeypatch):
    secret = "private-provider-credential"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    transcript = "Therapist: tell me more\nClient: I take sertraline for my anxiety"
    request = LLMRequest(tier="mid", system="sys prompt", user=transcript, response_schema={})
    messages = [{"role": "user", "content": [{"type": "text", "text": transcript}]}]
    error = RuntimeError(f"invalid_request key={secret}\nReceived Messages={messages}")
    error.status_code = 400
    other = RuntimeError(f"bad shape Invalid Message passed in - {messages[0]}. File an issue")
    other.status_code = 400

    route = Route(litellm_id="anthropic/claude-sonnet-5-5", api_key_env="ANTHROPIC_API_KEY", max_retries=0)
    for exc in (error, other):
        async def fail(*, exc=exc, **kwargs):
            raise exc

        caplog.clear()
        client = LiteLLMClient(LLMConfig(llm_mode="live", routes={"mid": route}), acompletion=fail)
        with caplog.at_level(logging.WARNING, logger="miti"), pytest.raises(LLMUnavailable):
            await client.complete_json(request)
        text = "\n".join(r.getMessage() for r in caplog.records)
        for leak in ("sertraline", "Therapist", "tell me more", secret, repr(transcript), "Received Messages", "Invalid Message passed in"):
            assert leak not in text
        assert "invalid_request" in text or "bad shape" in text
        assert len(json.loads(text.split("message=", 1)[1])) <= 300
