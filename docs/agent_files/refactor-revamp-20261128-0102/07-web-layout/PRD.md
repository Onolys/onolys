---
status: draft
summary: Regroup web/src into app/ + features/ (+ api/, constants.ts with a ROUTES constant), split the leftover auth folder, and move all 85 unit tests and the Playwright suite into one web/tests/ mirror. Pure move/rename, mocks stay until 08. No visual change.
date: 2026-11-28
---
# PRD: 07 Web layout (app/ + features/, one tests/ folder)

Repo/branch: Onolys/onolys / `refactor/revamp` · Depends on: 02 (hard: `components/ lib/` and auth core already in `@onolys/common`; no `features/auth`), 01 (soft: ids and guard tests already cleaned) · Does not depend on 06 · Owns: `web/src/**` layout, `web/tests/**` layout (moves only), the test/lint config paths in `web/vite.config.ts`, `web/tsconfig*.json`, `web/eslint.config.js`, `web/package.json` script paths, and the path repoints in `ci.yml` / `nightly.yml`. Does not own: `@onolys/common` (02), eval/web (03), `docs/` (except `web/` READMEs), mock removal, local-stack dev, e2e stack switch, emulator-backed `npm test` (all 08). Sequential with 08: both touch `vite.config.ts`, `package.json` and `nightly.yml`; 07 lands first.

## TL;DR
`web/src` becomes `main.tsx`, `constants.ts`, `config.ts`, `app/` (shell + route table), `api/`, `features/<screen>/`, `styles/`. Every test moves to `web/tests/` mirroring `src/`; Playwright moves to `web/tests/e2e/` (still on the current mock mode). All web URL paths live in one `ROUTES` constant. `features/auth` does not exist: its two leftover files go to `api/` and `app/`. Moves only (`git mv`, green at every commit); mocks, MSW and the mock-based test bodies are untouched (08 replaces them).

## Problem
| Gap | Evidence |
|---|---|
| Layout: tests beside source (85 files), `e2e_review/` (review-era name, finding ids in titles), `routes/` holds the app shell, `__fuzz_review__/`, `src/test/`, `src/flows/` | [verified: `find web`] |
| Product code is grouped by layer, not screen; auth remainder (`useApiClient`, `createAuthService`) is two unrelated files in one folder | [verified after 02: only these two files remain] |
| URL path strings and fixed values (Firestore collection name, retry/stale/poll numbers, contact address) are scattered | [from the owner decision O1; to count at T7] |
| `sample.ts` (shipped on `/sample`) lives in `mocks/fixtures/` | [verified: `SampleReportPage.tsx:9`] |

## Goals / Non-Goals
**Goals:** target tree below; one `tests/` folder; one `ROUTES` constant; same screens, same behaviour; green build/typecheck/lint/tests/e2e at every commit.
**Non-goals:** visual or UX change; new features; moving shared UI (02); `schema.d.ts` content (06 R9: must not change); eval/web; docs; rewriting src imports to `@/` beyond what moves force; deleting `mocks/`, MSW, the fake relay or `dev:mock`, running on the real API stack, the emulator-backed `npm test`, e2e CI re-platform (all 08).

## Requirements
**R1 Target tree.**
```
web/src/  main.tsx  constants.ts  config.ts  styles/index.css
  app/       App ErrorBoundary routes Layout Footer RouteError routeTitle placeholders bootError pageLoadError queryClient createAuthService
  api/       client useApiClient errors types buildInfo firestoreListener statusListener schema.d.ts report.d.ts
  features/  dashboard interview legal rating report session settings speakers upload usage
  mocks/     unchanged (08 deletes)
web/tests/   (mirrors src: app/ api/ features/<x>/)  helpers/  e2e/  flows/ (temporary, 08 deletes)
```
**R2 Mapping (today -> new).**
| Today | New |
|---|---|
| `routes/*` (not the files 02 moved), `App.tsx`, `ErrorBoundary.tsx`, `bootError.ts`, `pageLoadError.ts`, `queryClient.ts` | `app/` same names |
| `auth/useApiClient.ts` (what 02 leaves) | `api/useApiClient.ts` (D6) |
| `auth/createAuthService.ts` (what 02 leaves) | `app/createAuthService.ts` (D6) |
| `protocol/{miti-items.ts,rating.schema.json}` | `features/rating/` (only rating imports them; `api/types.ts` comment reworded) |
| `mocks/fixtures/sample.ts` (+ its `Turn` type) | `features/report/sample.ts` (shipped product data, D3); mock files that import it get the new path |
| `hosting/csp.ts` | `tests/helpers/csp.ts` (only tests + `vite.config` use it) |
| `test/{setup,renderApp,renderPage}` | `tests/helpers/` (bodies unchanged) |
| `hosting/{build,hosting,privacy}.test.ts`, `lint.test.ts`, `radixShims.test.tsx` | deleted (tests of tooling/shims; audit #8, [RESOLVED 2026-11-28: owner rule 17]) |
| `src/**/X.test.ts(x)` (84 more) | `tests/<same dir>/X.test.ts(x)`; names kept (already behaviour-named); `useSessionStatus.*.test` keep suffixes; mock-based bodies unchanged (they import `@/mocks/...` until 08) |
| `flows/flows.test.tsx` | `tests/flows/flows.test.tsx` (temporary; 08 turns the journeys into e2e) |
| `__fuzz_review__/` (`api-lib.property.test.ts`, 414 lines), `nightly/fast-check.ts`, `stryker.conf.json` + `@stryker-mutator/*` devDeps | deleted (one-off review harnesses; rules 16/17; audit #3, [RESOLVED 2026-11-28: owner rule 17]) |
| `e2e_review/*` (specs, helpers, fixtures, 2 configs, README) | `tests/e2e/*` (still mock mode; D4) |
**R3 Test config.** `vite.config.ts`: `test.include tests/**/*.test.{ts,tsx}`, exclude `tests/e2e/**`, `setupFiles tests/helpers/setup.ts`, alias `@` -> `src` (tests import `@/features/...`; `tsconfig` `paths` + `include` add `tests`; D1); FLAKY/NIGHTLY include globs and the nightly fuzz/mutation entries removed with the deleted harnesses; `eslint.config.js` e2e glob repointed (the `mockServiceWorker.js` ignore stays until 08); `stryker.conf.json` deleted. Playwright configs, `package.json` e2e scripts, `ci.yml` / `nightly.yml` artifact paths repointed (`tests/e2e/*`); mutation/fuzz campaigns removed. The finding-id grep in `playwright.smoke.config.cjs` is replaced by a `@smoke` title tag; finding/task ids are dropped from spec and test titles.
**R4 Constants.** `src/constants.ts`: values with no env dependence - Firestore collection name `session_status`, trusted app hosts (from 02), retry/stale/poll numbers, all web URL paths (`ROUTES`; no path string anywhere else), default contact address. `config.ts` stays the only reader of `import.meta.env`. State names stay schema types (O1).
**R5 Dependency rule.** `features/*` may import `api/`, `constants.ts`, `config.ts`, `@onolys/common`; `app/` imports features; features never import `app/` or each other except through a named export of the owning feature. Enforced by review, not a new CI check.

## Architecture
```
src/    main -> app/ (shell, route table, createAuthService) -> features/<screen>/ -> api/ -> @onolys/common
tests/  mirrors src/ ; helpers/ (setup, renderApp, csp) ; e2e/ (Playwright, .cjs)
```

## Migration (one commit per batch, each: typecheck, lint, touched tests green)
| # | Batch | Gate |
|---|---|---|
| T0 | Baseline: unit and e2e pass counts (no screenshot baseline: [RESOLVED 2026-11-28: owner rule 17], a pure move is gated by typecheck + test count + e2e smoke; Playwright `toHaveScreenshot` is the vendor option if a visual check is ever wanted) | counts recorded in the task log |
| T1 | `routes/` + shell files -> `app/` | tsc, tests |
| T2 | `auth/useApiClient` -> `api/`, `auth/createAuthService` -> `app/`; `protocol/` -> `features/rating/`; `sample.ts` -> `features/report/` | tsc, tests |
| T3 | Test config + `tests/helpers` (setup, renderApp, csp) + `tests/{app,api}` moves | `vitest run` count equals T0 |
| T4-T5 | `tests/features/*` moves + `tests/flows/` (two commits) | count equals T0 |
| T6 | `e2e_review` -> `tests/e2e` (still mock mode): configs, scripts, eslint, CI paths, README, `@smoke` tags, ids out of titles | e2e smoke green |
| T7 | `constants.ts` / `ROUTES` sweep (one commit); `web/` READMEs; final AC | full web gate (dev-ship) |
T1-T6 can start once 02's rewire commit landed. No dependency on 06.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | Test mirror imports | `@/` alias, tests only (src keeps relative paths) | `../../../src/...`; alias everywhere | Deep relative paths are unreadable; rewriting all src imports is churn nobody asked for |
| D2 | `hosting/` | `csp.ts` helper into `tests/helpers/` (its tests are deleted); `web/firebase.json` + `web/.firebaserc` **stay** in `web/` | Move to `firebase/` (09) | `deploy-prod/staging`, `pr-preview` (+`pr_preview.sh`), `release_target.py`, `test_hosting_targets.sh`, `vite.config` all name `web/firebase.json`; `.firebaserc` is live (release_target writes the deploy site into it) [verified]. The two mock-worker ignores are edited by 08 |
| D3 | Sample report | Product data `features/report/sample.ts` | Keep a `fixtures/` dir; fetch from API | It ships to users on `/sample`; not a fixture |
| D4 | e2e language/location | Stay `.cjs` Playwright, `tests/e2e/` | Port to TS | No benefit asked for; moves only |
| D5 | Constants | `constants.ts` (fixed) + `config.ts` (env) | Per-feature constants; none | Mirrors rule 10's split with `config/` |
| D6 | Auth remainder | `useApiClient` -> `api/`, `createAuthService` -> `app/`; no `features/auth` | One `features/auth` holding two unrelated files | Owner decision (O2) |
| D7 | `dev:live` / stryker | Keep `dev:live`; delete stryker and fuzz (audit #3) | Repoint | Rule 17 |
| D8 | Split from mock removal | Layout first (this SP), mocks second (08), mock-based test bodies moved as-is | One SP for both | Layout needs only 02; mock removal needs 06's real stack. Smaller reviewable steps, pixel-identical evidence after moves |

## Manual steps
None.

## Risks / Open Questions
- Risk: a move silently drops or duplicates a test. Mitigation: `vitest run` count must equal the T0 count after T3-T5; e2e smoke after T6.
- Risk: import churn collides with 02's rewire commit series. Mitigation: T1 starts only after 02's rewire landed; one `git mv` batch per commit.
- [RESOLVED: all paths] O1: `ROUTES` holds ALL web URL paths; state names stay schema types.
- [RESOLVED: split] O2: `useApiClient` -> `api/`, `createAuthService` -> `app/`; no `features/auth`.
- [DEFERRED] Legacy `app-staging -> onolys-app-staging` mapping in `web/.firebaserc` (needs `test_hosting_targets.sh` change; 09/owner after the old site is retired).

## Acceptance Criteria
- `src/routes`, `src/auth`, `src/components`, `src/lib`, `src/hosting`, `src/test`, `src/flows`, `src/protocol`, `src/__fuzz_review__`, `web/nightly/fast-check.ts`, `stryker.conf.json` and `e2e_review` do not exist; `src/mocks` still exists (08 deletes it) and contains no `sample.ts`.
- No `*.test.*` under `web/src`; `web/tests/` mirrors `src/`; no test or spec title carries a finding/task id; `@smoke` tag selects the smoke subset.
- `git grep -nE "['\"]/(dashboard|upload|settings|usage|sample|legal)" web/src` shows paths only in `constants.ts` (`ROUTES`) and `schema.d.ts`/`api` request paths; adjust the list to the real route table at T7.
- `npm run typecheck`, `lint`, `test`, `build`, `check:api` green; `src/api/schema.d.ts`/`report.d.ts` unchanged by 07 commits; unit test count equals the T0 count; e2e (mock mode) and smoke subset green.
- No-UX-change evidence: moves only; `git diff -M` shows renames plus import-path edits, no `className` diffs; e2e smoke green (no pixel-compare script).
- Rules cited: 1, 14, 15, 16, 17.
