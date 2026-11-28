---
status: draft
summary: Rename onolys-ui to onolys-common (@onolys/common); move the shared sign-in feature, shell pieces, components and UI helpers into it (release v0.4.0), rewire web/ and eval/web to it, delete the auth fakes in favour of the Firebase Auth emulator, and remove every @prod-* alias so eval/web imports nothing from web/src.
date: 2026-11-28
---
# PRD: 02 UI package (shared UI + sign-in into @onolys/common)

Repo/branch: Onolys/onolys-common (renamed from `onolys-ui`; `main`, release tag) then Onolys/onolys / `refactor/revamp` · Depends on: 01 (legacy purge) · Owns: all of `Onolys/onolys-common` (local clone `/root/projects/onolys/onolys-ui`; the agent renames the repo with `gh repo rename` during this SP); here: `web/src/{auth (moved parts), components, lib, routes/{AccountMenu,ThemeToggle,Footer,Layout}.tsx}`, `web/public/theme-init.js`, `web/src/test/renderApp.tsx`, `web/package.json`+lock, `eval/web/{vite.config.ts,tsconfig.json,package.json,lock,src/app.css,src/{Root,Shell,NoAccess,NewRun,Runs,main}.tsx,bundle.test.ts,*.test.tsx}`, the eval-web job in `ci.yml`, `api/firebase.json` (Auth emulator block only), and the landing page's imports of the renamed package. Does not own: `web/src` -> `app/`+`features/` regrouping and `web/tests/` (07), eval repo split (03), docs.

## TL;DR
`eval/web` reuses main-app code through three aliases. This SP renames the package to `@onolys/common`, moves everything shared into it (new entry points, tag `v0.4.0`), deletes `fake.ts`/`fakeService.ts` (tests use the Auth emulator, rule 9), and rewires both apps (and the landing page imports). Order: Auth-emulator spike 1 (`../spikes/PRD.md`) PASSED (2026-11-28); land + tag in onolys-common, then one atomic rewire commit here; eval never breaks because the old `@onolys/ui` v0.3.0 stays pinned until then.

## Problem
| Gap | Evidence |
|---|---|
| eval/web compiles `web/src/{auth,routes,components}` by alias, so it cannot leave the repo | [verified: `eval/web/vite.config.ts:16`, `tsconfig.json:14`] |
| Hidden coupling beyond the aliases: Tailwind `@source` of web files; `firebaseService` imports `web/src/api/client`; pages import `components/classes`; CI/deploy install web deps for eval | [verified: `eval/web/src/app.css:6-8`, `auth/firebaseService.ts:20`, `auth/pages/*:../../components/classes`, `ci.yml:218-222`, `deploy-eval.yml:199`, `bundle.test.ts`] |
| Duplicated UI: header-centred-nav class, NavItem class, compact footer, `theme-init.js` (comment says "keep in sync"), ErrorRecovery vs eval ErrorPage | [verified: `routes/Layout.tsx` vs `eval/web/src/Shell.tsx`; `eval/web/public/theme-init.js:2`; `eval/web/src/ErrorPage.tsx:4`] |
| Parallel fake auth (234 + 12 lines + tests) used by 22 web test files, `dev:mock`, eval tests | [verified: `auth/fakeService.ts`, `test/renderApp.tsx`, `eval Root.test.tsx`] |
| Package is not ready: no router/query/firebase peers, privacy guard bans storage/console/absolute URLs in `src/`, still exports `legacy.css` | [verified: onolys-ui `package.json`, `test/privacy-scan.ts`, `src/styles/legacy.css`] |

## Goals / Non-Goals
**Goals:** one home for shared UI; package named `@onolys/common`; eval/web has zero imports from `web/`; sign-in code exists once; no app constants in the package; apps pinned to `v0.4.0`.
**Non-goals:** regrouping `web/src` (07); moving eval to its repo (03); eval's own duplicates (`ui/Chip`, `ui/Note`, `ErrorPage`, theme-init copy; follow-up in eval repo, see Risks); new components or visual change; Storybook redesign; landing page work beyond updating its imports.

## Requirements
**R1 Inventory (what eval uses, where it ends up).**
| eval import | Used in | Destination |
|---|---|---|
| `@prod-auth/{AuthProvider,guards,pages/Login,types,useSignOut}` | Root, Shell, NoAccess | `@onolys/common/auth` |
| `@prod-auth/firebaseService` | main | `@onolys/common/auth/firebase` |
| `@prod-auth/fakeService` | Root.test, ErrorPage.test | deleted; emulator (R5) |
| `@prod-components/SlowStart` | Root, NewRun, Runs | `@onolys/common` |
| `@prod-routes/ThemeToggle` | Shell | `@onolys/common` |
Nothing is copied into eval; nothing is eval-specific.

**R2 What moves.** To `@onolys/common/auth` (subpath, needs router + react-query): `AuthProvider`/`useAuth`, `guards`, `pages/*` (Login, Signup, ForgotPassword, VerifyEmail, AuthAction + parts), `errors`, `types` (`AuthService`, `AuthError`), `next`, `useSignOut`. To `@onolys/common/auth/firebase` (the only module importing `firebase`): `createFirebaseAuthService`. To the root entry (no router/firebase): `Field`, `Notice`, `ErrorNote`, `StatusChip`, `SlowStartNotice`/`useSlowPending`, `ErrorRecovery` (props `status`, `reference`; `ApiError` mapping stays in web), `classes` constants (`H1 PAGE NOTE LINK LINK_BTN ACTIONS`), `ThemeToggle` + theme helpers (+ shipped `theme-init.js`), `AccountMenu`, `format`. `AppHeader` gains `centerNavigation`; package exports the nav-link class; `Footer` gains `compact` + `themeToggle` slot (replaces the two long duplicated class strings). `lib/spans.ts` is deleted, not moved (no production importer); `codepoints.ts` moves only if another importer needs it, else deleted with it.

**R3 What stays product-specific.** `useApiClient` (typed client, `VITE_API_BASE_URL`, session-expired wiring), `createAuthService` (env -> config; fake branch deleted), `Layout` (nav items, widths, `RouteTitle`), `Footer` content (notices, legal links, `CONTACT_EMAIL`), `routes`, `RouteError`, `config.ts`. These keep their paths; 07 relocates them.

**R4 Config injection (no app constants, no `import.meta.env` in the package).** `createFirebaseAuthService(config, { emailApi, emulatorUrl })` where `emailApi` is `{ sendVerification(getIdToken, next), sendPasswordReset(email) } | null` returning an HTTP status (web wires its typed client; eval passes `null`); `AuthAction` takes `allowedHosts` (the Onolys host list moves to web `constants`); `AccountMenu` takes `links` + `renderLink` (router-agnostic; web passes `/settings`). Sign-in paths (`/login /signup /forgot-password /verify-email /auth/action`) are fixed exported `AUTH_PATHS`: Firebase email links target them, both apps already use them.

**R5 Auth tests without fakes (rule 9).** [RESOLVED 2026-11-28, spike 1 PASS] The real `createFirebaseAuthService` ran against the Firebase Auth emulator under vitest+jsdom: sign up/in/verify/out, 10 files in parallel, 5 runs, 0 flakes, 4.6-7.5s. No fallback (no `signedInService` stub, no kept fake). Delete `fake.ts`, `fakeService.ts` and their tests. The testing helper calls `connectAuthEmulator(getAuth(initializeApp(cfg)), "http://127.0.0.1:9099")` before `createFirebaseAuthService`, with `emailApi: null`; verification codes come from the emulator REST `oobCodes`. Stateful flows run the real `createFirebaseAuthService` against the Auth emulator (`emulatorUrl` injected). Package ships `@onolys/common/auth/testing`: sign up/in/verify a user and read action codes through the emulator REST API. Failure paths (popup blocked, network) use `vi.spyOn` on the real service, not a second implementation. `renderApp`/eval tests use it. The old `firebaseService.test.ts` SDK module mocks are replaced by emulator tests where the emulator can express the case. Dev mode: `VITE_FIREBASE_AUTH_EMULATOR_URL` instead of `VITE_AUTH_MODE=fake`; `VITE_AUTH_MODE=fake` is deleted (owner D-A: official tools, no fake mode). The api side verifies emulator tokens with Firebase Admin `verify_id_token` (06 owns).

**R6 Package changes (onolys-common).** New tsup entries (`auth/index`, `auth/firebase`, `auth/testing`) with shared chunks so root and auth entries share one copy of each component; `exports` map + `typesVersions`-free types; `peerDependencies` add `react-router`, `@tanstack/react-query`, `firebase`, all optional via `peerDependenciesMeta` (CSS-only/Astro and non-auth consumers stay clean); remove the `legacy.css` export and file unconditionally (rule 16; nothing named legacy stays; no pre-check or confirm step), and the landing page's import of it if it has one; privacy guard keeps all rules and gains one named exception (the theme storage file); `theme-init.js` ships in the package. Stories for new components; `package.test` and consumer fixtures cover the new subpaths; CHANGELOG `0.4.0`; version bump; package name `@onolys/common`.

**R7 Rewire (this repo, one commit series that ends green).** Replace `@onolys/ui` with `@onolys/common` at `#v0.4.0` in `web/` and `eval/web/` (lockfile `resolved` stays https); replace imports (incl. every existing `@onolys/ui` import); delete moved files; delete `lib/spans.ts` and its tests; delete `@prod-*` from vite alias/tsconfig paths and the three `@source` lines in `eval/web/src/app.css`; drop `dedupe` entries only needed for aliasing; delete `bundle.test.ts` (test of bundler config; keep `resolve.dedupe` for react/firebase/`@onolys/common` in `vite.config.ts`, which is the vendor mechanism) [RESOLVED 2026-11-28: owner rule 17]; apps copy the package's `theme-init.js` into `public/` at build (replaces `web/public/theme-init.js` and eval's copy); remove "install prod web deps" steps from `ci.yml` eval-web job (and flag `deploy-eval.yml:199` to 03); this SP adds an Auth emulator block (port 9099) to `api/firebase.json` (the existing emulator config today), and web and eval-web CI start it with `firebase emulators:exec --only auth --config api/firebase.json "<test cmd>"`; 09 later moves that file into `firebase/` and updates the path (03 gives the eval repo's own `firebase.json` the same block). `hosting/privacy.test.ts` is deleted (audit #8), not updated.

**R8 Two-repo workflow.** (1) onolys-common branch: add code + moved tests (auth, theme, format, components tests travel with code), CI green, merge, push tag `release/v0.4.0` (its workflow builds dist, publishes `v0.4.0`) [verified: `release.yml`, `CHANGELOG` gate]. (2) Dev loop in this repo while (1) is in flight: `npm i file:../../onolys-ui` (or `onolys-common` after the rename) in `web/` and `eval/web/` + `npm run build:watch` in the package (documented in `web/README.md:10`); never commit `file:` or `git+ssh` lock entries. (3) Replace with the tag and commit. Repo is public, so CI needs no token [verified: `gh repo view`: PUBLIC; `web/README.md:7`].

**R9 Tests.** Package: moved suites pass in jsdom with emulator (CI job adds firebase-tools like `ci.yml` api-emulator). web/eval: full web and eval-web suites, typecheck, lint, build. The `next` unit test moves with the code; the web nightly auth fuzz/mutation entries (`stryker.conf.json`, `NIGHTLY_MUTATION` include, `auth.property`) are deleted, not moved, with `@stryker-mutator/*` devDeps (one-off review harnesses; rules 16/17; audit #3) [RESOLVED 2026-11-28: owner rule 17]. Tests of tooling (`hosting/privacy.test.ts`, `lint.test.ts`, `radixShims.test.tsx`) are deleted, not repointed (audit #8).

**R10 Rename and rules.** Repo `Onolys/onolys-ui` becomes `Onolys/onolys-common` (agent renames via `gh repo rename`; GitHub redirects the old URL); package `@onolys/ui` becomes `@onolys/common`, done inside this SP since it rewires every import anyway, including the landing page's. The package repo keeps its own copy of `docs/rules/` (00; synced by hand); `design-rules.md` there gains one line "UI pieces come from `@onolys/common`". Its "Apply to every UI: web/, eval/web" line is 03's.

## Architecture
```
onolys-common  src/
  components/ui/, components/onolys/   (existing + Field Notice StatusChip SlowStart ErrorRecovery AccountMenu ThemeToggle)
  lib/ (format classes theme)                         <- root entry '@onolys/common'   (peers: react, tailwind)
  auth/  provider guards pages errors next types      <- '@onolys/common/auth'         (+ react-router, react-query)
  auth/firebase.ts                                    <- '@onolys/common/auth/firebase' (+ firebase)
  auth/testing.ts                                     <- '@onolys/common/auth/testing'  (emulator helper)
web/ & eval/web:  config(env) -> createFirebaseAuthService(config,{emailApi|null}) -> <AuthProvider service> -> own routes + AUTH_PATHS pages
```
Tokens vs `lib/theme.ts`: no overlap. Colours/`data-theme` CSS live in the package since 0.2.0 [verified: `tokens.ts`, `theme.css`]; `lib/theme.ts` is the stored preference (localStorage key `onolys-theme`) that sets `data-theme`, absent from the package today [verified: grep]. They end up side by side.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| 1 | Entry points | root + `/auth` + `/auth/firebase` + `/auth/testing` | one index; separate package for auth | Root stays free of router/firebase for the Astro landing page; firebase only where needed; one repo, one tag |
| 2 | Peers | router, react-query, firebase optional peers | hard deps; bundled | Apps pin exact versions and must share one copy (eval `bundle.test` exists for this) |
| 3 | Auth fakes | Delete; Auth emulator for flows, `spyOn` for failures (spike 1 PASS, owner D-E 2026-11-28) | keep `fakeService`; logic-free static stub for the 22 incidental tests (both dropped: spike passed) | Rule 9 (no parallel fake; `fakeService` re-implements accounts/codes) |
| 4 | `useApiClient` | Stays in web; email via injected `emailApi` | move with `openapi-fetch`; plain `fetch` in package | Package must not know API paths/client; eval passes `null` |
| 5 | Route paths | Fixed `AUTH_PATHS` | configurable per app | Email links and both apps already fixed; no second consumer needs otherwise |
| 6 | Shell | Move AccountMenu, ThemeToggle, footer/nav pieces; `Layout` stays | move whole Layout; leave all in apps | Rule 15 asks for reusable pieces; nav items and widths are product choices |
| 7 | Version + name | `@onolys/common` `v0.4.0`, `legacy.css` removed entirely | `v0.3.1`; keep legacy; keep `@onolys/ui` | Pre-1.0 minor may break; rule 16; nothing here imports it [verified: `web/src/hosting/styles.test.ts:15-23`]; owner chose the name |
| 8 | Privacy guard | Keep; one named storage exception, no console, no literals (emulator URL injected) | relax rules; exclude `auth/` dir | Guard is a package promise; exception list stays reviewable |
| 9 | Release order | Package first, apps pinned after | monorepo workspace; `file:` in main | Tags are immutable so eval build is never half-moved; matches current pattern |
| 10 | `spans` | Delete `lib/spans.ts` (and its tests) | move per brainstorm lock | No production importer; rule 16 (owner decision) |
| 11 | `theme-init.js` | Package ships it; apps copy into `public/` at build | Vite plugin | Simple; CSP forbids inline script |

## Manual steps
- Agent renames GitHub repo `Onolys/onolys-ui` to `Onolys/onolys-common` (`gh repo rename`), then pushes tag `release/v0.4.0`; owner only steps in if the agent lacks push/admin rights.
- Review the combined phase-0 spike report (spike 1, Auth emulator) and decide (R5).

## Risks / Open Questions
- [RESOLVED: spike 1 PASS, 2026-11-28] Auth emulator under vitest+jsdom (28 auth test files, 22 web test files via `renderApp`) works, no flakes; fallback options removed.
- [RESOLVED: owner D-A 2026-11-28] No custom auth: web fake auth service and `VITE_AUTH_MODE=fake` deleted; tests and dev use the Auth emulator.
- [RESOLVED: delete] `lib/spans.ts` (no production importer): deleted, not moved.
- [RESOLVED: remove unconditionally] `legacy.css` removed, and the landing page's import if it has one; nothing named legacy stays.
- [RESOLVED: owned by 06; spike 2 / owner D-A] API accepts Auth-emulator ID tokens via Firebase Admin `verify_id_token` with `FIREBASE_AUTH_EMULATOR_HOST`. This SP only adds the emulator config (`api/firebase.json`; 06/08 CI also need it, 09 later moves it).
- [RESOLVED: package ships, apps copy] `theme-init.js` shipped by the package; apps copy it into `public/`.
- [RESOLVED: own copy] Rules for the package repo: own copy of `docs/rules/` (synced by hand); `design-rules.md` gains "UI pieces come from `@onolys/common`".
- [RESOLVED: lock] Eval sign-in comes from the package, not a copy.
- [RESOLVED: owner] Rename `onolys-ui` -> `onolys-common`, `@onolys/ui` -> `@onolys/common`, done by the agent in this SP (R10).
- [DEFERRED] Eval's own near-duplicates (`ui/Chip`, `ui/Note`, `ErrorPage`, `public/theme-init.js`) adopt the package components in the eval repo (03/10).
- [DEFERRED] `eval/web/README.md:3` and `deploy-eval.yml:199` mention the alias/web install; docs frozen, 03 rewrites both when eval moves.
- Rule 17 applies to this SP: auth = Firebase SDK + Auth emulator (documented REST `oobCodes`), no custom auth service or fake; the `auth/testing` helper stays a thin function over those (no wrapper classes). Rules cited: 9, 15, 16, 17.
- Interplay: 01 may delete/trim `hosting/*.test.ts` guards pinned to moved paths; 07 depends on this SP for the auth remainder (only `useApiClient`, `createAuthService` remain) and 08 deletes `mocks/` (whose `handlers.test.ts` this SP must keep compiling until then).

## Acceptance Criteria
- `grep -rn "@prod-\|\.\./web\|web/src" eval/web --exclude-dir=node_modules` finds no import, alias, path or `@source`; only comments/README prose may remain (code comments naming `web/src` are reworded); `eval/web` installs, typechecks, tests and builds with `web/` absent from the checkout.
- `api/firebase.json` has the Auth emulator block (port 9099); both CI jobs run `emulators:exec --only auth --config api/firebase.json`.
- `git grep "@onolys/ui"` outside `docs/` returns 0 (web, eval/web, landing page imports all on `@onolys/common`).
- `web/` and `eval/web` both depend on `@onolys/common#v0.4.0`; lock `resolved` entries are https git, no `file:`; `GIT_SSH_COMMAND=false npm ci` passes in both.
- onolys-common `v0.4.0` tag exists; its CI (lint, typecheck, tests incl. emulator auth tests, privacy guard, package build, consumer fixtures, Storybook a11y) is green; `legacy.css` gone; CHANGELOG has 0.4.0.
- No `fake.ts`/`fakeService.ts` anywhere (spike 1 PASS; no fallback); no `lib/spans.ts`; no `import.meta.env` or app constant (hosts, API path, contact email) in package `src/`.
- `web/src/components` and `web/src/lib` are gone; `web/src/auth` holds only `useApiClient`, `createAuthService`; web suite, typecheck, lint, build, e2e green.
- Sign-in, verify-email, forgot-password and email-action flows behave as before (existing assertions ported, not dropped).
