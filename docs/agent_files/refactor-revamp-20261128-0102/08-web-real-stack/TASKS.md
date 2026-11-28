---
status: draft
summary: Web on the real stack in 11 tasks - per-test checklist, typed MSW helpers, emulator-backed npm test, port mock-using tests, e2e on the API stack plus CI, then delete mocks and local-dev wiring.
date: 2026-11-28
---
# Tasks: 08 Web on the real stack

Source of truth: /root/projects/onolys/onolys/.worktrees/refactor/revamp/docs/agent_files/refactor-revamp-20261128-0102/08-web-real-stack/PRD.md. Delete `web/src/mocks` and every fake; dev and e2e run `api/scripts/dev.sh` plus the web dev server. Unit tests stub only HTTP. One commit per task; typecheck, lint and touched tests green after each. `schema.d.ts` and `report.d.ts` must not change. CI exists (`.github/workflows/ci.yml`); this SP edits it. Full suite runs only in dev-ship. Prereqs: 06 (combined dev mode, `[fail:*]` hook), 07 (layout), 02 (Auth-emulator helper), phase-0 spikes 1 and 2.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | T0 checklist, counts, timing (Migration T0) | none | todo |
| 2 | Typed test helpers: server, api builders, statusSource, socket (R1) | 1 | todo |
| 3 | `renderApp` on 02's emulator service; `npm test` under Auth emulator; `web` job (R1, R5, O5) | 2 | todo |
| 4 | Port mock-using tests to helpers, batches of at most 5 files (R1) | 3 | todo |
| 5 | e2e config on the real stack, helpers, CSP project (R4, O1) | 3 | todo |
| 6 | Port journeys and mobile/visual specs; interview e2e if voice stub exists (R4, O2-O4) | 4, 5 | todo |
| 7 | CI: `setup-emulators` action, `web-e2e`, nightly (R5) | 5, 6 | todo |
| 8 | Delete mocks, fake relay, `tests/flows/`, mock plumbing (R2) | 4, 6 | todo |
| 9 | `dev:local`, `.env.stack`, `.env.example`, privacy guard (R3) | 5 | todo |
| 10 | `web/` READMEs | 8, 9 | todo |
| 11 | Final acceptance sweep | 7, 8, 9, 10 | todo |

## Task 1 — T0 checklist, counts, timing
What it is / what it means: Porting about 110 `mockBackend` calls by hand can silently lose assertions. A per-test ledger prevents that (PRD risks, Migration T0).
What changes at a high level: Write a checklist in this folder listing every `it` in the 22 mock-using files with its new home: builder-based unit test, e2e, or deleted with a reason. Record vitest and e2e pass counts and the current `web` and `web-e2e` job times. Reuse 07's baseline screenshot set. No source change.
Done when: checklist committed; counts and timings recorded in it; every `it` has a home or a reason. Verified by running vitest and e2e once and reading the counts.

## Task 2 — Typed test helpers
What it is / what it means: Replace the 1,090-line state machine with stateless stubs. The API's own logic is the only implementation (R1, D1).
What changes at a high level: Add under `web/tests/helpers/`: an MSW node `server` with no default handlers and unhandled requests as errors; `api` with response builders typed from `schema.d.ts` schemas plus `respond.*` helpers; `statusSource` pushing docs through the existing `setStatusListener` seam; `socket`, a scripted WebSocket stub for the controller's `createSocket` option. Old mocks stay untouched.
Done when: a new helper test file proves each helper (unhandled request fails, builders typecheck against schema, status push reaches a listener, socket script plays); typecheck, lint, those tests green.

## Task 3 — Emulator-backed `npm test` and `renderApp`
What it is / what it means: Sign-in in unit tests uses 02's emulator-backed service, not a fake (R1, R5, O5). The path depends on the owner's spike-1 decision.
What changes at a high level: Point `renderApp` at 02's service. Per owner's spike-1 decision, either (a) `npm test` runs under `firebase emulators:exec --config api/firebase.json --only auth`, with the `web` CI job updated to match and the emulator var set, or (b) 02's logic-free signed-in stub, no automatic fallback. Record the choice in the task log. `check:api` untouched.
Done when: `renderApp` sign-in test passes under the chosen option; the full `npm test` command works locally (and in the `web` job, if option a); count not lower than T0 baseline.

## Task 4 — Port mock-using tests
What it is / what it means: Give each page test exactly the responses for its state; no state machine (R1, D4). Multi-step journeys go to Task 6, not here.
What changes at a high level: Move the 22 mock-using files to Task 2 helpers, at most 5 files per commit, mocks still present but unused by ported files. Delete `stateMachine`/`handlers`/`fixtures` tests (one implementation now lives in api tests). Move `schema.test.ts` to `tests/features/report/sample.test.ts` (sample vs report schema). Update the Task 1 ledger per file.
Done when: each batch's ledger rows done; ported files import nothing from `mocks/`; touched tests green; every removed `it` has a logged reason.

## Task 5 — e2e config on the real stack
What it is / what it means: e2e must exercise the real API, Firestore listener and sign-in (R4, O1).
What changes at a high level: `tests/e2e/playwright.config.cjs` starts `api/scripts/dev.sh` (waiting on its health URL) and the web dev server on :5173; confirm API `ENV=local` allows that origin and confirm env var names with 02/06. `helpers.cjs` gains fresh-email sign-up through the UI and oobCode read from the Auth emulator REST API. Add the `csp` project: `--mode stack` build, prod header plus loopback-only `connect-src` for :8000/:8080/:9099, added in `vite.config` only for stack mode.
Done when: one signed-up-and-verified smoke spec passes on the stack; `tests/hosting` proves the production header equals `web/firebase.json` and extra sources are loopback only; csp project reports zero violations.

## Task 6 — Port journeys and mobile/visual specs
What it is / what it means: Journeys from `flows.test` move to Playwright on real sessions (R4, D2).
What changes at a high level: Port journeys and `mobile`/`visual` specs. Real sessions run the stub pipeline to `report_ready`. Failure paths use title `[fail:no_speech]`. Processing-state screens and fast transient states are paused or shaped with `page.route`; no API stub change. Interview e2e runs only if 06's voice stub over WebSocket exists in combined mode; otherwise it stays unit-only (logged). Keep `@smoke` tags.
Done when: full e2e green on the stack, smoke subset green; every journey `it` from the ledger has an e2e home; axe gate passes.

## Task 7 — CI for the real stack
What it is / what it means: CI must run the stack e2e (R5).
What changes at a high level: New composite `.github/actions/setup-emulators` (Java 21, cached firebase-tools, lifted from `api-emulator`). `web-e2e` uses it plus `uv sync --frozen --package onolys-api` and the ffmpeg action, runs when `web` or `api` changed, PR runs smoke only, main and nightly run all, timeout set from Task 1 timing. `nightly.yml` runs the stack for firefox and webkit. PR preview and deploy workflows unchanged.
Done when: `actionlint` passes; CI run shows `web-e2e` smoke green on a PR and the composite action reused by `api-emulator`'s pattern; nightly config dry-read matches the old job set.

## Task 8 — Delete mocks and plumbing
What it is / what it means: Remove everything faked (R2).
What changes at a high level: Delete `src/mocks/`, `public/mockServiceWorker.js`, `.env.mock`, `relay/fakeRelay*.ts`, `tests/flows/`. `main.tsx` loses `enableMocking`; `createRelaySocket` returns `new WebSocket(url)` with `RelaySocket` type beside it; `vite.config` loses `dropMockWorker`; `package.json` loses `dev:mock` and `msw.workerDirectory` (MSW stays); `firebase.json` and `eslint.config.js` lose worker ignores; delete the "no mock worker" cases in `build.test.ts` and `hosting.test.ts`.
Done when: `git grep -nEi "mocks/|VITE_USE_MOCKS|VITE_AUTH_MODE|mockServiceWorker|dev:mock|FakeRelay|mockBackend" web .github scripts` is 0 (excluding lockfile, `docs/`); typecheck, lint, test, build, `check:api` green; hosting and build tests green.

## Task 9 — Local dev wiring
What it is / what it means: One documented way to run the app locally on the real stack (R3, D3).
What changes at a high level: Add `npm run dev:local` (`vite --mode stack`) and committed loopback-only `.env.stack` (API base, project id, 02's Auth-emulator var, Firestore emulator host). `.env.example` drops `VITE_USE_MOCKS`/`VITE_AUTH_MODE`, gains 02's var, keeps its no-emulator-host rule. `dev:live` unchanged.
Done when: a test asserts `.env.stack` hosts are loopback only and `.env.example` has no emulator host; manually, `dev.sh` plus `dev:local` reach sign up, upload, `report_ready` and `/sample` (logged).

## Task 10 — `web/` READMEs
What it is / what it means: Docs match the new flow (Migration T5). No `docs/` edits.
What changes at a high level: Update `web/` READMEs and the e2e README: two-terminal local flow, helpers, emulator prerequisites (`firebase-tools`, Java), `@smoke` and CSP project.
Done when: no README mentions mock mode; commands in READMEs match `package.json` scripts (checked by grep).

## Task 11 — Final acceptance sweep
What it is / what it means: Prove PRD acceptance criteria before review.
What changes at a high level: No edits unless a check fails. Run the AC greps, confirm `schema.d.ts` and `report.d.ts` unchanged, compare the Task 1 ledger with final counts, and collect no-UX-change evidence: axe gate, journey e2e, and shot set vs 07's baseline, with no `className` diffs.
Done when: all AC hold; `src/mocks`, `src/relay/fakeRelay*`, `tests/flows` absent; typecheck, lint, test (emulator), build, `check:api`, e2e and smoke green; every removed `it` accounted for.

Owner-only: report spike-1 and spike-2 decisions before Task 3; glance at the shot set vs 07's baseline in Task 11.
