---
status: draft
summary: POST /sessions/{id}/cancel sets a terminal `cancelled` state in one repo transaction (releases the run slot, charges 1 unit only if transcription started and no run was reserved), workers stop via a central state check, web gets a blue/red-hover link + confirm dialog + cancelled view + list chip.
date: 2026-11-23
---
# PRD: SP04 Cancel

Repo/branch: Onolys/onolys (local `iaudit`) / `feat/session-ux-logging-claude-email` · Depends on: SP03 (Phase 2; `jobs/charging.py`, status `counted`, `TRANSITIONS`), SP02 (log context) · Owns: `api/src/onolys_api/jobs/{machine.py (cancelled transitions), alive.py (ensure_active), worker.py (Cancelled handling), run.py, transcribe.py, validate.py (checks), charging.py (re-exports `decide_cancel`; file created by SP03)}`, `api/.../routes/{sessions.py (cancel route, list/detail fields), rating.py, speakers.py, runs.py (409 on cancelled)}`, `api/.../repo/{models.py, base.py, firestore.py, fake.py, limits.py}`, `web/src/features/session/{SessionPage.tsx, CancelLink.tsx (new), ConfirmDialog.tsx (new, extracted from DeleteDialog.tsx), CancelledView.tsx (new)}`, `web/src/features/dashboard/chips.ts`, `web/src/api/errors.ts`, `web/src/mocks/*`, `docs/reference/public-api.md` · Shared regen: `api/openapi.json`, `docs/contracts/public`, `web/src/api/schema.d.ts` (SP03, SP07 also regenerate; last merged wins)

## TL;DR
Only Delete exists today (`jobs/delete.py`); a user who uploads the wrong file must wait for transcription and rating, and the rating burns a unit [verified: `SessionPage.tsx` actions = Delete only; `machine.TRANSITIONS`]. This SP adds a non-destructive, terminal `cancelled` state, one atomic endpoint, and a charge rule that fits the existing "unit reserved at run start" model by adding the one missing case: a unit charged at cancel time when transcription started but no run exists yet.

## Problem
- No way to stop an in-progress session without destroying its data.
- Units are reserved only at run start (`start_run`/`start_first_run`, one txn with day count and `active_runs`) and released by `release_run_slot` [verified: `repo/firestore.py:699-800`]. A user cancelling at `awaiting_input` has spent a Chirp transcription but has no run doc to carry a charge. SP03 leaves that path to this SP [verified: SP03 Risks].
- Tasks already in Cloud Tasks, or mid-flight, keep running: only `deleting` is checked (`ensure_alive`, `run._execute`), and `advance(to=...)` from an unexpected state raises `invalid_state` into the generic failure path [verified: `alive.py`, `machine.advance`].

## Goals / Non-Goals
**Goals:** cancel from every in-progress state; stop work promptly with no stray state changes or failures; honest, durable, idempotent charge result; no refund, no double charge.
**Non-goals:** resume; killing the Chirp LRO (ignored, cost small); deleting data on cancel; cancel on finished/failed sessions (Delete); AI-interview cancel (separate resource); processing-screen layout (SP05 owns the slot).

## Requirements
**R1 State model.** `SessionState` gains `cancelled`. `TRANSITIONS`: `created, uploading, upload_incomplete, validating, transcribing, awaiting_input, running` each gain `cancelled`; `cancelled -> {deleting}` only; add to `_NOT_DELETING`. No separate "cancel requested" marker: the cancel txn sets `cancelled` directly (terminal), which is the marker workers read. Status doc keeps its last `progress`/`step`.
**R2 Endpoint.** `POST /sessions/{id}/cancel` (opId `cancelSession`), 200 `{counted: bool}`, owner only (same `User` dependency; another user's or `deleting` session → 404 via `NotFoundError`).
| Current state | Result |
|---|---|
| the seven in-progress states | cancel, 200 |
| `cancelled` | 200 with the persisted `counted` (idempotent, no second charge) |
| `report_ready`, `failed` | 409 `invalid_state` |
| `deleting` / unknown / not yours | 404 |
Never 429: cancel is allowed over the cap. A stuck session (stale chain) can be cancelled too; the route does not call `settle_if_stale` first.
**R3 Cancel transaction** (`Repo.cancel_session(uid, sid, date, defaults) -> CancelOutcome`, one txn on session + status + usage + user [+ active run]):
1. read session; state `cancelled` → return stored `counted`; not in the seven states → `invalid`.
2. if a run is unreleased (state `running`): mark it `failed` with `error="cancelled"` (so `claim_run` answers duplicate to late deliveries) and release its slot (`active_runs -1`, `refund=False`); same logic as `release_run_slot`, factored into one in-txn helper both use.
3. `units = decide_cancel(...)` (R4); if > 0, `usage/{uid}_{date}.runs += units` (over-cap tolerated, as SP11 allows `used > cap`).
4. set session `state=cancelled`, `cancel={counted, units, at}`; status `state`, `counted`; `stage_started_at`.
**R4 Charge rule** (pure `decide_cancel` in `repo/limits.py`, re-exported by `jobs/charging.py`; the SP03 helpers `release_once`/`should_refund` stay for run end):
| State at cancel | Run doc | Charge | `counted` |
|---|---|---|---|
| created, uploading, upload_incomplete, validating | none | 0 | false |
| transcribing, `steps.transcribe.stt_operation` unset | none | 0 | false |
| transcribing, operation set (Chirp job submitted) | none | 1 | true |
| awaiting_input (transcription done) | none | 1 | true |
| running | reserved at start | 0 new; no refund | run's `counted` |
Exempt sessions (`interview_id` set, not `free_run_void`) are charged 0 at every state → `counted=false` [RESOLVED: owner 2026-11-23: an AI interview includes its evaluation, which never consumes the user's evaluation limit; same predicate as `exempt` in `start_first_run`, `repo/{fake,firestore}.py`, so SP03 and SP04 agree]. A `free_run_void` session (uploaded audio did not match the relay recording) is a normal evaluation and follows the table. "Race" case (transcription starts while the dialog is open) is covered because the rule reads the state inside the txn at POST time. Unit is always 1, not `n_runs`.
*Data on cancel (owner rule 2026-11-23, confirms the locked "keep data"):* cancel never deletes anything: no blob, transcript, recording or run doc is removed, and `ensure_active` (R5) purges nothing on `cancelled` (only its `deleting` branch sweeps, which is the Delete path). Only the explicit Delete action deletes. Reason: a future "retry with existing upload" feature reuses the stored audio/transcripts. Same rule for failures lives in SP03 R8.
*Interaction with SP03:* a cancel charge has no run doc, so `should_refund`/`release_once` never see it; it is never refunded. A run that fails after cancel finds `released=true` and `release_once` is a no-op (idempotent), so no double refund. A cancelled session cannot start a run (`start_run`/`start_first_run` check state), so no charge-then-reserve double count.
**R5 Workers stop.** New `Cancelled(Exception)` in `jobs/worker.py`. `alive.ensure_active(repo, blobs, uid, sid)` = today's `ensure_alive` (deleting: purge + `NotFoundError`) plus: state `cancelled` → raise `Cancelled` and purge nothing (data is kept). `TaskRunner.handle` catches `Cancelled` → 200 outcome `cancelled`, records no failure, and, as a backstop, its catch-all `except Exception` first re-reads the session: if `cancelled`, answer 200 `cancelled` instead of `_fail`/`to_public` (covers the `invalid_state` that `advance` raises). `_fail`/`stale.py` never write `failed` over `cancelled`. Handlers check state first and after each blob or LLM call:
| Handler / moment | How it stops |
|---|---|
| `validate`, delivered after cancel | first-line state check (`validating` only) → return |
| `validate`, mid-flight | `ensure_active` after each blob write (existing `ensure_alive` call sites, `validate.py:164-176`); final `advance(to=transcribing)` fails the transition → backstop |
| `transcribe` (start) | `state != transcribing` → return (exists); `ensure_active` after `stt.start` returns; an operation submitted in the race window is ignored |
| `transcribe_poll` | `state != transcribing` → return, so no next poll is enqueued (exists); `ensure_active` before `put_transcript`/`advance`; the Chirp result is discarded |
| `run`, delivered after cancel | `claim_run` sees `failed` → duplicate; else `_execute` state check |
| `run`, mid-flight | `progress_cb` calls `ensure_active` at each stage boundary (re-raises `Cancelled`, like `NotFoundError` today); LLM calls in flight finish and are discarded; check before `put_report`; `advance(to=report_ready)` is the last guard |
Queued Cloud Tasks are not deleted; they no-op on delivery. Orphan blobs/artifacts written in a race stay under the session prefix and go with Delete.
**R6 Other routes.** `PUT /rating` (currently "every state but deleting"), `POST /speakers`, `POST /runs`, upload-URL/complete, SP03 `retry` return 409 `invalid_state` on `cancelled`. Reads (transcript, audio, reports) stay allowed; data is kept.
**R7 Fields.** `SessionDoc.cancel: {counted, units, at} | None`; `SessionStatusDoc.counted: bool | None` (SP03 adds the same field for failures; one field, one meaning: "this session consumed a unit at its end state"); add to `STATUS_FIELDS`. `SessionListItem.status` enum gains `cancelled`.
**R8 Logging** (SP02 context carries `session_id`): `session_cancel_requested` (`from_state`), `session_cancelled` (`from_state`, `counted`, `run_id` if any), `task_cancelled` (`step`) at each worker abort, `session_cancel_failed` (`exc_class`). Add `from_state`, `counted` to `logs.API_FIELDS`. No content.
**R9 Web.**
- `CancelLink`: text link, blue, `hover:` red, shown only on the processing page when `isCancellable(state)` is true (the seven states; SP05 reserves the slot; until it merges, rendered above the Delete row in `SessionPage.tsx`). Delete stays the red button.
- `ConfirmDialog` extracted from `DeleteDialog` (title, description, confirm label/variant props; `DeleteDialog` becomes a thin wrapper, focus-on-Cancel behaviour unchanged). Escape/Cancel blocked while the POST is in flight.
| Variant (state) | Title | Body | Buttons |
|---|---|---|---|
| A: created, uploading, upload_incomplete, validating | Cancel this session? | Processing stops. Your upload stays until you delete the session. This won't count toward your limit. | Keep processing / Cancel session |
| B: transcribing, awaiting_input, running | Cancel this session? | Processing stops. Transcription has started, so this counts toward your daily limit. | Keep processing / Cancel session |
- States: idle → on confirm dialog closes, link text `Cancelling…` + spinner, `aria-busy`, disabled (client-side, until the POST returns) → on 200 or when the status listener shows `cancelled`: `CancelledView`.
- `CancelledView`: heading "Cancelled"; line "Session cancelled. This counted toward your limit." / "…did not count toward your limit." from `doc.counted` (survives reload; `null` → omit the sentence); Delete button; nothing else (no rating card, no speaker gate, no retry). Invalidate `["usage"]` after success.
- List chip: `cancelled: {text: "Cancelled", tone: "neutral"}` (new grey tone; `sessionsRefetchInterval` unaffected); the `Record<State,…>` type forces the entry after regen.
- POST failure (network/5xx): dialog closed, link back to idle, inline `ErrorCard` "We couldn't cancel this session. Try again." with Reference = session id (safe to retry: idempotent). 409: "This session already finished or failed." and the page follows the live status. 404: existing not-found handling.
- MSW mock: `cancelSession` implements R2/R4 on the mock session machine.

## Architecture
```
web CancelLink -> ConfirmDialog -> POST /sessions/{id}/cancel
api: Repo.cancel_session (1 txn): [fail+release active run] + decide_cancel -> usage.runs += units
     -> session/status state=cancelled, counted   -> 200 {counted}
worker (any handler): ensure_active / backstop -> Cancelled -> 200 "cancelled" (no failure write)
web: status listener state=cancelled, counted -> CancelledView
```
Interface: `def cancel_session(self, uid: str, sid: str, date: str, defaults: LimitDefaults) -> CancelOutcome  # ("cancelled", counted) | ("invalid",)`.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | Marker vs terminal | set `cancelled` directly in one txn | `cancel_requested` flag then worker finalises | Worker may be dead or the task dropped; a flag would need a sweeper. Terminal state is the marker |
| D2 | Where the charge lives | usage day count incremented in the cancel txn, `cancel` on session | synthetic run doc; reserve at transcription start | No run exists; synthetic doc pollutes runs/reports; moving all charging is the rejected, riskier option |
| D3 | Run slot release | in-txn helper (same code as `release_run_slot`) | `release_once` after the txn | A crash between would leak `active_runs`; stale check does not cover `cancelled` |
| D4 | Stop mechanism | central `ensure_active` + worker backstop on any exception when `cancelled` | per-handler ad-hoc checks only | Misses (e.g. `advance` raising `invalid_state`) would otherwise write `failed` over `cancelled` |
| D5 | Run doc on cancel | `status=failed`, `error="cancelled"` | new `RunStatus` value | `claim_run` already treats `failed` as duplicate; no enum change in `RunDoc` |
| D6 | Over-cap | cancel charges even past the cap, never 429 | refuse cancel at cap | The unit is already spent; refusing traps the user |
| D7 | Dialog variant source | by state (A/B; A also when the session's `free_run` flag is true, since interview-linked sessions are never charged), result message by real `counted` | server-supplied "will count" preview | No extra call; slight over-warning in early `transcribing` is the safe side |
| D8 | `counted` field | reuse SP03's status field | separate `cancel_counted` | One reading for the web |
| D9 | Late work | results discarded, blobs kept until Delete | purge on cancel | "Keep data" is locked |

## Risks / Open Questions
- [RESOLVED: charge 0 (owner 2026-11-23): interview-linked sessions never count, the interview includes its evaluation] Interview-linked cancel charge. Only a `free_run_void` session is charged as normal (matches existing `exempt` code).
- [RESOLVED: aligned with SP05 — SP05 R7 reserves `<div data-slot="cancel">` directly under the phase hint, right-aligned, rendered iff the web predicate `isCancellable(state)` (the seven states, owned by SP04, exported from `CancelLink.tsx`) is true. SP04 renders `CancelLink` into that slot when SP05 has landed; until then, own row above Delete (coding order 03 → 04 → 05). "Cancelling…" replaces the slot content only.]
- [OPEN: owner question; default keep] Interview-linked sessions with `free_run_void` (uploaded audio does not match the interview recording) are charged as normal on cancel (exempt = `interview_id` and not `free_run_void`), same as SP03. Keep?
- [RESOLVED: default — accepted] `steps.transcribe.stt_operation` as "transcription started": a task that submitted but crashed before saving the handle spends Chirp cost uncounted (user-favourable, accepted).
- [RESOLVED: default — verify at coding (AC4 covers upload-URL/complete on `cancelled` → 409); add an explicit state check if `TRANSITIONS` does not already 409] Does the upload-complete route (late PUT after cancel) already 409 via `TRANSITIONS`?
- [DEFERRED] Chirp LRO cancellation; cleanup of Cloud Tasks queue entries.
- Risk: a run mid-LLM at cancel still spends tokens until its next stage boundary; accepted, charge stands (no refund).
- Risk: SP03/SP05 also edit `TRANSITIONS`, `worker._fail`, `SessionPage.tsx`, `errors.ts`, `STATUS_FIELDS`; additive, trivial rebases.

## Acceptance Criteria
1. State × cancel matrix test (FakeRepo): each of the seven states → 200 `cancelled`; `report_ready`/`failed` → 409; `deleting`/other user → 404; second cancel → 200 same `counted`, usage unchanged.
2. Charge tests (cancel deletes nothing: blobs and docs of the session are intact after cancel in every state): validating → no charge; transcribing without/with `stt_operation` → 0/1; awaiting_input → 1; running → no new charge, no refund, `active_runs` back to prior value; exempt interview session (`interview_id`, not `free_run_void`) → 0 at transcribing/awaiting_input too; `free_run_void` session → normal table; cancel at cap still succeeds and increments; cancel then a failing run end → no second release or refund.
3. Race tests: cancel vs `start_first_run` (one winner; if run wins, cancel reports counted and releases it; if cancel wins, run start returns `not_ready`); cancel vs poll completing (`put_transcript`/`advance` after cancel → handler returns 200 `cancelled`, session stays `cancelled`, no `failed`); cancel during `running` (late stage callback aborts; `report_ready` never set); late-delivered `validate`/`transcribe`/`run` tasks no-op.
4. Other routes: rating, speakers, runs, retry on `cancelled` → 409.
5. Web tests: link blue/red-hover class and only in the seven states; dialog variant A vs B copy; confirm → `Cancelling…` + spinner then both result messages; reload from status doc shows the persisted message; POST 500 shows the error card with Reference and link returns; 409 copy; cancelled view has Delete only; chip text "Cancelled".
6. Staging: cancel during transcribing leaves a session that shows "Cancelled", usage +1 once; cancel during validating shows "did not count"; logs for the session id show `session_cancelled` and any `task_cancelled`.
7. `openapi.json`, `docs/contracts/public`, `schema.d.ts` regenerated and consistent; `public-api.md` documents the route and the charge table.
