---
status: draft
summary: 10 tasks - onolys-ui Spinner+Progress and release prep (cross-repo), server progress contract, contract regen + mocks, web steps/hint, progress.ts + hook, ui dependency bump, SessionPage visuals, docs, visual e2e.
date: 2026-11-23
---
# Tasks: SP05 Processing screen clarity
Source of truth: docs/agent_files/feat-session-ux-logging-claude-email-20261123-2252/05-processing-screen/PRD.md. No [OPEN] items; the re-run Elapsed reset is DEFERRED, calibration constants are placeholders (R6). SP05 lands last (after SP03 failed card/`upload_failed` stub and SP04 `cancelled` state + `isCancellable`). Tasks 1-2 are in the separate repo `/root/projects/onolys/onolys-ui` (own branch/worktree, own PR). No CI change needed (`.github/workflows/ci.yml` exists). Tests use FakeRepo, MSW and the mock backend, no live API.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | onolys-ui: Spinner and Progress components | - | todo |
| 2 | onolys-ui: release prep (version, changelog) | 1 | todo |
| 3 | API: progress fields on status doc and detail | - | todo |
| 4 | Contract regen, mocks, status-doc note | 3 | todo |
| 5 | Web: timeline steps and hint | 4 | todo |
| 6 | Web: progress.ts and useSessionStatus | 4 | todo |
| 7 | Bump @onolys/ui to the new tag | 2 (+ owner step: tag) | todo |
| 8 | Web: SessionPage steps, bar, hint, cancel slot | 5, 6, 7 | todo |
| 9 | Docs: user-rating concept and hint consistency | 8 | todo |
| 10 | Visual e2e shots and mock state-machine alignment | 8 | todo |

## Task 1 — onolys-ui: Spinner and Progress components
What it is / what it means: The two library components the processing screen needs, built in the UI library, not inline. Traces to R4, R8, Cross-repo dependency, AC10.
What changes at a high level: In `/root/projects/onolys/onolys-ui` on a new branch/worktree off its main, add `Spinner` and `Progress` in `src/components/ui/` and export both from `src/index.ts`, following the repo's token, 44px-target and CSP conventions (no injected styles). `Spinner`: `aria-hidden`, `motion-safe:animate-spin`, static ring under reduced motion. `Progress`: native `<progress>` taking caller `aria-label`/`aria-valuetext`, no bar transition under reduced motion. Add Storybook stories (light/dark) per the repo's story-coverage test.
Done when: new component unit tests pass (renders native `<progress>` with value/max and caller label; Spinner has `aria-hidden` and the `motion-safe` class); the export/package, privacy and storybook-coverage tests pass with both components present; Storybook a11y check clean in both themes.

## Task 2 — onolys-ui: release prep (version, changelog)
What it is / what it means: Make the library ready for a new install tag so iaudit can depend on it. Traces to Cross-repo dependency, AC10.
What changes at a high level: In onolys-ui, bump `package.json` and `package-lock.json` to the next minor (v0.3.0 unless that repo's process dictates otherwise) and add a dated CHANGELOG section listing Spinner and Progress, so the three agree as the release README requires. Open the onolys-ui PR; the agent stops there (tagging is an owner step).
Done when: `src/release.test.ts` (version/changelog agreement) passes and the repo's CI is green on the PR; the PR is ready for review with the exact source commit named.

## Task 3 — API: progress fields on status doc and detail
What it is / what it means: The server publishes the numbers the web needs to show honest progress and Elapsed. Traces to R2, R6, D1, D2, D6, AC9.
What changes at a high level: Add `started_at`, `stage_started_at`, `waited_ms`, `audio_s`, `progress_next`, `stage_expected_s` to the `session_status` doc, its allowlist (`STATUS_FIELDS`) and `SessionDetail`. `advance` sets `started_at` on first `uploading` (and at re-run start), mirrors `stage_started_at`, accumulates `waited_ms` on leaving `awaiting_input`, and writes `progress_next` (cap 99 on the last stage); `validate` writes `audio_s` from `duration_ms`; `progress_cb` updates `progress_next`. One server table holds stage expected durations (transcription `clamp(20 + 0.2 x audio_s, 30, 600)`; others placeholders) and `STATE_PROGRESS`/`STAGE_WEIGHTS` values stay unchanged. Numbers and timestamps only, no text.
Done when: `advance` unit tests cover `started_at` (first upload, re-run), `waited_ms` across an await, and `progress_next` per state/stage incl. the 99 cap; the expected-duration function is tested at the clamp bounds and with unknown `audio_s`; the allowlist/no-text test (AC11) passes with the new fields; the detail route returns them.

## Task 4 — Contract regen, mocks, status-doc note
What it is / what it means: Make the shared contracts, web types and mock backend know the new fields. Traces to R2, AC9, mock-alignment resolution.
What changes at a high level: Regenerate `api/openapi.json`, `docs/contracts/public` and `web/src/api/schema.d.ts` (shared files: rebase on whatever SP03/SP04/SP07 already regenerated, regenerate last). Update `web/src/mocks/**` to emit the new fields and replace the mock's `[85, 93, 100]` progress with the real table. Add the new progress fields to the `docs/reference/` status-doc note.
Done when: the repo's contract drift/consistency check passes (openapi, public contracts and `schema.d.ts` agree); the updated `stateMachine.test.ts` passes with progress values matching the server table and the 99 cap; the reference note lists every new field.

## Task 5 — Web: timeline steps and hint
What it is / what it means: The pure logic for which six steps show, which is current, and which one-line hint applies. Traces to R1, R5, D5, D7, AC1, AC6.
What changes at a high level: In `timeline.ts` set visible keys to upload, transcribe, speaker, rating (only when `ratingEnabled()`), run, report; remove `validate` and the "Session setup" row; fold validating into transcribe as sub-label "Checking audio"; apply the R1 state table (failed placement, `cancelled`/`deleting` all pending, `upload_failed` not a timeline). Rating-off awaiting-input line reads "Waiting for your change goal". Add the hint output per the R5 phase table; drop "Usually under 5 minutes".
Done when: `timeline.test.ts` is table-driven over every state x `ratingEnabled` and passes for rows, current/failed marker, sub-labels and awaiting-input line; hint tests assert the exact copy per phase and "none" for terminal states; no "Check audio"/"Session setup"/"Usually under 5 minutes" strings remain in `web/src`.

## Task 6 — Web: progress.ts and useSessionStatus
What it is / what it means: The pure percent/Elapsed calculation, and the hook fixes that make it correct after reload. Traces to R3, D2, D3, D4, AC3, AC4, AC5.
What changes at a high level: New `progress.ts` with `deriveProgress(doc, now, uploadFraction?)` returning pct, elapsedMs, frozen, hidden: upload uses base plus real byte fraction (base only with no counter); timed stages use `1 - exp(-t/stage_expected_s)` capped below the next base; `awaiting_input` and its Elapsed freeze; `report_ready` is 100; failed/cancelled return hidden. `useSessionStatus` uses the real `updated_at` in `detailToDoc`, keeps the max pct within a state, and ticks only while a timed state is active. `UploadSlot.tsx` reports the byte fraction only.
Done when: new `progress.test.ts` passes for monotonic in t, always below `progress_next` while in-stage, never above 99 before `report_ready`, never below server `progress`, frozen pct/Elapsed over 10 simulated minutes in `awaiting_input`, unknown `audio_s` default, hidden on failed/cancelled; hook tests show a reload mid-transcription keeps Elapsed, a fallback-poll doc behaves the same, and a late lower doc cannot move the bar back.

## Task 7 — Bump @onolys/ui to the new tag
What it is / what it means: Point iaudit's web at the library release containing Spinner and Progress. Traces to Cross-repo dependency, AC10. Blocked until the owner has merged the onolys-ui PR and pushed the release tag (Owner steps).
What changes at a high level: Change the `@onolys/ui` ref in `web/package.json` from `#v0.2.0` to the new tag and refresh `web/package-lock.json`. No other dependency changes.
Done when: a clean `npm ci` in `web/` succeeds against the new tag; a throwaway-free check shows `Spinner` and `Progress` resolve from `@onolys/ui` (type-check/build of the web app passes with the imports in Task 8, or an existing import test of the package passes); lockfile diff touches only this package.

## Task 8 — Web: SessionPage steps, bar, hint, cancel slot
What it is / what it means: The visible screen. Traces to R4, R5, R7, R8, D1, AC2, AC3, AC7, AC8, AC10.
What changes at a high level: In the steps/progress/hint region of `SessionPage.tsx` only: step rows per R4 (done = check + `text-score-good`; current = `Spinner` + visible "In progress" + `text-primary`/`border-primary`; pending muted; failed destructive); `Progress` bar, "N%" and Elapsed above the list in every non-terminal state from `created` (hidden when `hidden`); one-line hint under the bar outside the live region; `<div data-slot="cancel">` right-aligned under the hint rendered iff SP04's `isCancellable(state)`. Status lines stay in the `role="status" aria-live="polite"` block and change only on step change; bar has `aria-label="Overall progress"` and `aria-valuetext`; imports Spinner/Progress from `@onolys/ui`, no inline spinner SVG.
Done when: `SessionPage.test.tsx` passes for hint per phase, bar/% /Elapsed present in upload and transcribing and absent at `report_ready`/`failed`/`cancelled`, "In progress" text and accent class on the current step, bar accessible name/value, live-region text unchanged across ticks, cancel slot present for every cancellable state and absent otherwise, reduced-motion (no spin class active); a grep test/check finds no inline spinner SVG.

## Task 9 — Docs: user-rating concept and hint consistency
What it is / what it means: Keep project docs true to the new screen. Traces to R9, AC12.
What changes at a high level: Make `docs/concepts/user-rating.md` state that self-rating is not offered today (flag off, code dormant) and agree with the "You can close this tab — we'll keep working" hint; link it from `docs/concepts/README.md`. Confirm the rating step is described as appearing only when `ratingEnabled()`.
Done when: the file exists, is linked from the concepts index (link check or grep passes), its statements match R5 copy and `ratingEnabled()` behaviour verified in code; the repo's docs check (if any) passes.

## Task 10 — Visual e2e shots and mock state-machine alignment
What it is / what it means: Proof of the screen in a browser, per phase, in both themes. Traces to AC2, AC7, AC11, D6.
What changes at a high level: Add one shot per phase (upload, background, waiting) to `web/e2e_review/visual.spec.cjs` in light and dark, driven by the mock backend with the new progress fields; check reduced-motion emulation shows no animation. Final pass on `stateMachine.test.ts` against the mock.
Done when: the visual spec runs and passes locally (shots show spinner + "In progress", bar/%/Elapsed, hint; dark mode legible); reduced-motion case asserts no animated spinner; `stateMachine.test.ts` passes. Full suites run only in dev-ship.

## Owner steps
- Review and merge the onolys-ui PR (Tasks 1-2), then push the release trigger tag (`release/v0.3.0` or next) per that repo's README; the workflow creates the install tag `v0.3.0`. Task 7 is blocked until the tag exists.
- Staging deploy of api + web via the normal workflow (PRD: no other manual steps); calibrating `stage_expected_s`/weights after SP01+SP02 timings exist is later follow-up work (R6), not in this task list.
