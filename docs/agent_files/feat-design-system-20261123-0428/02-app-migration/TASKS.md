---
status: draft
summary: Nine shippable tasks migrating web/ to @onolys/ui v0.1.0 via a layered legacy bridge, with CSP and dark-mode gates, then legacy cleanup.
date: 2026-11-23
---
# Tasks: 02 Migrate web/ to @onolys/ui
Source of truth: docs/agent_files/feat-design-system-20261123-0428/02-app-migration/PRD.md. One PR per task, each revertable alone; role/name-based RTL tests stay green throughout and merged #52/#54 shell, routes and report behaviors (PRD Requirements 5–7) are preserved.

| # | Task | Depends on | Status |
|---|------|-----------|--------|
| 1 | Phase 0: deps, CSS entry, shims, baseline | SP1 v0.1.0 + merged #52/#54 baseline | todo |
| 2 | Phase 0: CSP smoke, visual and axe gates | 1 | todo |
| 3 | Phase 1: shell | 2 | todo |
| 4 | Phase 2: auth | 3 | todo |
| 5 | Phase 3: chooser, sessions, upload, interview | 4 | todo |
| 6 | Phase 4: session page | 5 | todo |
| 7 | Phase 5: shared report and coded-transcript dialog | 6 | todo |
| 8 | Phase 6: settings and legal | 7 | todo |
| 9 | Phase 6: legacy cleanup | 8 | todo |

## Task 1 — Phase 0: deps, CSS entry, shims, baseline
**What it is / what it means:** Install the design system and switch the app's CSS entry without changing how any screen looks in light mode (Decisions 1, 2).
**What changes at a high level:** Add the tag-pinned git dependency and Tailwind; single layered CSS entry with old styles wrapped in a low-priority legacy layer and old token names bridged via SP1 legacy aliases; vitest setup retains existing native dialog/scrollIntoView shims and adds only missing Radix shims; document and verify the local `file:` link source path; confirm `npm ci` over git+https with no SSH and that the PR-preview install covers the git dep; record bundle baseline and soft budget (+25%, warning only); check the build-test style-injection concern and `data-slot` collisions.
**Done when:** build, unit tests, lint, typecheck green; build/hosting/privacy tests pass (or the single approved change); light screenshots of unmigrated screens show no preflight regressions; baseline recorded.

## Task 2 — Phase 0: CSP smoke, visual and axe gates
**What it is / what it means:** The runtime proof that the strict CSP still holds, plus the dark-mode evidence harness (Decisions 5, 6).
**What changes at a high level:** New Playwright project serving the built app with the exact CSP from the hosting config; MSW only where needed, with worker-src allowed in the test server config only; zero-violation listener; light/dark screenshot spec uploaded as a CI artifact; axe contrast gate in both schemes; CI web-e2e runs the new project.
**Done when:** CSP smoke passes with zero violations on the Phase 0 screens (skeleton), screenshots artifact appears in CI, axe gate runs, existing e2e specs still pass.

## Task 3 — Phase 1: shell
**What it is / what it means:** Header, footer, account menu, skip link, error and 404 pages move to design-system components.
**What changes at a high level:** Layout and footer use the shared header/footer; account menu becomes the shared dropdown keeping email label, Settings, Sign out, Escape-returns-focus; signed-out centered /sample link and verified /sessions, /new, /sample navigation preserved, including safe new-tab sample links; unverified remains brand-only; compact two-row footer and / → /new plus /sample-report → /sample redirects preserved; focus-to-h1 on route change kept; shrink legacy styles used.
**Done when:** layout and legal RTL tests green by role/name; mobile and signed-out e2e green; CSP smoke covers account menu; light/dark screenshots and axe clean for shell.

## Task 4 — Phase 2: auth
**What it is / what it means:** Login, Signup, Forgot password, Verify email and auth-action screens use shared form components.
**What changes at a high level:** Inputs, labels, buttons, alerts and cards replace hand-built markup; VerifyEmail keeps centered layout and "Use a different email". Decide here whether to split the large auth-action screen: only if more than half of it is touched.
**Done when:** auth page tests green (fireEvent uses re-checked); light/dark screenshots and axe clean for auth screens; split decision recorded.

## Task 5 — Phase 3: chooser, sessions, upload, interview
**What it is / what it means:** NewSessionChooser, SessionsPage, upload and interview screens move to shared components.
**What changes at a high level:** Cards, badges, native selects, alerts, usage meter and skeletons replace custom ones; preserve chooser links and cap/usage behavior plus session polling, pagination, errors/empty states, report links and status chips; keep current behavior queries working.
**Done when:** NewSessionChooser, SessionsPage, Interview and flows tests green; CSP smoke covers native Select choose/change; screenshots and axe clean in both schemes.

## Task 6 — Phase 4: session page
**What it is / what it means:** Session timeline, errors, rating and speaker gate adopt shared components while preserving existing modal behavior.
**What changes at a high level:** Delete confirmation becomes the alert-dialog (role change, affected assertions updated); class-based assertions move to data attributes; test helpers fixed so Radix aria-hidden on siblings does not hide `main()`; `data-slot` hooks kept.
**Done when:** session and rating tests green; CSP smoke covers the delete dialog; screenshots (each status, dialog open) and axe clean.

## Task 7 — Phase 5: shared report and coded-transcript dialog
**What it is / what it means:** Real and sample pages retain shared ReportView and native CodedTranscriptDialog while adopting shared tables, score/status badges, cards and buttons.
**What changes at a high level:** Preserve At a glance five-segment scales/summary table, feedback and evidence utterance links, counts, method/limits and real/sample controls. Style native CodedTranscriptDialog and responsive/sticky tables with tokens/primitives; preserve opener focus, Escape/Close/backdrop protection, scroll lock/cleanup, pointed-row centering/highlight and reduced-motion behavior. No deleted report tabs, score dots or standalone transcript panes are reintroduced.
**Done when:** ReportPage, SampleReportPage, ReportView, CodedTranscriptDialog, UtteranceLink and codedRows tests green; CSP smoke covers mobile native dialog open/close and pointed utterance navigation/focus return; screenshots and axe clean in both schemes.

## Task 8 — Phase 6: settings and legal
**What it is / what it means:** Settings, the secret dialog and legal pages move; the custom modal goes away.
**What changes at a high level:** Secret dialog uses the shared dialog with Escape and outside-click disabled; legal pages use shared card/separator, text and routes unchanged; the hand-rolled modal removed.
**Done when:** Settings test (no Escape close) and legal tests green; CSP smoke covers the secret dialog; screenshots and axe clean.

## Task 9 — Phase 6: legacy cleanup
**What it is / what it means:** Remove the bridge so only the design system styles the app (Decision 1; acceptance 2, 6, 7, 8).
**What changes at a high level:** Delete legacy app CSS, old tokens, font CSS and the alias import; styles folder holds only the entry; final bundle delta reported against the Phase 0 baseline; privacy, hosting and build tests re-checked.
**Done when:** grep for old style names in web source returns nothing; full unit, lint, typecheck, e2e, CSP smoke and axe green; bump procedure (lockfile only) documented.
