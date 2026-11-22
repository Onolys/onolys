---
status: draft
summary: web hides the clinician rating card behind VITE_RATING_ENABLED (default false), moves the two run inputs (change goal required, coded span optional) onto the upload screen with one submit that also PUTs a no_rating card (api untouched), shows only Onolys's coding + tips in reports (old rated reports too), accepts old and new stage names, and updates mocks and tests.
date: 2026-11-22
---
# PRD: SP03 web hides the rating card, MITI-only report

Repo/branch: Onolys/onolys (local `iaudit`) / `feat/miti-lean-engine` · Depends on: SP02 (stage names only; upload-screen setup works against today's api) · Blocks: SP05 (cleanup, only for the `web/` leftovers it lists)
Owns: `web/**` (src, e2e_review, `.env.example`). Not owned: `api/`, `engines/`, `admin/`, CI files.

## TL;DR
One build-time flag, `VITE_RATING_ENABLED` (absent = false), gates every clinician-rating UI: the rating card, "Your rating" copy, and all comparison parts of the report. With it off there is **no separate setup screen and no "Save setup" button** (owner, 2026-11-22): the upload screen (`/sessions/new`) gets "Change goal" (required) and "Coded span" (optional) next to the audio file, with ONE submit button. Submit runs `POST /sessions` -> `PUT /rating {final:true, no_rating:true, card:{change_goal, coded_span?}}` -> `POST /audio` -> upload. The AI-interview end flow sends the same PUT with the scenario's goal and no form. That one PUT sets `rating_submitted`, `change_goal`, `coded_span` and starts the first run, so Option A of SP02 [OPEN-1] works with zero api change. Report shows Onolys scores, evidence, summaries, tips only. Rating code stays, dormant. `timeline.ts` accepts `paudit|eaudit|tips|compare|assemble` and `code|tips|assemble`.

## Problem
- Hiding the card blocks first runs: `start_first_run` needs `rating_submitted`, and `change_goal`/`coded_span` reach the session only through `PUT /rating` [verified: `api/.../routes/rating.py:113-160`, SP02 R3]. The engine does use both (`_ENGINE_PARAMS` in `adapters/real.py:107`, params built from `session.change_goal` in `jobs/run.py`).
- The report still renders comparison UI: Scorecard has "You" and "Difference" columns even when unrated [verified: `ReportSections.tsx:84-100`], Behaviours has a "You" column (`:201`), Summaries show "You" (`:236`), Disagreements and Reasons sections exist (`:117`, `:254`), and the dashboard intro promises "where it agrees with your own rating" [verified: `Dashboard.tsx:54`].
- Progress labels are keyed on the old stage names [verified: `timeline.ts:45-51` `RUN_SUBLABELS`]; the mock worker walks `paudit,eaudit,tips,compare,assemble` [verified: `mocks/stateMachine.ts:11,66`].

## Goals / Non-Goals
**Goals:** no rating UI by default; first run still starts from the session page; report = Onolys coding + tips; old stored reports render without comparison parts; web deploys before or after SP02 with no break; rating code kept and flag-restorable.
**Non-Goals:** deleting `features/rating/*`, `miti-items.ts`, `rating.schema.json`; api gate change (Option B); editing report TS types (`api/report.d.ts`, generated); copy overhaul of "Rate session" / "Rating" chips / Settings "Ratings left"; a new report layout (comes from the report's own `layout[]`).

## Requirements
**R1. Flag.** `web/src/config.ts` adds `export const ratingEnabled = (): boolean => import.meta.env.VITE_RATING_ENABLED === "true"` (a function, so tests can `vi.stubEnv`). `.env.example` documents it (default false). No workflow edits: `deploy-prod.yml`, `deploy-staging.yml`, `pr-preview.yml` set no such var, so every build is off [verified: grep of VITE_ in `.github/workflows` finds only firebase/contact/db vars; admin precedent `VITE_EVAL_ENABLED` is likewise default-off]. `.env.mock` stays unchanged (mock/e2e exercise the default).

**R2. Wiring (flag off).** `session/slots.tsx` `RatingCardSlot` renders `<RatingCard>` only when `ratingEnabled()`; otherwise nothing, except the R3 fallback form for a session that still has `rating_submitted:false`. `SessionPage.tsx:211` is the single mount point; no other file mounts the card [verified: grep `RatingCard` outside `features/rating`: `slots.tsx` only].

**R3. Setup fields on the upload screen (Option A).** No separate setup screen, no "Save setup" button. New `features/rating/SetupFields.tsx` (beside the card, reuses `card.ts`; the card file is untouched) holds the two fields; `NewSessionPage.tsx` mounts it under Language/Title, above the single submit button (existing "Start").
- Fields: "Change goal" (required, textarea, soft counter via `softCount`/`LIMITS.item`); "Coded span" optional, "From" / "To" `mm:ss`, both or neither, helper text "Leave blank to code the whole session (up to 20 minutes)". Validation = `localIssues(form,{noRating:true})`; payload = `buildCard(form,{noRating:true})` [verified: `card.ts:45-55,106-125`]. Nothing else is collected.
- Submit gate: `canSubmit` additionally needs a non-blank change goal and no local span issue. Blank goal blocks submit locally.
- **Call sequence on submit (flag off), one click:**
  1. `POST /sessions` (as today; Idempotency-Key, cached in `created` ref).
  2. `PUT /rating {final:true, no_rating:true, card}`. Verified allowed right after creation: `put_rating` only refuses `deleting` (404) and already-submitted/has-report (409 `rating_final`); it has no state, transcript or duration gate [verified: `routes/rating.py:_open_session`, `put_rating`]. It sets `change_goal`, `coded_span`, `rating_submitted` and calls `maybe_start_first_run`, which is a no-op until `transcript_ready` and `speaker_confirmed` are also true [verified: `jobs/first_run.py` docstring, `jobs/machine.py:40` FLAGS].
  3. `POST /sessions/{id}/audio` (`prepareUpload`), then navigate and `getJob(id).start()` (upload + `complete`) as today.
  Why PUT before audio: an invalid card (422) fails before any audio is registered, so the form stays put with a field message and nothing half-done. Retry after a later failure re-enters at the cached session id: PUT returns 409 `rating_final`, treated as success, then audio is retried. Upload -> PUT order would also work (PUT is state-independent) but leaves an uploaded session without a goal if the PUT fails.
  The mutation tracks a `ratingSaved` ref so a retry skips step 2 when it already succeeded.
- Errors: 422 `rating_invalid` -> `issuesFromApi` onto the fields; 409 `rating_final` -> continue; other errors -> existing `ErrorCard`.
- **AI interview (own entry screen `NewInterviewPage`, no setup fields there):** the change goal comes from the scenario, not the user. The goal is not on the interview start screen; it is seeded as the `ratings/draft` `change_goal` when the session is created from the interview [verified: `routes/sessions.py:170`, `_create_for_interview`]. In `InterviewPage.tsx` End flow (`:138-140`: end -> `POST /sessions {interview_id}` -> `prepareUpload`) insert, after session creation: `GET /rating` -> read `draft.card.change_goal` -> `PUT /rating {final:true, no_rating:true, card:{change_goal}}` (409 `rating_final` = done; resume path reuses `sessionId.current`) -> `prepareUpload`. No span (whole interview). If the draft goal is missing, fall back to the R3 fallback form on the session page.
- **Fallback on the session page (not a setup screen):** a session that has `!doc.rating_submitted` (created before this build, or an interview whose PUT failed) shows the same `SetupFields` with a "Continue" button that only does the `PUT`. Shown while `!doc.rating_submitted && state !== "deleting"`; prefilled from `GET /rating` (`cardToForm(draft ?? final)`). Normal new sessions never see it. No autosave [DEFERRED].
- **Setup is final after submit:** the api refuses a second final card (`rating_final`, FX45), so no read-only view and no edit; the upload screen is the only place the goal/span is entered.
- **Coded span vs duration (verified):** the api does NOT check the span against audio length. Server checks are only `from_s,to_s >= 0` and `from_s <= to_s` [verified: `engines/evaluation/.../rating.py:92-99`]. The engine then keeps turns overlapping the span (`paudit/prepare.py:select_turns`); a span past the real end keeps no turns, the input checks run on that empty selection (like a too-short session), and a transcript without timestamps ignores the span with `span_ignored`. At submit time the duration is only known client-side: `useFilePick` already reads it from the file (`readDuration`), so the form soft-checks `to` (and `from`) against that duration when it is known and blocks a span entirely beyond it; when unknown it passes through unchecked. Transcribed duration is not available until after the PUT.

**R4. Timeline copy.** `deriveTimeline(doc, opts)` gains `opts.ratingEnabled` (default `ratingEnabled()`). Off: step label "Your rating" -> "Session setup"; line "Waiting for your rating" -> "Waiting for session setup". On: current copy. `RUN_SUBLABELS` gains `code: "Coding the session"`, keeps `tips`, `assemble`; legacy keys map `paudit` and `eaudit` -> "Coding the session", `compare` -> "Building the report". Unknown or null step falls back to "Coding the session" (was `paudit`'s text). Both name sets live side by side until SP02 has run in prod for a release, then the legacy keys are removable [DEFERRED].

**R5. Report (flag off).** `ReportSections.tsx` treats `rated = ratingEnabled() && header.has_clinician_rating`.
| Part | Behaviour |
|---|---|
| Scorecard | Drop "You" and "Difference" columns and the "No rating of yours..." note; Item + Onolys only |
| Behaviours | Drop "You" column |
| Globals | The `rated && clinician` block already hides |
| Summaries | Ignore `s.clinician` (no "You" text, no `you` dot) |
| Disagreements | Return null unless `ratingEnabled()` |
| Reasons audit | Return null unless `ratingEnabled()`; `reasons_audit_failed` already in `SKIPPED_WARNINGS`; also skip `reason_withheld_tone` |
| Tips, Method | Unchanged (tips present; `tips_failed` warning stays) |
Result: an old stored rated report renders Onolys-only (comparison fields ignored, never crash). Unknown or missing sections still skipped by the existing `default: return null`. `SampleReportPage` switches from `sampleReport` to `noRatingReport`.

**R6. Dashboard copy.** `Dashboard.tsx:54`: "Onolys codes a recorded session against the MITI, with evidence from your transcript and tips to improve." (flag on: old sentence).

**R7. Mocks.** `stateMachine.ts`: `STAGES = ["code","tips","assemble"]`, weights `{code:40,tips:8,assemble:3}` (match SP02 D4); title marker `fail-paudit` -> `fail-code`, `fail-eaudit` removed with `reasonsFailed`; `RunRec.stage` type updated. The `putRating` gate and `rating_final` stay (still the api contract). `fixtures/report.ts`: default run report is `noRatingReport`; `sampleReport` (rated) kept as the legacy-render fixture for tests; `reasonsFailedReport` kept for legacy-render tests. `handlers.ts` needs no change [verified: only passes through `putRating`/`getRating`].

## Architecture
```
NewSessionPage (audio + language + title + SetupFields) --one submit-->
    POST /sessions -> PUT /rating {final,no_rating,card{change_goal,coded_span?}} -> POST /audio -> upload+complete
InterviewPage End -> POST /sessions{interview_id} -> GET /rating (draft goal) -> PUT /rating {final,no_rating,card{change_goal}} -> POST /audio
SessionPage -> RatingCardSlot --ratingEnabled()?--> RatingCard (dormant, unchanged)
                                   \--off--> nothing (fallback SetupFields only if !rating_submitted)
api: rating_submitted + change_goal + coded_span set -> maybe_start_first_run (once speaker confirmed)
status doc step: code|tips|assemble  (old: paudit|eaudit|tips|compare|assemble)  -> RUN_SUBLABELS accepts both
ReportSections: rated = ratingEnabled() && header.has_clinician_rating  -> comparison parts hidden
```
No api, openapi, or generated-type change, so `npm run check:api` stays clean. The setup fields depend on api only for behavior that exists today; stage-name labels degrade gracefully either way.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | OPEN-1 (run gate) | Option A: upload-screen submit PUTs `no_rating` card | B: api flag + new endpoint | Verified workable: one existing call carries goal, span and `rating_submitted` and is allowed straight after session creation; zero api change, web ships independently |
| D2 | Flag | Build-time `VITE_RATING_ENABLED`, function accessor, default off | Runtime/remote flag; user setting | Matches admin precedent; no CI/infra edit; testable via `stubEnv` |
| D3 | Setup UI | Fields live on the upload screen; one submit, no separate setup screen, no "Save setup" button (owner 2026-11-22). New `SetupFields.tsx` reusing `card.ts` helpers | Separate `SessionSetup.tsx` form on the session page with its own button; compact mode in `RatingCard.tsx` | Owner decision: one step for the clinician; card stays untouched and restorable |
| D3b | Call order | create session -> PUT /rating -> POST /audio | upload -> PUT /rating | PUT has no state gate; failing validation before any audio is registered leaves nothing half-done; 409 on retry is benign |
| D3c | Interview goal | Web PUTs the scenario's seeded draft goal at End, no form | Ask the user | Goal is scenario-defined; draft already seeded by the api |
| D4 | Old rated reports | Hide comparison too (same flag) | Render them as stored | Locked: report UI shows only Onolys coding + tips |
| D5 | Stage labels | Accept both sets; neutral "Coding the session" | Cut over to new names only | Deploy order unknown; in-flight runs may show old step |
| D6 | Autosave in setup | None | Reuse `createAutosaver` | Two fields; simpler; draft only matters for tab-close |
| D7 | Product vocabulary | Leave "Rate session", "Rating" chip, Settings "Ratings left" | Rename now | Not in scope; one-line follow-up, avoids touching ~10 asserted strings |

## Risks / Open Questions
- [RESOLVED: Option A works] OPEN-1 from SP02. Needs only `change_goal`; `no_rating:true` is accepted at `final=true`. Failure mode: a user who closes the page loses the typed goal (no autosave, draft is not written).
- [RESOLVED: single submit on upload screen, owner 2026-11-22] Button copy / separate setup button: there is no setup button; the existing upload "Start" is the single submit.
- [OPEN] Span beyond real audio length is not rejected by the api (see R3); submitted before duration is known when the browser cannot read it. Default: client soft-check when duration is known, otherwise accept; an empty-selection run surfaces as a short-session warning/failure. Owner to confirm or ask for an api check (needs api change, out of SP03).
- [OPEN] Interview End flow: if the PUT succeeds but `prepareUpload` fails, the session has `rating_submitted` and no audio; the retry path (`sessionId.current`) must skip the PUT. Default: handle via 409-as-done.
- [OPEN] Flag off permanently locks a session's setup after the upload submit (`rating_final`); a mistyped goal cannot be corrected, same as today's card (and the goal is now entered before the user has seen anything else, so the field note should say it is final). Accepted; revisit with SP02 Option B if complaints.
- [DEFERRED] Vocabulary pass ("rating" -> "coding"), autosave of goal on the upload screen, removing legacy stage keys, deleting rating code (belongs to a later cleanup).
- [DEFERRED] Report `Diff`-related TS types/chips (`chips.ts`, `diffChip`) stay; dead while flag off.

## Acceptance Criteria
- Default build/dev: `/sessions/new` shows "Change goal" (required) and "Coded span" (optional mm:ss from/to) next to the audio file and one "Start" button; no separate setup screen, no "Save setup" button; no element with `data-slot="rating-card"` content on the session page; `#rating-globals-*` absent. `VITE_RATING_ENABLED=true` shows the original card (existing `RatingCard`, `card`, `autosave` suites pass untouched) and the upload screen has no setup fields (old behaviour).
- Submit sequence: Start with a goal calls `POST /sessions`, `PUT /rating` (`final:true,no_rating:true`, `card.change_goal`, `coded_span` only when both times given), `POST /audio`, in that order; blank goal blocks submit; span with only one time, from > to, or beyond the known file duration blocks with a field message.
- Failure paths: PUT 422 shows a field message and registers no audio; PUT 409 `rating_final` on retry is treated as success; audio request failure after a good PUT retries without a second PUT.
- Interview: End creates the session, reads the seeded draft goal, PUTs `no_rating` card with it, then uploads; the session page shows no setup form for it.
- Fallback: a session with `rating_submitted:false` shows the setup fields with "Continue" on the session page; a normal new session does not.
- E2E (mock mode): fill goal + audio, Start -> confirm speaker -> report appears (no separate setup step) with no "You"/"Difference"/disagreements/reasons parts; progress sublabels read "Coding the session".
- `deriveTimeline` unit table covers `step` in `{code,tips,assemble,paudit,eaudit,compare,zzz,null}`; no throw, labels as R4.
- Legacy rated fixture (`sampleReport`) renders: Scorecard has no "You" column, no Disagreements/Reasons regions, tips visible.
- Tests changed: `timeline.test.ts` (copy + sublabels), `SessionPage.test.tsx` (lines ~87-114 assert the card; switch to no-card/fallback, add flag-on variant), `NewSessionPage.test.tsx` and `Interview.test.tsx` (new fields, call order), `flows.test.tsx` (`submitRating` helper `:103-108`, "No rating" flow `:174-192`, "Rating the session" asserts), `ReportPage.test.tsx` (`:75-130` comparison asserts -> `stubEnv(true)` block; add flag-off block), `SampleReportPage.test.tsx`, `Dashboard.test.tsx:39`, `stateMachine.test.ts`/`handlers.test.ts`/`fixtures*.test.ts` (stage names, `fail-code`), `e2e_review/mobile.spec.cjs:41-45` (selects `#rating-globals-cct-score`, "Submit rating") and `session-flow.spec.cjs:42-51` (W2/E17 draft-persistence through card; drop, covered by vitest autosave suite with flag on). Stryker `mutate` (auth + api/errors) unaffected; no config change.
- `npm run typecheck`, `lint`, `test`, `e2e`, `check:api` green; build output contains no new env requirement.
