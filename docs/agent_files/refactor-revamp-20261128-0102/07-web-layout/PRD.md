---
status: draft
summary: Regroup web/src into app/ + features/ (+ api/, constants.ts), move all 85 unit tests and the Playwright suite into one web/tests/ mirror, and delete web/src/mocks (and the fake interview relay) - local dev and e2e run the real API stack, unit tests stub only the network edge with typed builders. No visual change.
date: 2026-11-28
---
# PRD: 07 Web layout (app/ + features/, tests/, no mocks)

Repo/branch: Onolys/onolys / `refactor/revamp` · Depends on: 02 (hard: `components/ lib/` and auth core already in `@onolys/common`; no `features/auth`), 06 (hard: `api/scripts/dev.sh` combined mode with Firestore + Auth emulators and stubs on :8000), 01 (soft: ids and guard tests already cleaned), 08 (soft: Firebase config path) · Owns: `web/**` except generated `src/api/{schema,report}.d.ts` content, `web/package.json` scripts + MSW block (02 owns deps, 04 owns the `gen:api` token), the `web` / `web-e2e` jobs and web steps of `nightly.yml`, one new composite action. Does not own: `@onolys/common` (02), eval/web (03), `docs/` (except `web/` READMEs).

## TL;DR
`web/src` becomes `main.tsx`, `constants.ts`, `config.ts`, `app/` (shell + route table), `api/`, `features/<screen>/`, `styles/`. Every test moves to `web/tests/` mirroring `src/`; Playwright moves to `web/tests/e2e/`. `src/mocks/` (15 files, 3,691 lines) is deleted: dev and e2e run `api/scripts/dev.sh` + the web dev server; unit tests stub only HTTP (MSW node server, typed response builders from `schema.d.ts`), with cross-page journeys moved to e2e. Moves first (`git mv`, green each commit), mock removal second.

## Problem
| Gap | Evidence |
|---|---|
| A 1,090-line state machine re-implements the API's session lifecycle (+1,051-line test, 286+66+221 more test lines); rule 9 forbids it | [verified: `wc -l src/mocks/*`] |
| 22 test files drive `mockBackend.settle/advance/getSession...` (~110 calls); `flows.test.tsx` runs whole journeys on it | [verified: grep `mockBackend\.`] |
| Production code imports from `mocks/`: `/sample` page uses `mocks/fixtures/sample.ts` | [verified: `SampleReportPage.tsx:9`] |
| Second fake: `FakeRelaySocket` (231 lines), chosen by `VITE_USE_MOCKS`; fake auth chosen by `VITE_AUTH_MODE=fake` (02 deletes it) | [verified: `createRelaySocket.ts:9`, `createAuthService.ts:6`] |
| Mock plumbing in build/config: `dropMockWorker` plugin, `public/mockServiceWorker.js`, `msw.workerDirectory`, `.env.mock`, `dev:mock`, firebase.json `ignore` entries, two build/hosting guard tests | [verified: `vite.config.ts:10`, `package.json`, `firebase.json`, `hosting/{build,hosting}.test.ts`] |
| Layout: tests beside source (85 files), `e2e_review/` (review-era name, finding ids in titles), `routes/` holds the app shell, `__fuzz_review__/`, `src/test/`, `src/flows/` | [verified: `find web`] |
| PR previews do **not** use mocks: they build the real app against staging with `VITE_*` secrets | [verified: `pr-preview.yml:150-168`] |

## Goals / Non-Goals
**Goals:** target tree below; zero mock/fake code in web; one `tests/` folder; same screens, same behaviour; green build/typecheck/lint/tests/e2e at every commit.
**Non-goals:** visual or UX change; new features; moving shared UI (02); `schema.d.ts` content (06 R9: must not change); eval/web; docs; rewriting src imports to `@/` beyond what moves force.

## Requirements
**R1 Target tree.**
```
web/src/  main.tsx  constants.ts  config.ts  styles/index.css
  app/       App ErrorBoundary routes Layout Footer RouteError routeTitle placeholders bootError pageLoadError queryClient createAuthService
  api/       client useApiClient errors types buildInfo firestoreListener statusListener schema.d.ts report.d.ts
  features/  dashboard interview legal rating report session settings speakers upload usage
web/tests/   (mirrors src: app/ api/ features/<x>/)  hosting/  helpers/  e2e/
```
**R2 Mapping (today -> new).**
| Today | New |
|---|---|
| `routes/*` (not the files 02 moved), `App.tsx`, `ErrorBoundary.tsx`, `bootError.ts`, `pageLoadError.ts`, `queryClient.ts` | `app/` same names |
| `auth/useApiClient.ts` (what 02 leaves) | `api/useApiClient.ts` (D9) |
| `auth/createAuthService.ts` (what 02 leaves) | `app/createAuthService.ts` (D9) |
| `protocol/{miti-items.ts,rating.schema.json}` | `features/rating/` (only rating imports them; `api/types.ts` comment reworded) |
| `mocks/fixtures/sample.ts` (+ its `Turn` type) | `features/report/sample.ts` (shipped product data) |
| rest of `mocks/`, `public/mockServiceWorker.js`, `.env.mock`, `relay/fakeRelay*.ts`, `src/flows/` | deleted (R5) |
| `hosting/csp.ts` | `tests/helpers/csp.ts` (only tests + `vite.config` use it) |
| `hosting/*.test.ts`, `test/{setup,renderApp,renderPage}`, `radixShims.test`, `nightly/fast-check.ts` | `tests/hosting/`, `tests/helpers/` |
| `src/**/X.test.ts(x)` (84 more) | `tests/<same dir>/X.test.ts(x)`; names kept (already behaviour-named); `useSessionStatus.*.test` keep suffixes |
| `__fuzz_review__/api-lib.property.test.ts` | `tests/api/errors.property.test.ts` (codepoints/format/spans parts went with 02) |
| `e2e_review/*` (specs, helpers, fixtures, 2 configs, README) | `tests/e2e/*` |
**R3 Test config.** `vite.config.ts`: `test.include tests/**/*.test.{ts,tsx}`, exclude `tests/e2e/**`, `setupFiles tests/helpers/setup.ts`, alias `@` -> `src` (tests import `@/features/...`; `tsconfig` `paths` + `include` add `tests`); FLAKY/NIGHTLY include globs repointed; `eslint.config.js` e2e glob repointed, `mockServiceWorker.js` ignore dropped; `stryker.conf.json` mutate list = `src/api/errors.ts` (auth files left in 02).
**R4 Unit tests without mocks (rule 9).** Only the network edge is stubbed: `tests/helpers/server.ts` = MSW `setupServer()` with **no default handlers**, `onUnhandledRequest: error`. `tests/helpers/api.ts` = typed builders (`sessionDetail({state})`, `reportView()`, `uploadLimits()`, `usage()`...) typed from `components["schemas"][...]`, so an OpenAPI change breaks typecheck, plus `respond.*(...)` handler helpers. No state machine: a page test gives the page the exact responses for its state (sequence = `once` handlers). Status doc: `tests/helpers/statusSource.ts` pushes docs through the existing `setStatusListener` seam (real Firestore path is covered by e2e + `firestoreListener.test`). Interview: `tests/helpers/socket.ts` scripted `WebSocket` stub passed to the controller's existing `createSocket` option. Sign-in: `renderApp` uses 02's emulator-backed service (subject to the 02 spike, O7). Journey-level tests (`flows.test.tsx`, multi-step `settle` chains) become e2e. `stateMachine`/`handlers`/`fixtures` tests are deleted (logic now has one implementation, tested in api `tests/sessions/`); `schema.test.ts` becomes `tests/features/report/sample.test.ts` (sample vs report schema).
**R5 Delete mocks.** `main.tsx` loses `enableMocking`; `createRelaySocket` returns `new WebSocket(url)` (the `RelaySocket` type moves next to it); `vite.config` loses `dropMockWorker`; `package.json` loses `dev:mock`, the `msw.workerDirectory` block (MSW stays, node only); `firebase.json` loses the two `**/mockServiceWorker.js` ignores; delete the "no mock worker" cases in `build.test.ts`/`hosting.test.ts`; `.env.example` loses `VITE_USE_MOCKS`/`VITE_AUTH_MODE` and gains 02's Auth-emulator var.
**R6 Local dev.** `npm run dev:local` = `vite --mode stack`; committed `.env.stack`: `VITE_API_BASE_URL=http://127.0.0.1:8000/v1`, `VITE_FIREBASE_PROJECT_ID=demo-onolys`, 02's `VITE_FIREBASE_AUTH_EMULATOR_URL`, `VITE_FIRESTORE_EMULATOR=127.0.0.1:8080`. Flow: `api/scripts/dev.sh` in one terminal, `npm run dev:local` in another. `dev:live` unchanged. Privacy guard: `.env.example` keeps its "no emulator host" rule; `.env.stack` is loopback-only (asserted) and only read by `--mode stack`.
**R7 e2e on the real stack.** `tests/e2e/playwright.config.cjs` `webServer`s: `api/scripts/dev.sh` (wait on its health URL) + `npm run dev:local --port 5173`; `csp` project builds `--mode stack` and previews with the prod `firebase.json` header **plus loopback sources only** (`connect-src` for :8000/:8080/:9099, added in `vite.config` when mode is `stack`; a test asserts the production header is unchanged). Each test signs up a fresh email through the UI; verification reads the oobCode from the Auth emulator REST API (helper in `helpers.cjs`). Real sessions run the stub pipeline to `report_ready`; transient states it passes too fast for (visual shots of upload/processing phases) use `page.route` to hold or shape one response. Failure paths use 06's `[fail:*]` title hook (`fail-no_speech`). Processing-state screens pause status requests via `page.route` (no API stub change). Interview is unit-only until 06's voice stub exists. PR runs the smoke subset selected by a `@smoke` title tag (replaces the finding-id grep in `playwright.smoke.config.cjs`; ids dropped from titles); main/nightly run all.
**R8 Constants.** `src/constants.ts`: values with no env dependence - Firestore collection name `session_status`, trusted app hosts (from 02), retry/stale/poll numbers, all web URL paths (`ROUTES`; no path string anywhere else), default contact address. `config.ts` stays the only reader of `import.meta.env`.
**R9 CI.** `web`: `npm test` runs under the Auth emulator (`firebase emulators:exec --config <08 path> --only auth` (subject to 08 O3 and 02 spikes)); `check:api` untouched. `web-e2e`: new composite `.github/actions/setup-emulators` (Java 21 + cached firebase-tools, lifted from `api-emulator`) + `uv sync --frozen --package onolys-api` + ffmpeg action; runs when `web` **or** `api` changed; timeout raised after T0 timing. `nightly.yml` repoints e2e/artifact paths, runs the stack for firefox/webkit, repoints campaigns to `tests/api/errors.property.test.ts` + `src/api/errors.ts`. PR preview/deploy workflows unchanged.

## Architecture
```
vitest (jsdom):  page/hook under test -> openapi-fetch -> MSW stub (typed builders)      status doc -> statusSource stub
dev / e2e:       browser -> vite :5173 -> API combined :8000 (stub STT/LLM/voice) -> Firestore + Auth emulators
                          \-> Firestore listener + sign-in talk to the emulators directly
```
Dependency rule: `features/*` may import `api/`, `constants.ts`, `config.ts`, `@onolys/common`; `app/` imports features; features never import `app/` or each other except through a named export of the owning feature.

## Migration (one commit per batch, each: typecheck, lint, touched tests green)
| # | Batch | Gate |
|---|---|---|
| T0 | Baseline: light/dark shots of every route (existing `visual.spec` shot code, `E2E_SHOTS=1`) kept **outside the repo**; per-file checklist of every `it` in the 22 mock-using files with its new home (builder test / e2e / deleted-with-reason); e2e and unit pass counts; time `web`/`web-e2e` | checklist committed to `agent_files` |
| T1 | `routes/` + shell files -> `app/` | tsc, tests |
| T2 | `auth/useApiClient` -> `api/`, `auth/createAuthService` -> `app/`; `protocol/` -> `features/rating/` | tsc, tests |
| T3 | Test config + `tests/helpers` (setup, renderApp, csp) + `tests/{app,api,hosting}` moves | `vitest run` count equals T0 |
| T4-T5 | `tests/features/*` moves (two commits) | count equals T0 |
| T6 | `e2e_review` -> `tests/e2e` (still mock mode): configs, scripts, eslint, CI paths, README, `@smoke` tags | e2e smoke green |
| T7 | Add `server`/`api`/`statusSource`/`socket` helpers; port mock-using tests <=5 files per commit (mocks still present, unused by ported files) | each file's checklist rows done |
| T8 | e2e switches to the real stack (R7), journeys from `flows.test` + `mobile`/`visual` ported, CI `web-e2e` + composite action | full e2e green, smoke green |
| T9 | Delete `mocks/`, fake relay, `flows/`, mock plumbing (R5); `sample.ts` to `features/report/`; `dev:local`, `.env.stack` | AC greps |
| T10 | `constants.ts` sweep (one commit); READMEs; final AC | full web gate (dev-ship) |
T8 needs 06 T9 + 02 emulator helper; T1-T6 can start once 02's rewire commit landed.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | Unit-test backend | MSW node stub + typed builders, no state | Real API in vitest global setup; recorded fixtures; bare `fetch` stubs | A JVM + Python start per unit run is slow and duplicates e2e; recordings go stale and pass silently when the contract moves, typed builders fail typecheck; MSW is already pinned and routes by method/URL |
| D2 | Journeys | Playwright against `dev.sh` | Keep `flows.test` on a stub backend | A stateful stub is the fake being deleted |
| D3 | Dev server | `dev:local` + `dev.sh` in two terminals | One script wrapping both; `concurrently` | No new dependency; `dev.sh` already owns emulator lifecycle |
| D4 | Test mirror imports | `@/` alias, tests only (src keeps relative paths) | `../../../src/...`; alias everywhere | Deep relative paths are unreadable; rewriting all src imports is churn nobody asked for |
| D5 | `hosting/` | Tests + `csp.ts` helper into `tests/`; `web/firebase.json` + `web/.firebaserc` **stay** in `web/` | Move to `firebase/` (08) | `deploy-prod/staging`, `pr-preview` (+`pr_preview.sh`), `release_target.py`, `test_hosting_targets.sh`, `vite.config` all name `web/firebase.json`; `.firebaserc` is live (release_target writes the deploy site into it) [verified]. Only the two mock-worker ignores are edited |
| D6 | Sample report | Product data `features/report/sample.ts` | Keep a `fixtures/` dir; fetch from API | It ships to users on `/sample`; not a fixture |
| D7 | e2e language/location | Stay `.cjs` Playwright, `tests/e2e/` | Port to TS | No benefit asked for; moves only |
| D8 | Constants | `constants.ts` (fixed) + `config.ts` (env) | Per-feature constants; none | Mirrors rule 10's split with `config/` |
| D9 | Auth remainder | `useApiClient` -> `api/`, `createAuthService` -> `app/`; no `features/auth` | One `features/auth` holding two unrelated files | Owner decision (O4) |
| D10 | `dev:live` / stryker | Keep, repoint paths | Delete | Not asked |

## Manual steps
None for cloud. Dev machine: `firebase-tools` + Java on PATH for `npm test` and e2e (same as 06).

## Risks / Open Questions
- Risk: ~110 `mockBackend` calls ported by hand lose assertions. Mitigation: T0 per-`it` checklist; pass-count equality gates; no `it` removed without a logged reason.
- Risk: e2e on JVM + Python is slower/flakier in CI. Mitigation: PR runs smoke only, unique user per test, serial fallback; T0 timing sets the timeout.
- Risk: stub pipeline finishes too fast for processing-screen shots. Mitigation: `page.route` holds in `visual.spec` only (see O5).
- [RESOLVED: default] O1: API in `ENV=local` allows origin `http://localhost:5173` (CORS); env var names (incl. 02's Auth-emulator var) confirmed with 02/06 before T8.
- [RESOLVED: yes] O2: `[fail:*]` title hook (06 O2) kept; web e2e uses `fail-no_speech`.
- [RESOLVED: all paths] O3: `ROUTES` holds ALL web URL paths; state names stay schema types.
- [RESOLVED: split] O4: `useApiClient` -> `api/`, `createAuthService` -> `app/`; no `features/auth`.
- [RESOLVED: page.route] O5: e2e pauses status requests via `page.route`; no API stub change.
- [RESOLVED: unit-only until 06 voice stub exists] O6: interview e2e needs stub voice over WebSocket in combined mode.
- [RESOLVED: decided after 02 spike] O7: emulator-backed `npm test` depends on 02's Auth-emulator spike; result goes to the owner, who decides. 02's logic-free signed-in stub is an option to present, not an automatic fallback.
- [DEFERRED] Legacy `app-staging -> onolys-app-staging` mapping in `web/.firebaserc` (needs `test_hosting_targets.sh` change; 08/owner after the old site is retired); stryker/nightly campaigns review.

## Acceptance Criteria
- `git grep -nEi "mocks/|VITE_USE_MOCKS|VITE_AUTH_MODE|mockServiceWorker|dev:mock|FakeRelay|mockBackend" web .github scripts` returns 0 (excl. lockfile, `docs/`); `src/mocks`, `e2e_review`, `src/routes`, `src/auth`, `src/components`, `src/lib`, `src/hosting`, `src/test`, `src/flows`, `src/protocol`, `src/__fuzz_review__` do not exist.
- No `*.test.*` under `web/src`; `web/tests/` mirrors `src/`; no test or spec title carries a finding/task id.
- `npm run typecheck`, `lint`, `test` (emulator), `build`, `check:api` green; `src/api/schema.d.ts`/`report.d.ts` unchanged by 07 commits; test count per T0 checklist accounted for.
- `npm run e2e` (stack) and smoke subset green in CI; csp project reports zero violations; `tests/hosting` proves the prod header equals `web/firebase.json` and extra sources are loopback only.
- No-UX-change evidence: after T1-T6 (mock data, same render) light/dark shots of every route match T0 baseline pixel-for-pixel by a throwaway compare script; after T9 (different data) axe gate, journey e2e, and an owner glance at the shot set; no `className` diffs outside moved imports.
- `api/scripts/dev.sh` + `npm run dev:local`: sign up, upload, reach `report_ready`, open `/sample` with no mock code.
