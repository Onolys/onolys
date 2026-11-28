---
status: draft
summary: Rename onolys-ui to onolys-common, move shared sign-in/shell/components into it (v0.4.0), then rewire web and eval/web in one atomic series with the Auth emulator replacing the fakes.
date: 2026-11-28
---
# Tasks: 02 UI package (@onolys/common)

Source of truth: /root/projects/onolys/onolys/.worktrees/refactor/revamp/docs/agent_files/refactor-revamp-20261128-0102/02-ui-package/PRD.md. No [OPEN] items remain. Package work (tasks 2-8) happens in the package repo (clone `/root/projects/onolys/onolys-ui`) and ends with the tag; app work (tasks 9-12) happens in this repo and pins the tag. Eval stays on `@onolys/ui` v0.3.0 until the rewire. The package repo has its own CI (`release.yml`, test workflow per PRD R6/R9); this SP extends it, and the main repo's `ci.yml` is edited in task 11.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Apply owner's spike-1 decision | none | todo |
| 2 | Rename repo and package; package CI gets the emulator | 1 | todo |
| 3 | Package cleanup: legacy.css, privacy guard, rules copy | 2 | todo |
| 4 | Move shared components and helpers to the root entry | 3 | todo |
| 5 | Move sign-in to `/auth` with injected config | 4 | todo |
| 6 | Add `/auth/firebase` and `/auth/testing`, emulator tests | 1, 5 | todo |
| 7 | Package build, peers, stories, CHANGELOG, tag v0.4.0 | 4, 5, 6 | todo |
| 8 | Auth emulator block in `api/firebase.json` | 1 | todo |
| 9 | Rewire web to `@onolys/common` | 7, 8 | todo |
| 10 | Rewire eval/web, drop all `@prod-*` | 7, 8 | todo |
| 11 | CI: emulator wrapper, drop prod-web install | 9, 10 | todo |
| 12 | Final verification (acceptance greps, clean install) | 9, 10, 11 | todo |

## Task 1 — Apply owner's spike-1 decision
What it is / what it means: Spike 1 (Auth emulator under vitest + jsdom, phase 0) was reported to the owner, who decided. 02 consumes that decision (PRD R5, Decision 3); it is not re-run here. If the decision is not yet recorded, this task is blocked and nothing downstream starts.
What changes at a high level: Record the decision at the top of the task notes. Option A (spike passed): follow R5 as planned (emulator for stateful flows, `vi.spyOn` for failures, fakes deleted). Option B (owner chose a fallback): a logic-free `signedInService(user)` stub for incidental tests in the 22 `renderApp` files, emulator only where it works; fakes still deleted unless owner says keep. Tasks 6, 9, 10, 11 adapt to the choice; no automatic fallback.
Done when: decision and chosen option written into the task notes and the affected task wording confirmed; no code change; the owner's spike report is cited.

## Task 2 — Rename repo and package; package CI gets the emulator
What it is / what it means: The owner chose `onolys-common` / `@onolys/common` (PRD R10, Decision 7). The agent does the rename; GitHub redirects the old URL.
What changes at a high level: `gh repo rename` Onolys/onolys-ui to onolys-common; update the local clone remote (and folder name if practical); set the package name `@onolys/common` and repo URLs in `package.json`, README, workflows. Add to the package test workflow a firebase-tools + Java step and run auth tests under `firebase emulators:exec --only auth` (model it on the `api-emulator` job in `ci.yml`), with a package-local `firebase.json` containing the Auth block.
Done when: `gh repo view Onolys/onolys-common` succeeds; the package's existing suite and build pass under the new name on its CI; the emulator job runs (even with a trivial smoke test) and is green.

## Task 3 — Package cleanup: legacy.css, privacy guard, rules copy
What it is / what it means: Remove everything legacy unconditionally (rule 16, R6), loosen the privacy guard by exactly one named exception, and give the package its own rules (R10).
What changes at a high level: Delete `legacy.css` and its export; remove the landing page's import of it if present (note for task 9). Privacy guard keeps all rules and adds one named exception (the theme storage file); still no console, no absolute-URL literals. Copy `docs/rules/` into the package repo (synced by hand) and add the line "UI pieces come from `@onolys/common`" to its `design-rules.md`.
Done when: `package.test` asserts no `legacy.css` export; the privacy-scan test passes with the exception listed and fails on a planted `console.log`; grep for "legacy" in the package returns nothing.

## Task 4 — Move shared components and helpers to the root entry
What it is / what it means: R2 root-entry items: no router, no firebase. `lib/spans.ts` is deleted, not moved; `codepoints.ts` moves only if another importer needs it.
What changes at a high level: Move `Field`, `Notice`, `ErrorNote`, `StatusChip`, `SlowStartNotice`/`useSlowPending`, `ErrorRecovery` (props `status`, `reference`; `ApiError` mapping stays in web), `classes` constants, `ThemeToggle` + theme helpers, `AccountMenu` (takes `links` + `renderLink`, router-agnostic), `format`. `AppHeader` gains `centerNavigation`; export the nav-link class; `Footer` gains `compact` and a `themeToggle` slot. Ship `theme-init.js`. Moved tests travel with the code.
Done when: moved component/helper tests plus new tests for `centerNavigation`, `compact` Footer, and `AccountMenu` links injection pass in jsdom in the package; typecheck and lint pass; no `import.meta.env` or app constant in `src/`.

## Task 5 — Move sign-in to `/auth` with injected config
What it is / what it means: R2/R4: sign-in code exists once, in the package, with no app constants. Paths are fixed and exported as `AUTH_PATHS`.
What changes at a high level: Move `AuthProvider`/`useAuth`, guards, pages (Login, Signup, ForgotPassword, VerifyEmail, AuthAction + parts), `errors`, `types`, `next`, `useSignOut`. `AuthAction` takes `allowedHosts` (Onolys host list stays in web constants). Add peers on router and react-query. Plain unit tests for `next` and `auth.property` move here (nightly mutation entries dropped per R9). Auth tests that used the fakes are ported against the task-1 option, assertions kept, not dropped.
Done when: moved/ported auth tests pass in the package, existing assertions preserved (count compared before/after); `allowedHosts` and `AUTH_PATHS` covered by tests; typecheck and lint pass.

## Task 6 — Add `/auth/firebase` and `/auth/testing`, emulator tests
What it is / what it means: R4/R5: the only module importing `firebase`, plus a helper to drive the emulator. Replaces `fake.ts` and `fakeService.ts` (not carried over).
What changes at a high level: `createFirebaseAuthService(config, { emailApi, emulatorUrl })`, with `emailApi` `{ sendVerification(getIdToken, next), sendPasswordReset(email) } | null` returning an HTTP status. `auth/testing` signs up/in/verifies a user and reads action codes via the emulator REST API. Stateful flows run on the real service against the emulator; failure paths (popup blocked, network) use `vi.spyOn`. Old SDK-mock tests are replaced where the emulator can express the case. If the owner chose option B in task 1, add the stub here instead.
Done when: emulator-backed tests for sign up, sign in, verify email, reset password, sign out pass under `emulators:exec --only auth` in package CI; spyOn failure-path tests pass; `emailApi: null` path tested.

## Task 7 — Package build, peers, stories, CHANGELOG, tag v0.4.0
What it is / what it means: R6/R8 step 1. Finish the package and publish the immutable tag the apps will pin.
What changes at a high level: tsup entries `auth/index`, `auth/firebase`, `auth/testing` with shared chunks; `exports` map; optional peers (`react-router`, `@tanstack/react-query`, `firebase`) via `peerDependenciesMeta`; stories for new components; consumer fixtures for new subpaths (including a CSS-only consumer with no auth peers); CHANGELOG 0.4.0; version bump. Merge to `main`, then push tag `release/v0.4.0` (agent has rights; owner only if not).
Done when: `package.test` and consumer-fixture tests pass for every subpath; Storybook a11y, lint, typecheck, privacy guard green; the release workflow publishes `v0.4.0`; `git ls-remote` shows the tag.

## Task 8 — Auth emulator block in `api/firebase.json`
What it is / what it means: R7: add the Auth emulator (port 9099) to the existing emulator config; nothing else in that file changes (09 moves it later; 03 mirrors it for eval).
What changes at a high level: One block added to `api/firebase.json`.
Done when: a test or script check asserts the file parses and has `emulators.auth.port` 9099 beside the existing Firestore entry; `firebase emulators:exec --only auth --config api/firebase.json "true"` exits 0.

## Task 9 — Rewire web to `@onolys/common`
What it is / what it means: R7 for `web/`: one atomic series that ends green. During development use `file:` plus `build:watch` (never committed), then pin the tag.
What changes at a high level: Replace `@onolys/ui` with `@onolys/common#v0.4.0` (https `resolved`, lock regenerated); update every import, including the landing page's. Delete moved files, `lib/spans.ts` and its tests, `web/public/theme-init.js` (copied from the package at build). `web/src/auth` keeps only `useApiClient` and `createAuthService` (fake branch deleted, `emailApi` wired to the typed client). `Layout` and `Footer` use the new package pieces. `renderApp` and the 22 test files use the task-1 approach. Dev mode uses `VITE_FIREBASE_AUTH_EMULATOR_URL`. Update `hosting/privacy.test.ts` paths; keep `mocks/handlers.test.ts` compiling. Drop the moved auth entries from `stryker.conf.json`.
Done when: web unit suite, typecheck, lint, build pass; `web/src/components` and `web/src/lib` are gone; ported sign-in, verify-email, forgot-password and email-action assertions pass; web e2e green; `GIT_SSH_COMMAND=false npm ci` passes in `web/`.

## Task 10 — Rewire eval/web, drop all `@prod-*`
What it is / what it means: R1/R7 for `eval/web`: zero imports from `web/` so it can leave the repo in 03.
What changes at a high level: Same package swap and pin. Replace the `@prod-auth`, `@prod-components`, `@prod-routes` imports in Root, Shell, NoAccess, NewRun, Runs, main with `@onolys/common` (eval passes `emailApi: null`). Remove the aliases from `vite.config.ts` and `tsconfig.json`, the three `@source` lines in `app.css`, and `dedupe` entries only needed for aliasing. Rewrite `bundle.test.ts` to assert one copy of react, firebase and `@onolys/common` without the web path. Copy the package's `theme-init.js` at build (replacing eval's copy). Port `Root.test`/`ErrorPage.test` off `fakeService`. Reword code comments naming `web/src`.
Done when: eval-web tests (incl. rewritten `bundle.test.ts`), typecheck, lint, build pass; the `@prod-` / `../web` / `web/src` grep over `eval/web` (excluding node_modules) finds no code, alias or path; build works with `web/` absent from the checkout; `GIT_SSH_COMMAND=false npm ci` passes.

## Task 11 — CI: emulator wrapper, drop prod-web install
What it is / what it means: R7/R9: CI must start the Auth emulator and stop installing web deps for eval.
What changes at a high level: In `ci.yml`, run web and eval-web test steps through `firebase emulators:exec --only auth --config api/firebase.json "<test cmd>"` (firebase-tools and Java as in the api-emulator job); remove "install prod web deps" from the eval-web job. Flag `deploy-eval.yml:199` and `eval/web/README.md:3` to 03 (left untouched; frozen docs).
Done when: a CI run on the branch has web and eval-web jobs green with the emulator wrapper; the eval-web job has no web install step; workflow file passes `actionlint` if available.

## Task 12 — Final verification
What it is / what it means: Walk the PRD Acceptance Criteria once, read-only, after everything lands.
What changes at a high level: No change unless a check fails (fix goes back to the owning task). Check: greps, tag, lock entries, deleted files, package CI state.
Done when: `git grep "@onolys/ui"` outside `docs/` returns 0; no `fake.ts`/`fakeService.ts`, no `lib/spans.ts`; both apps depend on `@onolys/common#v0.4.0` with https lock entries and no `file:`; no `import.meta.env` or app constant in package `src/`; tag `v0.4.0` and its green CI confirmed; `web/src/auth` holds only the two files; web and eval-web suites, typecheck, lint, build green.

Owner-only: none expected. The agent renames the repo and pushes the tag; the owner steps in only if admin/push rights are missing. The spike-1 decision (task 1) is the owner's and must be recorded before work starts.
