---
status: draft
summary: Migrate web/ (main app) from hand-built CSS to @onolys/ui v0.1.0 in phases (one commit each, single PR #55) behind a layered legacy bridge, preserving roles/tests and the strict CSP, with dark-mode and CSP Playwright gates.
date: 2026-11-23
---
# PRD: 02 Migrate web/ to @onolys/ui

Repo/branch: `Onolys/onolys`, `feat/design-system` (one branch and one PR (#55) for all 9 tasks, one commit per task, merged once; PR #55 stays draft until Task 9; PR title/body updated at first code push (Task 1), final scope at Task 9; full-branch dev-review precedes ship) · Depends on: SP1 tag `v0.1.0`; merged #52 and #54 preservation baseline (branch rebased onto main `d88fbc6`) · Owns: `web/package.json`, `web/vite.config.ts`, `web/src/styles/*`, `web/src/main.tsx`, all `web/src/**/*.tsx` markup/classes, `web/src/test/setup.ts`, `web/e2e_review/*`, `.github/workflows/ci.yml`

## TL;DR
Add `@onolys/ui` (git dep, tag-pinned) + Tailwind v4 Vite plugin. Phases are commits on one branch, not separately shippable units; deployment happens once, at merge of #55. Phase 0 swaps the CSS entry and wraps old `app.css` in a low-priority CSS layer: a light-mode-only visual no-op. On dark devices SP1 base.css sets `color-scheme: light dark`, so unmigrated screens with hardcoded hexes in app.css (e.g. app.css:33,43,44,47,131, incl. the --rv-info/--rv-info-bg change) can look off; the dark audit of those leftovers is a Task 2/3 item. Phases 1-6 migrate screen groups to SP1 components and shrink the legacy layer. Last phase deletes `app.css`, `tokens.css`, `inter-latin.css`, the SP1 `legacy.css` alias. Dark mode arrives per screen as it is migrated (and for unmigrated screens via aliased tokens). Role/name-based RTL tests stay; class-based assertions move to `data-*`. New: Playwright CSP smoke (built app + real CSP header) and light/dark screenshots + axe contrast.

## Problem
The app uses hand-built forms, dialogs, account-menu behavior and light-only styles. SP1 ships shared replacements. Migration must preserve the current merged #54 navigation, split start/session pages, and shared real/sample report with its native coded-transcript dialog, alongside the earlier email-verification behavior. Baseline: main `d88fbc6`; the merged #54 design is recorded in `docs/agent_files/feat-public-nav-sample-report-20261123-0545/`.

## Goals / Non-Goals
**Goals**
- Every web screen uses `@onolys/ui` primitives; dark mode correct on every screen.
- Preserve merged #52/#54 behavior (Requirements 5–7).
- Existing accessible names/roles unchanged; `privacy.test.ts`, `hosting.test.ts`, `build.test.ts` stay green without loosening (except the one flagged in Risks).
- Each task commit builds and passes CI; deployment happens at merge of #55.

**Non-Goals**
- Behaviour/copy/route changes; API changes; manual theme toggle; landing (SP3) and admin (SP4); new features.

## Requirements
1. **Dependency + build**: dependency spec `git+https://github.com/Onolys/onolys-ui.git#v0.1.0` (not `github:`; exact tag, lockfile committed; verify lockfile `resolved` is https). Tag `v0.1.0` (e503f28) contains `dist/`; `release/v0.1.0` is source-only, do not use it. Also add `tailwindcss` + `@tailwindcss/vite` (versions per SP1). `vite.config.ts`: `plugins: [react(), tailwindcss(), dropMockWorker(mode)]`. Gate tailwind on `mode !== "test"` only if vitest slows; never on `process.env.VITEST`, because `build.test.ts` calls `vite.build()` inside vitest and must exercise the real CSS pipeline. [verified: build.test.ts runs `build({configFile})`]
2. **CSS entry** `web/src/styles/index.css` (replaces the existing style imports in `main.tsx`):
   `@layer theme, base, legacy, components, utilities; @import "tailwindcss"; @import "@onolys/ui/theme.css"; @import "@onolys/ui/legacy.css"; @import "./legacy-app.css" layer(legacy); @source "../../node_modules/@onolys/ui/dist";` (no separate `fonts.css` import: `theme.css` already imports it; avoids duplicate `@font-face`)
   Rationale: unlayered `app.css` would beat all Tailwind utilities and preflight (unlayered > layered), so old rules must sit in a named layer below `components`/`utilities`. `legacy-app.css` = today's `app.css`, with `tokens.css` deleted and old `--color-*` names served by SP1's `legacy.css` alias [RESOLVED: orchestrator default 2026-11-23 — bridge via SP1 `legacy.css` until Phase 6 cleanup; if SP1 drops it, web keeps private `legacy-tokens.css` removed in Phase 6; verified in Task 1]. Preflight resets `h1`/`button`/`a` defaults, so Phase 0 must be eyeballed in light before merging.
3. **Decision: bridge, not big bang.** Migrate screen groups separately so each phase is reviewable; the bridge adds an initial compatibility phase. Final phase deletes `legacy-app.css` and the alias import; CI check: `grep -r "legacy" web/src/styles` empty.
4. **Phases** (each: migrate, update tests, light+dark screenshots, commit):
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
   - Class-assertion inventory (~63 hits across 12 test files; re-check against actual tests before changing). Task 3/4: `routes/layout.test.tsx:31,32,59,66` (`nav-login`, `nav-signup btn btn-primary`, `btn btn-secondary`, `verify-page`) move to data-*/role. Task 6: `RatingCard.test.tsx:67` `counter-over`. Task 7: ReportView/CodedTranscriptDialog/UtteranceLink tests (~36 hits: `.global`, `.g-evidence`, `.tip`, `.try .eg`, `.code`, `.codes .code`, `details.dlg-legend`, `.hl`, `html.dlg-open`; e.g. `CodedTranscriptDialog.test.tsx:53,135,149`, `ReportView.test.tsx:59,73,107`, `UtteranceLink.test.tsx:71`) and `SampleReportPage.test.tsx:38` `.notice`. Kept as semantic hooks: `.hl`, `dlg-open`, `utt-N`.
   - Re-check current class assertions against actual tests before changing them; replace styling-only hooks with state/data hooks when necessary without dropping behavioral assertions. Preserve existing upload/speaker/rating data-slot hooks and check for primitive collisions.
   - Extend existing test/setup.ts native dialog and scrollIntoView shims with missing Radix shims only (ResizeObserver, pointer capture, DOMRect, matchMedia as needed); retain native dialog tests.
   - New `e2e_review/csp.spec.cjs` and `visual.spec.cjs` cover the preserved shell, routes, split pages and shared report/dialog flows.
9. **CSP smoke** (gate, runs in `web-e2e`): its own Playwright project with per-project `testMatch`/`testIgnore` and a second `webServer` + port running `npm run build -- --mode mock` then `vite preview`. Today `web/e2e_review/playwright.config.cjs` has no projects and a single webServer on `dev:mock` with `testMatch "*.spec.cjs"`, so csp/visual specs would otherwise run against the CSP-less dev server. `csp.ts` is TS using `import.meta.dirname`, so `.cjs` specs cannot import it: inject the header via `preview.headers` in `vite.config.ts`, reading `readHosting/cspOf` (`src/hosting/csp.ts`) from `web/firebase.json`. Use the prod hosting entry's CSP (firebase.json has prod and staging entries with different `connect-src`). Serve the exact header, no test-only additions, so test and prod can't drift. Playwright listens for `securitypolicyviolation` and console CSP errors while: opening account menu; Settings secret dialog; session DeleteDialog; native coded-transcript dialog open/close, pointed utterance scrolling/highlight and focus return at mobile viewport; focus rings; native Select choose/change; tooltips (if used). Zero violations required. The dev-server e2e currently runs with no CSP [verified: `playwright.config.cjs` webServer = `dev:mock`], hence the separate project.
10. **Visual + a11y**: `visual.spec.cjs` iterates `colorScheme: light|dark` × {login, signup, verify, /new chooser, /sessions list, upload, session (each status), report, sample report, settings, dialogs open, privacy, 404, mobile 390px}; screenshots to `test-results/shots/` uploaded as CI artifact (no pixel diff gate). `@axe-core/playwright` (new devDep in web) gates `color-contrast` + critical violations in both schemes [RESOLVED: 2026-11-23 — approved; `privacy.test.ts` only bans analytics names].
11. **Dark-mode checklist** per screen (recorded per task in `code-<ts>.md`): text/bg ≥4.5:1, UI/focus ≥3:1; status chips and report score/status/code chips, five-segment scales, pointed-row highlight and reduced-motion outline, report/table surfaces, timeline/drop-zone borders, disabled opacity, errors and compact footer. Audit actual assets at migration time. `color-scheme: light dark` comes from SP1 base so native controls/scrollbars follow.
12. **Privacy/lint constraints** re-checked each phase: no storage, no absolute URLs, ≤2 console calls, no `dangerouslySetInnerHTML`, only `firebase/*` imports allowed by name (Radix/ui imports are fine) [verified: `privacy.test.ts` scans only non-test `web/src`, and `node_modules` is outside it]. `lint.test.ts`/jsx-a11y stay on; shadcn code lives in `node_modules`, not linted.

## Architecture
```
web/src/styles/index.css      # entry: layers, tailwind, @onolys/ui theme (incl. fonts), legacy layer (deleted in Ph6); final form keeps a small "app overrides" section
web/src/styles/legacy-app.css # old app.css, layer(legacy), shrinks each phase
web/src/main.tsx              # single CSS import
```
Select uses SP1’s styled native `<select>` with native `<option>` children and native props; do not import Radix-only Select helpers. SP1 Task 7 measured two inline `style-src-elem` violations from Radix Select under `style-src 'self'`; the user delegated the policy choice and the orchestrator retained strict CSP. App browser selection smoke must prove native selection/change behavior with zero CSP violations. Radix Dialog/AlertDialog retain custom CSS locking and DropdownMenu is nonmodal.

Class strategy: app-specific layout via Tailwind utilities in JSX; no new global CSS except a small "app overrides" section in `index.css` for rules utilities cannot express: `html.dlg-open{overflow:hidden}` (set from JS on documentElement, `CodedTranscriptDialog.tsx:60`, asserted in tests; `app.css:188`), `.coded-dialog::backdrop` (`app.css:191`), and `@keyframes utt-hl` + reduced-motion variant (`app.css:211`). Note: SP1 `legacy.css` redefines `--color-gray-50..900` unlayered at `:root`, overriding the Tailwind gray palette; new code uses semantic tokens, not `text-gray-*`. Chips (Task 5): SP1 `Badge` has no tone variants and `ScoreBadge` has fixed Good/Fair/Low labels, but `SessionsPage.tsx:71` and `ReportView.tsx:217` use `data-tone` / `st.cls` chips with their own text, so use `Badge` with className/`data-tone` overrides via a web-local chip wrapper. Domain composites that are web-only (RatingCard, SpeakerGate, ReportView, CodedTranscriptDialog, UtteranceLink, Timeline) stay in `web/src/features/*` composed from ui primitives; promote to `@onolys/ui` only if SP4 reuses them.

## Decisions
| # | Decision | Choice | Alternative | Why |
|---|---|---|---|---|
| 1 | Cutover | Layered legacy bridge, 7 phases | Big-bang rewrite | Reviewable commit-by-commit; each commit CI-green; no unlayered-CSS override bugs |
| 2 | Legacy tokens | SP1 `legacy.css` aliases, deleted in Ph6 | Keep forever | Avoids two token systems |
| 3 | Delete dialog | AlertDialog (update affected role assertions) | Dialog | Correct a11y role for destructive confirm |
| 4 | Class assertions | Move to `data-*` | Keep dead class names | No styling-only hooks |
| 5 | Dark-mode proof | axe + screenshots, no pixel diff | Pixel baselines | Baselines churn with Inter/Chromium versions |
| 6 | CSP proof | Preview server with exact firebase.json CSP | Assert in dev server | Dev server has no CSP |
| 7 | Build checks | Owner 2026-11-23: build/hosting checks (e.g. `build.test.ts` `createElement("style")` ban) may be changed or removed when they block the design system; CSP stays strict, proven by Playwright CSP smoke; prefer Radix Dialog/AlertDialog | Keep check, avoid react-style-singleton | No one is using prod; runtime smoke is the real proof |
| 8 | Orchestrator defaults 2026-11-23 | Resolve remaining open items with listed defaults (legacy bridge, shims, layers, budget +25%; the earlier CSP `worker-src` test-only idea is dropped) | Leave open | Owner delegated; each verified in a named task |

## CI / deploy impact
- `ci.yml` jobs `web` and `web-e2e` both run `npm ci`; git dep over HTTPS needs no token (public repo, SP1 spec) and the tag commit ships `dist/`, so no build on install [depends on SP1 no-`prepare`]. Task 2 CI edits: `web-e2e` adds the build+preview CSP project (see Req 9); screenshot artifact upload becomes `if: always()` from `web/e2e_review/test-results/` (today `ci.yml:582-590` is `if: failure()`); raise `web-e2e` `timeout-minutes` (today 15 at `ci.yml:557`).
- Cache key `cache-dependency-path: web/package-lock.json` already covers a bump: lock changes with the tag. Same in `deploy-staging.yml`, `deploy-prod.yml`. `pr-preview.yml` builds web via the same path [RESOLVED: orchestrator default 2026-11-23 — verify install step covers the git dep, add one if not; verified in Task 1]. `changes.sh` already maps `web/**` to the `web` job.
- `deploy-*` need outbound GitHub access during `npm ci` (already true for actions). [RESOLVED: orchestrator default 2026-11-23 — `git+https://github.com/Onolys/onolys-ui.git#v0.1.0` spec (not `github:`) resolves via https; check lockfile `resolved` is https; confirm `npm ci` in CI with no SSH; verified in Task 1]
- Firebase hosting CSP: no change (`style-src 'self'`; fonts under `default-src 'self'`). `hosting.test.ts` `style-src === ['self']` assertion stays.

## Bundle size
No size budget exists [verified: `build.test.ts` has none]. Phase 0 records baseline (`vite build` asset table; firebase dominates JS). Expected add: Tailwind CSS tens of KB (min), Radix Dialog/Dropdown/Tabs/AlertDialog + native Select + cva ~30-50KB min JS. Soft budget recorded per task in the `code-<ts>.md` artifact and summarized in the final PR body: JS gzip +60KB, CSS gzip +15KB; exceeding it needs a note, not a hard fail [RESOLVED: orchestrator default 2026-11-23 — record baseline in Phase 0; soft budget = baseline +25%, warning only; verified in Task 1].

## Rollback
Revert the merge of #55. Merge with merge-commit or rebase-merge, never squash, so individual task commits stay revertable/bisectable. Rebase on main before each task and before ship; re-verify the `d88fbc6` preservation baseline claims after each rebase. Pin never floats, so SP1 changes cannot break web unplanned.

## Bumping @onolys/ui later
`npm i git+https://github.com/Onolys/onolys-ui.git#vX.Y.Z` → read SP1 CHANGELOG → run `npm test`, `npm run e2e` (incl. CSP + axe) → review screenshot artifact → PR. Pre-1.0 minor = potential break, so never batch with feature work. Local dev: `file:../onolys-ui` + `build:watch` (do not commit).

## Manual steps
- Owner: approved the new devDependency `@axe-core/playwright` (2026-11-23, delegated).
- Owner: dark-mode device check (cannot be automated for taste) on the pr-55 preview channel after Task 2, and once more before merge.

## Risks / Open Questions
- [RESOLVED: owner 2026-11-23 — build/hosting checks may be changed or removed when they block the design system; keep the CSP itself strict (style-src 'self') and prove it with the Playwright CSP smoke; prefer Radix Dialog/AlertDialog] **`build.test.ts` regex** fails on any JS containing `createElement("style")` [verified: build.test.ts]. `react-style-singleton` (pulled by `react-remove-scroll`, a Radix Dialog dependency) contains that call; unreachable if SP1 bypasses RemoveScroll, but still bundled/minified into output. Check at Phase 0 build. Fix options: SP1 avoids the dependency, or narrow the test to "no runtime style injection observed" via the CSP smoke. Owner has now allowed changing or removing the check; keep CSP strict and rely on the CSP smoke.
- [RESOLVED: orchestrator default 2026-11-23 — add standard Radix jsdom shims in Phase 0; tests use role queries scoped so Radix `aria-hidden` on siblings does not break `main()` helpers, helpers fixed in the phase that introduces the first modal; verified in Task 1 (shims), Task 6 (helpers)]
- [RESOLVED: orchestrator default 2026-11-23 — local `file:` link needs `@source` to the real path; document and verify; verified in Task 1]
- [RESOLVED: orchestrator default 2026-11-23 — Tailwind preflight scoped/ordered via cascade layers so unmigrated screens do not regress; verified with Phase 0 screenshots; verified in Task 1]
- [RESOLVED: orchestrator default 2026-11-23 — split AuthAction only if migration touches >50% of it; decide in Phase 2; verified in Task 4]
- [RESOLVED: orchestrator default 2026-11-23 — CSP smoke serves built app with MSW only where needed under the exact prod CSP header; no `worker-src` addition, since `worker-src` falls back to `script-src`, which already has `'self'` (`web/firebase.json:31`); verified in Task 2]
- [DEFERRED] Theme toggle, pixel-diff baselines, promoting web composites to `@onolys/ui`.

## Acceptance Criteria
1. Web builds, `npm test`, `npm run lint`, `npm run typecheck`, `npm run e2e` green at each task commit (CI) and on the final PR.
2. `grep -rn "app.css\|tokens.css\|inter-latin\|legacy" web/src` returns nothing after Phase 6; `web/src/styles` holds only `index.css` (which may contain the documented "app overrides" section).
3. CSP smoke: zero violations across the listed interactions under the exact `firebase.json` CSP.
4. axe `color-contrast` clean in light and dark on all listed screens; screenshots artifact present.
5. Merged shell/routes and report behaviors (Requirements 5–7) covered by tests that pass unchanged in name/role.
6. `privacy.test.ts`, `hosting.test.ts`, `build.test.ts` pass unmodified (or the single approved change from Risks).
7. Bundle delta recorded per task in the `code-<ts>.md` artifact and summarized in the final PR body; baseline recorded in Phase 0.
8. Bumping to a new `@onolys/ui` tag requires only a lockfile change + gate runs.
