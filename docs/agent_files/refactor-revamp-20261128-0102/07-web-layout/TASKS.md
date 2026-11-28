---
status: draft
summary: Web layout regroup in 8 tasks (T0-T7 of the PRD) - app/ + features/ + api/, one web/tests/ mirror, ROUTES constant; pure moves, no visual change.
date: 2026-11-28
---
# Tasks: 07 Web layout (app/ + features/, one tests/ folder)

Source of truth: /root/projects/onolys/onolys/.worktrees/refactor/revamp/docs/agent_files/refactor-revamp-20261128-0102/07-web-layout/PRD.md. Moves only (`git mv`), one commit per task, typecheck, lint and impacted tests green at every commit. Mocks, MSW and mock-based test bodies stay untouched (08 owns them). Never change `schema.d.ts` / `report.d.ts` content, `web/firebase.json` or `web/.firebaserc`. CI exists (`.github/workflows/ci.yml`, `nightly.yml`); this SP only repoints paths. Task 1-6 start only after 02's rewire commit landed; no dependency on 06. Full suite runs only in dev-ship (Task 8 prepares for it).

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Baseline: pixel shots + test counts (T0) | none | todo |
| 2 | `routes/` + shell files into `app/` (T1) | 1 | todo |
| 3 | Auth remainder, `protocol/`, `sample.ts` placement (T2) | 2 | todo |
| 4 | Test config, `tests/helpers`, `tests/{app,api,hosting}` moves (T3) | 3 | todo |
| 5 | `tests/features/*` moves (T4) | 4 | todo |
| 6 | `tests/flows/` move (T5) | 5 | todo |
| 7 | `e2e_review` into `tests/e2e`, CI/script/lint repoints (T6) | 6 | todo |
| 8 | `constants.ts` / `ROUTES` sweep, READMEs, final acceptance (T7) | 7 | todo |

## Task 1 — Baseline: pixel shots and test counts
What it is / what it means: Evidence for "no visual change, no test lost". PRD Migration T0, AC4-5.
What changes at a high level: Nothing in the repo. Using the existing `visual.spec` shot code with `E2E_SHOTS=1`, capture light and dark shots of every route and keep them outside the repo (08 reuses them). Record unit test count (`vitest run`) and e2e pass counts in the task log. Confirm 02's rewire commit is on the branch.
Done when: baseline shots exist outside the repo; unit and e2e counts recorded; full unit and e2e run green on the starting tree.

## Task 2 — `routes/` and shell files into `app/`
What it is / what it means: The app shell and route table become `app/`. PRD R1, R2 first row, T1.
What changes at a high level: `git mv` the remaining `routes/*`, `App.tsx`, `ErrorBoundary.tsx`, `bootError.ts`, `pageLoadError.ts`, `queryClient.ts` into `src/app/` with the same names; fix imports only. Other layer folders are not touched here.
Done when: `tsc` and lint pass; impacted unit tests (still beside source) pass; `src/routes` is gone and the diff is rename plus import edits only.

## Task 3 — Auth remainder, `protocol/`, `sample.ts`
What it is / what it means: Place the leftover files by owner (D6, D3). PRD R2, T2.
What changes at a high level: `auth/useApiClient.ts` to `api/`, `auth/createAuthService.ts` to `app/` (no `features/auth`); `protocol/{miti-items.ts,rating.schema.json}` to `features/rating/` and reword the `api/types.ts` comment; `mocks/fixtures/sample.ts` (and its `Turn` type) to `features/report/sample.ts`, repointing the mock files that import it. `mocks/` otherwise unchanged.
Done when: `tsc`, lint and impacted tests pass; `src/auth`, `src/protocol` gone; `src/mocks` has no `sample.ts`; `SampleReportPage` renders from `features/report`.

## Task 4 — Test config, helpers, `tests/{app,api,hosting}`
What it is / what it means: Create the single `web/tests/` tree and point tooling at it. PRD R3, R2, D1, D2, T3.
What changes at a high level: Set `vite.config.ts` test include to `tests/**`, exclude `tests/e2e/**`, setup file `tests/helpers/setup.ts`, alias `@` to `src`; add `tests` to `tsconfig` paths and include; repoint FLAKY/NIGHTLY globs and the `eslint.config.js` e2e glob (keep the `mockServiceWorker.js` ignore). Move `test/{setup,renderApp,renderPage}`, `hosting/csp.ts` to `tests/helpers/csp.ts`, `hosting/*.test.ts` to `tests/hosting/`, `radixShims.test`, `nightly/fast-check.ts`, and the `app/` and `api/` tests. Move `__fuzz_review__/api-lib.property.test.ts` to `tests/api/errors.property.test.ts`. Repoint `stryker.conf.json` mutate to `src/api/errors.ts` and stryker/nightly test paths. Bodies unchanged; tests import via `@/`.
Done when: `vitest run` total equals the Task 1 count; tsc, lint pass; `src/hosting`, `src/test`, `src/__fuzz_review__` gone; `web/firebase.json` and `.firebaserc` untouched.

## Task 5 — `tests/features/*` moves
What it is / what it means: Mirror every feature test under `tests/features/<x>/`. PRD R2 row 6, T4.
What changes at a high level: Move all remaining `src/**/X.test.ts(x)` into `tests/<same dir>/` for the nine features, keeping names (including `useSessionStatus.*.test` suffixes); bodies unchanged except import paths (`@/features/...`, `@/mocks/...`).
Done when: no `*.test.*` left under `web/src` except `src/flows`; `vitest run` count equals Task 1 count; tsc and lint pass.

## Task 6 — `tests/flows/` move
What it is / what it means: Temporary home for the journey tests until 08 turns them into e2e. PRD R2 row `flows`, T5.
What changes at a high level: Move `src/flows/flows.test.tsx` to `tests/flows/flows.test.tsx`; body unchanged; separate commit from Task 5.
Done when: `src/flows` is gone and no `*.test.*` remains under `web/src`; `vitest run` count equals Task 1 count.

## Task 7 — `e2e_review` into `tests/e2e`, CI and script repoints
What it is / what it means: Playwright joins the one tests folder, still on mock mode. PRD R2 last row, R3, D4, T6.
What changes at a high level: Move specs, helpers, fixtures, the two configs and README to `tests/e2e/` (stay `.cjs`). Repoint `package.json` e2e scripts, `playwright.*.config.cjs`, `eslint.config.js`, and artifact and campaign paths in `ci.yml` / `nightly.yml` (campaigns to `tests/api/errors.property.test.ts` and `src/api/errors.ts`). Replace the finding-id grep in `playwright.smoke.config.cjs` with a `@smoke` title tag; drop finding/task ids from spec and test titles.
Done when: e2e (mock mode) full and `@smoke` subset green with counts equal to Task 1; `actionlint` passes on both workflows; no `e2e_review` string remains in repo config, scripts or workflows; grep for finding/task ids in `web/tests` titles is 0.

## Task 8 — `constants.ts` / `ROUTES` sweep, READMEs, final acceptance
What it is / what it means: One home for fixed values and all URL paths, then prove the PRD. PRD R4, R5, T7, Acceptance Criteria.
What changes at a high level: Create `src/constants.ts` with Firestore collection `session_status`, trusted app hosts (from 02), retry/stale/poll numbers, default contact address and `ROUTES` holding all web URL paths; replace scattered literals (listing real route table first); `config.ts` stays the only `import.meta.env` reader. Update `web/` READMEs to the new layout. Verify the dependency rule (R5) by review. Run the full web gate.
Done when: the `git grep` for route path strings in `web/src` hits only `constants.ts` and api request paths; `typecheck`, `lint`, `test`, `build`, `check:api` green; `schema.d.ts`/`report.d.ts` unchanged by 07 commits; unit count equals Task 1; e2e and smoke green; throwaway compare of light/dark shots against the Task 1 baseline is pixel-identical with no `className` diffs outside moved imports; listed old folders absent and `src/mocks` still present.

Owner-only: none (PRD Manual steps: none). Deferred to 09/owner: legacy `app-staging` mapping in `web/.firebaserc`.
