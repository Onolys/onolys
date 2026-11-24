---
status: draft
summary: 10 tasks - classifier + is_transient, persisted kind/retry fields, charging rules, retry endpoint, upload-limits API, upload-failure discard, interview mismatch, web failure cards + countdown, web pre-checks + upload-failed view, contracts and docs.
date: 2026-11-23
---
# Tasks: SP03 Failure policy + retry
Source of truth: docs/agent_files/feat-session-ux-logging-claude-email-20261123-2252/03-failure-policy/PRD.md. All PRD Open Questions are RESOLVED (none OPEN). Depends on SP01 and SP02 landing first (reads SP02's `LLMError.http_status`/`error_type`; reuses SP02 Task 7's `interview_audio_check` helper, it is not re-implemented here). No CI change needed (`.github/workflows/ci.yml` exists). Tests use no live API.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Classifier, KIND_BY_CODE, is_transient | - | done |
| 2 | Persist kind, counted, retry_count; retire BAD_FILE_CODES | 1 | done |
| 3 | Charging module, interview never counted, retire free_run_void | 2 | done |
| 4 | Retry endpoint and TRANSITIONS | 2, 3 | done |
| 5 | GET /v1/upload-limits and one accepted-types source | - | done |
| 6 | Validation failure = upload failure; keep data after validation | 2 | done |
| 7 | Interview audio mismatch = our error | 3, 6 | done |
| 8 | Web failure cards, copy, countdown retry | 2, 4 | done |
| 9 | Web pre-checks from served limits; UploadFailedView | 5, 6, 8 | done |
| 10 | Contracts regen, mocks, docs | 4, 5, 6, 7, 8, 9 | done |

## Task 1 — Classifier, KIND_BY_CODE, is_transient
What it is / what it means: One place decides whether a failure is a blip, our fault, or the file's fault. Traces to D1, D2, D6, D8, R1, R2.
What changes at a high level: In `error_map.py` add `classify(exc, stage) -> Failure(code, kind)` following the R1 table; `to_public` stays as a thin wrapper so the 3 callers keep working. Add one `KIND_BY_CODE` table. Add `is_transient(exc)` in engine-core `llm/errors.py` (status/type rules, no api imports) and call it from `error_map`. A second transient STT failure stays `upstream_unavailable` (D6). Reads SP02's structured fields only, never `provider_error` text. Keep the `_llm_cause` walk.
Done when: `test_error_map.py` table test covers every R1 row for stages validate/stt/run (incl. 404 to `internal_error`/permanent_internal, 503 to `upstream_unavailable`/transient, Google `InvalidArgument` to user_file, `AllRunsFailed` with transient cause stays transient); `is_transient` unit tests pass in engine-core with no api import.

## Task 2 — Persist kind, counted, retry_count; retire BAD_FILE_CODES
What it is / what it means: The kind is stored once on the session so the server and web never re-derive it. Traces to D2, D4, R3.
What changes at a high level: `SessionError` gains `kind` and `counted`; `SessionDoc` gains `retry_count`; `SessionStatusDoc` gains `error_kind`, `retries_left`, `counted`. `worker._fail`, the `runs._compensate` path and `stale.py` fill `kind` from `KIND_BY_CODE`. Delete `BAD_FILE_CODES`/`is_system_failure` from `machine.py` and move call sites to the table. Add `MAX_SESSION_RETRIES` (3) to config. Old failed docs without `kind` derive it from the code.
Done when: tests pass for: each write site persists the right kind; status doc exposes `error_kind`, `retries_left`, `counted`; an old failed doc without `kind` reads as derived; grep shows no `BAD_FILE_CODES`/`is_system_failure`; fake and Firestore repos stay in parity.

## Task 3 — Charging module, interview never counted, retire free_run_void
What it is / what it means: Only a user/file fault after the model started is ever counted; interview sessions are never counted. Traces to D5, R5, R9 (retirement), acceptance criteria 3 and 8.
What changes at a high level: New `jobs/charging.py` holding `should_refund(kind, llm_started)` and `release_once(...)` (moved from `run.py`'s `_refund`); `release_run_slot` reports whether a unit was kept and `worker._fail` writes it to `SessionError.counted`. Refund runs in `run.py` before `_fail`. The exempt predicate becomes `interview_id is not None` in `repo/{fake,firestore}.py` and `routes/sessions.py` `free_run`; no day count, `counted=false`. Remove `free_run_void` from models and code (read tolerant via `extra=ignore`, no migration). Cancel charging stays SP04's; do not touch it.
Done when: tests pass for: transient and permanent_internal run failures refund and `counted=false`; double release refunds once; user_file with `llm_started` keeps the unit (`counted=true`), without refunds; interview-linked first run (failing or succeeding) leaves usage unchanged and `counted=false`; non-interview first-free-run unchanged; a doc carrying `free_run_void` still loads; grep for `free_run_void` is clean.

## Task 4 — Retry endpoint and TRANSITIONS
What it is / what it means: One capped retry path that re-enters whichever step failed. Traces to D3, D4, R4.
What changes at a high level: New `POST /sessions/{id}/retry` (opId `retrySession`, 202) in `routes/sessions.py`. Allowed only when `state=failed`, `error.kind=transient`, `retry_count < MAX_SESSION_RETRIES`, rating not final; else 409 `invalid_state`. One repo transaction (fake and Firestore) increments `retry_count` and moves state. Re-entry: validate to `validating` and enqueue (409 if staged copy is gone), transcribe resets the step and enqueues, run reuses `start_run` logic with a new run id and unit. `TRANSITIONS["failed"]` gains `validating`, `transcribing`. `POST /runs` on a `failed` session returns 409. Silent worker retries do not touch the counter.
Done when: tests pass for: three retries succeed and the fourth is 409 with `retry_count` still 3; two concurrent retries at count 2 give one winner; non-transient or non-failed or finalized-rating gives 409; each step re-enters the right state and enqueues the right task (run uses same preset/n_runs/span); `POST /runs` on failed is 409; a retried run at the day cap shows `daily_cap_reached`.

## Task 5 — GET /v1/upload-limits and one accepted-types source
What it is / what it means: The server publishes the upload limits it enforces so the web stops keeping copies. Traces to R10 (server half), acceptance criterion 10.
What changes at a high level: New `routes/upload_limits.py` (opId `getUploadLimits`, authenticated like `/usage`) returning `max_bytes`, `max_duration_s` (default STT preset), `interview_max_duration_s`, `short_warning_s`, `extensions[]`, `mime_types[]`. Built from `MAX_UPLOAD_BYTES`, `max_audio_s`, `ai_max_seconds + ai_tolerance_seconds`, and one accepted-types table in `audio.py` that also feeds `sniff`.
Done when: tests pass for: endpoint values equal the constants/presets; response requires auth; a drift test fails if the served extension/MIME set differs from what `sniff` accepts.

## Task 6 — Validation failure = upload failure; keep data after validation
What it is / what it means: A bad file is an upload failure that leaves nothing behind; any later failure keeps the user's data. Traces to R8, R11, acceptance criteria 7 and 11.
What changes at a high level: In `validate.py`, file-check codes (`audio_unreadable`, `audio_too_large`, `unsupported_audio`, `audio_too_long`, `interview_too_long`; confirm with `rg 'fail\(ctx, "'`) call a new repo method `discard_failed_upload(uid, sid, code)`: purge staged/stored audio (`purge()` stays, narrowed to this case, docstring updated), delete the session doc and its recordings/runs, write a data-free status stub (`state=upload_failed`, `error_code`, `updated_at`, `expire_at` +7 days). Add the Firestore TTL policy in Terraform, or fall back to the stale sweep for stubs older than 7 days. `GET /sessions/{id}` on a discarded id is 404; the list omits it. Transcribe, run, transient validate and mismatch failures delete nothing.
Done when: tests pass for: each file-check code removes session doc, subcollections and blobs, leaves usage unchanged, is absent from `listSessions`, 404s on get, and leaves a stub with no user data; a validated upload that later fails transcription keeps blobs, transcript and run docs (no `delete_prefix`); successful validation still removes the staged object; Delete still sweeps everything; stub expiry (TTL or sweep) verified.

## Task 7 — Interview audio mismatch = our error
What it is / what it means: A relay/upload duration mismatch beyond a lenient threshold stops the session as our fault, never charged. Traces to R9, acceptance criterion 9; coordinates with SP02 Task 7.
What changes at a high level: Add `AI_MISMATCH_MIN_SECONDS=60` and `AI_MISMATCH_PCT=15` settings (config plus the environment Terraform variables beside `AI_TOLERANCE_SECONDS`); `ai_tolerance_seconds` keeps only the interview-ceiling job. In `validate`, after file checks and before the recording doc, compute `max(min, pct of relay_s)`; within it proceed free; beyond it raise `PermanentError("internal_error")` (kind permanent_internal, `counted=false`, no retry, data kept). Unknown relay duration or missing interview doc proceeds. Replace the old `free_run_void` write and `_matches_relay`. Call SP02's existing `interview_audio_check` helper with the threshold and result; do not add a second log line.
Done when: tests pass for: relay 600 s with upload 689 s proceeds (`ok`), 691 s stops as `internal_error`/permanent_internal with usage unchanged and data kept; relay 180 s tolerates 60 s; unknown relay duration and missing interview doc proceed; each case emits exactly one `interview_audio_check`.

## Task 8 — Web failure cards, copy, countdown retry
What it is / what it means: The user sees the right message and action for each kind, driven by the server's kind. Traces to D2, D7, R6, acceptance criterion 5.
What changes at a high level: In `errors.ts` add copy for `output_invalid`, `deadline_exceeded`, `run_failed` (internal copy). Replace `failureAction(code, transcriptReady)` with `failureView(doc)` reading `error_kind`, `retries_left`, `counted` (unknown code and no kind gives permanent_internal copy; no hardcoded code sets). New `RetryButton.tsx`: client-only 5 s countdown from mount, `Retry (5)...(1)` then `Retry`, `aria-disabled` while counting, calls `retrySession`. `SessionPage.tsx` renders the four card variants per the R6 table, each with `Reference: <session id>`; "counted" sentence only when `counted=true`.
Done when: web tests pass for: copy per kind; countdown disabled then enabled after 5 s (fake timers) and resets only on remount; new-session CTA at `retries_left=0`; no Retry for permanent_internal; Reference shown on all cards; counted sentence only when `counted=true`; unknown code falls back to internal copy.

## Task 9 — Web pre-checks from served limits; UploadFailedView
What it is / what it means: Browser checks use the server's numbers, and an upload failure has its own screen. Traces to R10 (web half), R11 (web), acceptance criteria 10 and 11.
What changes at a high level: New `useUploadLimits.ts` (react-query, long `staleTime`) feeds `checkFile(file, duration, limits)` in `precheck.ts`; delete the numeric constants and type sets there and build messages from served values. Block on too large, wrong type, over max duration; warn under the short threshold; fail open when limits are unavailable or duration unreadable. New `UploadFailedView.tsx`: "Upload failed: <reason>. Choose a different file." with button to `/sessions/new` and Reference line, shown when status is `upload_failed`; on a stale-link 404 show it if the stub exists, else the not-found notice. Never listed.
Done when: web tests pass for: `checkFile` has no literals and blocks/warns per served limits; skips on missing limits and unreadable duration; `UploadFailedView` shows reason text from existing per-code copy, the way back, and the Reference; stale link with stub shows the same view, without stub shows the not-found notice.

## Task 10 — Contracts regen, mocks, docs
What it is / what it means: Generated contracts, mocks and docs match the new API. Traces to R7, acceptance criterion 6.
What changes at a high level: Regenerate `api/openapi.json`, `docs/contracts/public`, `web/src/api/schema.d.ts` last (SP07 also regenerates; last merged wins). Update `web/src/mocks/*` for the retry route, upload-limits, new status fields and `upload_failed`. Add kind/retry columns to the `docs/reference/public-api.md` error table and link `logging.md`'s error_code table (SP02) to it.
Done when: contract drift check passes with the three artifacts consistent; mocks cover each card kind and the upload-limits response; the docs table lists every code with kind and retryability (a check asserts every `KIND_BY_CODE` code appears).

## Owner steps
- Staging forced-failure run (AC4): force a 404 model (expect "our side" card, no Retry, usage unchanged) and a 503 (expect countdown, 3 retries, then new-session CTA); also verify a real bad-audio STT case classifies as user_file (resolved default).
- Terraform apply for the new `AI_MISMATCH_*` variables and the Firestore TTL policy on `expire_at` (if TTL is unavailable in the module, the stale sweep is the fallback).
- Revisit 529/400 ambiguity from SP02 logs later (resolved default: 529 transient, 400 permanent).
