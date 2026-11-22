# LLM client

Every model call goes through one interface. Code: `engines/miti/src/onolys_miti/llm/`.

**Audience:** maintainers and coding agents.

`LLMClient.complete_json(req, metrics)` takes an `LLMRequest` (route, system text, user text, a pydantic `response_model`, a `call_tag`, optional cache prefixes, token cap, per-call timeout, fixture key, deadline, retry flag) and returns an `LLMResult` holding the parsed object, usage, latency, model and attempts.

## Routes

`LLMRequest.tier` names a **route**. Routes come from the registry in `llm/routes.py`, not from per-stage settings. Prompts name routes only, never model ids. The engine's routes are `cheap`, `mid`, `strong`, and the aliases `miti_code`, `miti_globals` and `tips` (all aliases of `mid` by default).

Model choice is data. The registry loads `llm/routes.default.yaml`, or the file named by env `ROUTES_FILE` (the deployed copies are `config/{env}/routes.yaml`). Each route entry holds:

- `litellm_id`, `api_key_env` (the variable name, never the key).
- `structured_output_mode` (`json_object` or `json_schema`), `caching_mode` (`none`, `provider_implicit`, `anthropic_ephemeral`), `supports_temperature`, `extra_params`.
- `max_output_tokens`, `context_tokens`, `timeout_s` (a larger request value is clamped), `max_concurrency` (semaphore per route), `max_retries`, `backoff_s`.

A route may be an alias (`miti_code: {alias: mid}`). A `presets:` section bundles route overrides plus an STT key; env `DEFAULT_PRESET` picks one (default `default`). The `MITI_MODEL_*` and `MITI_LLM_RESPONSE_FORMAT` variables override a route's model id and output mode ([configuration.md](../reference/configuration.md#miti-engine)). The default routes run on the Google Gemini API (key in `GEMINI_API_KEY`) with `caching_mode: provider_implicit`, `json_object` output, `supports_temperature: false` and `reasoning_effort: low` (Gemini thinks by default and thinking tokens count against `max_tokens`, so this protects small output caps). The `claude` preset switches to Claude Sonnet (`ANTHROPIC_API_KEY`). Adding another provider is a YAML entry, not code. A live check of the routes and the engine: `uv run --package onolys-miti python -m onolys_miti.check --preset <p>` (manual; needs keys). Rationale for routes as data: [ADR 0017](../decisions/0017-workspace-routes-shared-core.md) (superseded in layout by [ADR 0025](../decisions/0025-miti-only-lean-engine.md)).

## Implementations

| Class | Use |
|---|---|
| `LiteLLMClient` | Live calls. JSON output, its own timeout and retry (LiteLLM's retries are off), a per-route concurrency semaphore. |
| `FixtureClient` | Replays recorded answers by key; raises `FixtureMiss` on an unknown key and never touches the network. |
| `RecordingClient` | Wraps a live client and writes fixtures (`MITI_LLM_RECORD=1`). |
| `StubClient` | Canned answers per call tag, for tests. |
| `FailingClient` | Always raises, for failure tests. |

`warm_then_fanout()` (`llm/warm.py`) sends one call first so a prompt cache entry exists before parallel calls. Golden fixtures and re-recording: [engines/miti/README.md](../../engines/miti/README.md#golden-fixtures).

## Errors

`LLMTimeout`, `LLMUnavailable`, `LLMRateLimited` and `LLMBadOutput` (all `LLMError`, `llm/errors.py`). A 429 or 529 raises `LLMRateLimited` and backs off inside the deadline rather than consuming retries. A transport retry happens at most `max_retries` times, only if the request deadline leaves room, and never for errors retrying cannot fix (authentication, not found). A request with `retry=False` is tried once.

## Caching

`cache_prefix` (one) or `cache_prefixes` (up to two, each a cache breakpoint) become leading system blocks marked ephemeral; the call's own `system` text follows. A fixture key includes `cache_prefixes` only when present.
