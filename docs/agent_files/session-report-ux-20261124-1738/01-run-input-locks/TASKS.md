---
status: draft
summary: 7 tasks - transcript hash/language factory, speaker lock, goal lock, RunDoc snapshot + retry guard, worker reads RunDoc only, web gate/rating read-only, no-exposure and engine-output guards.
date: 2026-11-24
---
# Tasks: SP01 Run input locks + run-owned inputs
Source of truth: docs/agent_files/session-report-ux-20261124-1738/01-run-input-locks/PRD.md. All PRD Open Questions are RESOLVED (none OPEN). Backend-only change plus minimal web; no public API/openapi/error-code change, no legacy handling. Lands before SP02 (engines/miti only). CI already exists and runs api (non-firestore + emulator), web and engine tests on push/PR, so no CI task. Tests use no live LLM; each task also updates the fake repo (R9) and keeps the suite green.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | TranscriptDoc factory: sha256 + language | - | done |
| 2 | Speaker write-once lock | - | done |
| 3 | Goal lock after first run | - | done |
| 4 | RunDoc snapshot in start txns + retry guard | 1 | done |
| 5 | Worker reads RunDoc only, hash check | 4 | done |
| 6 | Web: speaker gate and rating card read-only | 2, 3 | done |
| 7 | No-exposure and engine-output guards | 5 | done |

## Task 1 — TranscriptDoc factory: sha256 + language
What it is / what it means: Every stored transcript carries a content hash and its effective language, computed once in one place. Traces to R4, D5, D7, D10, AC 8, 9.
What changes at a high level: `TranscriptDoc` gains required `sha256` and `language`. Add `transcript_sha256()` (canonical JSON, sha256) and the single `TranscriptDoc.build(transcript, pointer, session_language)` in `repo/models.py`; language is `transcript.language or session_language`. The upload route `_persist` and `put_transcript` (STT path; firestore + fake) both create docs only through it. Existing direct constructions and fixtures move to the factory.
Done when: tests pass showing sha256 and language are set after the upload endpoint and after the STT path, are stable for equal content, and recompute equal to the stored value for an inline and a blob/pointer (> `MAX_INLINE_BYTES`) transcript; language follows the old rule incl. session `auto`; fake/Firestore parity holds.

## Task 2 — Speaker write-once lock
What it is / what it means: Once a clinician speaker is chosen it cannot change, and failure is terminal. Traces to R1, D1, AC 1.
What changes at a high level: `CONFIRM_STATES` becomes `("awaiting_input",)` in `routes/speakers.py`. `repo.confirm_speaker` returns a tri-state (written/same/conflict) in firestore and fake: same speaker is an idempotent 202 with no write (route still calls `maybe_start_first_run`); a different speaker is 409 `invalid_state`; state `failed` is 409 first, even for the same speaker. Update the module and route docstrings.
Done when: route and repo tests pass for: first confirm writes; same-speaker re-confirm gives 202, no write, start attempted; different speaker 409; `failed` 409 even for the same speaker; fake parity test pins both repos.

## Task 3 — Goal lock after first run
What it is / what it means: The change goal can no longer be finalized once a run exists. Traces to R2, D2, AC 2.
What changes at a high level: A final rating is refused with 409 `rating_final` when `first_run_id` is set, in both the txn `_not_final` guard and the early check in `put_rating` (firestore + fake). Drafts stay allowed; `change_goal` is still written once, by final submit.
Done when: tests pass for: final rating while `running` and `failed` after run start gives 409 `rating_final` with `change_goal` unchanged; drafts still save; final rating before any run still works; fake parity.

## Task 4 — RunDoc snapshot in start txns + retry guard
What it is / what it means: A run copies its inputs at start, atomically, so it is self-describing. Traces to R3, R7, R9, D3, D4, D8, AC 3, 7, 10.
What changes at a high level: `RunDoc` gains required `change_goal`, `clinician_speaker`, `language`, `transcript_sha256`. `start_first_run` and `start_run` (firestore + fake) read the transcript doc in the txn and copy goal, speaker, language and hash; both return `not_ready` when speaker or transcript doc is missing; `start_run` coerces a missing rating goal to `""`. `start_run` also returns `not_ready` if the first run doc's hash differs from the transcript doc's (no extra read). `begin_run` retry keeps copying preset/n_runs/span. Test fixtures building `RunDoc` are updated.
Done when: tests pass (emulator + fake parity) for: all snapshot fields populated by both txns; `not_ready` on missing speaker, missing transcript, and hash mismatch; RunDoc language equals `transcript.language or session.language` incl. `auto` and pointer transcripts; user retry gives a new run id, same inputs, failed run kept; retry cap, quota refund and `retry_count` tests unchanged and green.

## Task 5 — Worker reads RunDoc only, hash check
What it is / what it means: The worker executes on exactly the inputs the run started with and refuses a changed transcript. Traces to R5, R6, D6, AC 4, 5, 6.
What changes at a high level: `_evaluate` in `jobs/run.py` takes goal, speaker, language and stt from `run_doc`; `session` is read only for deleting/cancelled and title. Before any adapter call it recomputes the transcript sha256 and raises `PermanentError("internal_error")` with log `reason=run_input_mismatch` (run/session ids, no content) on: missing transcript doc/body, hash mismatch, or any empty required RunDoc input. No new code in `KIND_BY_CODE`, errors, openapi or web.
Done when: worker tests pass for: tampering goal/speaker/language/stt on the session after start leaves adapter params at the originals; altered transcript, missing transcript, and each missing RunDoc field fail with `internal_error` and the log reason, with the adapter asserted not called; redelivery keeps the same run id and snapshot; `publish_report` still one txn; grep shows no new public code.

## Task 6 — Web: speaker gate and rating card read-only
What it is / what it means: The UI stops offering changes the backend now refuses. Traces to R8, AC 12.
What changes at a high level: `slots.tsx`/`SessionPage.tsx` show the speaker gate only for `transcript_ready && !speaker_confirmed && state==="awaiting_input"`. Remove the `rerun` mode, the "Change who the clinician is" link and the post-save `/retry` call from `SpeakerGate.tsx`. The rating card is `readOnly` also in `running`, `failed` and `report_ready`.
Done when: web tests pass for: no gate after confirmation or in `failed`; rating card read-only in running/failed/report_ready; rerun-mode tests removed and remaining SpeakerGate/RatingCard/SessionPage tests updated; `npm test`, typecheck and lint clean.

## Task 7 — No-exposure and engine-output guards
What it is / what it means: Proof that the snapshot stays private and engine behavior is unchanged. Traces to R3 (non-goals), AC 11, 13.
What changes at a high level: Tests only. Assert `RunView` and `GET /runs` do not expose `change_goal`, `clinician_speaker`, language or hash. Add a fixture-run comparison that engine adapter output is byte-identical to the pre-SP01 baseline (recorded fixtures, no live LLM).
Done when: both tests pass, and the contract drift check (`openapi.json`, `docs/contracts/public`) shows no diff.

## Owner steps
- Optional: wipe dev/staging data (Firestore `sessions` + children, `session_status`, `usage`; related GCS blobs). Old docs lacking the new required fields fail loudly if loaded.
- No openapi/contract regeneration needed.
