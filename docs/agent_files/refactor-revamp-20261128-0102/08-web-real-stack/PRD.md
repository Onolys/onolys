---
status: draft
summary: Delete web/src/mocks (and the fake interview relay, MSW worker, dev:mock). Local dev and e2e run on the real API stack (combined local mode from 06); unit tests stub only the network edge with typed builders; npm test runs under the Auth emulator; e2e and its CI re-platformed. No visual change.
date: 2026-11-28
---
# PRD: 08 Web on the real stack (no mocks, e2e on the API stack)

Repo/branch: Onolys/onolys / `refactor/revamp` · Depends on: 06 (hard: `api/scripts/dev.sh` combined mode with Firestore + Auth emulators and stubs on :8000, `[fail:*]` hook, stub voice for interview e2e once it exists), 07 (hard: `web/tests/` layout, `app/`/`features/`, `sample.ts` already in `features/report/`), 02 (hard: Auth-emulator helper; spike 1 PASS), 09 (none: 09 runs after 08 and repoints the Firebase config path) · Owns: `web/src/mocks/**`, `web/src/relay/fakeRelay*.ts`, `web/src/flows/` leftovers, `web/public/mockServiceWorker.js`, `web/.env.*`, `web/tests/helpers/{server,api,statusSource,socket}.ts`, mock-based test bodies in `web/tests/`, `web/tests/e2e/**` content and Playwright configs, the mock/MSW parts of `web/package.json`, `vite.config.ts` and `web/firebase.json`, the `web` / `web-e2e` jobs and stack steps of `nightly.yml`, one new composite action. Does not own: `@onolys/common` (02), `schema.d.ts` content (06 R9), the layout moves (07), eval/web (03), `docs/` (except `web/` READMEs).

## TL;DR
`src/mocks/` (15 files, 3,691 lines) is deleted. Dev and e2e run `api/scripts/dev.sh` + the web dev server. Unit tests stub only HTTP (MSW node server, typed response builders from `schema.d.ts`), with cross-page journeys moved to e2e; `npm test` runs under the Auth emulator. Playwright runs against the real stack (stub STT/LLM/voice), including a loopback-only CSP project and CI changes. One commit series; layout is already done by 07.

## Problem
| Gap | Evidence |
|---|---|
| A 1,090-line state machine re-implements the API's session lifecycle (+1,051-line test, 286+66+221 more test lines); rule 9 forbids it | [verified: `wc -l src/mocks/*`] |
| 22 test files drive `mockBackend.settle/advance/getSession...` (~110 calls); `flows.test.tsx` runs whole journeys on it | [verified: grep `mockBackend\.`] |
| Second fake: `FakeRelaySocket` (231 lines), chosen by `VITE_USE_MOCKS`; fake auth chosen by `VITE_AUTH_MODE=fake` (02 deletes it) | [verified: `createRelaySocket.ts:9`, `createAuthService.ts:6`] |
| Mock plumbing in build/config: `dropMockWorker` plugin, `public/mockServiceWorker.js`, `msw.workerDirectory`, `.env.mock`, `dev:mock`, firebase.json `ignore` entries, two build/hosting guard tests | [verified: `vite.config.ts:10`, `package.json`, `firebase.json`, `hosting/{build,hosting}.test.ts`] |
| e2e runs on mock mode, so it never exercises the real API, Firestore listener or sign-in | [verified: `e2e_review` configs] |
| PR previews do **not** use mocks: they build the real app against staging with `VITE_*` secrets | [verified: `pr-preview.yml:150-168`] |
(Production code importing `mocks/fixtures/sample.ts` was fixed by 07: `sample.ts` now lives in `features/report/`.)

## Goals / Non-Goals
**Goals:** zero mock/fake code in web; local dev and e2e on the real API stack; unit tests with one implementation of the API logic (the API's); same screens, same behaviour; green build/typecheck/lint/tests/e2e at every commit.
**Non-goals:** visual or UX change; new features; layout moves, `ROUTES`, `constants.ts` (07); `schema.d.ts` content (06 R9: must not change); API stub changes (O3); eval/web; docs.

## Requirements
**R1 Unit tests without mocks (rule 9).** Only the network edge is stubbed: `tests/helpers/server.ts` = MSW `setupServer()` with **no default handlers**, `onUnhandledRequest: error`. `tests/helpers/api.ts` = typed builders (`sessionDetail({state})`, `reportView()`, `uploadLimits()`, `usage()`...) typed from `components["schemas"][...]`, so an OpenAPI change breaks typecheck, plus `respond.*(...)` handler helpers. No state machine: a page test gives the page the exact responses for its state (sequence = `once` handlers). Status doc: `tests/helpers/statusSource.ts` pushes docs through the existing `setStatusListener` seam (real Firestore path is covered by e2e + `firestoreListener.test`). Interview: `tests/helpers/socket.ts` = MSW's own WebSocket interception (`ws.link(...)` handlers on the same `setupServer()`; `ws` is exported by the pinned `msw` 3.0.7) [RESOLVED 2026-11-28: rule 17, vendor hook instead of a hand-written scripted socket]; the controller's existing `createSocket` option stays as is. Sign-in: `renderApp` uses 02's emulator-backed real service (spike 1 PASS, no stub fallback; helper calls `connectAuthEmulator(getAuth(initializeApp(cfg)), "http://127.0.0.1:9099")`). Journey-level tests (`tests/flows/flows.test.tsx`, multi-step `settle` chains) become e2e. `stateMachine`/`handlers`/`fixtures` tests are deleted (logic now has one implementation, tested in api `tests/sessions/`); `schema.test.ts` becomes `tests/features/report/sample.test.ts` (sample vs report schema).
**R2 Delete mocks.** `main.tsx` loses `enableMocking`; `createRelaySocket` returns `new WebSocket(url)` (the `RelaySocket` type moves next to it); `vite.config` loses `dropMockWorker`; `package.json` loses `dev:mock`, the `msw.workerDirectory` block (MSW stays, node only); `firebase.json` loses the two `**/mockServiceWorker.js` ignores; `eslint.config.js` loses the `mockServiceWorker.js` ignore; (`build.test.ts`/`hosting.test.ts` are already deleted by 07, audit #8); `.env.example` loses `VITE_USE_MOCKS` (02 already removed `VITE_AUTH_MODE` everywhere and added 02's Auth-emulator var name). Deleted: rest of `src/mocks/`, `public/mockServiceWorker.js`, `.env.mock`, `features/interview/relay/fakeRelay*.ts` (path after 07; `fakeRelay.test.ts` too), `tests/flows/`.
**R2b `VITE_FIRESTORE_DATABASE` removed (owner D-B; 09 R6b hands the web side to 08).** Every env uses the `(default)` database, so web stops reading `VITE_FIRESTORE_DATABASE`: `main.tsx` (`database:` option of the Firestore init), the `firestoreListener.ts` header comment, and the `web/.env.example` line. 09 removes the variable from the deploy/preview workflows and `infra/identity.tf`. Order: 08 lands before 09 applies the staging database switch.
**R3 Local dev.** `npm run dev:local` = `vite --mode stack`; committed `.env.stack`: `VITE_API_BASE_URL=http://127.0.0.1:8000/v1`, `VITE_FIREBASE_PROJECT_ID=demo-onolys`, 02's `VITE_FIREBASE_AUTH_EMULATOR_URL`, `VITE_FIRESTORE_EMULATOR=127.0.0.1:8080`. Flow: `api/scripts/dev.sh` in one terminal, `npm run dev:local` in another. `dev:live` unchanged. Privacy guard: `.env.example` keeps its "no emulator host" rule; `.env.stack` is loopback-only by content and only read by `--mode stack` (no test asserting it: [RESOLVED 2026-11-28: owner rule 17]).
**R4 e2e on the real stack.** `tests/e2e/playwright.config.cjs` `webServer`s: `api/scripts/dev.sh` (wait on its health URL) + `npm run dev:local --port 5173`; `csp` project builds `--mode stack` and previews with the prod `firebase.json` header **plus loopback sources only** (`connect-src` for :8000/:8080/:9099, added in `vite.config` when mode is `stack`; no test of the production header: the CSP project's browser-reported violations are the check, [RESOLVED 2026-11-28: owner rule 17]). Each test signs up a fresh email through the UI; verification reads the oobCode from the Auth emulator REST API (helper in `helpers.cjs`). Real sessions run the stub pipeline to `report_ready`; transient states it passes too fast for (visual shots of upload/processing phases) use `page.route` to hold or shape one response. Failure paths use 06's `[fail:*]` title hook (`fail-no_speech`). Processing-state screens pause status requests via `page.route` (no API stub change). Interview e2e runs through 06's voice stub over WebSocket in combined mode; until that stub exists the interview stays unit-only (O4). Journeys from `flows.test` + `mobile`/`visual` are ported. PR runs the smoke subset (`@smoke` tag from 07); main/nightly run all.
**R5 CI.** `web`: `npm test` itself runs under the Auth emulator: T3 moves 02's CI wrapper into the `package.json` `test` script (`firebase emulators:exec --config api/firebase.json --only auth`, spike 1 PASS: 10 files parallel, 5 runs, 0 flakes, 4.6-7.5s) so local and CI match and the `web` job just runs `npm test`; the path is `api/firebase.json` until 09 Task 1, which repoints it to `firebase/firebase.json` in `package.json` and the `web`/`web-e2e` jobs). API side in e2e/dev: Firebase Admin `verify_id_token` with `FIREBASE_AUTH_EMULATOR_HOST` set by `dev.sh` (06 R5b, owner D-A); web has no fake auth mode); `check:api` untouched. `web-e2e`: new composite `.github/actions/setup-emulators` (Java 21 + cached firebase-tools, lifted from `api-emulator`) + `uv sync --frozen --package onolys-api` + ffmpeg action; runs when `web` **or** `api` changed; timeout raised after T0 timing. `nightly.yml` runs the stack for firefox/webkit. PR preview/deploy workflows unchanged.
**R6 No email rate-limit UI ([RESOLVED 2026-11-28: owner], with 06 R10).** The api no longer throttles the verification and reset email endpoints, so web drops the `email/rate-limited` path. After 02 these files no longer live in `web/src/auth/`: they are in `@onolys/common` (`auth/firebase` `firebaseService`, `auth` `errors`, `types`, `pages/ForgotPassword`; today's lines: `firebaseService.ts:54` `429` -> `email/rate-limited`, `errors.ts:52-53` "Too many requests. Wait a minute and try again.", `types.ts:37,39`, `ForgotPassword.tsx:16` `SHOWN`, tests `firebaseService.test.ts:214-216,238-240`, `errors.test.ts:71-73`, `pages.test.tsx:231`). A 429 now falls to `email/unavailable`. [RESOLVED 2026-11-28: build order] 02 runs first and removes it from `@onolys/common` while moving auth in (02 R2, Task 4/5, released in `v0.4.0`); no `v0.4.1`. 08 only removes web-side remnants (tests/copy still in `web/`) and runs the grep gate. Keep Firebase's own `auth/too-many-requests` (client SDK, not ours) and the generic `429`/`rate_limited` handling for run/interview caps (`queryClient`, `api/errors`, `pageLoadError`). Done in T2 (only web-side remnants; the package side is 02's).

## Architecture
```
vitest (jsdom):  page/hook under test -> openapi-fetch -> MSW stub (typed builders)      status doc -> statusSource stub
dev / e2e:       browser -> vite :5173 -> API combined :8000 (stub STT/LLM/voice) -> Firestore + Auth emulators
                          \-> Firestore listener + sign-in talk to the emulators directly
```

## Migration (one commit per batch, each: typecheck, lint, touched tests green)
| # | Batch | Gate |
|---|---|---|
| T0 | Per-file checklist of every `it` in the 22 mock-using files with its new home (builder test / e2e / deleted-with-reason); e2e and unit pass counts; time `web`/`web-e2e`; no screenshot baseline (dropped in 07) | checklist committed to `agent_files` |
| T1 | Add `server`/`api`/`statusSource`/`socket` helpers; `renderApp` on 02's emulator service; `npm test` under the Auth emulator + `web` job (R5) | helper tests green, `npm test` green under emulator |
| T2 | Port mock-using tests <=5 files per commit (mocks still present, unused by ported files); drop `email/rate-limited` code, copy and tests (R6) | each file's checklist rows done; `git grep -n "email/rate-limited" web` returns 0 |
| T3 | e2e switches to the real stack (R4), journeys from `flows.test` + `mobile`/`visual` ported, CI `web-e2e` + composite action, `nightly.yml` stack runs | full e2e green, smoke green |
| T4 | Delete `mocks/`, fake relay, `tests/flows/`, mock plumbing (R2); `dev:local`, `.env.stack` | AC greps |
| T5 | `web/` READMEs; final AC | full web gate (dev-ship) |
T3 needs 06 T9 + 02 emulator helper; T1 needs 02's emulator helper (spike 1 PASS).

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | Unit-test backend | MSW node stub + typed builders, no state | Real API in vitest global setup; recorded fixtures; bare `fetch` stubs | A JVM + Python start per unit run is slow and duplicates e2e; recordings go stale and pass silently when the contract moves, typed builders fail typecheck; MSW is already pinned and routes by method/URL |
| D2 | Journeys | Playwright against `dev.sh` | Keep `flows.test` on a stub backend | A stateful stub is the fake being deleted |
| D3 | Dev server | `dev:local` + `dev.sh` in two terminals | One script wrapping both; `concurrently` | No new dependency; `dev.sh` already owns emulator lifecycle |
| D4 | Order vs layout | After 07; mock-based test bodies were moved untouched there | Port tests while moving them | Keeps 07 a pure move (gated by typecheck, test count, e2e smoke); this SP changes data, not layout |

## Manual steps
None for cloud. Dev machine: `firebase-tools` + Java on PATH for `npm test` and e2e (same as 06).

## Risks / Open Questions
- Risk: ~110 `mockBackend` calls ported by hand lose assertions. Mitigation: T0 per-`it` checklist; pass-count equality gates; no `it` removed without a logged reason.
- Risk: e2e on JVM + Python is slower/flakier in CI. Mitigation: PR runs smoke only, unique user per test; T0 timing sets the timeout; any further change (serial run, split job) is presented to the owner, not applied automatically. Every `web`/`web-e2e` job stays within 5 minutes (owner rule 6).
- Risk: stub pipeline finishes too fast for processing-screen shots. Mitigation: `page.route` holds in `visual.spec` only (see O3).
- [RESOLVED: default] O1: API in `ENV=local` allows origin `http://localhost:5173` (CORS); env var names (incl. 02's Auth-emulator var) confirmed with 02/06 before T3.
- [RESOLVED: yes] O2: `[fail:*]` title hook (06 O2) kept; web e2e uses `fail-no_speech`.
- [RESOLVED: page.route] O3: e2e pauses status requests via `page.route`; no API stub change.
- [RESOLVED: unit-only until 06 voice stub exists] O4: interview e2e needs stub voice over WebSocket in combined mode.
- [RESOLVED: spike 1 PASS, owner D-E 2026-11-28] O5: emulator-backed `npm test` works; no `signedInService` stub, no kept fake.
- [RESOLVED: owner D-A 2026-11-28] Real stack uses the Auth emulator only; the api verifies its tokens with Admin `verify_id_token` (06). Web fake auth service and `VITE_AUTH_MODE=fake` are deleted by 02; here only `.env.example` cleanup.

## Acceptance Criteria
- `git grep -nEi "mocks/|VITE_USE_MOCKS|VITE_AUTH_MODE|mockServiceWorker|dev:mock|FakeRelay|mockBackend" web .github scripts` returns 0 (excl. lockfile, `docs/`); `src/mocks`, `src/features/interview/relay/fakeRelay*`, `tests/flows` do not exist; `git grep VITE_FIRESTORE_DATABASE web` returns 0.
- `npm run typecheck`, `lint`, `test` (emulator), `build`, `check:api` green; `src/api/schema.d.ts`/`report.d.ts` unchanged by 08 commits; test count per T0 checklist accounted for (every removed `it` has a logged reason).
- `npm run e2e` (stack) and smoke subset green in CI; csp project reports zero violations on the stack build.
- No-UX-change evidence: after T4 (different data) axe gate, journey e2e and an owner glance at the e2e `visual.spec` shots; no `className` diffs.
- Rules cited: 9, 14, 16, 17 (Auth emulator + MSW + Playwright `page.route` are the vendor hooks; no custom fakes).
- `api/scripts/dev.sh` + `npm run dev:local`: sign up, upload, reach `report_ready`, open `/sample` with no mock code.
