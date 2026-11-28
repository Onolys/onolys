---
status: draft
summary: Rename onolys-ui to onolys-common, move shared sign-in/shell/components into it (v0.4.0), then rewire web and eval/web in one atomic series with the Auth emulator replacing the fakes.
date: 2026-11-28
---
# Tasks: 02 UI package (@onolys/common)

Source of truth: /root/projects/onolys/onolys/.worktrees/refactor/revamp/docs/agent_files/refactor-revamp-20261128-0102/02-ui-package/PRD.md. No [OPEN] items remain; spike 1 passed (owner D-E), so the Auth emulator is the only auth-test path and no fallback exists. Package work (tasks 1-6) happens in the package repo (clone `/root/projects/onolys/onolys-ui`) and ends with the tag; app work (tasks 7-10) happens in this repo and pins the tag. Eval stays on `@onolys/ui` v0.3.0 until the rewire. Follow `docs/rules/coding-rules.md`; rule 17 applies (use the Firebase SDK and emulator, build no custom auth or fakes).

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Rename repo and package; package CI gets the emulator | none | todo |
| 2 | Package cleanup: legacy.css, privacy guard, rules copy | 1 | todo |
| 3 | Move shared components and helpers to the root entry | 2 | todo |
| 4 | Move sign-in to `/auth` with injected config | 3 | todo |
| 5 | Add `/auth/firebase` and `/auth/testing`, emulator tests | 4 | todo |
| 6 | Package build, peers, stories, CHANGELOG, tag v0.4.0 | 3, 4, 5 | todo |
| 7 | Auth emulator block in `api/firebase.json` | none | todo |
| 8 | Rewire web to `@onolys/common` | 6, 7 | todo |
| 9 | Rewire eval/web, drop all `@prod-*` | 6, 7 | todo |
| 10 | CI: emulator wrapper, drop prod-web install | 8, 9 | todo |
| 11 | Final verification (acceptance greps, clean install) | 8, 9, 10 | todo |

## Task 1 — Rename repo and package; package CI gets the emulator
What it is / what it means: The owner chose `onolys-common` / `@onolys/common` (PRD R10, Decision 7). The agent does the rename; GitHub redirects the old URL.
What changes at a high level: `gh repo rename` Onolys/onolys-ui to onolys-common; update the local clone remote (and folder name if practical); set the package name `@onolys/common` and repo URLs in `package.json`, README, workflows. Add to the package test workflow a firebase-tools + Java step and run auth tests under `firebase emulators:exec --only auth` (model it on the `api-emulator` job in `ci.yml`), with a package-local `firebase.json` containing the Auth block.
Done when: `gh repo view Onolys/onolys-common` succeeds; the package's existing suite and build pass under the new name on its CI; the emulator job runs (even with a trivial smoke test) and is green.

## Task 2 — Package cleanup: legacy.css, privacy guard, rules copy
What it is / what it means: Remove everything legacy unconditionally, with no pre-check or confirm step (rule 16, R6, Decision 7), loosen the privacy guard by exactly one named exception (Decision 8), and give the package its own rules (R10).
What changes at a high level: Delete `legacy.css` and its export; remove the landing page's import of it if present. Privacy guard keeps all rules and adds one named exception (the theme storage file); still no console, no absolute-URL literals (emulator URL is injected). Copy `docs/rules/` into the package repo (synced by hand) and add the line "UI pieces come from `@onolys/common`" to its `design-rules.md`.
Done when: `package.test` asserts no `legacy.css` export; the privacy-scan test passes with the exception listed and fails on a planted `console.log`; grep for "legacy" in the package returns nothing.

## Task 3 — Move shared components and helpers to the root entry
What it is / what it means: R2 root-entry items: no router, no firebase. `lib/spans.ts` is deleted, not moved (Decision 10); `codepoints.ts` moves only if another importer needs it, else is deleted with it.
What changes at a high level: Move `Field`, `Notice`, `ErrorNote`, `StatusChip`, `SlowStartNotice`/`useSlowPending`, `ErrorRecovery` (props `status`, `reference`; `ApiError` mapping stays in web), `classes` constants, `ThemeToggle` + theme helpers, `AccountMenu` (takes `links` + `renderLink`, router-agnostic), `format`. `AppHeader` gains `centerNavigation`; export the nav-link class; `Footer` gains `compact` and a `themeToggle` slot. Ship `theme-init.js` (Decision 11). Moved tests travel with the code.
Done when: moved component/helper tests plus new tests for `centerNavigation`, `compact` Footer, and `AccountMenu` links injection pass in jsdom in the package; typecheck and lint pass; no `import.meta.env` or app constant in `src/`.

## Task 4 — Move sign-in to `/auth` with injected config
What it is / what it means: R2/R4: sign-in code exists once, in the package, with no app constants. Paths are fixed and exported as `AUTH_PATHS` (Decision 5).
What changes at a high level: Move `AuthProvider`/`useAuth`, guards, pages (Login, Signup, ForgotPassword, VerifyEmail, AuthAction + parts), `errors`, `types`, `next`, `useSignOut`. `AuthAction` takes `allowedHosts` (Onolys host list stays in web `constants`). Add optional peers on router and react-query. The `next` unit test moves with the code. `auth.property` and the nightly fuzz/mutation entries are deleted, not moved (R9, audit #3). Tests that used the fakes are ported to the emulator helper from task 5 (or `vi.spyOn` for failure paths), assertions kept, not dropped.
Done when: moved/ported auth tests pass in the package, existing assertions preserved (count compared before/after, excluding the deleted property tests); `allowedHosts` and `AUTH_PATHS` covered by tests; typecheck and lint pass.

## Task 5 — Add `/auth/firebase` and `/auth/testing`, emulator tests
What it is / what it means: R4/R5: the only module importing `firebase`, plus a thin helper to drive the emulator. Replaces `fake.ts` and `fakeService.ts` (not carried over; no stub, no fallback; rules 9, 17).
What changes at a high level: `createFirebaseAuthService(config, { emailApi, emulatorUrl })`, with `emailApi` `{ sendVerification(getIdToken, next), sendPasswordReset(email) } | null` returning an HTTP status. `auth/testing` is a plain function over the SDK and the emulator REST API (documented `oobCodes`): `connectAuthEmulator(getAuth(initializeApp(cfg)), "http://127.0.0.1:9099")`, sign up/in/verify a user, read action codes; no wrapper classes. Stateful flows run on the real service; failure paths (popup blocked, network) use `vi.spyOn` on it. Old SDK-mock tests are replaced where the emulator can express the case.
Done when: emulator-backed tests for sign up, sign in, verify email, reset password, sign out pass under `emulators:exec --only auth` in package CI; spyOn failure-path tests pass; `emailApi: null` path tested.

## Task 6 — Package build, peers, stories, CHANGELOG, tag v0.4.0
What it is / what it means: R6/R8 step 1. Finish the package and publish the immutable tag the apps will pin (Decisions 1, 2, 9).
What changes at a high level: tsup entries `auth/index`, `auth/firebase`, `auth/testing` with shared chunks; `exports` map; optional peers (`react-router`, `@tanstack/react-query`, `firebase`) via `peerDependenciesMeta`; stories for new components; consumer fixtures for new subpaths (including a CSS-only consumer with no auth peers); CHANGELOG 0.4.0; version bump. Merge to `main`, then push tag `release/v0.4.0` (agent has rights; owner only if not).
Done when: `package.test` and consumer-fixture tests pass for every subpath; Storybook a11y, lint, typecheck, privacy guard green; the release workflow publishes `v0.4.0`; `git ls-remote` shows the tag.

## Task 7 — Auth emulator block in `api/firebase.json`
What it is / what it means: R7: add the Auth emulator (port 9099) to the existing emulator config; nothing else in that file changes (09 moves it later; 03 mirrors it for eval; 06/08 CI also need it).
What changes at a high level: One block added to `api/firebase.json`.
Done when: a test or script check asserts the file parses and has `emulators.auth.port` 9099 beside the existing Firestore entry; `firebase emulators:exec --only auth --config api/firebase.json "true"` exits 0.

## Task 8 — Rewire web to `@onolys/common`
What it is / what it means: R7 for `web/`: one atomic series that ends green. During development use `file:` plus `build:watch` (never committed), then pin the tag.
What changes at a high level: Replace `@onolys/ui` with `@onolys/common#v0.4.0` (https `resolved`, lock regenerated); update every import, including the landing page's. Delete moved files, `lib/spans.ts` and its tests, `web/public/theme-init.js` (copied from the package at build). `web/src/auth` keeps only `useApiClient` and `createAuthService` (fake branch deleted, `emailApi` wired to the typed client). `Layout` and `Footer` use the new package pieces. `renderApp` and the 22 test files use the emulator helper. Dev mode uses `VITE_FIREBASE_AUTH_EMULATOR_URL`; `VITE_AUTH_MODE=fake` is deleted. Delete `hosting/privacy.test.ts`, `stryker.conf.json`, the `NIGHTLY_MUTATION` include and `@stryker-mutator/*` devDeps (audit #3, #8); keep `mocks/handlers.test.ts` compiling.
Done when: web unit suite, typecheck, lint, build pass; `web/src/components` and `web/src/lib` are gone; ported sign-in, verify-email, forgot-password and email-action assertions pass; web e2e green; `GIT_SSH_COMMAND=false npm ci` passes in `web/`.

## Task 9 — Rewire eval/web, drop all `@prod-*`
What it is / what it means: R1/R7 for `eval/web`: zero imports from `web/` so it can leave the repo in 03.
What changes at a high level: Same package swap and pin. Replace the `@prod-auth`, `@prod-components`, `@prod-routes` imports in Root, Shell, NoAccess, NewRun, Runs, main with `@onolys/common` (eval passes `emailApi: null`). Remove the aliases from `vite.config.ts` and `tsconfig.json`, the three `@source` lines in `app.css`, and `dedupe` entries only needed for aliasing. Delete `bundle.test.ts` (tooling test, rule 17); keep `resolve.dedupe` for react, firebase and `@onolys/common`. Copy the package's `theme-init.js` at build (replacing eval's copy). Port `Root.test`/`ErrorPage.test` off `fakeService` to the emulator. Reword code comments naming `web/src`.
Done when: eval-web tests, typecheck, lint, build pass; the `@prod-` / `../web` / `web/src` grep over `eval/web` (excluding node_modules) finds no code, alias or path; build works with `web/` absent from the checkout; `GIT_SSH_COMMAND=false npm ci` passes.

## Task 10 — CI: emulator wrapper, drop prod-web install
What it is / what it means: R7/R9: CI must start the Auth emulator and stop installing web deps for eval.
What changes at a high level: In `ci.yml`, run web and eval-web test steps through `firebase emulators:exec --only auth --config api/firebase.json "<test cmd>"` (firebase-tools and Java as in the api-emulator job); remove "install prod web deps" from the eval-web job. Flag `deploy-eval.yml:199` and `eval/web/README.md:3` to 03 (left untouched; deferred).
Done when: a CI run on the branch has web and eval-web jobs green with the emulator wrapper; the eval-web job has no web install step; workflow file passes `actionlint` if available.

## Task 11 — Final verification
What it is / what it means: Walk the PRD Acceptance Criteria once, read-only, after everything lands.
What changes at a high level: No change unless a check fails (fix goes back to the owning task). Check: greps, tag, lock entries, deleted files, package CI state.
Done when: `git grep "@onolys/ui"` outside `docs/` returns 0; no `fake.ts`/`fakeService.ts`, no `lib/spans.ts`, no `legacy.css`; both apps depend on `@onolys/common#v0.4.0` with https lock entries and no `file:`; no `import.meta.env` or app constant in package `src/`; tag `v0.4.0` and its green CI confirmed; `web/src/auth` holds only the two files; web and eval-web suites, typecheck, lint, build green.

Owner-only: none. The agent renames the repo and pushes the tag; the owner steps in only if admin/push rights are missing.
