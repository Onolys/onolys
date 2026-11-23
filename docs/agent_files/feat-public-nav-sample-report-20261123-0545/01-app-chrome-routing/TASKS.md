---
status: draft
summary: Compact footer, three-button nav, /new chooser + /sessions list split, public /sample route with /sample-report redirect, re-pointed navigate targets.
date: 2026-11-23
---
# Tasks: App chrome and routing
Source of truth: 01-app-chrome-routing/PRD.md. Pure front-end restructure, no API/schema change. CI (`.github/workflows/ci.yml`) already runs web tests, so no CI task. Tests are written first in every task; run only the impacted tests.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Compact footer | none | done |
| 2 | Split Dashboard into /new and /sessions pages | none | done |
| 3 | Routes, redirects and public /sample | 2 | done |
| 4 | Nav buttons and re-pointed targets | 3 | done |

## Task 1 — Compact footer
What it is / what it means: The single `Footer` shrinks to two small lines used by every route (PRD Requirements 1-3, Decision 3).
What changes at a high level: Rewrite footer markup to the two specified lines (disclaimer; Privacy, Terms, Contact, current year Onolys), no "Questions?" line, no "All rights reserved". Tighten `.app-footer*` rules in `app.css` (small type, small vertical padding, no border, CSS dot separators). No inline `style=`.
Done when: updated footer assertions pass in `routes/legal.test.tsx` (text, Privacy/Terms link names), `routes/layout.test.tsx` (footer part) and `routes/routes.flaky.test.tsx`; a test asserts absence of "Questions?" and "All rights reserved" and the `mailto:` Contact.

## Task 2 — Split Dashboard into /new and /sessions pages
What it is / what it means: Move code along the existing seam in `Dashboard.tsx` with no logic rewrite (Requirements 10-13, Decision 5).
What changes at a high level: Create `NewSessionChooser` (the two landing cards, interview cap/usage behaviour intact, h1 "New Session", no Sessions heading) and `SessionsPage` (query, polling, chips, Report vN links, error card, Load more, h1 "Sessions"; empty state links to `/new`, no sample link). Remove or reduce `Dashboard`; keep shared helpers importable.
Done when: `Dashboard.test.tsx` is split into new-session and sessions tests covering cards, disabled cap button, polling/chips/Load more, and empty-state link to `/new`; all pass rendering each page directly.

## Task 3 — Routes, redirects and public /sample
What it is / what it means: Router wiring (Requirements 7-9, Decisions 1, 4).
What changes at a high level: In `routes.tsx`, `/` redirects to `/new`; guarded `/new` and `/sessions`; public `/sample` rendering the existing `SampleReportPage` (not edited) and `/sample-report` redirecting to `/sample`. Update tests that land on `/` to assert the `/new` h1 and list tests to render `/sessions` (`auth/pages.test.tsx` incl. pathname `/new`, `auth/guards.test.tsx`, `routes/routes.test.tsx`, `flows/flows.test.tsx`). In `SampleReportPage.test.tsx` change only the route string.
Done when: new tests pass: `/` ends at `/new`; `/sample-report` ends at `/sample`; `/sample` reachable signed out; signed-out `/new` goes to login with `next=/new`; the updated tests above are green.

## Task 4 — Nav buttons and re-pointed targets
What it is / what it means: Nav per auth phase and deliberate link targets (Requirements 4-6, table of re-pointed sites, Decisions 2, 6).
What changes at a high level: `Layout.tsx` nav: verified shows `Sessions` (end match), `New Session`, `Sample report` as `btn btn-secondary` buttons; signed-out shows a centred Sample report with Log in/Sign up right (CSS only); sample link is a plain `Link` with `target=_blank rel="noopener noreferrer"`; other phases unchanged. Re-point the listed navigate/link sites in `SessionPage`, `InterviewPage`, `NewInterviewPage`, `placeholders.tsx` to `/sessions` or `/new` as tabled; `RouteError` unchanged. Nav styling appended in its own block of `app.css`.
Done when: `layout.test.tsx` (nav names per phase incl. target/rel, no active state on sample, "New Session" label), `routes.test.tsx`, `flows.test.tsx` and one test per re-pointed navigate (delete session, discard interview, back links, Not now, Cancel, NotFound) pass. E2E `mobile.spec.cjs` PUBLIC list and `signed-out.spec.cjs` route updated to `/sample` (owner-run).

## Closing note — manual steps
No deploy steps beyond the normal app deploy. Owner visually checks nav centring at phone width and runs the e2e_review specs. Land this branch before feat/design-system (it rebases).
