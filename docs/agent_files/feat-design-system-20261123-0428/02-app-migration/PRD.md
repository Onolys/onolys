---
status: draft
summary: Migrate web/ (main app) from hand-built CSS to @onolys/ui v0.1.0 in phases behind a layered legacy bridge, preserving roles/tests and the strict CSP, with dark-mode and CSP Playwright gates.
date: 2026-11-23
---
# PRD: 02 Migrate web/ to @onolys/ui

Repo/branch: `Onolys/onolys`, `feat/design-system` (one PR per phase, each shippable) · Depends on: SP1 tag `v0.1.0`; PR `fix/email-verify-and-public-chrome` merged (rebase first) · Owns: `web/package.json`, `web/vite.config.ts`, `web/src/styles/*`, `web/src/main.tsx`, all `web/src/**/*.tsx` markup/classes, `web/src/test/setup.ts`, `web/e2e_review/*`, `.github/workflows/ci.yml`

## TL;DR
Add `@onolys/ui` (git dep, tag-pinned) + Tailwind v4 Vite plugin. Phase 0 swaps the CSS entry and wraps old `app.css` in a low-priority CSS layer so nothing changes visually in light mode. Phases 1-6 migrate screen groups to SP1 components and shrink the legacy layer. Last phase deletes `app.css`, `tokens.css`, `inter-latin.css`, the SP1 `legacy.css` alias. Dark mode arrives per screen as it is migrated (and for unmigrated screens via aliased tokens). Role/name-based RTL tests stay; class-based assertions move to `data-*`. New: Playwright CSP smoke (built app + real CSP header) and light/dark screenshots + axe contrast.

## Problem
~74 hand-built buttons, 9 forms, 2 custom dialogs, an ad-hoc account menu, 145 lines of global CSS and light-only tokens. [verified: `web/src/styles/app.css` 145 lines; `Modal.tsx` + `DeleteDialog.tsx` hand-roll focus trap; fix-branch `AccountMenu.tsx` hand-rolls menu keyboard handling] SP1 ships the replacements; web must adopt them without breaking CSP/privacy/tests.

## Goals / Non-Goals
**Goals**
- Every web screen uses `@onolys/ui` primitives; dark mode correct on every screen.
- Preserve behaviours added by the fix branch (see Requirement 5).
- Existing accessible names/roles unchanged; `privacy.test.ts`, `hosting.test.ts`, `build.test.ts` stay green without loosening (except the one flagged in Risks).
- Each phase deployable alone; rollback = revert that PR.

**Non-Goals**
- Behaviour/copy/route changes; API changes; manual theme toggle; landing (SP3) and admin (SP4); new features.

## Requirements
1. **Dependency + build**: `npm i github:Onolys/onolys-ui#v0.1.0` (exact tag, lockfile committed), `tailwindcss` + `@tailwindcss/vite` (versions per SP1). `vite.config.ts`: `plugins: [react(), tailwindcss(), dropMockWorker(mode)]`. Gate tailwind on `mode !== "test"` only if vitest slows; never on `process.env.VITEST`, because `build.test.ts` calls `vite.build()` inside vitest and must exercise the real CSS pipeline. [verified: build.test.ts runs `build({configFile})`]
2. **CSS entry** `web/src/styles/index.css` (replaces the three imports in `main.tsx:8-10`):
   `@layer theme, base, legacy, components, utilities; @import "tailwindcss"; @import "@onolys/ui/theme.css"; @import "@onolys/ui/fonts.css"; @import "@onolys/ui/legacy.css"; @import "./legacy-app.css" layer(legacy); @source "../../node_modules/@onolys/ui/dist";`
   Rationale: unlayered `app.css` would beat all Tailwind utilities and preflight (unlayered > layered), so old rules must sit in a named layer below `components`/`utilities`. `legacy-app.css` = today's `app.css`, with `tokens.css` deleted and old `--color-*` names served by SP1's `legacy.css` alias [RESOLVED: orchestrator default 2026-11-23 — bridge via SP1 `legacy.css` until Phase 6 cleanup; if SP1 drops it, web keeps private `legacy-tokens.css` removed in Phase 6; verified in Task 1]. Preflight resets `h1`/`button`/`a` defaults, so Phase 0 must be eyeballed in light before merging.
3. **Decision: bridge, not big bang.** Rewrite is allowed, but ~39 component files and ~120 test files' worth of assertions in one PR is unreviewable; bridge costs ~1 phase of overhead. Final phase deletes `legacy-app.css` and the alias import; CI check: `grep -r "legacy" web/src/styles` empty.
4. **Phases** (each: migrate, update tests, light+dark screenshots, merge):
   | # | Scope | Components |
   |---|---|---|
   | 0 | deps, vite, CSS entry, test setup shims, CSP smoke skeleton | none |
   | 1 | Shell: `Layout.tsx`, `Footer.tsx`, `AccountMenu.tsx`, skip link, `RouteError`, 404 (`placeholders.tsx`) | AppHeader, SkipLink, Footer, DropdownMenu, Button |
   | 2 | Auth: Login, Signup, ForgotPassword, VerifyEmail, AuthAction (400 lines, many states), `parts.tsx` | Input, Label, Button, Alert, Card |
   | 3 | Dashboard (session list, status chips, usage), NewSession/Upload (drop zone, file notices), NewInterview/Interview | Card, Badge, Select (styled native), Alert, UsageMeter, Skeleton |
   | 4 | Session page (timeline, ErrorCard, DeleteDialog, speaker gate), RatingCard/Setup fields | AlertDialog, Alert, Card, Textarea, Select, Checkbox |
   | 5 | Report + SampleReport + Transcript: tabs, tables, chips, score scale, `mark` highlight | Tabs, Table, ScoreBadge, Badge, Card |
   | 6 | Settings + secret dialog (`Modal.tsx` deleted), legal pages (`LegalPage/PrivacyPolicy/Terms`), final cleanup (delete legacy CSS) | Dialog, Card, Separator |
5. **Fix-branch behaviours preserved** [verified: read in `.worktrees/fix/email-verify-and-public-chrome`]:
   - Signed-out header: `Sample report`, `Log in` (text link), `Sign up` (primary button style) → AppHeader nav items + Button `asChild` Link.
   - Verified: nav `Sessions`/`New session` + avatar `Account menu` button (initial of email) → DropdownMenu with email label, `Settings` link item, `Sign out` item; Escape returns focus to trigger; roles `menu`/`menuitem` kept (Radix default).
   - Unverified: brand-only header, no nav, no avatar.
   - Footer: three notice bullets, Privacy/Terms/`mailto:` Contact links, copyright, dark-teal in both themes (SP1 `--footer-*`).
   - `/privacy`, `/terms` routes and text unchanged; VerifyEmail centered with "Use a different email".
   - Focus-to-h1 on route change in `Layout` stays (`mainRef` effect); `h1:focus{outline:none}` moves to SP1 base or a Tailwind class.
6. **Dialogs**: Settings secret dialog has no Escape (`Modal` `onEscape` omitted; test at `Settings.test.tsx:50`) → Radix `onEscapeKeyDown={e=>e.preventDefault()}` + `onInteractOutside` prevented. `DeleteDialog` → `AlertDialog` (role `alertdialog`; update the 2 `getByRole("dialog")` assertions at `SessionPage.test.tsx:687,711`). Focus return to opener is provided by Radix.
7. **Score scale** (`ReportSections.tsx:253-256`) keeps `style={{left}}` — React writes via CSSOM, which `style-src 'self'` allows (already in prod today); track/ticks/dots become Tailwind classes on tokens (`bg-muted`, `bg-muted-foreground`, `bg-primary`); "you" dot ring `border-primary`.
8. **Tests**:
   - Keep all role/text RTL tests. At-risk list and action: `routes/layout.test.tsx`, `routes/legal.test.tsx` (header/menu, Radix opens on pointerdown: `userEvent` ok, `fireEvent.click` not), `auth/pages.test.tsx` and `features/rating/RatingCard.test.tsx` and `session/SessionPage.test.tsx` (3+2+2 `fireEvent` uses: re-check), `settings/Settings.test.tsx` + `SessionPage.test.tsx` (dialogs), `report/ReportPage.test.tsx` (`.ref-dot[data-kind]`, `mark.pulse`, tabs, `getAllByRole("region")`), `transcript/Transcript.test.tsx` (`pulse`), `RatingCard.test.tsx` (`counter-over`), `Dashboard.test.tsx`/`Interview.test.tsx` (`.closest("li")` rows), `flows/flows.test.tsx`, e2e specs `mobile.spec.cjs`, `signed-out.spec.cjs`.
   - Class assertions (`pulse`, `counter-over`, `ref-dot`) → `data-state`/`data-*` attributes (5 edits). `data-slot="upload|speaker-gate|rating-card|rating-fallback"` hooks kept [verified: `SessionPage.test.tsx:212-274`]; SP1/shadcn `data-slot` names (button, card…) don't collide, confirm in Phase 0.
   - `test/setup.ts` adds jsdom shims Radix needs (`ResizeObserver`, `hasPointerCapture`, `scrollIntoView`, `matchMedia`) [RESOLVED: orchestrator default 2026-11-23 — standard Radix set added in vitest setup: ResizeObserver, pointer capture, scrollIntoView, DOMRect, matchMedia; verified in Task 1].
   - New `e2e_review/csp.spec.cjs` (below), `visual.spec.cjs` (below).
9. **CSP smoke** (gate, runs in `web-e2e`): `npm run build -- --mode mock` then `vite preview` with `preview.headers` carrying the exact CSP string read from `firebase.json` (via `src/hosting/csp.ts` `readHosting/cspOf`), so test and prod can't drift. Playwright listens for `securitypolicyviolation` and console CSP errors while: opening account menu; Settings secret dialog; session DeleteDialog; report tabs at mobile viewport; focus rings; native Select choose/change; tooltips (if used). Zero violations required. The dev-server e2e currently runs with no CSP [verified: `playwright.config.cjs` webServer = `dev:mock`], hence the separate project.
10. **Visual + a11y**: `visual.spec.cjs` iterates `colorScheme: light|dark` × {login, signup, verify, dashboard, new session, session (each status), report, sample report, settings, dialogs open, privacy, 404, mobile 390px}; screenshots to `test-results/shots/` uploaded as CI artifact (no pixel diff gate). `@axe-core/playwright` (new devDep in web) gates `color-contrast` + critical violations in both schemes [RESOLVED: 2026-11-23 — approved; `privacy.test.ts` only bans analytics names].
11. **Dark-mode checklist** per screen (PR template item): text/bg ≥4.5:1, UI/focus ≥3:1; status chips (`data-tone` agree/differs/flagged/progress/wait/done/failed → ScoreBadge/Badge variants), `mark` highlight + pulse, timeline borders, drop-zone border, disabled opacity, error card, footer; no images/SVG/canvas exist in `web/src` [verified: grep `<img|<svg|<canvas` → 0 non-test hits], so no asset inversion work; `color-scheme: light dark` comes from SP1 base so native controls/scrollbars follow.
12. **Privacy/lint constraints** re-checked each phase: no storage, no absolute URLs, ≤2 console calls, no `dangerouslySetInnerHTML`, only `firebase/*` imports allowed by name (Radix/ui imports are fine) [verified: `privacy.test.ts` scans only non-test `web/src`, and `node_modules` is outside it]. `lint.test.ts`/jsx-a11y stay on; shadcn code lives in `node_modules`, not linted.

## Architecture
```
web/src/styles/index.css      # entry: layers, tailwind, @onolys/ui theme+fonts, legacy layer (deleted in Ph6)
web/src/styles/legacy-app.css # old app.css, layer(legacy), shrinks each phase
web/src/main.tsx              # single CSS import
```
Select uses SP1’s styled native `<select>` with native `<option>` children and native props; do not import Radix-only Select helpers. SP1 Task 7 measured two inline `style-src-elem` violations from Radix Select under `style-src 'self'`; the user delegated the policy choice and the orchestrator retained strict CSP. App browser selection smoke must prove native selection/change behavior with zero CSP violations. Radix Dialog/AlertDialog retain custom CSS locking and DropdownMenu is nonmodal.

Class strategy: app-specific layout via Tailwind utilities in JSX; no new global CSS. Domain composites that are web-only (RatingCard, SpeakerGate, Transcript, Timeline) stay in `web/src/features/*` composed from ui primitives; promote to `@onolys/ui` only if SP4 reuses them.

## Decisions
| # | Decision | Choice | Alternative | Why |
|---|---|---|---|---|
| 1 | Cutover | Layered legacy bridge, 7 phases | Big-bang rewrite | Reviewable; each PR deployable; no unlayered-CSS override bugs |
| 2 | Legacy tokens | SP1 `legacy.css` aliases, deleted in Ph6 | Keep forever | Avoids two token systems |
| 3 | Delete dialog | AlertDialog (+2 test edits) | Dialog (zero test edits) | Correct a11y role for destructive confirm |
| 4 | Class assertions | Move to `data-*` | Keep dead class names | No styling-only hooks |
| 5 | Dark-mode proof | axe + screenshots, no pixel diff | Pixel baselines | Baselines churn with Inter/Chromium versions |
| 6 | CSP proof | Preview server with exact firebase.json CSP | Assert in dev server | Dev server has no CSP |
| 7 | Build checks | Owner 2026-11-23: build/hosting checks (e.g. `build.test.ts` `createElement("style")` ban) may be changed or removed when they block the design system; CSP stays strict, proven by Playwright CSP smoke; prefer Radix Dialog/AlertDialog | Keep check, avoid react-style-singleton | No one is using prod; runtime smoke is the real proof |
| 8 | Orchestrator defaults 2026-11-23 | Resolve remaining open items with listed defaults (legacy bridge, shims, layers, budget +25%, CSP worker-src test-only) | Leave open | Owner delegated; each verified in a named task |

## CI / deploy impact
- `ci.yml` jobs `web` and `web-e2e` (lines ~400-478) both run `npm ci`; git dep over HTTPS needs no token (public repo, SP1 spec) and the tag commit ships `dist/`, so no build on install [depends on SP1 no-`prepare`]. Nothing to change besides `web-e2e` adding the build+preview CSP project.
- Cache key `cache-dependency-path: web/package-lock.json` already covers a bump: lock changes with the tag. Same in `deploy-staging.yml:201`, `deploy-prod.yml:240`. `pr-preview.yml` builds web via the same path [RESOLVED: orchestrator default 2026-11-23 — verify install step covers the git dep, add one if not; verified in Task 1]. `changes.sh` already maps `web/**` to the `web` job.
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
- [RESOLVED: owner 2026-11-23 — build/hosting checks may be changed or removed when they block the design system; keep the CSP itself strict (style-src 'self') and prove it with the Playwright CSP smoke; prefer Radix Dialog/AlertDialog] **`build.test.ts` regex** fails on any JS containing `createElement("style")` [verified: build.test.ts line ~28]. `react-style-singleton` (pulled by `react-remove-scroll`, a Radix Dialog dependency) contains that call; unreachable if SP1 bypasses RemoveScroll, but still bundled/minified into output. Check at Phase 0 build. Fix options: SP1 avoids the dependency, or narrow the test to "no runtime style injection observed" via the CSP smoke. Owner has now allowed changing or removing the check; keep CSP strict and rely on the CSP smoke.
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
5. Fix-branch behaviours (Requirement 5) covered by tests that pass unchanged in name/role.
6. `privacy.test.ts`, `hosting.test.ts`, `build.test.ts` pass unmodified (or the single approved change from Risks).
7. Bundle delta reported in each PR; baseline recorded in Phase 0.
8. Bumping to a new `@onolys/ui` tag requires only a lockfile change + gate runs.
