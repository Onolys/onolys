---
status: draft
summary: Move the shared sign-in feature, shell pieces, components and UI helpers into @onolys/ui (new repo release v0.4.0), rewire web/ and eval/web to it, delete the auth fakes in favour of the Firebase Auth emulator, and remove every @prod-* alias so eval/web imports nothing from web/src.
date: 2026-11-28
---
# PRD: 02 UI package (shared UI + sign-in into @onolys/ui)

Repo/branch: Onolys/onolys-ui (`main`, release tag) then Onolys/onolys / `refactor/revamp` · Depends on: 01 (legacy purge) · Owns: all of `Onolys/onolys-ui` (local clone `/root/projects/onolys/onolys-ui`); here: `web/src/{auth (moved parts), components, lib, routes/{AccountMenu,ThemeToggle,Footer,Layout}.tsx}`, `web/public/theme-init.js`, `web/src/test/renderApp.tsx`, `web/package.json`+lock, `eval/web/{vite.config.ts,tsconfig.json,package.json,lock,src/app.css,src/{Root,Shell,NoAccess,NewRun,Runs,main}.tsx,bundle.test.ts,*.test.tsx}`, the eval-web job in `ci.yml`. Does not own: `web/src` -> `app/`+`features/` regrouping and `web/tests/` (07), eval repo split (03), docs.

## TL;DR
`eval/web` reuses main-app code through three aliases. This SP moves everything shared into `@onolys/ui` (new entry points, tag `v0.4.0`), deletes `fake.ts`/`fakeService.ts` (tests use the Auth emulator, rule 9), and rewires both apps. Order: land + tag in onolys-ui first, then one atomic rewire commit here; eval never breaks because v0.3.0 stays pinned until then.

## Problem
| Gap | Evidence |
|---|---|
| eval/web compiles `web/src/{auth,routes,components}` by alias, so it cannot leave the repo | [verified: `eval/web/vite.config.ts:16`, `tsconfig.json:14`] |
| Hidden coupling beyond the aliases: Tailwind `@source` of web files; `firebaseService` imports `web/src/api/client`; pages import `components/classes`; CI/deploy install web deps for eval | [verified: `eval/web/src/app.css:6-8`, `auth/firebaseService.ts:20`, `auth/pages/*:../../components/classes`, `ci.yml:218-222`, `deploy-eval.yml:199`, `bundle.test.ts`] |
| Duplicated UI: header-centred-nav class, NavItem class, compact footer, `theme-init.js` (comment says "keep in sync"), ErrorRecovery vs eval ErrorPage | [verified: `routes/Layout.tsx` vs `eval/web/src/Shell.tsx`; `eval/web/public/theme-init.js:2`; `eval/web/src/ErrorPage.tsx:4`] |
| Parallel fake auth (234 + 12 lines + tests) used by 22 web test files, `dev:mock`, eval tests | [verified: `auth/fakeService.ts`, `test/renderApp.tsx`, `eval Root.test.tsx`] |
| Package is not ready: no router/query/firebase peers, privacy guard bans storage/console/absolute URLs in `src/`, still exports `legacy.css` | [verified: onolys-ui `package.json`, `test/privacy-scan.ts`, `src/styles/legacy.css`] |

## Goals / Non-Goals
**Goals:** one home for shared UI; eval/web has zero imports from `web/`; sign-in code exists once; no app constants in the package; apps pinned to `v0.4.0`.
**Non-goals:** regrouping `web/src` (07); moving eval to its repo (03); eval's own duplicates (`ui/Chip`, `ui/Note`, `ErrorPage`, theme-init copy; follow-up in eval repo, see Risks); new components or visual change; Storybook redesign; landing page work.

## Requirements
**R1 Inventory (what eval uses, where it ends up).**
| eval import | Used in | Destination |
|---|---|---|
| `@prod-auth/{AuthProvider,guards,pages/Login,types,useSignOut}` | Root, Shell, NoAccess | `@onolys/ui/auth` |
| `@prod-auth/firebaseService` | main | `@onolys/ui/auth/firebase` |
| `@prod-auth/fakeService` | Root.test, ErrorPage.test | deleted; emulator (R5) |
| `@prod-components/SlowStart` | Root, NewRun, Runs | `@onolys/ui` |
| `@prod-routes/ThemeToggle` | Shell | `@onolys/ui` |
Nothing is copied into eval; nothing is eval-specific.

**R2 What moves.** To `@onolys/ui/auth` (subpath, needs router + react-query): `AuthProvider`/`useAuth`, `guards`, `pages/*` (Login, Signup, ForgotPassword, VerifyEmail, AuthAction + parts), `errors`, `types` (`AuthService`, `AuthError`), `next`, `useSignOut`. To `@onolys/ui/auth/firebase` (the only module importing `firebase`): `createFirebaseAuthService`. To the root entry (no router/firebase): `Field`, `Notice`, `ErrorNote`, `StatusChip`, `SlowStartNotice`/`useSlowPending`, `ErrorRecovery` (props `status`, `reference`; `ApiError` mapping stays in web), `classes` constants (`H1 PAGE NOTE LINK LINK_BTN ACTIONS`), `ThemeToggle` + theme helpers (+ shipped `theme-init.js`), `AccountMenu`, `format`, `spans`+`codepoints`. `AppHeader` gains `centerNavigation`; package exports the nav-link class; `Footer` gains `compact` + `themeToggle` slot (replaces the two long duplicated class strings).

**R3 What stays product-specific.** `useApiClient` (typed client, `VITE_API_BASE_URL`, session-expired wiring), `createAuthService` (env -> config; fake branch deleted), `Layout` (nav items, widths, `RouteTitle`), `Footer` content (notices, legal links, `CONTACT_EMAIL`), `routes`, `RouteError`, `config.ts`. These keep their paths; 07 relocates them.

**R4 Config injection (no app constants, no `import.meta.env` in the package).** `createFirebaseAuthService(config, { emailApi, emulatorUrl })` where `emailApi` is `{ sendVerification(getIdToken, next), sendPasswordReset(email) } | null` returning an HTTP status (web wires its typed client; eval passes `null`); `AuthAction` takes `allowedHosts` (the Onolys host list moves to web `constants`); `AccountMenu` takes `links` + `renderLink` (router-agnostic; web passes `/settings`). Sign-in paths (`/login /signup /forgot-password /verify-email /auth/action`) are fixed exported `AUTH_PATHS`: Firebase email links target them, both apps already use them.

**R5 Auth tests without fakes (rule 9).** Delete `fake.ts`, `fakeService.ts` and their tests. Stateful flows run the real `createFirebaseAuthService` against the Firebase Auth emulator (`emulatorUrl` injected). Package ships `@onolys/ui/auth/testing`: sign up/in/verify a user and read action codes through the emulator REST API. Failure paths (popup blocked, network) use `vi.spyOn` on the real service, not a second implementation. `renderApp`/eval tests use it. The old `firebaseService.test.ts` SDK module mocks are replaced by emulator tests where the emulator can express the case. Dev mode: `VITE_FIREBASE_AUTH_EMULATOR_URL` instead of `VITE_AUTH_MODE=fake`.

**R6 Package changes (onolys-ui).** New tsup entries (`auth/index`, `auth/firebase`, `auth/testing`) with shared chunks so root and auth entries share one copy of each component; `exports` map + `typesVersions`-free types; `peerDependencies` add `react-router`, `@tanstack/react-query`, `firebase`, all optional via `peerDependenciesMeta` (CSS-only/Astro and non-auth consumers stay clean); remove `legacy.css` export + file (rule 16; no consumer here); privacy guard keeps all rules and gains one named exception (the theme storage file); `spans` drops its `console.warn` (callers use `rejected`). Stories for new components; `package.test` and consumer fixtures cover the new subpaths; CHANGELOG `0.4.0`; version bump.

**R7 Rewire (this repo, one commit series that ends green).** Bump `@onolys/ui` to `#v0.4.0` in `web/` and `eval/web/` (lockfile `resolved` stays https); replace imports; delete moved files; delete `@prod-*` from vite alias/tsconfig paths and the three `@source` lines in `eval/web/src/app.css`; drop `dedupe` entries only needed for aliasing; rewrite `bundle.test.ts` to assert one copy of react/firebase/`@onolys/ui` without the web path; remove "install prod web deps" steps from `ci.yml` eval-web job (and flag `deploy-eval.yml:199` to 03); web and eval-web CI start the Auth emulator (`firebase emulators:exec --only auth`), config port added to the Firebase config 08 consolidates. Update `hosting/privacy.test.ts` paths (it names `src/lib/theme.ts`, `spans.ts`).

**R8 Two-repo workflow.** (1) onolys-ui branch: add code + moved tests (auth, theme, format, spans, components tests travel with code), CI green, merge, push tag `release/v0.4.0` (its workflow builds dist, publishes `v0.4.0`) [verified: `release.yml`, `CHANGELOG` gate]. (2) Dev loop in this repo while (1) is in flight: `npm i file:../../onolys-ui` in `web/` and `eval/web/` + `npm run build:watch` in onolys-ui (documented in `web/README.md:10`); never commit `file:` or `git+ssh` lock entries. (3) Replace with the tag and commit. Repo is public, so CI needs no token [verified: `gh repo view`: PUBLIC; `web/README.md:7`].

**R9 Tests.** Package: moved suites pass in jsdom with emulator (CI job adds firebase-tools like `ci.yml` api-emulator). web/eval: full web and eval-web suites, typecheck, lint, build. `web` nightly auth mutation/fuzz entries (`stryker.conf.json`, `NIGHTLY_MUTATION` include) move as plain unit tests (`next`, `auth.property`) into the package; mutation config for them is dropped.

## Architecture
```
onolys-ui  src/
  components/ui/, components/onolys/   (existing + Field Notice StatusChip SlowStart ErrorRecovery AccountMenu ThemeToggle)
  lib/ (format spans codepoints classes theme)        <- root entry '@onolys/ui'   (peers: react, tailwind)
  auth/  provider guards pages errors next types      <- '@onolys/ui/auth'         (+ react-router, react-query)
  auth/firebase.ts                                    <- '@onolys/ui/auth/firebase' (+ firebase)
  auth/testing.ts                                     <- '@onolys/ui/auth/testing'  (emulator helper)
web/ & eval/web:  config(env) -> createFirebaseAuthService(config,{emailApi|null}) -> <AuthProvider service> -> own routes + AUTH_PATHS pages
```
Tokens vs `lib/theme.ts`: no overlap. Colours/`data-theme` CSS live in the package since 0.2.0 [verified: `tokens.ts`, `theme.css`]; `lib/theme.ts` is the stored preference (localStorage key `onolys-theme`) that sets `data-theme`, absent from the package today [verified: grep]. They end up side by side.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| 1 | Entry points | root + `/auth` + `/auth/firebase` + `/auth/testing` | one index; separate package for auth | Root stays free of router/firebase for the Astro landing page; firebase only where needed; one repo, one tag |
| 2 | Peers | router, react-query, firebase optional peers | hard deps; bundled | Apps pin exact versions and must share one copy (eval `bundle.test` exists for this) |
| 3 | Auth fakes | Delete; Auth emulator for flows, `spyOn` for failures | keep `fakeService`; logic-free static stub for the 22 incidental tests | Rule 9 (no parallel fake; `fakeService` re-implements accounts/codes). Stub fallback only if emulator proves too slow (OPEN) |
| 4 | `useApiClient` | Stays in web; email via injected `emailApi` | move with `openapi-fetch`; plain `fetch` in package | Package must not know API paths/client; eval passes `null` |
| 5 | Route paths | Fixed `AUTH_PATHS` | configurable per app | Email links and both apps already fixed; no second consumer needs otherwise |
| 6 | Shell | Move AccountMenu, ThemeToggle, footer/nav pieces; `Layout` stays | move whole Layout; leave all in apps | Rule 15 asks for reusable pieces; nav items and widths are product choices |
| 7 | Version | `v0.4.0`, `legacy.css` removed | `v0.3.1`; keep legacy | Pre-1.0 minor may break; rule 16; nothing here imports it [verified: `web/src/hosting/styles.test.ts:15-23`] |
| 8 | Privacy guard | Keep; one named storage exception, no console, no literals (emulator URL injected) | relax rules; exclude `auth/` dir | Guard is a package promise; exception list stays reviewable |
| 9 | Release order | Package first, apps pinned after | monorepo workspace; `file:` in main | Tags are immutable so eval build is never half-moved; matches current pattern |
| 10 | `spans` | Move per lock (brainstorm) | delete as dead | See OPEN: no production importer |

## Manual steps
- Confirm the agent can push to `Onolys/onolys-ui` and push tag `release/v0.4.0`; otherwise owner merges the package PR and pushes the tag.

## Risks / Open Questions
- [OPEN] Auth emulator under vitest+jsdom (28 auth test files, 22 web test files via `renderApp`): not tried here, ~80% confident it works (REST endpoints from Firebase docs, not run). First task is a spike. Default if slow/flaky: logic-free `signedInService(user)` stub in `/auth/testing` for incidental tests, emulator only for auth-flow tests. Needs owner OK since it bends rule 9.
- [OPEN] `lib/spans.ts` has no production importer (only its test, a fuzz test, a privacy-test line) [verified: grep `web/src`, `eval/web/src`]; brainstorm said move because eval/landing need it. Default: follow the lock and move with `codepoints.ts`; recommend owner chooses delete (rule 16).
- [OPEN] Does the landing page (not in this repo) import `@onolys/ui/legacy.css`? Default: remove; confirm before tagging.
- [OPEN] API in combined mode must accept Auth-emulator ID tokens instead of `AUTH_MODE=fake` (`test:<uid>`) for `dev` without mocks. Owned by 06/07; this SP only adds the emulator config.
- [OPEN] `theme-init.js` (blocking pre-paint script, CSP forbids inline) shipping: default the package ships the file and apps copy it into `public/` at build; alternative a tiny Vite plugin.
- [OPEN] Rules for the package repo: `onolys-ui` has no `AGENTS.md`/rules. Default: same as 03 (copy rules at release, link source). `design-rules.md` should gain one line "UI pieces come from `@onolys/ui`" (00 moves it verbatim; rules files may change); its "Apply to every UI: web/, eval/web" line is 03's.
- [RESOLVED: lock] Eval sign-in comes from the package, not a copy.
- [DEFERRED] Eval's own near-duplicates (`ui/Chip`, `ui/Note`, `ErrorPage`, `public/theme-init.js`) adopt the package components in the eval repo (03/09).
- [DEFERRED] `eval/web/README.md:3` and `deploy-eval.yml:199` mention the alias/web install; docs frozen, 03 rewrites both when eval moves.
- Interplay: 01 may delete/trim `hosting/*.test.ts` guards pinned to moved paths; 07 depends on this SP for `features/auth` (only `useApiClient`, `createAuthService` remain) and deletes `mocks/` (whose `handlers.test.ts` this SP must keep compiling until then).

## Acceptance Criteria
- `grep -rn "@prod-\|\.\./web\|web/src" eval/web --exclude-dir=node_modules` finds no import, alias, path or `@source`; only comments/README prose may remain (code comments naming `web/src` are reworded); `eval/web` installs, typechecks, tests and builds with `web/` absent from the checkout.
- `web/` and `eval/web` both depend on `#v0.4.0`; lock `resolved` entries are https git, no `file:`; `GIT_SSH_COMMAND=false npm ci` passes in both.
- onolys-ui `v0.4.0` tag exists; its CI (lint, typecheck, tests incl. emulator auth tests, privacy guard, package build, consumer fixtures, Storybook a11y) is green; `legacy.css` gone; CHANGELOG has 0.4.0.
- No `fake.ts`/`fakeService.ts` anywhere; no `import.meta.env` or app constant (hosts, API path, contact email) in package `src/`.
- `web/src/components` and `web/src/lib` are gone; `web/src/auth` holds only `useApiClient`, `createAuthService`; web suite, typecheck, lint, build, e2e green.
- Sign-in, verify-email, forgot-password and email-action flows behave as before (existing assertions ported, not dropped).
