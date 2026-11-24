---
status: draft
summary: Lock clinician speaker and change goal once chosen, copy every run input onto RunDoc inside the start transactions, make the worker read only RunDoc and refuse a transcript whose sha256 changed (no new public error code).
date: 2026-11-24
---
# PRD: SP01 Run input locks + run-owned inputs

Repo/branch: Onolys/iaudit / `session-report-ux` · Depends on: none (lands first; must not change engine output) · Owns: `api/src/onolys_api/{routes/speakers.py, routes/rating.py, routes/runs.py (retry copy), jobs/run.py (_evaluate input read), routes/transcript.py (use the factory), jobs/transcribe.py (use the factory), repo/{models.py, base.py, firestore.py, fake.py}}`, `web/src/features/{speakers/SpeakerGate.tsx, session/slots.tsx, session/SessionPage.tsx}` · No public API/openapi/error-enum change. SP02 owns only `engines/miti/**`.

## TL;DR
The worker reads goal, speaker, language and STT live from the session [verified: `jobs/run.py:148-164`], so a run is not tied to the inputs it started with. This SP (1) makes speaker and goal write-once, (2) snapshots all inputs onto `RunDoc` in the start transaction, (3) makes the worker read only `RunDoc` and check the transcript sha256 before any model call. Backend-only; no API/UI exposure of the snapshot, no new public error code.

## Problem
| Input | Gap today | Evidence |
|---|---|---|
| change_goal | Final rating can be submitted while a run is `running`/`failed` (`start_run` does not require `rating_submitted`); worker reads the goal live | [verified: `routes/rating.py` `_not_final` checks only `rating_submitted`/report; `firestore.py:1173-1179`; `run.py:155`] |
| clinician_speaker | Re-selectable in `failed` | [verified: `speakers.py:27` `CONFIRM_STATES=("awaiting_input","failed")`] |
| transcript | No hash; `put_transcript` overwrites in place; the upload route never calls it (builds `TranscriptDoc` itself) | [verified: `models.py:265-268`, `firestore.py:652`, `routes/transcript.py:69-81`] |
| language, stt | Read live from session/transcript (`transcript.language or session.language`; session default `auto`); `RunDoc.stt` exists but unused by worker | [verified: `run.py:157-161`, `models.py:298-322`] |
Transcript/language/STT cannot change after a run starts today (transcript PUT only from `created`; transcribe retry only with no run) [verified per eval-run-inputs.md]; the hash and snapshot defend future change and make a run self-describing.

## Goals / Non-Goals
**Goals:** once selected, selected (speaker, goal); a run executes on exactly the inputs copied at its start; a changed transcript fails before any LLM call; no change to quota, retry cap, or engine output.
**Non-goals:** exposing inputs in API/UI; `rating_id` pinning; lineage/previous-run reference; requested-vs-actual settings; failure taxonomy beyond one code; claiming reproducibility (same pinned inputs != identical LLM output; seed = session id); legacy/migration handling; engine fixes (SP02).

## Requirements
**R1 Speaker lock.** `CONFIRM_STATES = ("awaiting_input",)`. `repo.confirm_speaker` txn: if `speaker_confirmed` is already true with the SAME speaker -> idempotent success (202, no write, route still calls `maybe_start_first_run`, so a lost response/failed start after a committed confirm is recoverable by retry); with a DIFFERENT speaker -> 409 `invalid_state`. State `failed` -> 409 always (failure is terminal; the state check precedes idempotency). Repo returns a tri-state (`written`/`same`/`conflict`) or equivalent; fake mirrors it. Update the module/route docstrings (`speakers.py:1-8`, description at ~L100). Failed sessions no longer allow a speaker fix; the user starts a new session.
**R2 Goal lock.** A final rating is refused with 409 `rating_final` when `first_run_id` is set (guard in the txn `_not_final` and the early check in `put_rating`). Drafts remain allowed (never read by the worker). `change_goal` is still written once, by final submit.
**R3 RunDoc snapshot (required fields).** Add to `RunDoc`: `change_goal: str`, `clinician_speaker: str`, `language: str` (effective language, copied from `TranscriptDoc.language` per R4), `transcript_sha256: str` (copied from `TranscriptDoc.sha256`). Existing: `stt`, `coded_span`, `preset`, `n_runs`, `code_version` (already copied). `rating_id` unchanged/unused. Populated inside `start_first_run` and `start_run` (firestore + fake) from the session doc and the transcript doc read in the txn; both start txns also return `not_ready` when `clinician_speaker` is missing (as `start_run` does) and when the transcript doc is missing; `start_run` gets `change_goal` coerced to `""` when no rating (run without rating stays allowed, goal then locked empty by R2).
**R4 Transcript hash + language, one factory.** `TranscriptDoc` gains `sha256: str` and `language: str`. ONE factory `TranscriptDoc.build(transcript, pointer, session_language)` (in `repo/models.py`) is the only way a `TranscriptDoc` is created; it sets `sha256 = transcript_sha256(transcript)` over canonical JSON (`json.dumps(transcript.model_dump(mode="json"), sort_keys=True, separators=(",",":"), ensure_ascii=False)`, utf-8, from the object in memory, valid for inline and blob/pointer storage alike) and `language = transcript.language or session_language` (exactly the worker's current rule `run.py:157`; the upload route's `_session_language(...)` result is used where it applies). Both write paths use it: the upload route `routes/transcript.py:_persist` (replaces the direct `TranscriptDoc(...)` at L69) and `put_transcript` (STT, `jobs/transcribe.py:~267`; firestore + fake). `transcript_sha256()` also lives in `repo/models.py` and is reused by the worker. Language is stored on the doc at write time because it cannot be resolved in the start txn from a pointer doc (`transcript` is None there, `firestore.py:652-658`). The start txns read `transcripts/current` (one extra doc read) and copy `sha256` and `language`.
**R5 Worker reads RunDoc only.** `_evaluate` takes goal, speaker, language, stt_run from `run_doc`, never `session` (session is still read for `deleting`/`cancelled` and title). Before any adapter/model call: recompute sha256 of the loaded transcript; mismatch -> `PermanentError("internal_error")` with a structured log field `reason=run_input_mismatch` (see R6). Automatic worker retry/redelivery reuses the same run doc, so inputs are pinned for free.
**R6 Errors (no new public code).** `run_input_mismatch` is NOT added to `KIND_BY_CODE`, `MESSAGES`, `errors.py`, openapi, `public-api.md` or `web/src/api/errors.ts`: the path is unreachable under the locks and the owner never required a public code. Every input-integrity failure raises the existing `PermanentError("internal_error")` and logs `reason=run_input_mismatch` (plus run/session ids; never transcript content). Raise sites in `jobs/run.py:_evaluate`: (a) missing transcript doc/body (today `run.py:150-153`); (b) recomputed sha256 != `run_doc.transcript_sha256`; (c) any required RunDoc input field missing/empty (`clinician_speaker`, `language`, `transcript_sha256`; replaces the session speaker-None check). No openapi/contract regeneration.
**R7 Retry.** `begin_run` retry (`runs.py:172-178`) keeps copying preset/n_runs/span from the failed run; goal/speaker/language/hash come from the session snapshot in `start_run` (identical to the failed run by R1/R2/transcript immutability). Add an in-txn assertion in `start_run`: the txn already reads the first run doc (`sess["first_run_id"]`, `firestore.py:~1186`); if its `transcript_sha256` differs from the current `TranscriptDoc.sha256`, return `not_ready` (cannot happen today; guards future re-transcription). No extra read; the fake does the same. New run id; failed run kept; only the new run's success publishes the report. Cap/quota/`retry_count` logic untouched.
**R8 Web (minimal).** `slots.tsx`/`SessionPage.tsx`: show the speaker gate only for `transcript_ready && !speaker_confirmed && state==="awaiting_input"`; delete the `rerun` mode, "Change who the clinician is" link and post-save `/retry` call in `SpeakerGate.tsx`. Rating card `readOnly` also when state is `running`, `failed` or `report_ready` (UI is slightly stricter than backend R2, which keys on `first_run_id`; a pre-run failed session can resubmit after its retry re-enters `awaiting_input`). Card copy already says "final".
**R9 Fake parity.** Every repo change above is mirrored in `repo/fake.py`; parity test pins both.

## Architecture
```
confirm speaker --(txn: not yet confirmed)--> session.clinician_speaker  [write-once]
final rating   --(txn: no first_run_id)-----> session.change_goal        [write-once]
upload route + STT put_transcript --> TranscriptDoc.build(...) --> {sha256, language}  [one factory, computed once]
start_first_run/start_run (ONE txn) reads session + transcript doc (requires clinician_speaker + transcript)
   --> RunDoc{goal, speaker, language(from transcript doc), stt, span, preset, n_runs, code_version, transcript_sha256}
worker: run_doc inputs only; load transcript; sha256 == run_doc.transcript_sha256 else internal_error (log reason=run_input_mismatch); then adapter
publish_report: unchanged single txn
```
- Retry flows: auto retry = same run id, same RunDoc. User Retry = `begin_run(retry_max)` -> new run id, copies from session (== failed run).
- Earlier-step retry (`retry_session` for validate/transcribe, `sessions.py:474-504`): only reachable with no run (step must be validate/transcribe; a failed run sets step `run`) [verified: `sessions.py:482-486`]. It re-writes the transcript before any run exists, so the hash is fresh at the next start; speaker/goal cannot be set yet (transcript not ready). No change needed.
- Cancel/delete: unchanged; RunDoc is a session child, no new collections [verified: only `runs` subcollection touched]. `ensure_active` checks still precede model calls.
- Firestore rules: `sessions` has no client rule and falls under the catch-all deny (`allow read, write: if false`), so clients have no access [verified: `firestore.rules`, only `session_status` is client-readable]; locks are server-side only, no rules change.
- Engine call args: same keys, values now from RunDoc (SP02 interface assumption holds).

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| 1 | Speaker lock | Write-once; same-speaker re-confirm idempotent (202, re-calls `maybe_start_first_run`); different speaker or `failed` -> 409 | 409 on any re-confirm; keep fix-after-failure | Owner: once selected is selected; a lost response after commit must not strand the session |
| 2 | Goal lock | Reject final rating once `first_run_id` set | Require `rating_submitted` to start a run | No product change to run-without-rating; closes the race |
| 3 | Snapshot location | Copy into RunDoc inside existing start txns | Worker snapshots at first read | Atomic with state check; no second step |
| 4 | RunDoc fields | Required, non-optional | Optional + "unknown" handling | Owner: no legacy; missing fields fail loudly |
| 5 | Hash basis | sha256 of canonical transcript JSON, at write, verified by recompute in worker | Blob bytes; compare stored hashes only | Data already in memory; recompute detects real replacement |
| 6 | Error code | Existing `internal_error` + log `reason=run_input_mismatch` | New public `run_input_mismatch` code (errors/openapi/web copy) | Owner never required it; unreachable under locks; avoids public-surface churn |
| 7 | Language | Effective language stored on `TranscriptDoc` at write (same factory as sha256), copied at start | Resolve in start txn; store requested + actual | Pointer docs have no transcript body in-txn; behavior-neutral vs worker rule |
| 10 | Hash/language write | Single `TranscriptDoc.build` used by upload route and STT | Hash only in `put_transcript` | Upload route never calls `put_transcript` |
| 8 | Retry source | Session snapshot + hash assertion vs first run doc (already read in txn) | Copy everything from failed RunDoc | Identical by locks; guard covers future edit |
| 9 | Publish | Untouched single txn | Add "mark done" step | Brief |

## Manual steps
- Optional: wipe existing dev/staging data (Firestore `sessions` + children, `session_status`, `usage`; GCS blobs for those sessions). Not required; old docs missing the new required fields will fail loudly if loaded.
- No openapi/contract regeneration needed (no API surface change).

## Risks / Open Questions
| Item | Status |
|---|---|
| No legacy handling; existing DB entries may be deleted, hidden or error on load | [RESOLVED: owner; nobody uses the app yet, required RunDoc fields, no fallback/migration/compat read/"unknown" state] |
| Speaker re-selection blocked even after failure | [RESOLVED: owner; failed state -> 409] |
| Goal locked once first run starts | [RESOLVED: owner] |
| Successful report final; only failed runs retry; auto retry keeps run id; user Retry new run id | [RESOLVED: owner, existing policy] |
| Do not claim reproducibility | [RESOLVED: owner] |
| Inputs backend-only; no `rating_id` pin, lineage, requested-vs-actual, extra taxonomy | [RESOLVED: owner] |
| Failed session with transcript ready but speaker unconfirmed and no run: no way to confirm (state `failed`) | [RESOLVED: owner — failure is terminal; a session that fails before speaker confirmation stays failed, no confirm after failure, no recovery path] |
| Start txn adds one transcript doc read; transcript pointer docs hold sha256 in the doc, not the blob | [RESOLVED: acceptable] |
| Re-transcription / transcript editing | [DEFERRED: hash + R7 guard cover it when built] |
| Same-speaker re-confirm is accepted after commit (idempotent) | [RESOLVED: retry-safety; different speaker still 409] |
| Worker recompute cost on large (blob) transcripts | [RESOLVED: transcript already loaded in `_evaluate`; hashing is O(size), negligible vs LLM] |

## Acceptance Criteria
1. Confirm with a DIFFERENT speaker after confirmation -> 409; `failed` state confirm -> 409 (even same speaker). Same-speaker re-confirm -> 202, no write, `maybe_start_first_run` called (retry after a lost start/response recovers).
2. Final rating after run start (`running`, `failed`) -> 409 `rating_final`; session `change_goal` unchanged; drafts still saved.
3. `start_first_run` and `start_run` create a RunDoc with goal, speaker, language, stt, span, preset, n_runs, code_version, transcript_sha256 (firestore emulator + fake parity test). Both return `not_ready` when `clinician_speaker` or the transcript doc is missing.
4. Worker uses RunDoc values when the session doc is tampered after start (goal/speaker/language/stt changed in session -> adapter params still the originals).
5. Transcript replaced/altered after start -> run fails with `internal_error` and log `reason=run_input_mismatch` before any adapter call (assert adapter not called); no new code in `KIND_BY_CODE`/errors/openapi/web; same for missing transcript and missing RunDoc input fields.
6. Worker redelivery keeps the same run id and snapshot; `publish_report` still one txn.
7. User Retry after failure -> new run id, same inputs, failed run kept; start txn returns `not_ready` if the first run doc's hash differs from the transcript doc's; retry cap, quota refund and `retry_count` tests unchanged and green.
8. `TranscriptDoc.sha256` and `.language` are present after the upload endpoint (`routes/transcript.py`) AND after the STT path (`jobs/transcribe.py:~267`), stable for equal content.
9. Recomputed `transcript_sha256` equals the stored value for both an inline transcript and a blob/pointer transcript (> `MAX_INLINE_BYTES`).
10. RunDoc `language` equals what the worker used before (`transcript.language or session.language`), incl. session language `auto` and pointer transcripts (behavior-neutral).
11. `RunView` (`routes/runs.py:~116`) and `GET /runs` do not expose `change_goal` or `clinician_speaker` (nor the hash/language snapshot).
12. Web: speaker gate absent after confirmation and in `failed`; rating card read-only in running/failed/report_ready; existing SpeakerGate/RatingCard/SessionPage tests updated (rerun mode tests removed).
13. Engine output for fixture runs byte-identical before/after SP01.
