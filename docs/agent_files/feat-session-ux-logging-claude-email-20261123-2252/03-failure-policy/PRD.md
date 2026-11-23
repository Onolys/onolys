---
status: draft
summary: Classify every failure as transient / permanent_internal / user_file at one site (error_map), persist kind + retry_count on the session, one capped (3) retry endpoint that re-enters the failed step, refund every non-user failure, web copy + 5 s countdown retry button per kind.
date: 2026-11-23
---
# PRD: SP03 Failure policy + retry

Repo/branch: Onolys/onolys (local `iaudit`) / `feat/session-ux-logging-claude-email` · Depends on: SP01, SP02 (Phase 2) · Owns: `api/src/onolys_api/adapters/error_map.py`, `api/.../jobs/{charging.py (new), worker.py (_fail), run.py (refund call), machine.py (TRANSITIONS, BAD_FILE_CODES removal), stale.py (kind on write)}`, `api/.../routes/{runs.py, sessions.py (new retry route + fields)}`, `api/.../repo/{models.py (fields), firestore.py, fake.py (release/retry txn)}`, `api/.../config.py` (`MAX_SESSION_RETRIES`), `engines/core/src/onolys_engine_core/llm/errors.py` (`is_transient`), `web/src/api/errors.ts`, `web/src/features/session/{SessionPage.tsx, RetryButton.tsx (new)}`, `web/src/mocks/*`, `docs/reference/public-api.md` error table · Shared regen: `api/openapi.json`, `docs/contracts/public`, `web/src/api/schema.d.ts` (SP07 also regenerates; run last-merged wins)

## TL;DR
Today every provider failure, including "model not found", maps to retryable `upstream_unavailable` [verified: `error_map._classify_llm` returns `(UPSTREAM, True)` for any `LLMError`; `docs/reference/staging-e2e.md:105-115`], and "Try again" exists only for the run step: a validate or transcribe failure forces a new upload [verified: `SessionPage.tsx:203`, `failureAction`]. This SP adds a three-way kind, a capped retry at every step, makes the limit rule "only a user/file fault is ever counted", and (owner rule) makes failures non-destructive: a failed step never deletes the user's blobs or docs, so a retry (and a future "retry with existing upload") reuses them.

## Problem
- No distinction between a blip and a broken config: the user is told to retry something that cannot succeed (anti-goal in the brief).
- Retry is unlimited and run-only (`start_run` on `failed`, no counter) [verified: `routes/runs.py:163`].
- Kind is implicit: `BAD_FILE_CODES` frozenset + `is_system_failure(code)` in `machine.py`; `error_map` returns `(code, retryable)` only; web re-derives from its own `UPLOAD_NEW` set. Three lists, one meaning.
- Second transient STT failure becomes `transcription_failed` ("Upload a different file") though the file is fine [verified: `error_map.to_public`, `stage="stt"` attempt>=2].
- Web has no copy for `output_invalid`, `deadline_exceeded`, `run_failed`; they fall to the generic message [verified: `errors.ts` MESSAGES].

## Goals / Non-Goals
**Goals:** one classifier; persisted kind; retry cap 3 per session enforced server-side; no unit lost to our faults; failures never delete user data (R8); copy and countdown per the locked table; reusable helpers for SP04/SP06.
**Non-goals:** logging fields (SP02); cancel state and charge-on-cancel (SP04); processing-screen layout (SP05); silent worker/LiteLLM retries (unchanged, `MAX_ATTEMPTS=2`); changing STT/LLM providers.

## Requirements
**R1 Taxonomy** (`error_map.classify(exc, stage) -> Failure(code, kind)`; `to_public` stays as a thin wrapper so the 3 callers and `test_error_map.py` keep working).
| Source | kind | public code |
|---|---|---|
| `LLMTimeout`, `LLMRateLimited`, `LLMError` with `http_status` 408/429/500/502/503/504/529 or no status + connection/timeout `error_type`; Google 5xx/429/deadline (`_GOOGLE_TRANSIENT`); `TimeoutError`; AdapterError `upstream_unavailable`/`deadline_exceeded`/`rate_limited` | transient | `upstream_unavailable` / `deadline_exceeded` / `rate_limited` |
| `LLMError` with 400/401/403/404 (model not found, auth, bad request), `FixtureMiss`, `LLMBadOutput` after engine retries, `OutputInvalid`, `AllRunsFailed`/`CodePassFailed`/`GlobalsPassFailed` whose cause is not transient, Google `PermissionDenied`/`Unauthenticated`/`NotFound`/`FailedPrecondition`, unknown exception, AdapterError with unknown code | permanent_internal | `internal_error` |
| `InputError` (`invalid_coded_span`, `session_too_long`, `invalid_parameters`), `no_speech`, `speakers_not_separated`, `transcription_failed` (Google `InvalidArgument`/`SttProviderError` non-transient), validate codes (`unsupported_audio`, `audio_too_long`, `audio_too_large`, `audio_unreadable`, `interview_too_long`) | user_file | existing codes |
Classification reads SP02's `LLMError.http_status`/`error_type` (SP02 R9); it never parses `provider_error`. Chained causes keep today's `_llm_cause` walk. Applies to stage `validate`, `stt`, `run` alike (validate reads GCS/Firestore: transient Google errors already retry).
**R2 Reusable predicate.** `onolys_engine_core.llm.errors.is_transient(exc) -> bool` holds the LLM half of R1 (status/type rules); `error_map` calls it. SP06 (eval) imports it for per-unit retry instead of re-deriving.
**R3 Persisted fields.** `SessionError` gains `kind: Literal["transient","permanent_internal","user_file"]` and `counted: bool | None`; `SessionDoc` gains `retry_count: int = 0`. `SessionStatusDoc` (client-readable) gains `error_kind`, `retries_left`, `counted`. A single `KIND_BY_CODE` table in `error_map` fills `kind` at every write site (`worker._fail`, `runs._compensate` path, `stale.py`); `BAD_FILE_CODES`/`is_system_failure` are deleted and call sites use it. Old failed docs without `kind` read as derived-from-code.
**R4 Retry endpoint.** `POST /sessions/{id}/retry` (opId `retrySession`), 202. Allowed only when `state=failed`, `error.kind=transient`, `retry_count < MAX_SESSION_RETRIES` (3, setting), rating not final; else 409 `invalid_state`. One repo transaction increments `retry_count` and moves state, so the cap cannot be raced. Re-entry by `error.step`:
| failed step | transition | action |
|---|---|---|
| validate | `failed -> validating` | enqueue `validate`; staged/original audio still exists (failures never purge, R8; the staged `uploads/` copy expires after 1 day by bucket lifecycle, see R8); if gone → 409 |
| transcribe | `failed -> transcribing` | reset `steps.transcribe` (pending, attempts 0, no `stt_operation`), enqueue `transcribe` |
| run | `failed -> running` | existing `start_run` logic (same preset/n_runs/span as the failed run), new run id, new unit reserved |
`TRANSITIONS["failed"]` gains `validating`, `transcribing`. `POST /runs` on a `failed` session returns 409 so there is one retry path and one counter. Silent worker retry (`MAX_ATTEMPTS=2`) stays inside one user-visible attempt and does not touch `retry_count`.
**R5 Limit accounting** (new `jobs/charging.py`; `_refund` moves here).
- A unit is reserved only at run start (`start_run`/`start_first_run`, one txn with the day count and `active_runs`); validate/transcribe never charge [verified: `repo/firestore.py` start_*; `caps.py` docstring]. So "reverse at rating step" = refund at run end, which already exists via `release_run_slot` (idempotent: `released` flag set in the same txn) [verified: `firestore.py:699`].
- New rule `should_refund(kind, llm_started) -> bool`: `transient` and `permanent_internal` → always refund; `user_file` → refund only if `llm_started` is False (today's rule). This replaces `is_system_failure`, so an `output_invalid`/`internal_error` is refunded as before, and a model-not-found no longer looks like a retryable blip.
- `release_once(repo, uid, sid, run_id, refund, date)` and `should_refund` are the public helpers SP04 reuses; `release_run_slot` returns whether a unit was kept, which `worker._fail` writes to `SessionError.counted`.
- Interview-linked sessions (owner 2026-11-23): an AI interview includes its evaluation, and that evaluation never consumes the user's evaluation limit. Existing code already treats a session with `interview_id` and not `free_run_void` as exempt (`exempt` in `repo/{fake,firestore}.py` `start_first_run`: no day count, `counted=false`); SP03 keeps that and `should_refund` never refunds an uncounted run. A `free_run_void` session (uploaded audio did not match the relay recording, `validate.py` A10) is a normal evaluation and counts as today. Same rule as SP04 R4. so the retry reserves normally (cap check applies; at cap the user sees today's `daily_cap_reached` text, except `free_run` sessions, unchanged). `counted=False` and `units` semantics on the run doc stay.
- Ordering: refund happens in `run.py` before `worker._fail`; `counted` is read from the released run doc there.
**R6 Web.** Copy lives in `errors.ts` (`MESSAGES`, add `output_invalid`, `deadline_exceeded`, `run_failed`→internal copy). `failureAction(code, transcriptReady)` is replaced by `failureView(doc)` reading `error_kind`, `retries_left`, `counted` from the status doc (no hardcoded code sets; unknown code + no kind → permanent_internal copy).
| kind | card |
|---|---|
| transient, `retries_left>0` | message + "This did not count toward your limit." + `Retry (5)…(1)` then `Retry` |
| transient, `retries_left=0` | "We couldn't finish this after several tries. Start a new session." + CTA to `/sessions/new` |
| permanent_internal | "Something went wrong on our side. This did not count toward your limit. Please start a new session." + CTA |
| user_file | existing per-code text + "Upload a different file" (`/sessions/new?from=`); appends "This counted toward your limit." only when `counted=true` |
All cards show `Reference: <session id>` (existing `ErrorCard reference`). Countdown: client-side, 5 s from card mount, button disabled (`aria-disabled`, text `Retry (n)`), resets on remount only; the server does not enforce it (it is UX, the cap is the guard).
**R7 Docs.** `public-api.md` error table gets kind/retry columns; `logging.md` error_code table (SP02) links to it.

**R8 Failures never delete user data (owner rule 2026-11-23).** Only the explicit Delete action deletes (`jobs/delete.py` sweep, and `jobs/alive.py` `ensure_alive`'s sweep after a `deleting` mark, which is the Delete path and stays). Reason: a future "retry with existing upload" feature reuses stored audio and transcripts. Verified today (grep `delete_prefix`/`.delete(` over `api/src/onolys_api/jobs`): the only delete-on-failure path is `validate.py` `purge()` (lines 63-65: `uploads/{uid}/{sid}/` and `{uid}/{sid}/audio/`), called only from `fail()` (line 71); its docstring (line 7) says "A failure removes every object of the session's audio". `transcribe.py`, `run.py`, `worker.py`, `stale.py`, `interviews.py`, `interview_sweep.py` have no blob or doc deletes. Changes:
- Remove `purge()` and its call in `validate.fail()` (it only returns `PermanentError(code)`); fix the module docstring (a failure keeps the objects and records the public code).
- Validation, transcription and run failures keep every blob and doc (uploads, original, canonical, recording doc, transcript, run docs).
- Kept as is: staged-object cleanup after a SUCCESSFUL move (`validate.py:171-175`, `blobs.delete_prefix("uploads/{uid}/{sid}/")` for late PUTs and stale-URL strays) and `blobs.move` deleting its source. This is housekeeping of a duplicate after success, not user data; the audio is in `{uid}/{sid}/audio/`.
- Retention: the audio bucket (`infra/modules/environment/main.tf`) has one lifecycle rule: delete objects under `uploads/` after age 1 day; versioning off; soft delete retention 0. No rule on `{uid}/{sid}/audio/` or other prefixes. So a session that fails validation (audio still only in staged `uploads/`) loses that copy after 1 day by bucket TTL (not by code); everything past the move (`{uid}/{sid}/audio/`, transcripts, docs) persists until the user presses Delete. The "retry with existing upload" feature (future) must account for the 1-day `uploads/` TTL (or the move must happen before it); out of scope here.

## Architecture
```
exception -> error_map.classify() -> (code, kind)
   worker/_fail, stale, runs ──► SessionError{code,step,kind,counted} + status{error_kind,retries_left,counted}
run end: should_refund(kind, llm_started) -> release_once() -> counted
web: failureView(status) -> card | RetryButton(5s) -> POST /sessions/{id}/retry
retry: txn(retry_count+1, failed->step state) -> enqueue step | start_run
```
Interface: `classify(exc: BaseException, stage: Stage) -> Failure` ; `is_transient(exc: LLMError) -> bool` (engine-core, SP06 reuse).

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | permanent code | reuse `internal_error` | new `permanent_error` code | No enum change in 3 places; text already "our side" |
| D2 | kind source | server persists `kind`; web reads it | web re-derives from code sets | One table; fixes today's 3-list drift |
| D3 | retry endpoint | one `POST /sessions/{id}/retry` | extend `POST /runs` | Run-only; validate/transcribe need re-entry |
| D4 | cap counter | `SessionDoc.retry_count` in the retry txn | count failed runs | Covers steps with no run doc; race-safe |
| D5 | charge reversal | refund at run end via existing `release_once` | refund at rating submit | Charge only exists from run start; refund already idempotent |
| D6 | transient STT after 2nd failure | stays `upstream_unavailable` (user retries) | map to `transcription_failed` (today) | File is not at fault |
| D7 | countdown | client-only, 5 s from mount | server `retry_after` | Brief wants UI pacing; cap is the real guard |
| D8 | is_transient home | engine-core `llm/errors.py` | api-only | SP06 needs it; api already imports engine-core |

## Risks / Open Questions
- [RESOLVED: default — user_file; verify against a real bad-audio staging case (task note, see AC4 forced-failure run)] Google `InvalidArgument` on STT: user_file vs permanent_internal.
- [RESOLVED: default — 529 transient, 400 permanent; revisit later from SP02 logs] Provider statuses with ambiguous meaning (Anthropic 529 overloaded, Gemini 400 "model overloaded").
- [RESOLVED: aligned with SP04 — SP04 owns the pre-run cancel charge: pure `decide_cancel` in `repo/limits.py` (re-exported by `jobs/charging.py`), charged in the cancel txn via `usage.runs += units`, stored in `SessionDoc.cancel`; never refunded. It does not use `should_refund`/`release_once`, which stay run-end only. `counted` on the status doc is the one shared field (SP03 failures, SP04 cancel).]
- [RESOLVED: default — both (run doc is source, session copy for the UI)] `counted` on `SessionError` vs run doc only.
- [RESOLVED: no change] `AllRunsFailed` from a transient cause stays retryable via `_llm_cause`.
- [OPEN: owner question; default keep] Interview-linked sessions with `free_run_void` (uploaded audio does not match the interview recording) are charged as normal evaluations today (exempt = `interview_id` and not `free_run_void`). Keep?
- [OPEN: owner question; default move on failure] No-delete-on-failure (R8) vs bucket TTL: the `uploads/` prefix auto-deletes after 1 day [verified: `infra/modules/environment/main.tf`], so audio of a session that failed validation (still staged in `uploads/`) expires after 1 day. Options: keep the TTL (accept) / move failed uploads to `{uid}/{sid}/audio/` on failure so they persist until Delete.
- Risk: SP04/SP05 also edit `TRANSITIONS`, `SessionPage.tsx`, `errors.ts`; additive, rebase trivial. SP07 and this SP both regenerate the contracts.
- Risk: a retry that re-reserves can hit the day cap after we refunded; accepted, shown with today's text.

## Acceptance Criteria
1. `test_error_map.py` table test: every row of R1 (plus `LLMError` 404 → `internal_error`/permanent_internal, 503 → `upstream_unavailable`/transient) maps as specified, for stages validate/stt/run.
2. Retry cap test: 3 retries succeed in changing state, the 4th returns 409 and `retry_count` stays 3; two concurrent retries at count 2 yield one winner. Non-transient or non-failed → 409. Each step (validate, transcribe, run) re-enters the right state and enqueues the right task.
3. Charge tests: run failing with transient, permanent_internal → unit refunded, `counted=false`, released once under a double call; user_file with `llm_started` → kept, `counted=true`; without → refunded; first-free-run unchanged.
4. Staging: forcing a 404 model yields the "our side… start a new session" card with the session id and no Retry; forcing a 503 yields the countdown button, 3 retries then the new-session CTA; usage count unchanged after each.
5. Web tests: copy per kind, countdown `Retry (5)`→enabled after 5 s (fake timers), CTA shown at `retries_left=0`, Reference shown, "counted" sentence only when `counted=true`.
6. `is_transient` has unit tests and no api imports; `openapi.json`, `docs/contracts/public`, `schema.d.ts` regenerated and consistent.
7. Failed validation leaves the uploaded audio in place: a validate failure (e.g. `unsupported_audio`, `audio_too_long`) writes the error code and leaves the staged/original blobs and session docs intact (no `delete_prefix` call; fake `BlobStore` still lists the objects). Same for transcribe and run failures (blobs, transcript and run docs remain). Successful validation still removes the staged `uploads/` object after the move (existing test stays). Delete still sweeps everything.
8. Interview-linked session (`interview_id` set, not `free_run_void`): a failing or succeeding first run leaves `counted=false` and never changes usage counters; `free_run_void` session counts as a normal evaluation.
