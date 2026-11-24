# Logging

How to find the logs of one failed session or API error, and what each log field and `error_code` means. Lines carry ids, codes and numbers, never user content (see [PHI rules](#phi-rules)). Code: `engines/core/src/onolys_engine_core/{json_logging,safe_log,log_context}.py`, `api/src/onolys_api/logs.py`.

**Audience:** users and the owner on call.

## Reference

The failed session card shows the **session id** as its Reference. One session id spans the api, the worker and the engines (context `session_id` is bound on every line of a request or task). Interview routes bind the interview id as `session_id` too.

Logs Explorer link (both envs share project `onolys`); replace `<ID>`:

```
https://console.cloud.google.com/logs/query;query=jsonPayload.session_id%3D%22<ID>%22;duration=P14D?project=onolys
```

For one env add `resource.labels.service_name=("onolys-api-prod" OR "onolys-worker-prod")` (or `-staging`) to the query. Narrow to the failure with `jsonPayload.status="failed"`; sort ascending to read the trail in order. For one run add `jsonPayload.run_id="<rid>"`.

### Errors with no session (Settings cards and other API-only calls)

These show a `request_id` (also the `X-Request-Id` of the response and the `request_id` in the error body). Query:

```
jsonPayload.request_id="<id>"
```

The api line, and the worker lines of a task it enqueued, share that `request_id`.

## Line shape

One JSON object per line on stdout/stderr; Cloud Logging reads `severity` and `message`, the rest is `jsonPayload.*`.

| Field | Meaning |
|---|---|
| `severity`, `message`, `event` | Level, single-line text (cap 300) and event name (`session_stale`, `llm_provider_error`, `interview_audio_check`, `stt_poll`, ...) |
| `logger` | Only on third-party lines (litellm, uvicorn, httpx, google): `{severity, message, logger}` plus context fields |
| `code_version` | Deployed git sha of the api/worker image (same as `/v1/healthz`) |
| `revision` | Cloud Run revision (`K_REVISION`), when set |

### Context fields (on every line of a request or task)

`session_id`, `run_id`, `step`, `request_id`, `client_version` (from the `X-Client-Version` request header, when well-formed).

### Event fields

All names a line may carry (anything else is dropped; see `ALLOWED_FIELDS` and `API_FIELDS`):

| Group | Fields |
|---|---|
| Ids | `request_id`, `session_id`, `run_id`, `step`, `job_id`, `interview_id`, `uid_hash` (keyed HMAC of the uid, 16 hex) |
| Outcome | `status` (`failed` is what alerts match), `outcome`, `result`, `failure`, `error_code`, `exc_class`, `attempt`, `retries` |
| Request | `method`, `route`, `auth_kind`, `duration_ms`, `total_ms` |
| LLM metrics | `calls`, `calls_ok`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `models` |
| Provider error | `provider`, `model`, `http_status`, `error_type`, `provider_error` |
| STT | `stt_provider`, `stt_model`, `stt_operation`, `stt_started`, `poll_n`, `elapsed_s`, `audio_ms`, `language`, `speakers` |
| Email | `email_kind`, `provider_status` |
| Interview audio check | `uploaded_s`, `relay_s`, `diff_s`, `threshold_s`, `result` (`ok`, `mismatch`, `skipped_no_relay_duration`, `skipped_no_interview`) |
| Versions | `code_version`, `revision`, `relay_version`, `relay_revision`, `web_version`, `user_agent`, `recorder_mime`, `audio_engine`, `audio_format`, `audio_codec`, `audio_streams` |

### Version fields

`code_version` and `revision` are on every line. `interview_audio_check` adds the client and relay builds: `web_version`, `user_agent`, `recorder_mime`, `audio_engine` (from the session's/interview's `client` record, the interview's own value wins), `relay_version`, `relay_revision` (the interview's `relay` record), and the probed `audio_format`, `audio_codec`, `audio_streams`. A source that is not there is absent from the line, not an error.

## `error_code` table

The code in the failed line is what `to_public` (`api/src/onolys_api/adapters/error_map.py`) returns for the exception; the same code is on the session and its card. Fixed user text is `PUBLIC_MESSAGES[code]`. A test (`api/tests/test_logging_docs.py`) fails when a code of `PUBLIC_MESSAGES` is missing here, so update this table with the map.

| `error_code` | Meaning | Where raised | Retryable |
|---|---|---|---|
| `output_invalid` | Engine answer did not match its schema | `OutputInvalid` from `validated_run` (engine run) | no |
| `invalid_coded_span` | `coded_span` outside the transcript, or time span without timestamps | `InputError` from the span check (request validation, run) | no |
| `session_too_long` | Coded portion over 25 min or 6000 words | `InputError` from `coded_span.py` | no |
| `invalid_parameters` | Engine rejected the input | Any other `InputError` | no |
| `upstream_unavailable` | LLM, STT or Google (GCS, Firestore) dependency failed or timed out | transient `LLMError` (status 408/429/5xx/529, timeout/rate limit), transient Google errors, transient STT error (any attempt) | yes (one automatic retry) |
| `deadline_exceeded` | Run exceeded its time limit | `TimeoutError`, adapter deadline | yes |
| `transcription_failed` | A non-transient STT error | `SttProviderError`, Google `InvalidArgument` (stt) | no |
| `no_speech` | No usable speech in the recording | STT adapter | no |
| `speakers_not_separated` | Diarization could not tell speakers apart | STT adapter | no |
| `rate_limited` | Provider or API rate limit | Adapter error | yes |
| `internal_error` | Anything else (permanent `LLMError` such as 400/401/403/404, `LLMBadOutput`, engine failure with no transient cause, unknown exception, unknown adapter code) | catch-all of `to_public` | no (owner alerted) |

Codes that exist only as 4xx replies (`unauthenticated`, `not_found`, `daily_cap_reached`, ...) are listed in `api/src/onolys_api/errors.py` and are not `status=failed` lines. The fix per code is in the [infra runbook](infra.md#error_code-table).

### Reading `error_code`, `provider_error` and `http_status` together

For a provider failure the trail has a WARNING `llm_provider_error` line (`provider`, `model`, `http_status`, `error_type`, `provider_error`) before the `status=failed` line, same `session_id` and `run_id`.

| `error_code` | `http_status` | Reading |
|---|---|---|
| `upstream_unavailable` | 429 | Provider rate limit; `provider_error` names the quota |
| `upstream_unavailable` | 5xx | Provider outage or overload |
| `upstream_unavailable` | 401/403 | Bad or missing key (worker secret); the user retry will not help |
| `upstream_unavailable` | 400/404 | Bad request or model id (routes file, `LLM_MODEL`) |
| `upstream_unavailable` | none | Timeout or network error; see `error_type` |
| `internal_error` | n/a | Read `exc_class`, then the trail |

`provider_error` is the sanitized first line of the provider's text, up to 300 chars; `error_type` is the exception class name.

## PHI rules

- Only allowlisted field names are logged; names containing `text`, `body`, `transcript`, `excerpt` or `message` are blocked. Values are capped (200 chars, `provider_error` 300).
- `provider_error` is sanitized: first line only, text after an echo marker cut, `Bearer`/`key=`/`sk-` secrets and quoted spans over 20 chars redacted.
- Exceptions are reduced to class names; no tracebacks or exception messages.
- Prompts, completions, transcripts and request bodies are never passed to a logger by our code.
- LiteLLM lines (WARNING and above) are kept as emitted, single line, capped 300 (owner decision 2026-11-23; a PHI audit of those lines is deferred).

Details: [logging-and-phi.md](../implementation/logging-and-phi.md).
