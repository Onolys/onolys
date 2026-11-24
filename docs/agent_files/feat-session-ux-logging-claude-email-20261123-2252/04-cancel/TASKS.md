---
status: draft
summary: 9 tasks - cancelled state + fields, decide_cancel rule, atomic cancel txn, cancel route + 409s, worker stop (ensure_active/backstop), logging, web dialog/chip/mock, web link + cancelled view, contract regen + docs + race tests.
date: 2026-11-23
---
# Tasks: SP04 Cancel
Source of truth: docs/agent_files/feat-session-ux-logging-claude-email-20261123-2252/04-cancel/PRD.md. All PRD Open Questions are RESOLVED or DEFERRED (none OPEN); Chirp LRO cancellation and Cloud Tasks queue cleanup are deferred and out of scope. Depends on SP03 landing first (`jobs/charging.py`, status `counted`, `TRANSITIONS`, `retry`) and SP02 (log context). No CI change needed (`.github/workflows/ci.yml` exists). Tests use FakeRepo and MSW, no live API.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Cancelled state and data fields | - | todo |
| 2 | decide_cancel charge rule | 1 | todo |
| 3 | Atomic cancel transaction in repos | 1, 2 | todo |
| 4 | Cancel route and 409 on other routes | 3 | todo |
| 5 | Workers stop on cancel | 1 | todo |
| 6 | Cancel logging | 4, 5 | todo |
| 7 | Web: ConfirmDialog, chip, errors, mock | 1 | todo |
| 8 | Web: CancelLink, CancelledView, SessionPage | 4, 7 | todo |
| 9 | Contract regen, public docs, race tests | 4, 5, 8 | todo |

## Task 1 — Cancelled state and data fields
What it is / what it means: The terminal `cancelled` state and the fields that remember its result, so every later piece shares one model. Traces to R1, R7, D1, D8.
What changes at a high level: Add `cancelled` to `SessionState` and `TRANSITIONS` (each of the seven in-progress states gains it; `cancelled` goes only to `deleting`; added to `_NOT_DELETING`). Add `SessionDoc.cancel {counted, units, at}`, reuse SP03's `SessionStatusDoc.counted` (add to `STATUS_FIELDS`), and add `cancelled` to the `SessionListItem.status` enum. No separate "cancel requested" marker.
Done when: unit tests pass for: each of the seven states may transition to `cancelled`; `report_ready`/`failed` may not; `cancelled -> deleting` allowed, anything else rejected; `cancelled` is in `_NOT_DELETING`; model round-trips with and without `cancel`/`counted`; `STATUS_FIELDS` includes `counted`.

## Task 2 — decide_cancel charge rule
What it is / what it means: One pure function that says how many units a cancel costs, so the rule is testable without a database. Traces to R4, D2, D6, interview-exempt resolution.
What changes at a high level: Add `decide_cancel` to `repo/limits.py` and re-export from `jobs/charging.py` (file created by SP03). Inputs: state, whether `stt_operation` is set, run reserved or not, `interview_id`. Output: units (0 or 1) and `counted`. Follows the R4 table: early states and transcribing without an operation cost 0; transcribing with an operation and `awaiting_input` cost 1; `running` adds 0 and reports the run's `counted`; interview-linked sessions cost 0 everywhere. Same exempt predicate as `start_first_run`. SP03 `release_once`/`should_refund` stay untouched.
Done when: table-driven unit tests cover every row of R4 including the exempt interview session at transcribing and `awaiting_input`, and unit is always 1 (never `n_runs`).

## Task 3 — Atomic cancel transaction in repos
What it is / what it means: The single operation that cancels a session, releases any run slot and records the charge, all or nothing. Traces to R3, D1, D2, D3, D5, D6, R7.
What changes at a high level: Add `Repo.cancel_session(uid, sid, date, defaults) -> CancelOutcome` to `base.py`, with Fake and Firestore implementations in one transaction over session, status, usage, user and the active run. Already `cancelled` returns the stored `counted`; a state outside the seven returns `invalid`. In `running`, mark the run `failed` with `error="cancelled"` and release its slot (`refund=False`) through one in-transaction helper factored out of `release_run_slot` and shared by both. Apply `decide_cancel`, increment `usage.runs` even past the cap, then set session `state/cancel` and status `state/counted/stage_started_at`. Nothing is deleted.
Done when: FakeRepo (and Firestore-emulator where the repo has such tests) cover: each state's outcome and charge; idempotent second call leaves usage unchanged; over-cap cancel increments; `running` cancel restores `active_runs` with no refund; run doc is `failed`/`cancelled` so `claim_run` answers duplicate; session blobs and docs intact after cancel; a later failing run end finds `released=true` and does no second release; cancelled session cannot start a run.

## Task 4 — Cancel route and 409 on other routes
What it is / what it means: The public endpoint, plus making every other write route refuse a cancelled session. Traces to R2, R6, R7, D6.
What changes at a high level: Add `POST /sessions/{id}/cancel` (opId `cancelSession`), 200 `{counted}`, owner-only via the existing `User` dependency; `deleting`, unknown or another user's session returns 404, `report_ready`/`failed` return 409 `invalid_state`, never 429, and `settle_if_stale` is not called first. Expose `cancel` and `counted` in the session list/detail responses. Make `PUT /rating`, `POST /speakers`, `POST /runs`, upload-URL, upload-complete and SP03 `retry` return 409 `invalid_state` on `cancelled`; if `TRANSITIONS` does not already cause the 409 for upload routes, add an explicit state check. Reads stay allowed.
Done when: API tests pass for the full state x cancel matrix (seven states 200, `report_ready`/`failed` 409, `deleting`/other user 404, second cancel 200 with same `counted` and unchanged usage), cancel at the cap succeeds, and rating, speakers, runs, upload-URL, upload-complete and retry on `cancelled` return 409 while transcript/audio/report reads still work.

## Task 5 — Workers stop on cancel
What it is / what it means: Background tasks stop quickly and quietly after a cancel, never writing `failed` over `cancelled`. Traces to R5, D4, D9.
What changes at a high level: Add `Cancelled` in `jobs/worker.py`. Replace `ensure_alive` with `alive.ensure_active` (keeps the deleting purge; raises `Cancelled` on `cancelled` and purges nothing). `TaskRunner.handle` catches `Cancelled` and answers 200 outcome `cancelled` with no failure record; its catch-all first re-reads the session and answers 200 `cancelled` if cancelled (covers `invalid_state` from `advance`). `_fail` and `stale.py` never overwrite `cancelled`. Apply the R5 handler table: first-line state checks in `validate`, `transcribe`, `transcribe_poll`; `ensure_active` after each blob write, after `stt.start`, before `put_transcript`/`advance`; in `run`, `progress_cb` calls it at stage boundaries (re-raising `Cancelled`) and a check runs before `put_report`. Queued tasks are not deleted; late results are discarded.
Done when: worker tests pass for: late-delivered validate, transcribe, poll and run no-op with 200 `cancelled`; cancel mid-validate, mid-poll (`put_transcript`/`advance` after cancel) and mid-run (late stage callback aborts, `report_ready` never set) leave the session `cancelled` with no `failed` write; `stale.py` ignores `cancelled`; a cancelled session keeps all blobs and transcripts; `deleting` behaviour unchanged.

## Task 6 — Cancel logging
What it is / what it means: Cancels are traceable by session id in the SP02 JSON logs, with no content. Traces to R8.
What changes at a high level: Emit `session_cancel_requested` (`from_state`), `session_cancelled` (`from_state`, `counted`, `run_id` if any) and `session_cancel_failed` (`exc_class`) in the route and repo path, and `task_cancelled` (`step`) at each worker abort. Add `from_state` and `counted` to `logs.API_FIELDS`. Ids come from SP02 context, not call arguments.
Done when: tests assert, via log capture, that a cancel emits the requested and cancelled lines with `session_id`, a worker abort emits `task_cancelled` with `step`, a forced txn failure emits `session_cancel_failed` with the class name only, and no line carries content fields.

## Task 7 — Web: ConfirmDialog, chip, errors, mock
What it is / what it means: The reusable pieces the cancel UI needs, built before the page uses them. Traces to R9 (dialog, chip, mock, errors), D7.
What changes at a high level: Extract `ConfirmDialog` (title, description, confirm label and variant props, focus-on-Cancel kept, Escape and Cancel blocked while a request is in flight) from `DeleteDialog.tsx`, which becomes a thin wrapper. Add `cancelled: {text: "Cancelled", tone: "neutral"}` with a new grey tone to `dashboard/chips.ts`. Add cancel error copy (409 "This session already finished or failed.", failure "We couldn't cancel this session. Try again.") to `api/errors.ts`. Implement `cancelSession` in the MSW mock session machine following R2/R4. Types follow the regenerated schema (Task 9 finalises it).
Done when: web tests pass for: `DeleteDialog` behaviour unchanged (focus, confirm, existing tests green); `ConfirmDialog` blocks Escape/Cancel while pending; chip renders "Cancelled" neutral and `Record<State,...>` type-checks; mock returns the correct `counted` per state, 409 for finished/failed and idempotent repeat.

## Task 8 — Web: CancelLink, CancelledView, SessionPage
What it is / what it means: What the user sees: a quiet link, a confirmation, then a clear cancelled page. Traces to R9, D7, D8, SP05 slot resolution.
What changes at a high level: New `CancelLink.tsx` exporting `isCancellable(state)` (the seven states) and a blue link with red hover, shown only when cancellable. It opens `ConfirmDialog` variant A (created, uploading, upload_incomplete, validating, or `free_run`) or B (transcribing, awaiting_input, running) with the R9 copy. After confirm: link shows `Cancelling…` with spinner, `aria-busy`, disabled until the POST returns. New `CancelledView.tsx`: heading "Cancelled", counted or not-counted sentence from persisted `counted` (omitted when null), Delete button only. `SessionPage.tsx` renders the link in the SP05 `data-slot="cancel"` when present, otherwise a row above Delete, switches to `CancelledView` on 200 or status `cancelled`, invalidates `["usage"]`, and shows the inline `ErrorCard` with Reference on failure (retry safe) and the 409 copy with the page following live status.
Done when: web tests pass for: link blue/red-hover and visible only in the seven states; variant A vs B copy; confirm shows `Cancelling…` + spinner then both result messages; reload from status doc shows the persisted message; POST 500 shows the error card with Reference and the link returns; 409 copy; cancelled view has Delete only and no rating, speaker gate or retry; 404 uses existing not-found handling.

## Task 9 — Contract regen, public docs, race tests
What it is / what it means: Lock the public contract and prove the concurrency cases. Traces to Acceptance Criteria 3 and 7, R2, R4, shared regen note.
What changes at a high level: Regenerate `api/openapi.json`, `docs/contracts/public` and `web/src/api/schema.d.ts` (rebase on SP03/SP07 regen; last merged wins). Update `docs/reference/public-api.md` with the `cancelSession` route and the charge table. Add the race tests: cancel vs `start_first_run` (one winner; if the run wins, cancel reports counted and releases it; if cancel wins, run start returns `not_ready`) and cancel vs poll completing.
Done when: contract-consistency check passes (generated files match code, web type-checks against new schema); `public-api.md` documents route, statuses and charge table; race tests pass; related existing tests green.

## Owner steps
- Staging check (AC6): cancel during transcribing shows "Cancelled" with usage +1 once; cancel during validating shows "did not count"; logs show `session_cancelled` and any `task_cancelled` for the session id. Needs staging access.
- Coding order reminder: SP03 must merge first; SP05 later renders `CancelLink` in its reserved slot.
