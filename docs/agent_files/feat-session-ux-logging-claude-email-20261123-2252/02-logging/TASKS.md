---
status: draft
summary: 9 tasks - log context module, safe_log/sanitizer, JSON formatter + configure, api/worker/voice binding, provider error fields, client/relay version capture, interview_audio_check line, docs, end-to-end log tests.
date: 2026-11-23
---
# Tasks: SP02 Traceable logging
Source of truth: docs/agent_files/feat-session-ux-logging-claude-email-20261123-2252/02-logging/PRD.md. All PRD Open Questions are RESOLVED or DEFERRED (none OPEN); the PHI audit of logs is deferred to the owner and out of scope. Depends on SP01 landing first (SP02 replaces its `_once` error log). No CI change needed (`.github/workflows/ci.yml` exists). Tests use no live API.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Log context module | - | done |
| 2 | safe_log: allowlist, caps, sanitizer, JSON fields | - | done |
| 3 | JsonFormatter, ContextFilter, configure_logging | 1, 2 | done |
| 4 | Bind context in API, worker, voice | 3 | done |
| 5 | Provider error fields + LLMError attributes | 2, 3 | done |
| 6 | Client and relay version capture | 4 | done |
| 7 | interview_audio_check log line | 3, 6 | done |
| 8 | Docs: logging.md, runbook, PHI doc | 5, 7 | done |
| 9 | End-to-end log tests (worker, API, PHI, leak) | 4, 5 | done |

## Task 1 — Log context module
What it is / what it means: One place that holds the ids every log line should carry (session, run, step, request). Traces to D1, R1.
What changes at a high level: New `log_context.py` in engine-core with four context variables, `bind`/`reset`, a `log_context(**ids)` context manager that merges over current values (a nested step overrides only `step`), and `snapshot()` returning the non-None values. Engines never import `api`.
Done when: unit tests pass for: bind/reset restores prior values; nested `log_context` overrides only the given keys; `snapshot()` omits None; values survive `asyncio.run`, `to_thread` and anyio task hops; context does not leak after the `with` block exits.

## Task 2 — safe_log: allowlist, caps, sanitizer, JSON fields
What it is / what it means: Make the PHI-safe field layer ready for provider errors and the new fields, and stop rendering text `k=v`. Traces to D5, R7, R8, R12, R13 (names).
What changes at a high level: Extend `ALLOWED_FIELDS` with `provider, model, http_status, error_type, provider_error`, the interview-check fields (`interview_id, uploaded_s, relay_s, diff_s, threshold_s, result`) and the R13 version names. Add `FIELD_CAPS` (`provider_error` 300 over the default 200) applied in both clean paths, and `sanitize_provider_text` (first line only, quoted spans over 20 chars become `"<redacted>"`, cap 300). `log_event` passes kept fields via `extra={"fields": ...}` instead of text. Update existing consumers/tests of the old text format in `engines/miti/tests` and `test_safe_log.py`.
Done when: tests pass for: sanitizer (quotes, backticks, multiline, truncation); per-field cap; the blocked-`message` rule still drops a `message` field while `provider_error` is kept; new allowlist names kept; `log_event` attaches fields as extra; updated miti/safe_log tests green.

## Task 3 — JsonFormatter, ContextFilter, configure_logging
What it is / what it means: One JSON log shape for our code, miti, LiteLLM and other libraries, with ids injected automatically. Traces to D1, D2, D3, D4, D9, R3, R4, R5, R13 (`revision`).
What changes at a high level: In engine-core add `json_logging.py` with `ContextFilter` (copies `snapshot()` to `record.ctx`) and `JsonFormatter` (severity, message, event, allowlisted fields with explicit over context, `code_version`, `revision` from `K_REVISION`). Non-onolys loggers emit severity, single-line message capped at 300, logger name, plus context; exceptions reduced to class names on the handler for all loggers. `logs.emit` keeps its API but routes through the same formatter. `configure_logging(settings)` installs one stderr handler on root with filter attached to the handler, makes `miti`, `onolys_api.events`, litellm loggers and `httpx` propagate, pins LiteLLM loggers to WARNING, sets `litellm.suppress_debug_info=True`, no DEBUG, no `LITELLM_LOG`. LiteLLM WARNING/ERROR text is kept as emitted (owner decision).
Done when: tests pass for: every line valid single-line JSON; no CR/LF forging from hostile message text; `miti` INFO lines now emitted; litellm WARNING emitted, DEBUG not; no duplicate lines; explicit field beats context; `revision` present when `K_REVISION` set and absent otherwise; exception text reduced to class names.

## Task 4 — Bind context in API, worker, voice
What it is / what it means: Set the ids at the points where they are known, so no call site has to pass them. Traces to D6, D7, R2, risks on sync handlers and voice service.
What changes at a high level: `RequestIdMiddleware` binds `request_id` (before the request logger reads it) and the request-scoped `client_version` from `X-Client-Version`. Add an async router-level dependency `bind_session` on routes with `{sid}`/`{iid}` path params (async on purpose). `TaskRunner.handle` wraps claim, handler and error paths in `log_context(session_id, run_id, request_id, step)` with reset in `finally`; interview tasks bind the interview id as `session_id`. Call `configure_logging` from `logs.configure`; grep whether the voice service shares it and add the same call if not. `bookkeeping_failed` and `unhandled_exception` lines gain the ids through context. No raw threads in worker code.
Done when: tests pass for: request id bound before request log; a sync endpoint on a `{sid}` route logs with `session_id`; `TaskRunner.handle` lines carry all four ids and context is clean after the task (incl. on handler exception); interview task binds the interview id; voice entrypoint configures logging.

## Task 5 — Provider error fields + LLMError attributes
What it is / what it means: The real provider failure becomes visible and readable by SP03. Traces to D5, D8, R6, R9.
What changes at a high level: In `_once`, replace SP01's error log with one WARNING `llm_provider_error` carrying `provider` (from `litellm_id` prefix), `model`, `http_status` (existing `_status(exc)`), `error_type`, and sanitized `provider_error`. Same for rate-limit and timeout (`http_status` None). `LLMError` gains the five matching attributes. 400 text is logged too, sanitized and capped (owner decision). Our code never passes prompts, completions or bodies to a logger.
Done when: tests pass for: stubbed `acompletion` raising `status_code=503` yields the five fields with `provider_error` at most 300 chars and quoted spans redacted; rate-limit and timeout cases; `LLMError` exposes the five attributes; SP01's old log call is gone (no duplicate line).

## Task 6 — Client and relay version capture
What it is / what it means: Record which web build, browser, recorder and relay produced a session, so version-specific failures are findable. Traces to R13 and the owner decision that versions are logged.
What changes at a high level: Web build injects `VITE_BUILD_SHA` (CI `GITHUB_SHA`, `dev` locally) and `web/src/api/client.ts` sends `X-Client-Version` on every request. Session-create and interview create/end accept an optional server-validated `client` object (`web_version`, `user_agent`, `recorder_mime`, `audio_engine`; 4 optional strings, length-capped, control chars stripped, UA trimmed to 200) stored on the session and interview docs; unknown or missing is never rejected. Web sends `recorder_mime` (from `audio/mime.ts`) and `audio_engine` name plus version constant. The voice relay writes `relay_version` (`GIT_SHA`) and `relay_revision` (`K_REVISION`) to `InterviewDoc.relay` at connect. Regenerate contracts.
Done when: tests pass for: request with the header stores `client.web_version` on the session doc; overlong or control-char values sanitized; old clients without `client` still work; relay writes both fields at connect; web unit test asserts the header is sent; contract drift check green.

## Task 7 — interview_audio_check log line
What it is / what it means: Every interview-linked validation leaves one traceable line, match or not. Traces to R12, R13 (probe fields), acceptance criterion 7. Behaviour of the mismatch decision stays in SP03.
What changes at a high level: In `validate`, emit exactly one `interview_audio_check` per interview-linked validation (INFO on ok, WARNING on mismatch/skip) with `session_id, interview_id, uploaded_s, relay_s, diff_s, threshold_s` (rounded to 0.1 s), `result` (`ok|mismatch|skipped_no_relay_duration|skipped_no_interview`) and the version fields, reading web/relay versions from the stored docs. Add `codec_name` to the probe result if absent; log `audio_format`, `audio_codec`, `audio_streams`. Absent sources log as absent. If SP03's decision code is not yet present, provide the emit helper and the call at the existing validation point so SP03 reuses it.
Done when: tests pass for match, mismatch, skipped_no_relay_duration and skipped_no_interview, each producing exactly one line with all listed fields; missing version sources log as absent without error; no audio content or user text in the line.

## Task 8 — Docs: logging.md, runbook, PHI doc
What it is / what it means: Docs match what the UI shows and give a ready query per session. Traces to D7, R10, acceptance criterion 5.
What changes at a high level: New `docs/reference/logging.md`: Reference = session id on the failed card; Logs Explorer link template (project `onolys`, optional `service_name`); field list; `request_id` query for Settings-card API errors; error_code table taken from `PUBLIC_MESSAGES` in `error_map.py` (code, meaning, where raised, retryable) and how `error_code`, `provider_error`, `http_status` read together; version fields; PHI summary. Rewrite the `infra.md` runbook (reference is session id, step order, link, keep the verified-2026-11-20 REST example). Update `logging-and-phi.md` (field list, per-field cap, sanitizer, third-party-logger rule) and `docs/reference/README.md` index.
Done when: files exist and links resolve; table codes match `PUBLIC_MESSAGES` (a small test or check script asserts every code is listed); the runbook no longer says the card shows `request_id` for session failures.

## Task 9 — End-to-end log tests (worker, API, PHI, leak)
What it is / what it means: The guard tests that prove both properties: traceable and PHI-safe. Traces to R11, acceptance criteria 1-4.
What changes at a high level: Add `api/tests/test_logging.py` and engine-core tests that run through real wiring: a sample `TaskRunner` task whose handler logs via `miti` `log_event`, plain `logging.getLogger("litellm")` WARNING and `logs.emit`; an API sync-route request; a sentinel (`SENTINEL-PHI-7731`) in transcript plus a stub provider exception quoting it, asserting no line from our code contains it (LiteLLM-emitted lines not asserted, per deferral); two consecutive tasks to prove no context leak.
Done when: all four tests pass: every worker line has `session_id, run_id, step, request_id`; sync-route line has `session_id`; sentinel absent; second task's lines do not carry the first task's ids.

## Owner steps
- PHI audit of staging logs (`provider_error` text, LiteLLM WARNING/ERROR lines, Gemini 400 text) is the owner's deferred follow-up; decide any tightening afterwards.
- After deploy to staging, owner may confirm in Logs Explorer that `jsonPayload.session_id="<sid>"` returns api, worker and engine lines (acceptance criterion 1 on real infra).
