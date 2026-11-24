import importlib.util
import json
import logging
from pathlib import Path

import pytest

from onolys_engine_core.json_logging import render
from onolys_engine_core.llm import (
    LiteLLMClient,
    LLMConfig,
    LLMError,
    LLMRateLimited,
    LLMRequest,
    LLMTimeout,
    LLMUnavailable,
)
from onolys_engine_core.llm.routes import Route

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _restore_logger_state():
    """probe_llm.run_probe sets `disabled=True` on every LiteLLM* logger (fine for a one-shot
    script, a leak between tests). Restore each logger's state and the global disable level."""
    manager = logging.root.manager
    saved = {
        name: (lg.disabled, lg.level, list(lg.handlers), lg.propagate)
        for name, lg in list(manager.loggerDict.items())
        if isinstance(lg, logging.Logger)
    }
    root_saved = (logging.root.level, list(logging.root.handlers), manager.disable)
    yield
    for name, lg in list(manager.loggerDict.items()):
        if not isinstance(lg, logging.Logger):
            continue
        # loggers first created during the test (e.g. LiteLLM* on import) default to enabled
        disabled, level, handlers, propagate = saved.get(name, (False, 0, [], True))
        lg.disabled, lg.level, lg.propagate = disabled, level, propagate
        lg.handlers[:] = handlers
    logging.root.level = root_saved[0]
    logging.root.handlers[:] = root_saved[1]
    logging.disable(root_saved[2])


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
    text = render(record)
    line = json.loads(text)
    assert record.levelno == logging.WARNING
    assert record.getMessage() == "llm_provider_error"
    assert line["provider"] == "anthropic" and line["model"] == "claude-sonnet-5-5"
    assert line["http_status"] == 503 and line["error_type"] == "RuntimeError"
    assert secret not in text and "another-token" not in text
    assert request.user not in text and request.system not in text
    assert "provider unavailable" in line["provider_error"]
    assert len(line["provider_error"]) <= 300
    assert "llm.provider_error" not in text


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
        records = [r for r in caplog.records if r.name == "miti"]
        assert len(records) == 1
        text = render(records[0])
        for leak in ("sertraline", "Therapist", "tell me more", secret, repr(transcript), "Received Messages", "Invalid Message passed in"):
            assert leak not in text
        assert "invalid_request" in text or "bad shape" in text
        assert len(json.loads(text)["provider_error"]) <= 300


def _client(exc, route=None):
    async def fail(**kwargs):
        raise exc

    route = route or Route(litellm_id="anthropic/claude-sonnet-5-5", api_key_env="ANTHROPIC_API_KEY", max_retries=0)
    return LiteLLMClient(LLMConfig(llm_mode="live", routes={"mid": route}), acompletion=fail)


def _req(**kw):
    return LLMRequest(tier="mid", system="sys", user="usr", response_schema={}, **kw)


async def test_503_exposes_five_fields_redacts_quoted_spans_and_caps(caplog):
    quoted = "a long quoted span that is surely over twenty chars"
    exc = RuntimeError(f"upstream failed \"{quoted}\" " + "y" * 500)
    exc.status_code = 503
    with caplog.at_level(logging.WARNING, logger="miti"), pytest.raises(LLMUnavailable) as ei:
        await _client(exc).complete_json(_req())
    record, = [r for r in caplog.records if r.name == "miti"]
    line = json.loads(render(record))
    assert line["provider"] == "anthropic" and line["model"] == "claude-sonnet-5-5"
    assert line["http_status"] == 503 and line["error_type"] == "RuntimeError"
    assert quoted not in line["provider_error"] and len(line["provider_error"]) <= 300
    e = ei.value
    assert (e.provider, e.model, e.http_status, e.error_type) == (
        "anthropic", "claude-sonnet-5-5", 503, "RuntimeError",
    )
    assert e.provider_error == line["provider_error"]


async def test_400_text_is_logged_sanitized(caplog):
    exc = RuntimeError("invalid_request: max_tokens too large")
    exc.status_code = 400
    with caplog.at_level(logging.WARNING, logger="miti"), pytest.raises(LLMUnavailable) as ei:
        await _client(exc).complete_json(_req())
    record, = [r for r in caplog.records if r.name == "miti"]
    assert json.loads(render(record))["provider_error"] == "invalid_request: max_tokens too large"
    assert ei.value.http_status == 400


async def test_rate_limit_fields(caplog):
    exc = RuntimeError("slow down")
    exc.status_code = 429
    route = Route(litellm_id="anthropic/claude-sonnet-5-5", api_key_env="ANTHROPIC_API_KEY", max_retries=0, timeout_s=1)
    with caplog.at_level(logging.WARNING, logger="miti"), pytest.raises(LLMRateLimited) as ei:
        await _client(exc, route).complete_json(_req())
    records = [r for r in caplog.records if r.name == "miti"]
    assert len(records) >= 1
    line = json.loads(render(records[0]))
    assert line["http_status"] == 429 and line["provider"] == "anthropic"
    assert line["provider_error"] == "slow down"
    e = ei.value
    assert (e.provider, e.model, e.http_status, e.error_type, e.provider_error) == (
        "anthropic", "claude-sonnet-5-5", 429, "RuntimeError", "slow down",
    )


async def test_timeout_fields_http_status_none(caplog):
    exc = TimeoutError("took too long")
    with caplog.at_level(logging.WARNING, logger="miti"), pytest.raises(LLMTimeout) as ei:
        await _client(exc).complete_json(_req())
    record, = [r for r in caplog.records if r.name == "miti"]
    line = json.loads(render(record))
    assert line["error_type"] == "TimeoutError" and line["provider"] == "anthropic"
    assert line.get("http_status") is None
    e = ei.value
    assert e.http_status is None and e.error_type == "TimeoutError"
    assert e.provider == "anthropic" and e.model == "claude-sonnet-5-5"


def test_llm_error_defaults_to_none():
    e = LLMError("x")
    for name in ("provider", "model", "http_status", "error_type", "provider_error"):
        assert getattr(e, name) is None


async def test_prompt_repr_and_json_escaped_forms_redacted(caplog):
    system = 'sys "quoted" line\nTherapist said hi'
    user = "usr\twith 'tab' and \\ slash"
    req = LLMRequest(tier="mid", system=system, user=user, cache_prefix="PREFIX-SECRET-TEXT", response_schema={})
    exc = RuntimeError(f"bad {system!r} {json.dumps(user)} {json.dumps(system)[1:-1]} {repr(user)[1:-1]} PREFIX-SECRET-TEXT")
    exc.status_code = 500
    with caplog.at_level(logging.WARNING, logger="miti"), pytest.raises(LLMUnavailable):
        await _client(exc).complete_json(req)
    record, = [r for r in caplog.records if r.name == "miti"]
    text = json.loads(render(record))["provider_error"]
    for leak in ("Therapist", "with 'tab'", "PREFIX-SECRET-TEXT", "\\t", "quoted"):
        assert leak not in text
    assert text.startswith("bad")


async def test_token_env_value_and_bearer_redacted(caplog, monkeypatch):
    monkeypatch.setenv("MY_SERVICE_TOKEN", "tok-abcdef-123456")
    monkeypatch.setenv("CUSTOM_KEY_ENV", "route-secret-value-9")
    route = Route(litellm_id="anthropic/claude-sonnet-5-5", api_key_env="CUSTOM_KEY_ENV", max_retries=0)
    exc = RuntimeError("fail tok-abcdef-123456 route-secret-value-9 Bearer zzz999 api_key=qqq111")
    exc.status_code = 401
    with caplog.at_level(logging.WARNING, logger="miti"), pytest.raises(LLMUnavailable):
        await _client(exc, route).complete_json(_req())
    text = render([r for r in caplog.records if r.name == "miti"][0])
    for leak in ("tok-abcdef-123456", "route-secret-value-9", "zzz999", "qqq111"):
        assert leak not in text
