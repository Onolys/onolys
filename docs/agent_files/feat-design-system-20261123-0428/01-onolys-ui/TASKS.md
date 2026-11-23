---
status: draft
summary: 13 tasks - repo, scaffold + spike, tokens + contrast, styles, shadcn and Onolys components, CSP-safe Radix, Storybook, build/types, CSP smoke + fixtures, CI, v0.1.0 release
date: 2026-11-23
---
# Tasks: SP1 @onolys/ui shared design system
Source of truth: docs/agent_files/feat-design-system-20261123-0428/01-onolys-ui/PRD.md. All work is in the new repo `Onolys/onolys-ui` except this file. Each task writes tests first, runs only what it touches, and ends with a commit. SP2 consumes tag `v0.1.0`.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Create public repo Onolys/onolys-ui | - | done |
| 2 | Scaffold toolchain + Storybook/shadcn spike | 1 | done |
| 3 | Tokens, dark theme, contrast test | 2 | done |
| 4 | Theme, base, fonts, legacy CSS, cn | 3 | done |
| 5 | shadcn components | 4 | done |
| 6 | Onolys components | 5 | done |
| 7 | CSP-safe Radix overlays | 5 | done |
| 8 | Hit-area, privacy and RTL test suite | 6, 7 | done |
| 9 | Storybook docs + axe tests | 6, 7 | done |
| 10 | Build, exports, types under TS 6 and 7 | 8 | done |
| 11 | CSP smoke, Vite/Tailwind and Astro fixtures | 9, 10 | todo |
| 12 | CI workflow | 9, 10, 11 | todo |
| 13 | Release workflow, CHANGELOG, tag v0.1.0 | 12 | todo |

## Task 1 — Create public repo Onolys/onolys-ui
What it is / what it means: The package needs its own home before anything else (PRD Manual steps, Decision 6, 7). Owner-only parts (branch protection) are noted, not blocked on.
What changes at a high level: Create public `Onolys/onolys-ui` with `gh`, default branch `main`, a README stub, LICENSE, `.gitignore`, and Actions enabled. Clone it beside the other projects and register it in the projects README index. Record the owner step "enable branch protection on main" in the handoff.
Done when: `gh repo view Onolys/onolys-ui --json visibility,defaultBranchRef` shows PUBLIC and `main`; a fresh clone works without credentials; the projects index lists the repo.

## Task 2 — Scaffold toolchain + Storybook/shadcn spike
What it is / what it means: Package skeleton plus the verification spike that settles the build-time questions (Req 1-2, Decisions 3, 4, 10, 12).
What changes at a high level: ESM package with peers (react >=19, tailwindcss 4), tsup/tsc, eslint + jsx-a11y, vitest + RTL, `components.json` following current shadcn CLI conventions for Tailwind v4 (`@theme inline`, `tw-animate-css`, `data-slot`, React 19 refs). Spike: install Storybook 10 on Vite 8; if unsupported, switch to Ladle and note it in the PRD. Run `npx shadcn@latest diff` once.
Done when: `npm run lint`, `typecheck`, `test` pass on a smoke test; Storybook (or Ladle) builds a sample story; spike outcome and shadcn conventions are written into the PRD Decisions row.

## Task 3 — Tokens, dark theme, contrast test
What it is / what it means: The single source of truth for colours, light and dark (Req 4-5, Decision 2, Token mapping, Dark derivation).
What changes at a high level: `tokens.ts` with shadcn semantic names plus Onolys extras (score, tone, footer, verdict, role, selected, radius, shadow), generated `tokens.css` with `:root` and `prefers-color-scheme: dark` blocks, a parity test, and a vitest WCAG contrast check over every fg/bg pair. Dark values tuned by the test.
Done when: parity test passes; contrast test passes both themes (text 4.5:1, large/UI/ring 3:1); a negative test with a deliberately bad token fails as expected.

## Task 4 — Theme, base, fonts, legacy CSS, cn
What it is / what it means: The CSS consumers import, and the class-merge helper (Req 1-3, 6, Decisions 9, 10, 12).
What changes at a high level: `theme.css` (`@theme inline` mapping to Tailwind colours, spacing, text, header, gutter), `base.css` (3px focus ring, reduced motion, `body[data-scroll-locked]` rule), `fonts.css` with relative woff2 `@font-face` and the Inter file, `legacy.css` aliasing old `--color-*` names (kept until SP2 final cleanup), and `cn.ts`.
Done when: unit test for `cn`; a Tailwind build test shows `bg-primary` resolves and dark vars switch under emulated dark; test that every old `--color-*` name has a legacy alias; woff2 present and referenced relatively.

## Task 5 — shadcn components
What it is / what it means: The owned shadcn set SP2 needs (Component set table, Req 6).
What changes at a high level: Add Button, Input, Label, Textarea, Select, Checkbox, Tabs, Card, Badge, Alert, Table, Dialog, AlertDialog, DropdownMenu, Separator, Skeleton, Tooltip via the shadcn CLI into `src/components/ui`, adapted to tokens, 44px default sizes, icon buttons 44x44, 3px ring.
Done when: RTL tests per component for render, variants, keyboard operation and accessible names pass; `npx shadcn diff` still runs against `components.json`.

## Task 6 — Onolys components
What it is / what it means: App chrome and domain pieces that replace today's app.css (Component set table, Onolys row).
What changes at a high level: AppHeader with account-menu slot, Footer, ScoreBadge (good/fair/low), UsageMeter, SkipLink, Page/Section, built on the shared tokens.
Done when: RTL tests cover each (landmarks, SkipLink focus target, ScoreBadge variants with text not colour alone, UsageMeter `role`/values and bounds) and pass.

## Task 7 — CSP-safe Radix overlays
What it is / what it means: Make Dialog, AlertDialog, DropdownMenu and Select work under `style-src 'self'` (Req 8, Architecture CSP, Decisions 5, 11).
What changes at a high level: Dialog/AlertDialog built on Radix Dialog with Radix scroll-lock bypassed and our own `body[data-scroll-locked]` class; DropdownMenu `modal={false}`; Radix Select kept, falling back to styled native `<select>` only if the runtime check fails. Native `<dialog>` only if Dialog also fails.
Done when: jsdom tests show no `<style>` element is injected on open, scroll lock class toggles, focus trap and Escape work; result is recorded for the Task 11 smoke.

## Task 8 — Hit-area, privacy and RTL test suite
What it is / what it means: Cross-cutting guards (Req 6-7, AC 5-6).
What changes at a high level: A test that renders every interactive component and asserts at least 44px height/width; a port of web's `privacy.test.ts` scanning `src/` for storage, network, absolute URLs, `dangerouslySetInnerHTML`, console calls and remote fonts.
Done when: both suites pass; each fails when a violation is injected in a temporary fixture.

## Task 9 — Storybook docs + axe tests
What it is / what it means: Component docs in both themes with automated accessibility checks (Req 9-10, AC 9).
What changes at a high level: Stories for every component and state; light/dark via `prefers-color-scheme` emulation; a11y addon; test-runner using `@axe-core/playwright` against the built Storybook.
Done when: Storybook builds listing all components; axe run reports zero violations in light and dark; a story with a known violation proves the check fails.
Verified: UI Task 9 commit `0b708b0fb9356c9a24d2b095b97c4028e151df17`, integrated as `36992b9`; 47 stories across 24 families, 94 light/dark axe scans with zero failures. Only Storybook’s documented page-level region fixture exception is disabled; WCAG rules remain active. Missing-name negative story fails as intended.

## Task 10 — Build, exports, types under TS 6 and 7
What it is / what it means: The publishable shape (Req 2, Decisions 1, 4, 12).
What changes at a high level: Build ESM plus `.d.ts` with TS 6.0.x; CSS and woff2 copied as plain files; `exports` for `.`, `./theme.css`, `./tokens.css`, `./base.css`, `./fonts.css`, `./legacy.css`, `./tokens`, `./components.json`; no `prepare` script; `build:watch` for local dev.
Done when: a packaged-tarball test resolves every export; a fixture importing the types typechecks under TS 6.0.x and TS 7; test asserts package.json has no `prepare`.
Verified: UI Task 10 commit `89cdb2c4c4e0addfd6a9ec365bf94c8eef18fb1d`; five package tests verify built ESM/declarations, exports, no prepare, and installed consumer types under exact TypeScript 6.0.3 and 7.0.2. Explicit build:watch source/script paths now refresh TypeScript/declarations, CSS, and token CSS.

## Task 11 — CSP smoke, Vite/Tailwind and Astro fixtures
What it is / what it means: Runtime proof of the headline guarantees (AC 1, 2, 4, 7, Decision 12).
What changes at a high level: A Vite + Tailwind v4 fixture installed from the packed tarball using `@source` over dist, with `assetsInlineLimit` set so fonts are files; Playwright serves it with `style-src 'self'; font-src 'self'` and opens Dialog, AlertDialog, DropdownMenu, Select. An Astro fixture imports only `theme.css`.
Done when: zero CSP violations and no `data:` font URL in the built CSS; Button renders teal; dark emulation changes `--background`; Astro build shows tokens and font; Select fallback applied if it fails.

## Task 12 — CI workflow
What it is / what it means: The repo has no CI yet (Req 10, AC 8).
What changes at a high level: GitHub Actions on push and pull request: lint, typecheck, vitest (contrast, hit-area, privacy), Storybook build plus axe test-runner, package build, CSP smoke, fixtures, TS 6/7 typecheck job. Node 22, npm cache, Playwright browsers.
Done when: a PR on the repo shows every job green; a deliberately failing contrast change turns CI red (then reverted).

## Task 13 — Release workflow, CHANGELOG, tag v0.1.0
What it is / what it means: The artifact SP2 consumes (Decisions 1, 6, 8, 12, AC 1, 8).
What changes at a high level: Tag `vX.Y.Z` workflow: CI gate, build, commit `dist/` to a detached tag commit only, GitHub Release notes from `CHANGELOG.md` (Keep a Changelog). Consumer-install smoke on Node 22: `npm install github:Onolys/onolys-ui#<tag>` via git+https, no build run. Cut `v0.1.0`.
Done when: tag `v0.1.0` exists with committed `dist/` and a GitHub Release; smoke installs into a clean Vite + Tailwind v4 fixture without building and renders styled Button and Dialog; `main` carries no `dist/`.
