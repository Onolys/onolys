# Logging and PHI

Session recordings and transcripts may be sensitive. Code: `engines/core/src/onolys_engine_core/{safe_log,json_logging,log_context}.py`, `api/src/onolys_api/logs.py`. How to find and read the logs: [reference/logging.md](../reference/logging.md).

**Audience:** maintainers and coding agents.

- **Allowlist.** `log_event` keeps only fields named in `ALLOWED_FIELDS`: ids, counts, durations, modes and class names. Any other field is dropped silently. A field whose name contains `text`, `body`, `transcript`, `excerpt` or `message` is blocked even if allowed. Add a field to the list when a stage needs to log a new count (and to the field list in `reference/logging.md`; a test checks it). The base list is `safe_log.ALLOWED_FIELDS`; the api adds `API_FIELDS` and engines call `register_fields`.
- **Values.** Numbers are written bare; everything else is a string capped per field: 200 chars (`MAX_VALUE_CHARS`), 300 for `provider_error` (`FIELD_CAPS`). The JSON formatter escapes values, so a value cannot forge another field.
- **Provider text.** `sanitize_provider_text` is the only way provider error text reaches a log: first line only, cut at echo markers (`Received Messages=`, `Invalid Message passed in`), `Bearer`/`key=`/`sk-` credentials and quoted spans over 20 chars redacted (also request-aware redaction in `llm_provider_error`), capped at 300. Prompts, completions and request bodies are never logged.
- **Third-party loggers.** litellm, uvicorn, httpx and google records go through the same JSON handler as one line capped at 300 chars (`{severity, message, logger}` plus context fields), never DEBUG; LiteLLM loggers are pinned to WARNING. Their WARNING/ERROR text is kept as emitted (owner decision 2026-11-23, PHI audit deferred), so never pass user text to them. Exceptions are reduced to class names.
- **Context.** `session_id`, `run_id`, `step`, `request_id`, `client_version` are bound per request/task (`log_context`) and added to every line.
- **Exceptions.** Log the class name and a few frame locations, never the message, because a message can hold user data.
- **Errors in replies.** Error bodies carry fixed messages and a request id, never instance values.
- **Metrics.** The per-request collector holds no prompt or output text.
- **Test.** `engines/miti/tests/test_safe_log.py` covers the allowlist and the blocked names; the api has its own log tests under `api/tests/`.
