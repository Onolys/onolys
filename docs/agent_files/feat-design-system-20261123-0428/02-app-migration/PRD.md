---
status: draft
summary: Migrate web/ (main app) from hand-built CSS to @onolys/ui v0.1.0 in phases behind a layered legacy bridge, preserving roles/tests and the strict CSP, with dark-mode and CSP Playwright gates.
date: 2026-11-23
---
# PRD: 02 Migrate web/ to @onolys/ui

Repo/branch: `Onolys/onolys`, `feat/design-system` (one PR per phase, each shippable) · Depends on: SP1 tag `v0.1.0`; merged #52 and #54 preservation baseline (branch rebased onto main `d88fbc6`) · Owns: `web/package.json`, `web/vite.config.ts`, `web/src/styles/*`, `web/src/main.tsx`, all `web/src/**/*.tsx` markup/classes, `web/src/test/setup.ts`, `web/e2e_review/*`, `.github/workflows/ci.yml`

## TL;DR
Add `@onolys/ui` (git dep, tag-pinned) + Tailwind v4 Vite plugin. Phase 0 swaps the CSS entry and wraps old `app.css` in a low-priority CSS layer so nothing changes visually in light mode. Phases 1-6 migrate screen groups to SP1 components and shrink the legacy layer. Last phase deletes `app.css`, `tokens.css`, `inter-latin.css`, the SP1 `legacy.css` alias. Dark mode arrives per screen as it is migrated (and for unmigrated screens via aliased tokens). Role/name-based RTL tests stay; class-based assertions move to `data-*`. New: Playwright CSP smoke (built app + real CSP header) and light/dark screenshots + axe contrast.

## Problem
The app uses hand-built forms, dialogs, account-menu behavior and light-only styles. SP1 ships shared replacements. Migration must preserve the current merged #54 navigation, split start/session pages, and shared real/sample report with its native coded-transcript dialog, alongside the earlier email-verification behavior. Baseline: main `d88fbc6`; the merged #54 design is recorded in `docs/agent_files/feat-public-nav-sample-report-20261123-0545/`.

## Goals / Non-Goals
**Goals**
- Every web screen uses `@onolys/ui` primitives; dark mode correct on every screen.
- Preserve merged #52/#54 behavior (Requirements 5–7).
- Existing accessible names/roles unchanged; `privacy.test.ts`, `hosting.test.ts`, `build.test.ts` stay green without loosening (except the one flagged in Risks).
- Each phase deployable alone; rollback = revert that PR.

**Non-Goals**
- Behaviour/copy/route changes; API changes; manual theme toggle; landing (SP3) and admin (SP4); new features.

## Requirements
1. **Dependency + build**: `npm i github:Onolys/onolys-ui#v0.1.0` (exact tag, lockfile committed), `tailwindcss` + `@tailwindcss/vite` (versions per SP1). `vite.config.ts`: `plugins: [react(), tailwindcss(), dropMockWorker(mode)]`. Gate tailwind on `mode !== "test"` only if vitest slows; never on `process.env.VITEST`, because `build.test.ts` calls `vite.build()` inside vitest and must exercise the real CSS pipeline. [verified: build.test.ts runs `build({configFile})`]
2. **CSS entry** `web/src/styles/index.css` (replaces the existing style imports in `main.tsx`):
   `@layer theme, base, legacy, components, utilities; @import "tailwindcss"; @import "@onolys/ui/theme.css"; @import "@onolys/ui/fonts.css"; @import "@onolys/ui/legacy.css"; @import "./legacy-app.css" layer(legacy); @source "../../node_modules/@onolys/ui/dist";`
   Rationale: unlayered `app.css` would beat all Tailwind utilities and preflight (unlayered > layered), so old rules must sit in a named layer below `components`/`utilities`. `legacy-app.css` = today's `app.css`, with `tokens.css` deleted and old `--color-*` names served by SP1's `legacy.css` alias [RESOLVED: orchestrator default 2026-11-23 — bridge via SP1 `legacy.css` until Phase 6 cleanup; if SP1 drops it, web keeps private `legacy-tokens.css` removed in Phase 6; verified in Task 1]. Preflight resets `h1`/`button`/`a` defaults, so Phase 0 must be eyeballed in light before merging.
3. **Decision: bridge, not big bang.** Migrate screen groups separately so each phase is reviewable; the bridge adds an initial compatibility phase. Final phase deletes `legacy-app.css` and the alias import; CI check: `grep -r "legacy" web/src/styles` empty.
4. **Phases** (each: migrate, update tests, light+dark screenshots, merge):
   | # | Scope | Components |
   |---|---|---|
   | 0 | deps, vite, CSS entry, test setup shims, CSP smoke skeleton | none |
   | 1 | Shell: `Layout.tsx`, `Footer.tsx`, `AccountMenu.tsx`, skip link, `RouteError`, 404 (`placeholders.tsx`) | AppHeader, SkipLink, Footer, DropdownMenu, Button |
   | 2 | Auth: Login, Signup, ForgotPassword, VerifyEmail, AuthAction (many states), `parts.tsx` | Input, Label, Button, Alert, Card |
   | 3 | NewSessionChooser (start cards and usage), SessionsPage (session list and status chips), NewSession/Upload (drop zone, file notices), NewInterview/Interview | Card, Badge, Select (styled native), Alert, UsageMeter, Skeleton |
   | 4 | Session page (timeline, ErrorCard, DeleteDialog, speaker gate), RatingCard/Setup fields | AlertDialog, Alert, Card, Textarea, Select, Checkbox |
   | 5 | ReportPage + SampleReportPage share ReportView; CodedTranscriptDialog and UtteranceLink | Table, ScoreBadge, Badge, Card, Button; preserve native dialog |
   | 6 | Settings + secret dialog (`Modal.tsx` deleted), legal pages (`LegalPage/PrivacyPolicy/Terms`), final cleanup (delete legacy CSS) | Dialog, Card, Separator |
5. **Current shell/routes preserved** (merged #52/#54; verified against `Layout.tsx`, `Footer.tsx`, `routes.tsx` and focused tests):
   - Signed out: centered `Sample report` button links to `/sample` in a new tab with `target="_blank" rel="noopener noreferrer"`; `Log in` and primary `Sign up` remain right-aligned, with responsive wrapping.
   - Verified: `Sessions` → `/sessions`, `New Session` → `/new`, `Sample report` → `/sample` in the same safe new-tab form; account menu retains email label, Settings, Sign out, menu roles, keyboard handling and Escape focus return.
   - Unverified: brand-only header, no nav items or avatar. Brand retains `/`; `/` redirects to guarded `/new`; public `/sample-report` redirects to `/sample`.
   - Compact two-row footer: three notices, then Privacy/Terms/`mailto:` Contact/copyright; no extra contact paragraph. Preserve dark-teal treatment in both themes and responsive layout.
   - `/privacy`, `/terms`, existing session/interview/report routes and copy stay; VerifyEmail remains centered with "Use a different email". Delete/discard/back-to-sessions targets remain `/sessions`; abandoned start flows retain `/new` targets.
   - Focus-to-h1 on route change in `Layout` stays. NewSessionChooser retains start links and usage/cap behavior; SessionsPage retains polling, pagination, loading/error/empty states, status chips and report links.
6. **Dialogs**: Settings secret dialog retains its no-Escape/no-outside-close contract using shared Radix Dialog handlers. DeleteDialog becomes shared AlertDialog with the appropriate `alertdialog` role; update affected role assertions and retain opener focus. The report’s CodedTranscriptDialog remains native `<dialog>`: migrate styling/table/buttons without replacing its native modal behavior.
7. **Shared report preserved**: ReportPage and SampleReportPage continue using ReportView, in order: header, At a glance, Feedback: ideas to try, Behaviour counts, Coded transcript, Method & limits. Preserve global five-segment scales, summary values/statuses, evidence-to-utterance mapping, quotes and method/limits. The removed ReportSections score-dot positioning, tabs and standalone transcript components are not migration targets. Keep real report version routes/selection and parallel transcript loading/retry; sample remains public, zero-network and without real-report controls. CodedTranscriptDialog preserves `utt-N` rows, code/rationale table and legend, native Escape/Close, opener focus return, scroll locking/cleanup, deliberate-backdrop-click protection (not drag-to-backdrop), centered pointed-row scrolling and temporary highlight, with instant scrolling/static highlight under reduced motion. Preserve responsive table scrolling, sticky headers and mobile dialog layout using shared tokens/primitives and app utilities.
8. **Tests**:
   - Preserve role/text contracts in routes/layout/legal/routes tests, auth tests, NewSessionChooser/SessionsPage tests, Interview/flows, session/rating/settings tests, and ReportPage/SampleReportPage/ReportView/CodedTranscriptDialog/UtteranceLink/codedRows tests. Re-check pointer/keyboard queries when introducing Radix and scope queries appropriately around modals.
   - Re-check current class assertions against actual tests before changing them; replace styling-only hooks with state/data hooks when necessary without dropping behavioral assertions. Preserve existing upload/speaker/rating data-slot hooks and check for primitive collisions.
   - Extend existing test/setup.ts native dialog and scrollIntoView shims with missing Radix shims only (ResizeObserver, pointer capture, DOMRect, matchMedia as needed); retain native dialog tests.
   - New `e2e_review/csp.spec.cjs` and `visual.spec.cjs` cover the preserved shell, routes, split pages and shared report/dialog flows.
9. **CSP smoke** (gate, runs in `web-e2e`): `npm run build -- --mode mock` then `vite preview` with `preview.headers` carrying the exact CSP string read from `firebase.json` (via `src/hosting/csp.ts` `readHosting/cspOf`), so test and prod can't drift. Playwright listens for `securitypolicyviolation` and console CSP errors while: opening account menu; Settings secret dialog; session DeleteDialog; native coded-transcript dialog open/close, pointed utterance scrolling/highlight and focus return at mobile viewport; focus rings; native Select choose/change; tooltips (if used). Zero violations required. The dev-server e2e currently runs with no CSP [verified: `playwright.config.cjs` webServer = `dev:mock`], hence the separate project.
10. **Visual + a11y**: `visual.spec.cjs` iterates `colorScheme: light|dark` × {login, signup, verify, /new chooser, /sessions list, upload, session (each status), report, sample report, settings, dialogs open, privacy, 404, mobile 390px}; screenshots to `test-results/shots/` uploaded as CI artifact (no pixel diff gate). `@axe-core/playwright` (new devDep in web) gates `color-contrast` + critical violations in both schemes [RESOLVED: 2026-11-23 — approved; `privacy.test.ts` only bans analytics names].
11. **Dark-mode checklist** per screen (PR template item): text/bg ≥4.5:1, UI/focus ≥3:1; status chips and report score/status/code chips, five-segment scales, pointed-row highlight and reduced-motion outline, report/table surfaces, timeline/drop-zone borders, disabled opacity, errors and compact footer. Audit actual assets at migration time. `color-scheme: light dark` comes from SP1 base so native controls/scrollbars follow.
12. **Privacy/lint constraints** re-checked each phase: no storage, no absolute URLs, ≤2 console calls, no `dangerouslySetInnerHTML`, only `firebase/*` imports allowed by name (Radix/ui imports are fine) [verified: `privacy.test.ts` scans only non-test `web/src`, and `node_modules` is outside it]. `lint.test.ts`/jsx-a11y stay on; shadcn code lives in `node_modules`, not linted.

## Architecture
```
web/src/styles/index.css      # entry: layers, tailwind, @onolys/ui theme+fonts, legacy layer (deleted in Ph6)
web/src/styles/legacy-app.css # old app.css, layer(legacy), shrinks each phase
web/src/main.tsx              # single CSS import
```
Select uses SP1’s styled native `<select>` with native `<option>` children and native props; do not import Radix-only Select helpers. SP1 Task 7 measured two inline `style-src-elem` violations from Radix Select under `style-src 'self'`; the user delegated the policy choice and the orchestrator retained strict CSP. App browser selection smoke must prove native selection/change behavior with zero CSP violations. Radix Dialog/AlertDialog retain custom CSS locking and DropdownMenu is nonmodal.

Class strategy: app-specific layout via Tailwind utilities in JSX; no new global CSS. Domain composites that are web-only (RatingCard, SpeakerGate, ReportView, CodedTranscriptDialog, UtteranceLink, Timeline) stay in `web/src/features/*` composed from ui primitives; promote to `@onolys/ui` only if SP4 reuses them.

## Decisions
| # | Decision | Choice | Alternative | Why |
|---|---|---|---|---|
| 1 | Cutover | Layered legacy bridge, 7 phases | Big-bang rewrite | Reviewable; each PR deployable; no unlayered-CSS override bugs |
| 2 | Legacy tokens | SP1 `legacy.css` aliases, deleted in Ph6 | Keep forever | Avoids two token systems |
| 3 | Delete dialog | AlertDialog (update affected role assertions) | Dialog | Correct a11y role for destructive confirm |
| 4 | Class assertions | Move to `data-*` | Keep dead class names | No styling-only hooks |
| 5 | Dark-mode proof | axe + screenshots, no pixel diff | Pixel baselines | Baselines churn with Inter/Chromium versions |
| 6 | CSP proof | Preview server with exact firebase.json CSP | Assert in dev server | Dev server has no CSP |
| 7 | Build checks | Owner 2026-11-23: build/hosting checks (e.g. `build.test.ts` `createElement("style")` ban) may be changed or removed when they block the design system; CSP stays strict, proven by Playwright CSP smoke; prefer Radix Dialog/AlertDialog | Keep check, avoid react-style-singleton | No one is using prod; runtime smoke is the real proof |
| 8 | Orchestrator defaults 2026-11-23 | Resolve remaining open items with listed defaults (legacy bridge, shims, layers, budget +25%, CSP worker-src test-only) | Leave open | Owner delegated; each verified in a named task |

## CI / deploy impact
- `ci.yml` jobs `web` and `web-e2e` both run `npm ci`; git dep over HTTPS needs no token (public repo, SP1 spec) and the tag commit ships `dist/`, so no build on install [depends on SP1 no-`prepare`]. Nothing to change besides `web-e2e` adding the build+preview CSP project.
- Cache key `cache-dependency-path: web/package-lock.json` already covers a bump: lock changes with the tag. Same in `deploy-staging.yml`, `deploy-prod.yml`. `pr-preview.yml` builds web via the same path [RESOLVED: orchestrator default 2026-11-23 — verify install step covers the git dep, add one if not; verified in Task 1]. `changes.sh` already maps `web/**` to the `web` job.
- `deploy-*` need outbound GitHub access during `npm ci` (already true for actions). [RESOLVED: orchestrator default 2026-11-23 — `github:` spec resolves via git+https; confirm `npm ci` in CI with no SSH; verified in Task 1]
- Firebase hosting CSP: no change (`style-src 'self'`; fonts under `default-src 'self'`). `hosting.test.ts` `style-src === ['self']` assertion stays.

## Bundle size
No size budget exists [verified: `build.test.ts` has none]. Phase 0 records baseline (`vite build` asset table; firebase dominates JS). Expected add: Tailwind CSS tens of KB (min), Radix Dialog/Dropdown/Tabs/AlertDialog + native Select + cva ~30-50KB min JS. Soft budget reported in each PR: JS gzip +60KB, CSS gzip +15KB; exceeding it needs a note, not a hard fail [RESOLVED: orchestrator default 2026-11-23 — record baseline in Phase 0; soft budget = baseline +25%, warning only; verified in Task 1].

## Rollback
Each phase is a revert-able PR; Phase 0 alone is a no-op visually. If production shows a regression after Phase N: revert PR N (legacy layer still supplies old rules until Ph6, so partial state is coherent). Pin never floats, so SP1 changes cannot break web unplanned.

## Bumping @onolys/ui later
`npm i github:Onolys/onolys-ui#vX.Y.Z` → read SP1 CHANGELOG → run `npm test`, `npm run e2e` (incl. CSP + axe) → review screenshot artifact → PR. Pre-1.0 minor = potential break, so never batch with feature work. Local dev: `file:../onolys-ui` + `build:watch` (do not commit).

## Manual steps
- Owner: approved the new devDependency `@axe-core/playwright` (2026-11-23, delegated).
- Owner: after Phase 0 preview, eyeball staging in a dark-mode device (cannot be automated for taste).

## Risks / Open Questions
- [RESOLVED: owner 2026-11-23 — build/hosting checks may be changed or removed when they block the design system; keep the CSP itself strict (style-src 'self') and prove it with the Playwright CSP smoke; prefer Radix Dialog/AlertDialog] **`build.test.ts` regex** fails on any JS containing `createElement("style")` [verified: build.test.ts]. `react-style-singleton` (pulled by `react-remove-scroll`, a Radix Dialog dependency) contains that call; unreachable if SP1 bypasses RemoveScroll, but still bundled/minified into output. Check at Phase 0 build. Fix options: SP1 avoids the dependency, or narrow the test to "no runtime style injection observed" via the CSP smoke. Owner has now allowed changing or removing the check; keep CSP strict and rely on the CSP smoke.
- [RESOLVED: orchestrator default 2026-11-23 — add standard Radix jsdom shims in Phase 0; tests use role queries scoped so Radix `aria-hidden` on siblings does not break `main()` helpers, helpers fixed in the phase that introduces the first modal; verified in Task 1 (shims), Task 6 (helpers)]
- [RESOLVED: orchestrator default 2026-11-23 — local `file:` link needs `@source` to the real path; document and verify; verified in Task 1]
- [RESOLVED: orchestrator default 2026-11-23 — Tailwind preflight scoped/ordered via cascade layers so unmigrated screens do not regress; verified with Phase 0 screenshots; verified in Task 1]
- [RESOLVED: orchestrator default 2026-11-23 — split AuthAction only if migration touches >50% of it; decide in Phase 2; verified in Task 4]
- [RESOLVED: orchestrator default 2026-11-23 — CSP smoke serves built app with MSW only where needed and adds `worker-src 'self'` only to the test server config, not prod; verified in Task 2]
- [DEFERRED] Theme toggle, pixel-diff baselines, promoting web composites to `@onolys/ui`.

## Acceptance Criteria
1. Web builds, `npm test`, `npm run lint`, `npm run typecheck`, `npm run e2e` green on every phase PR.
2. `grep -rn "app.css\|tokens.css\|inter-latin" web/src` returns nothing after Phase 6; `web/src/styles` holds only `index.css`.
3. CSP smoke: zero violations across the listed interactions under the exact `firebase.json` CSP.
4. axe `color-contrast` clean in light and dark on all listed screens; screenshots artifact present.
5. Merged shell/routes and report behaviors (Requirements 5–7) covered by tests that pass unchanged in name/role.
6. `privacy.test.ts`, `hosting.test.ts`, `build.test.ts` pass unmodified (or the single approved change from Risks).
7. Bundle delta reported in each PR; baseline recorded in Phase 0.
8. Bumping to a new `@onolys/ui` tag requires only a lockfile change + gate runs.
