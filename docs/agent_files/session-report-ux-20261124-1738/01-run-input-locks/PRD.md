---
status: draft
summary: Lock clinician speaker and change goal once chosen, copy every run input onto RunDoc inside the start transactions, make the worker read only RunDoc and refuse a transcript whose sha256 changed (one new error code).
date: 2026-11-24
---
# PRD: SP01 Run input locks + run-owned inputs

Repo/branch: Onolys/iaudit / `session-report-ux` · Depends on: none (lands first; must not change engine output) · Owns: `api/src/onolys_api/{routes/speakers.py, routes/rating.py, routes/runs.py (retry copy), jobs/run.py (_evaluate input read), jobs/transcribe.py (hash at write), repo/{models.py, base.py, firestore.py, fake.py}, adapters/error_map.py}`, `web/src/features/{speakers/SpeakerGate.tsx, session/slots.tsx, session/SessionPage.tsx}`, `web/src/api/errors.ts`, `docs/reference/public-api.md`, regen `api/openapi.json`, `docs/contracts/public`, `web/src/api/schema.d.ts` · Shared with SP02: `jobs/run.py` `_evaluate` params block only (SP01 changes where values come from, not which values).

## TL;DR
The worker reads goal, speaker, language and STT live from the session [verified: `jobs/run.py:148-164`], so a run is not tied to the inputs it started with. This SP (1) makes speaker and goal write-once, (2) snapshots all inputs onto `RunDoc` in the start transaction, (3) makes the worker read only `RunDoc` and check the transcript sha256 before any model call. Backend-only; no API/UI exposure of the snapshot.

## Problem
| Input | Gap today | Evidence |
|---|---|---|
| change_goal | Final rating can be submitted while a run is `running`/`failed` (`start_run` does not require `rating_submitted`); worker reads the goal live | [verified: `routes/rating.py` `_not_final` checks only `rating_submitted`/report; `firestore.py:1173-1179`; `run.py:155`] |
| clinician_speaker | Re-selectable in `failed` | [verified: `speakers.py:27` `CONFIRM_STATES=("awaiting_input","failed")`] |
| transcript | No hash; `put_transcript` overwrites in place | [verified: `models.py:265-268`, `firestore.py:652`] |
| language, stt | Read live from session/transcript; `RunDoc.stt` exists but unused by worker | [verified: `run.py:157-161`, `models.py:298-322`] |
Transcript/language/STT cannot change after a run starts today (transcript PUT only from `created`; transcribe retry only with no run) [verified per eval-run-inputs.md]; the hash and snapshot defend future change and make a run self-describing.

## Goals / Non-Goals
**Goals:** once selected, selected (speaker, goal); a run executes on exactly the inputs copied at its start; a changed transcript fails before any LLM call; no change to quota, retry cap, or engine output.
**Non-goals:** exposing inputs in API/UI; `rating_id` pinning; lineage/previous-run reference; requested-vs-actual settings; failure taxonomy beyond one code; claiming reproducibility (same pinned inputs != identical LLM output; seed = session id); legacy/migration handling; engine fixes (SP02).

## Requirements
**R1 Speaker lock.** `CONFIRM_STATES = ("awaiting_input",)`. `repo.confirm_speaker` txn also returns False when `speaker_confirmed` is already true (any state, same or different speaker) -> 409 `invalid_state`. Update the module/route docstrings (`speakers.py:1-8`, description at ~L100). Failed runs no longer allow a speaker fix; the user starts a new session.
**R2 Goal lock.** A final rating is refused with 409 `rating_final` when `first_run_id` is set (guard in the txn `_not_final` and the early check in `put_rating`). Drafts remain allowed (never read by the worker). `change_goal` is still written once, by final submit.
**R3 RunDoc snapshot (required fields).** Add to `RunDoc`: `change_goal: str`, `clinician_speaker: str`, `language: str` (effective: transcript language else session language, resolved in-txn from the transcript doc's language or stored session value), `transcript_sha256: str`. Existing: `stt`, `coded_span`, `preset`, `n_runs`, `code_version` (already copied). `rating_id` unchanged/unused. Populated inside `start_first_run` and `start_run` (firestore + fake) from the session doc already read in the txn; `start_run` gets `change_goal` coerced to `""` when no rating (run without rating stays allowed, goal then locked empty by R2).
**R4 Transcript hash.** `TranscriptDoc.sha256: str` computed once in `put_transcript` (firestore + fake) over canonical JSON (`json.dumps(transcript.model_dump(mode="json"), sort_keys=True, separators=(",",":"), ensure_ascii=False)`, utf-8) from the object already in memory. One helper `transcript_sha256(transcript)` in `repo/models.py` (or `repo/large.py`) used by both repos and the worker. The start txns read `transcripts/current` (one extra doc read in the txn) and copy `sha256`; start returns `not_ready` if the transcript doc is missing.
**R5 Worker reads RunDoc only.** `_evaluate` takes goal, speaker, language, stt_run from `run_doc`, never `session` (session is still read for `deleting`/`cancelled` and title). Before any adapter/model call: recompute sha256 of the loaded transcript; mismatch -> `PermanentError("run_input_mismatch")`. Automatic worker retry/redelivery reuses the same run doc, so inputs are pinned for free.
**R6 Error code.** `run_input_mismatch`, kind permanent_internal: add to `KIND_BY_CODE`, `MESSAGES` (error_map), `web/src/api/errors.ts` (internal-error copy), error enum in `errors.py`/openapi/public-api.md table. Replaces the `internal_error` raise at `run.py:150-153` for missing transcript only where it is an input-integrity failure; speaker-None check goes away (required field).
**R7 Retry.** `begin_run` retry (`runs.py:172-178`) keeps copying preset/n_runs/span from the failed run; goal/speaker/language/hash come from the session snapshot in `start_run` (identical to the failed run by R1/R2/transcript immutability). Add an in-txn assertion: if the session transcript sha256 differs from the failed run's, return `not_ready` (cannot happen today; guards future re-transcription). New run id; failed run kept; only the new run's success publishes the report. Cap/quota/`retry_count` logic untouched.
**R8 Web (minimal).** `slots.tsx`/`SessionPage.tsx`: show the speaker gate only for `transcript_ready && !speaker_confirmed && state==="awaiting_input"`; delete the `rerun` mode, "Change who the clinician is" link and post-save `/retry` call in `SpeakerGate.tsx`. Rating card `readOnly` also when state is `running`, `failed` or `report_ready` (UI is slightly stricter than backend R2, which keys on `first_run_id`; a pre-run failed session can resubmit after its retry re-enters `awaiting_input`). Card copy already says "final".
**R9 Fake parity.** Every repo change above is mirrored in `repo/fake.py`; parity test pins both.

## Architecture
```
confirm speaker --(txn: not yet confirmed)--> session.clinician_speaker  [write-once]
final rating   --(txn: no first_run_id)-----> session.change_goal        [write-once]
put_transcript --> TranscriptDoc{sha256}                                  [computed once]
start_first_run/start_run (ONE txn) reads session + transcript doc
   --> RunDoc{goal, speaker, language, stt, span, preset, n_runs, code_version, transcript_sha256}
worker: run_doc inputs only; load transcript; sha256 == run_doc.transcript_sha256 else run_input_mismatch; then adapter
publish_report: unchanged single txn
```
- Retry flows: auto retry = same run id, same RunDoc. User Retry = `begin_run(retry_max)` -> new run id, copies from session (== failed run).
- Earlier-step retry (`retry_session` for validate/transcribe, `sessions.py:474-504`): only reachable with no run (step must be validate/transcribe; a failed run sets step `run`) [verified: `sessions.py:482-486`]. It re-writes the transcript before any run exists, so the hash is fresh at the next start; speaker/goal cannot be set yet (transcript not ready). No change needed.
- Cancel/delete: unchanged; RunDoc is a session child, no new collections [verified: only `runs` subcollection touched]. `ensure_active` checks still precede model calls.
- Firestore rules: clients read-only on `sessions` (`allow write: if false`) [verified: `firestore.rules:10-11`]; locks are server-side only, no rules change.
- Engine call args: same keys, values now from RunDoc (SP02 interface assumption holds).

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| 1 | Speaker lock | Write-once on first confirm; 409 on any re-confirm | Keep fix-after-failure; idempotent same-value | Owner: once selected is selected |
| 2 | Goal lock | Reject final rating once `first_run_id` set | Require `rating_submitted` to start a run | No product change to run-without-rating; closes the race |
| 3 | Snapshot location | Copy into RunDoc inside existing start txns | Worker snapshots at first read | Atomic with state check; no second step |
| 4 | RunDoc fields | Required, non-optional | Optional + "unknown" handling | Owner: no legacy; missing fields fail loudly |
| 5 | Hash basis | sha256 of canonical transcript JSON, at write, verified by recompute in worker | Blob bytes; compare stored hashes only | Data already in memory; recompute detects real replacement |
| 6 | Error code | One new `run_input_mismatch` (permanent_internal) | Reuse `internal_error` | Distinguishable in logs; one code only |
| 7 | Language | Effective language resolved at start | Store requested + actual | Skip requested-vs-actual |
| 8 | Retry source | Session snapshot + hash assertion | Copy everything from failed RunDoc | Identical by locks; guard covers future edit |
| 9 | Publish | Untouched single txn | Add "mark done" step | Brief |

## Manual steps
- Optional: wipe existing dev/staging data (Firestore `sessions` + children, `session_status`, `usage`; GCS blobs for those sessions). Not required; old docs missing the new required fields will fail loudly if loaded.
- Regenerate `api/openapi.json`, `docs/contracts/public`, `web/src/api/schema.d.ts` (error-code enum) after R6.

## Risks / Open Questions
| Item | Status |
|---|---|
| No legacy handling; existing DB entries may be deleted, hidden or error on load | [RESOLVED: owner; nobody uses the app yet, required RunDoc fields, no fallback/migration/compat read/"unknown" state] |
| Speaker re-selection blocked even after failure | [RESOLVED: owner] |
| Goal locked once first run starts | [RESOLVED: owner] |
| Successful report final; only failed runs retry; auto retry keeps run id; user Retry new run id | [RESOLVED: owner, existing policy] |
| Do not claim reproducibility | [RESOLVED: owner] |
| Inputs backend-only; no `rating_id` pin, lineage, requested-vs-actual, extra taxonomy | [RESOLVED: owner] |
| Failed session with transcript ready but speaker unconfirmed and no run: no way to confirm (state `failed`) | [RESOLVED: owner — failure is terminal; a session that fails before speaker confirmation stays failed, no confirm after failure, no recovery path] |
| Start txn adds one transcript doc read; transcript pointer docs hold sha256 in the doc, not the blob | [RESOLVED: acceptable] |
| Re-transcription / transcript editing | [DEFERRED: hash + R7 guard cover it when built] |
| Worker recompute cost on large (blob) transcripts | [RESOLVED: transcript already loaded in `_evaluate`; hashing is O(size), negligible vs LLM] |

## Acceptance Criteria
1. Second `POST /speakers/confirm` (any state, same or different speaker) -> 409; `failed` state confirm -> 409.
2. Final rating after run start (`running`, `failed`) -> 409 `rating_final`; session `change_goal` unchanged; drafts still saved.
3. `start_first_run` and `start_run` create a RunDoc with goal, speaker, language, stt, span, preset, n_runs, code_version, transcript_sha256 (firestore emulator + fake parity test).
4. Worker uses RunDoc values when the session doc is tampered after start (goal/speaker/language/stt changed in session -> adapter params still the originals).
5. Transcript replaced/altered after start -> run fails `run_input_mismatch` before any adapter call (assert adapter not called); code maps to permanent_internal and has web copy.
6. Worker redelivery keeps the same run id and snapshot; `publish_report` still one txn.
7. User Retry after failure -> new run id, same inputs, failed run kept; retry cap, quota refund and `retry_count` tests unchanged and green.
8. Transcript sha256 set on both PUT (`routes/transcript.py`) and STT (`jobs/transcribe.py:267`) paths, stable for equal content.
9. Web: speaker gate absent after confirmation and in `failed`; rating card read-only in running/failed/report_ready; existing SpeakerGate/RatingCard/SessionPage tests updated (rerun mode tests removed).
10. Engine output for fixture runs byte-identical before/after SP01.
