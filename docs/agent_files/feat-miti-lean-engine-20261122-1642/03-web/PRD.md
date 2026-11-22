---
status: draft
summary: web hides the clinician rating card behind VITE_RATING_ENABLED (default false), replaces it with a two-field session-setup form that PUTs a no_rating card (api untouched), shows only Onolys's coding + tips in reports (old rated reports too), accepts old and new stage names, and updates mocks and tests.
date: 2026-11-22
---
# PRD: SP03 web hides the rating card, MITI-only report

Repo/branch: Onolys/onolys (local `iaudit`) / `feat/miti-lean-engine` · Depends on: SP02 (stage names only; setup form works against today's api) · Blocks: SP05 (cleanup, only for the `web/` leftovers it lists)
Owns: `web/**` (src, e2e_review, `.env.example`). Not owned: `api/`, `engines/`, `admin/`, CI files.

## TL;DR
One build-time flag, `VITE_RATING_ENABLED` (absent = false), gates every clinician-rating UI: the rating card, "Your rating" copy, and all comparison parts of the report. With it off, the session page shows a small **Session setup** form (change goal required, coded span optional) that submits `PUT /rating {final:true, no_rating:true, card:{change_goal, coded_span?}}`. That one call sets `rating_submitted`, `change_goal`, `coded_span` and starts the first run, so Option A of SP02 [OPEN-1] works with zero api change. Report shows Onolys scores, evidence, summaries, tips only. Rating code stays, dormant. `timeline.ts` accepts `paudit|eaudit|tips|compare|assemble` and `code|tips|assemble`.

## Problem
- Hiding the card blocks first runs: `start_first_run` needs `rating_submitted`, and `change_goal`/`coded_span` reach the session only through `PUT /rating` [verified: `api/.../routes/rating.py:113-160`, SP02 R3]. The engine does use both (`_ENGINE_PARAMS` in `adapters/real.py:107`, params built from `session.change_goal` in `jobs/run.py`).
- The report still renders comparison UI: Scorecard has "You" and "Difference" columns even when unrated [verified: `ReportSections.tsx:84-100`], Behaviours has a "You" column (`:201`), Summaries show "You" (`:236`), Disagreements and Reasons sections exist (`:117`, `:254`), and the dashboard intro promises "where it agrees with your own rating" [verified: `Dashboard.tsx:54`].
- Progress labels are keyed on the old stage names [verified: `timeline.ts:45-51` `RUN_SUBLABELS`]; the mock worker walks `paudit,eaudit,tips,compare,assemble` [verified: `mocks/stateMachine.ts:11,66`].

## Goals / Non-Goals
**Goals:** no rating UI by default; first run still starts from the session page; report = Onolys coding + tips; old stored reports render without comparison parts; web deploys before or after SP02 with no break; rating code kept and flag-restorable.
**Non-Goals:** deleting `features/rating/*`, `miti-items.ts`, `rating.schema.json`; api gate change (Option B); editing report TS types (`api/report.d.ts`, generated); copy overhaul of "Rate session" / "Rating" chips / Settings "Ratings left"; a new report layout (comes from the report's own `layout[]`).

## Requirements
**R1. Flag.** `web/src/config.ts` adds `export const ratingEnabled = (): boolean => import.meta.env.VITE_RATING_ENABLED === "true"` (a function, so tests can `vi.stubEnv`). `.env.example` documents it (default false). No workflow edits: `deploy-prod.yml`, `deploy-staging.yml`, `pr-preview.yml` set no such var, so every build is off [verified: grep of VITE_ in `.github/workflows` finds only firebase/contact/db vars; admin precedent `VITE_EVAL_ENABLED` is likewise default-off]. `.env.mock` stays unchanged (mock/e2e exercise the default).

**R2. Wiring (flag off).** `session/slots.tsx` `RatingCardSlot` renders `<RatingCard>` only when `ratingEnabled()`; otherwise `<SessionSetupSlot>` (R3). `SessionPage.tsx:211` is the single mount point; no other file mounts the card [verified: grep `RatingCard` outside `features/rating`: `slots.tsx` only].

**R3. Session setup form (Option A).** New `features/rating/SessionSetup.tsx` (beside the card so it reuses `card.ts`; the card file is untouched).
- Fields: "Change goal" (required, textarea, soft counter via `softCount`/`LIMITS.item`), "Coded span from / to" (optional `mm:ss`, both or neither). Exactly what `buildCard(form,{noRating:true})` and `localIssues(form,{noRating:true})` already emit/check [verified: `card.ts:45-55,106-125`]. Nothing else is collected (scores/counts/notes are not engine inputs).
- Prefill: `GET /rating` -> `cardToForm(draft ?? final)` (interview sessions seed a draft `change_goal` [verified: `routes/sessions.py:170`]).
- Submit button "Start" (not "Submit rating"): `PUT {final:true, no_rating:true, card}`; 422 `rating_invalid` -> `issuesFromApi`; 409 `rating_final` -> treat as done. After success the form is replaced by "Session setup saved." and, once the speaker is confirmed, the run starts by itself (same as today).
- Shown while `!doc.rating_submitted && state !== "deleting"`; hidden after submit (the form is final by api rule FX45, no read-only view needed). No autosave in v1 (two fields; ship fast) [DEFERRED].
- Valid for the api: `validate_rating(final=True)` needs only a non-blank `change_goal`; `no_rating:true` forces `has_rating:false` [verified: `rating.py:45-53`, `engines/evaluation/.../rating.py:103-122`, route `:117`]. A card with no scores is `no_rating` anyway.

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
SessionPage -> RatingCardSlot --ratingEnabled()?--> RatingCard (dormant, unchanged)
                                   \--off--> SessionSetup --PUT /rating {final,no_rating,card{change_goal,coded_span?}}
api: rating_submitted + change_goal + coded_span set -> maybe_start_first_run (once speaker confirmed)
status doc step: code|tips|assemble  (old: paudit|eaudit|tips|compare|assemble)  -> RUN_SUBLABELS accepts both
ReportSections: rated = ratingEnabled() && header.has_clinician_rating  -> comparison parts hidden
```
No api, openapi, or generated-type change, so `npm run check:api` stays clean. Setup form depends on api only for behavior that exists today; stage-name labels degrade gracefully either way.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | OPEN-1 (run gate) | Option A: setup form PUTs `no_rating` card | B: api flag + new endpoint | Verified workable: one existing call carries goal, span and `rating_submitted`; zero api change, web ships independently |
| D2 | Flag | Build-time `VITE_RATING_ENABLED`, function accessor, default off | Runtime/remote flag; user setting | Matches admin precedent; no CI/infra edit; testable via `stubEnv` |
| D3 | Setup component | New `SessionSetup.tsx` reusing `card.ts` helpers | Add a "compact" mode inside `RatingCard.tsx` | Card stays untouched and restorable; 338-line card has autosave/final logic we do not want |
| D4 | Old rated reports | Hide comparison too (same flag) | Render them as stored | Locked: report UI shows only Onolys coding + tips |
| D5 | Stage labels | Accept both sets; neutral "Coding the session" | Cut over to new names only | Deploy order unknown; in-flight runs may show old step |
| D6 | Autosave in setup | None | Reuse `createAutosaver` | Two fields; simpler; draft only matters for tab-close |
| D7 | Product vocabulary | Leave "Rate session", "Rating" chip, Settings "Ratings left" | Rename now | Not in scope; one-line follow-up, avoids touching ~10 asserted strings |

## Risks / Open Questions
- [RESOLVED: Option A works] OPEN-1 from SP02. Needs only `change_goal`; `no_rating:true` is accepted at `final=true`. Failure mode: a user who closes the page loses the typed goal (no autosave, draft is not written).
- [OPEN] "Start" button naming: the PUT does not itself start the run if the speaker is unconfirmed (gate unchanged). Label text may mislead; default "Save setup" with the status line explaining. Owner to confirm copy.
- [OPEN] Flag off permanently locks a session's setup after one submit (`rating_final`); a mistyped goal cannot be corrected, same as today's card. Accepted; revisit with SP02 Option B if complaints.
- [DEFERRED] Vocabulary pass ("rating" -> "coding"), autosave for setup, removing legacy stage keys, deleting rating code (belongs to a later cleanup).
- [DEFERRED] Report `Diff`-related TS types/chips (`chips.ts`, `diffChip`) stay; dead while flag off.

## Acceptance Criteria
- Default build/dev: no element with `data-slot="rating-card"` content; the session page shows "Session setup"; `#rating-globals-*` absent. `VITE_RATING_ENABLED=true` shows the original card (existing `RatingCard`, `card`, `autosave` suites pass untouched).
- E2E (mock mode): upload -> confirm speaker -> fill change goal -> report appears with no "You"/"Difference"/disagreements/reasons parts; progress sublabels read "Coding the session".
- Setup 422/409 paths show a field message / treat as saved; blank goal blocks submit locally.
- `deriveTimeline` unit table covers `step` in `{code,tips,assemble,paudit,eaudit,compare,zzz,null}`; no throw, labels as R4.
- Legacy rated fixture (`sampleReport`) renders: Scorecard has no "You" column, no Disagreements/Reasons regions, tips visible.
- Tests changed: `timeline.test.ts` (copy + sublabels), `SessionPage.test.tsx` (lines ~87-114 assert the card; switch to setup, add flag-on variant), `flows.test.tsx` (`submitRating` helper `:103-108`, "No rating" flow `:174-192`, "Rating the session" asserts), `ReportPage.test.tsx` (`:75-130` comparison asserts -> `stubEnv(true)` block; add flag-off block), `SampleReportPage.test.tsx`, `Dashboard.test.tsx:39`, `stateMachine.test.ts`/`handlers.test.ts`/`fixtures*.test.ts` (stage names, `fail-code`), `e2e_review/mobile.spec.cjs:41-45` (selects `#rating-globals-cct-score`, "Submit rating") and `session-flow.spec.cjs:42-51` (W2/E17 draft-persistence through card; drop, covered by vitest autosave suite with flag on). Stryker `mutate` (auth + api/errors) unaffected; no config change.
- `npm run typecheck`, `lint`, `test`, `e2e`, `check:api` green; build output contains no new env requirement.
