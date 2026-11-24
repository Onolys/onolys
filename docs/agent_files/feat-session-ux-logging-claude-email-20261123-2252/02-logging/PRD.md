---
status: draft
summary: Every api/worker/engine log line carries session_id (plus run_id, step, request_id) via a contextvar; miti and LiteLLM logs join the same JSON format; provider failures log status/type/truncated text through the allowlist; one logging.md runbook keyed on the on-screen Reference (session id).
date: 2026-11-23
---
# PRD: SP02 Traceable logging

Repo/branch: Onolys/onolys (local `iaudit`) / `feat/session-ux-logging-claude-email` · Depends on: SP01 (Phase 1; lands first, SP02 replaces its error log) · Owns: `engines/core/src/onolys_engine_core/{log_context.py (new), json_logging.py (new), safe_log.py, llm/errors.py (fields only), llm/litellm_client.py (error log only)}`, `engines/miti/src/onolys_miti/run.py` (no change expected), `api/src/onolys_api/{logs.py, app.py (middleware+configure), jobs/worker.py (bind)}`, `api/src/onolys_api/{routes/sessions.py + web client header (session-create `client` field), voice/relay.py (relay version fields)}`, `web/src/api/client.ts` (`X-Client-Version`), `docs/reference/{infra.md (runbook), logging.md (new), README.md}`, `docs/implementation/logging-and-phi.md`, tests under `api/tests/test_logging.py`, `engines/core/tests/`

## TL;DR
A failed staging run today leaves almost nothing to search: errors log only `upstream_unavailable`/`LLMUnavailable`, engine lines have no `session_id`, and the runbook tells you to search `request_id` while the failed card shows the session id. This SP adds one context mechanism (contextvars in engine-core), one JSON formatter for `onolys_api`, `miti` and LiteLLM loggers, PHI-safe provider error fields, and a `logging.md` with a ready Logs Explorer link per session id.

## Problem
- `litellm_client.py:~330` keeps only `type(exc).__name__`; the provider status/text are dropped [verified: read]. Session 9521150e… staging shows only `upstream_unavailable`/`LLMUnavailable` [brief evidence].
- Nothing calls `safe_log.setup_logging` (`grep -rn setup_logging` hits only its definition). So `miti` `log_event` INFO lines are dropped and WARNING+ fall to Python's last-resort plain text; LiteLLM and uvicorn loggers are also unformatted [verified: grep].
- Engine lines carry `request_id` (`RunContext.request_id`, `run.py:271`) but no `session_id`/`run_id`. API lines pass ids by hand (`logs.emit(session_id=...)`), so any line that forgets it is untraceable; `bookkeeping_failed` and `unhandled_exception` already lack it (`worker.py`, `app.py:313`).
- `infra.md:236-246` says the error card shows the `request_id`; the session failed card shows `Reference: <sid>` (`web/src/flows/flows.test.tsx:175,279`), only Settings cards show a `request_id`. Mismatch.
- `safe_log` blocks names containing `message`, so a naive `provider_message` field would be silently dropped [verified: `_BLOCKED_PARTS`].

## Goals / Non-Goals
**Goals:** paste a session id, see every log line of that session across api, worker, engine; real provider error visible without leaking content; one JSON shape; docs match what the UI shows; tests guard both properties.
**Non-goals:** error classification/retry policy (SP03), new alerts, log sinks/metrics, `uid_hash` changes, web changes, request-body logging, prod rollout.

## Requirements
**R1 Context module** `onolys_engine_core/log_context.py`: four `ContextVar[str|None]` (`session_id`, `run_id`, `step`, `request_id`); `bind(**ids) -> token` / `reset(token)` and a context manager `log_context(**ids)` that merges over the current values (so a nested engine step overrides only `step`). `snapshot() -> dict` of the non-None values.
**R2 Where set.**
- API: `RequestIdMiddleware` binds `request_id` (before `RequestLogMiddleware` reads it). Routes with a `{sid}`/`{iid}` path param get a router-level `async def` dependency `bind_session` that sets `session_id` (async on purpose: a sync dependency runs in a threadpool copy of the context and its `set` is lost).
- Worker: `TaskRunner.handle` wraps the claim, handler and error paths in `log_context(session_id=p.sid, run_id=p.run_id, request_id=p.request_id, step=spec.step or p.kind)`, reset in `finally`. Interview tasks set `session_id=<iid>` (payload `sid` holds the interview id there, `queue.py:5`).
- Engine: no new binds; it inherits, since `asyncio.run`, `to_thread` and anyio copy the context. Engine stages may narrow `step` with `log_context`.
**R3 Injection.** A `logging.Filter` (`ContextFilter`) copies `snapshot()` onto the record as `record.ctx`; the formatter merges it. Attached to the handler, not the loggers (logger filters skip records from child loggers).
**R4 One formatter** `onolys_engine_core/json_logging.py`: `JsonFormatter` emits `{severity, message, event, <allowlisted fields>, code_version}` (same shape and Cloud Logging keys as `logs.emit` today). Field sources, in order: context, then explicit fields (explicit wins). `safe_log.log_event` stops rendering `k=v` text and passes `extra={"fields": kept}`; `logs.emit` keeps its API and routes through the same formatter (one code path). `configure_logging(settings)` in `logs.configure` (api and worker share one image/app, so one entrypoint) installs one stderr handler with ContextFilter+JsonFormatter on **root**, and sets `miti`, `onolys_api.events`, `litellm`, `LiteLLM`, `LiteLLM Router`, `LiteLLM Proxy`, `httpx` to propagate to root (no per-logger handlers, so no duplicates).
**R5 Third-party records.** Non-onolys loggers (litellm, uvicorn, httpx, google) emit `{severity, message (single line, capped 300), logger}` plus context fields; never DEBUG. LiteLLM loggers are pinned to WARNING at configure time and their WARNING/ERROR lines are kept as emitted (no reduction to class+status; owner 2026-11-23, PHI audit of logs deferred); `litellm.suppress_debug_info=True`; `LITELLM_LOG` is not set. Exceptions are reduced to class names with the existing `_NoTraceback` rule, now applied on the handler for all loggers.
**R6 Provider error fields.** In `_once`, on provider exceptions log one WARNING `llm_provider_error` (and set the same attributes on the raised `LLMError`): `provider` (from `litellm_id` prefix), `model`, `http_status` (int|None, existing `_status(exc)`), `error_type` (exception class name), `provider_error` (sanitized text, R7). Replaces SP01's R2 log call. Also logged for rate-limit (`LLMRateLimited`) and timeout (`http_status` None). The name `provider_error` avoids the blocked `message` part.
**R7 Sanitizer.** `safe_log.sanitize_provider_text(s)`: first line collapsed, quoted spans over 20 chars (`"…"`, `'…'`, backticks) replaced by `"<redacted>"`, truncated to 300. Per-field caps: `FIELD_CAPS={"provider_error": 300}` over the default 200 (`MAX_VALUE_CHARS`), applied in both `_fmt`/`_clean` paths. Prompts, completions and request bodies are never passed to a logger by our code.
**R8 Allowlist.** Add to `safe_log.ALLOWED_FIELDS`: `provider`, `model`, `http_status`, `error_type`, `provider_error`. Context fields `session_id,run_id,step,request_id` already allowed. SP07 adds `email_kind, outcome, provider_status` to `logs.py` `API_FIELDS`; SP02 adds none there, so the two edits are disjoint (conflict only on that frozenset literal; rebase trivial).
**R9 Exposed to SP03.** `LLMError` gains `provider: str|None`, `model: str|None`, `http_status: int|None`, `error_type: str|None`, `provider_error: str|None` (sanitized, ≤300). SP03 classifies on `http_status`/`error_type`; it must not log `provider_error` itself (already logged here).
**R10 Docs.**
- `docs/reference/logging.md`: Reference = session id shown on the failed card; link template `https://console.cloud.google.com/logs/query;query=jsonPayload.session_id%3D%22<ID>%22;duration=P14D?project=onolys` (both envs share project `onolys`; add `resource.labels.service_name` for one env); field list; `request_id` query for API-only errors (Settings cards); error_code table (from `PUBLIC_MESSAGES` in `error_map.py`: code, meaning, where raised, retryable) and how `error_code` + `provider_error` + `http_status` read together; PHI rules summary.
- `infra.md` runbook: reference id is the session id (request_id only for non-session API errors), step order rewritten, link to `logging.md`; keep the verified-2026-11-20 REST example.
- `logging-and-phi.md`: add field list, per-field cap, sanitizer, third-party-logger rule.
**R11 Tests.**
- Interview audio check (R12/R13): match, mismatch and skipped cases each emit exactly one `interview_audio_check` line with all listed fields; versions absent from docs log as absent.
- Worker: run a sample task through `TaskRunner` with a handler that logs via `miti` `log_event`, a plain `logging.getLogger("litellm")` WARNING and `logs.emit`; assert every captured line has `session_id`, `run_id`, `step`, `request_id`.
- API: request to a `{sid}` route with a sync endpoint; assert its in-handler line carries `session_id`.
- PHI: handler/engine run with a transcript sentinel string (e.g. `"SENTINEL-PHI-7731"`) in transcript and a stub provider exception whose text embeds it in quotes; assert no line emitted by our code (including exceptions) contains it. LiteLLM-emitted lines are not asserted (kept as is, see [DEFERRED] PHI audit).
- Provider error: stubbed `acompletion` raising an error with `status_code=503`; assert fields `provider, model, http_status=503, error_type`, `provider_error` ≤300 and redacted.
- Formatter: valid JSON per line, no CR/LF forging, `miti` INFO lines now emitted; context reset after task (no leak into next task).

**R12 Interview validation log (owner 2026-11-23; behaviour in SP03 R9).** `validate` logs ONE `interview_audio_check` line for every interview-linked validation, match or not (INFO on ok, WARNING on mismatch/skip): `session_id`, `interview_id`, `uploaded_s`, `relay_s`, `diff_s`, `threshold_s`, `result` (`ok`|`mismatch`|`skipped_no_relay_duration`|`skipped_no_interview`), plus the version fields of R13. Add to `safe_log.ALLOWED_FIELDS`: `interview_id`, `uploaded_s`, `relay_s`, `diff_s`, `threshold_s`, `result`, and the R13 names. Numbers are rounded to 0.1 s. No audio content or user text.
**R13 Version fields (every `interview_audio_check` line; the first two are on every log line already or by one-line additions).**
| Field | Source today | Change |
|---|---|---|
| `code_version` (api/worker image) | `settings.git_sha` (`GIT_SHA` env, `logs.py:82`), already on every line | none |
| `revision` (api/worker Cloud Run revision) | `K_REVISION` env set by Cloud Run; NOT read anywhere today [verified: grep] | `JsonFormatter` adds `revision=os.environ.get("K_REVISION")` beside `code_version` (static, every line) |
| `relay_version`, `relay_revision` (voice service) | same image as the api with `SERVICE_MODE=voice`; `GIT_SHA` set in `infra/modules/environment/voice.tf:92`; `K_REVISION` set by Cloud Run | relay writes both onto the interview doc at connect (`InterviewDoc.relay`), `validate` reads them from there (the worker has no relay context) |
| `web_version` | NOT sent to the api today [verified: no build id in `web/src`, no client header] | web build injects `VITE_BUILD_SHA` (CI `GITHUB_SHA`, `dev` locally); `web/src/api/client.ts` sends `X-Client-Version: <sha>` on every request; session-create stores `client.web_version` and `client.user_agent` on the session doc; the interview create/end call stores them on the interview doc too; `validate` reads from the docs (the Cloud Task has no request headers). A `client_version` request-scoped context field is bound by `RequestIdMiddleware` for API lines |
| `user_agent` | request `User-Agent` header, available at session/interview create | stored with `client` (trimmed to 200 chars, control chars stripped); logged only on `interview_audio_check` (not a per-line field) |
| `recorder_mime`, `audio_engine` | web `audio/mime.ts` (chosen `MediaRecorder` mimeType) and `audio/engine.ts` | web sends both with `client` at interview end / session create (`recorder_mime`, `audio_engine` = engine name + its version constant) |
| `audio_format`, `audio_codec`, `audio_streams` | `validate` sniff (`fmt`) and `tools.probe` result | logged from the probe (add `codec_name` to the probe result if absent) |
`client` is a small server-validated object (4 optional strings, length-capped); unknown or missing values are logged as absent, never rejected.

## Architecture
```
API: RequestIdMiddleware -> request_id ─┐
     bind_session dependency -> session_id ─┤
Worker: TaskRunner.handle -> all four ─────┼─► ContextVars (engine-core)
Engine (miti, LiteLLM client) inherits ────┘            │
                                                        ▼
any logger (onolys_api.events | miti | litellm | root) ─► root handler: ContextFilter ─► JsonFormatter ─► stderr ─► Cloud Logging jsonPayload.*
```
Interface: `with log_context(session_id=..., run_id=..., step=..., request_id=...): ...`. Engine-core owns it, so engines never import `api`; api already depends on engine-core.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | Context carrier | contextvars + handler `ContextFilter` in engine-core | `LoggerAdapter`; passing ids as args | Adapters need every call site changed and miss third-party loggers; contextvars covers LiteLLM/uvicorn lines too |
| D2 | Filter attach point | The handler | Per-logger filters | Logger filters do not see child-logger records |
| D3 | Formatter home | engine-core, reused by api | Separate copies | One shape; `miti` already lives there |
| D4 | Third-party log text | Cap 300, WARNING+, class-name-only exceptions, LiteLLM lines kept (owner: log everything for now) | Silence litellm entirely; reduce to class+status | Brief locks wiring; prompts only appear at DEBUG, which stays off |
| D5 | Provider text | Sanitized `provider_error`, 300 chars, quoted spans redacted | Log nothing; full text | Needed to debug; allowlist + redaction bound PHI echo |
| D6 | Session routes | async dependency `bind_session` | Middleware parsing the path; sync dependency | Path params exist only after routing; sync deps lose contextvar sets |
| D7 | Reference | session id | request_id on card | Locked in brief; one id spans api+worker+engine |
| D8 | Expose to SP03 | Attributes on `LLMError` | SP03 re-parses exceptions | One extraction site, in the client |
| D9 | Level for LiteLLM | WARNING | INFO/DEBUG | INFO logs request summaries; DEBUG logs payloads |

## Risks / Open Questions
- [RESOLVED: log everything for now; keep LiteLLM WARNING/ERROR output, no suppression to class+status (owner 2026-11-23)] Does a LiteLLM WARNING/ERROR line ever echo prompt text on provider errors? Not gated on; covered by the deferred audit below.
- [RESOLVED: log Gemini 400 text / `provider_error` for 400s too, cleaned (R7 sanitizer) and capped at 300 chars (owner 2026-11-23)] Gemini 400 messages can quote request content; the quoted-span redactor is a heuristic, not a guarantee. Residual risk accepted; reviewed in the deferred audit.
- [DEFERRED] PHI audit of logs: owner will audit staging logs later (provider_error text, LiteLLM WARNING/ERROR lines, Gemini 400 text) and decide any tightening. Out of scope for this SP.
- [RESOLVED: default — grep at task time; if the voice service does not share `logs.configure`, it gets the same `configure_logging` call] Does the voice service share `logs.configure`?
- [RESOLVED: `RunContext.request_id` equals the API request id, `run.py:271`] engine `request_id` fields do not conflict with context.
- Risk: moving `log_event` from `k=v` text to JSON changes `miti` line format; any consumer or test parsing it (`engines/miti/tests`, `test_safe_log.py`) updates in the same PR.
- Risk: sync handlers on threads. Worker handlers run inside `handle`; `to_thread`/`asyncio.run` copy context. A raw `threading.Thread` does not: forbid in worker code, covered by the sample-task test.
- Risk: `X-Client-Version` and `client` add a field to session-create/interview-create request bodies and the contracts (SP03/04/05/07 also regenerate; last merged wins). Fields are optional; old clients keep working.
- Risk: SP01 and SP02 both edit `_once`. Order fixed: SP01 first.

## Acceptance Criteria
1. For a staging session, `jsonPayload.session_id="<sid>"` returns api request lines, worker step lines, `miti.*` lines and any provider error line, ordered.
2. A forced provider failure shows one `llm_provider_error` line with `provider, model, http_status, error_type, provider_error` (≤300 chars), and no prompt/transcript text in any line emitted by our code (LiteLLM's own WARNING/ERROR lines are kept unfiltered for now; see [DEFERRED] PHI audit).
3. `miti` and LiteLLM records are single-line JSON with `severity`; no plain-text lines remain except none from our code.
4. The tests in R11 pass (worker `session_id` on every line; sentinel PHI absent; context does not leak between tasks).
5. `docs/reference/logging.md` exists with the link template, request_id query, error_code table and field list; the `infra.md` runbook says Reference = session id.
6. `LLMError` exposes the five attributes of R9 and SP03 can read `http_status` without re-parsing.
7. Every interview-linked validation (match, mismatch, skipped) emits one `interview_audio_check` line carrying `session_id, interview_id, uploaded_s, relay_s, diff_s, threshold_s, result` and the R13 version fields (`code_version, revision, relay_version, relay_revision, web_version, user_agent, recorder_mime, audio_engine, audio_format, audio_codec`); absent sources show as absent, not as an error.
8. `K_REVISION` appears as `revision` on every api/worker line; the web sends `X-Client-Version` on every request and the value reaches the session doc (test: request with the header, read `client.web_version`).
