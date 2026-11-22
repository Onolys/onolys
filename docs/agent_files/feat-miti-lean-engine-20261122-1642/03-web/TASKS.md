---
status: draft
summary: 6 tasks - flag + timeline/mocks on new stage names, upload-screen goal field with one submit, interview and fallback paths, flag-gated report, dashboard copy and e2e
date: 2026-11-22
---
# Tasks: SP03 web hides the rating card, MITI-only report
Source of truth: /root/projects/onolys/iaudit/.worktrees/feat/miti-lean-engine/docs/agent_files/feat-miti-lean-engine-20261122-1642/03-web/PRD.md. Web only (`web/`); api is untouched. Each task writes its tests first, runs only the tests it touches, and ends with a commit. Depends on SP02 for stage names `code|tips|assemble` and the report `run_info` renames.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Rating flag, timeline copy, mock stage names | - | todo |
| 2 | Upload screen: change goal + one submit | 1 | todo |
| 3 | Interview End flow and session-page fallback | 2 | todo |
| 4 | Report shows Onolys coding + tips only | 1 | todo |
| 5 | Dashboard copy and sample report | 4 | todo |
| 6 | Update affected tests and e2e, full web gate | 2, 3, 5 | todo |

## Task 1 — Rating flag, timeline copy, mock stage names
What it is / what it means: A single build-time switch `VITE_RATING_ENABLED` (absent = off) decides whether any clinician-rating UI exists. This task also moves the progress labels and the mock worker onto the new stage names only (D2, D5, R1, R4, R7).
What changes at a high level: Add the flag accessor as a function so tests can stub it, and document it in the env example. The timeline derives "Session setup" wording when off and today's wording when on, with sublabels keyed only on `code|tips|assemble` and unknown or null falling back to "Coding the session". The mock state machine walks `code,tips,assemble` with SP02 weights, renames the failure marker to `fail-code`, and drops the reasons-failure path. Default mock run report becomes the no-rating fixture with `run_info.miti`; regenerate the report type so `check:api` is clean.
Done when: tests written first for the flag accessor, timeline table (`code,tips,assemble,zzz,null`, both flag states), and mock stage/failure behaviour pass; no legacy stage names remain in web; `check:api` clean.

## Task 2 — Upload screen: change goal + one submit
What it is / what it means: With the flag off, `/sessions/new` is audio + a required "Change goal" + the existing single "Start" button. No time-range field, no separate setup screen (D1, D3, D3b, D3d, R3).
What changes at a high level: A new goal-field component beside the rating card (card untouched) reuses the card helpers for validation and payload. Submit gate also needs a non-blank goal. One click runs: create session, `PUT /rating` as final no-rating card with only the goal, then audio registration and upload. A 422 shows a field message and registers no audio; a 409 `rating_final` on retry counts as success; an audio failure after a good PUT retries without a second PUT. Flag on keeps the old behaviour with no goal field.
Done when: tests first covering call order, goal-only payload (never `coded_span`), blank-goal block, 422, 409-as-done and no-double-PUT retry pass; flag-on variant shows no setup fields.

## Task 3 — Interview End flow and session-page fallback
What it is / what it means: The two paths that reach a session without the upload screen must still set the goal and start the first run (D3c, R2, R3).
What changes at a high level: In the AI-interview End flow, after the session is created, read the seeded draft goal and send the same final no-rating `PUT`, tolerate 409 on resume, then continue to upload. The session page's rating slot renders the card only with the flag on; with it off it renders nothing, except a fallback "Continue" form (goal field, prefilled from the draft, PUT only) for sessions still unsubmitted and not deleting. If the draft goal is missing, the fallback appears.
Done when: tests first show interview End order (create, read draft, PUT, upload), 409 resume, no card or `#rating-globals-*` with flag off, fallback shown only when unsubmitted, and the original card shown with flag on.

## Task 4 — Report shows Onolys coding + tips only
What it is / what it means: Remove every comparison part of the report unless the flag is on (D4, R5).
What changes at a high level: The report treats "rated" as flag-on AND has-clinician-rating. Off: Scorecard keeps Item + Onolys only (no "You", "Difference", or unrated note), Behaviours loses its "You" column, Summaries ignore clinician text, Disagreements and Reasons audit return nothing, and the reasons-withheld warning is skipped. Tips and Method unchanged. Old rated reports get no special handling.
Done when: tests first prove the rated fixture still renders Onolys-only with the flag off (no "You" column, no Disagreements/Reasons, tips visible) and the full comparison renders with the flag on.

## Task 5 — Dashboard copy and sample report
What it is / what it means: Remaining user-facing text must stop promising a comparison (R6, R5 tail).
What changes at a high level: The dashboard intro says Onolys codes a recorded session against the MITI with evidence and tips (old sentence when flag on). The sample report page switches to the no-rating fixture.
Done when: dashboard and sample-report tests pass for both flag states.

## Task 6 — Update affected tests and e2e, full web gate
What it is / what it means: Bring remaining suites and Playwright flows in line with the one-submit, no-card default (Acceptance Criteria, tests-changed list).
What changes at a high level: Update the session, flow, interview and new-session suites that asserted the card or "Rating the session"; move comparison asserts into flag-on blocks; adjust the mobile and session-flow e2e specs to fill goal + audio, Start, confirm speaker, and see a report with no "You", "Difference", disagreements or reasons and "Coding the session" progress. Drop the card draft-persistence e2e, covered by the autosave unit suite with the flag on.
Done when: typecheck, lint, test, e2e and `check:api` are green; build adds no new env requirement; CI workflow needs no change.
