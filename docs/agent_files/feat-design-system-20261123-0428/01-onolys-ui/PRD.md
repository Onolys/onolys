---
status: draft
summary: New public repo Onolys/onolys-ui publishing @onolys/ui (tokens light/dark, Tailwind v4 theme, shadcn-owned + Onolys components) as a tag-pinned git dependency, CSP-safe.
date: 2026-11-23
---
# PRD: 01 @onolys/ui shared design system

Repo/branch: new repo `Onolys/onolys-ui` (public), `main` + tags `vX.Y.Z` (design docs live in iaudit `feat/design-system`) · Depends on: none · Owns: whole `onolys-ui` repo (`src/tokens`, `src/styles`, `src/components`, `src/lib/cn.ts`, `components.json`, `fonts/`, `.storybook/`, `.github/workflows/`, `CHANGELOG.md`, `dist/`)

## TL;DR
One repo, one package. Ships CSS (tokens + Tailwind v4 `@theme`, light and dark via `prefers-color-scheme`), ESM + types for React components (shadcn code we own, plus Onolys components), and self-hosted Inter. Consumers install `github:Onolys/onolys-ui#vX.Y.Z`. Built `dist/` is committed only on the tag commit (no `prepare` build in consumers). Radix (Dialog, AlertDialog, DropdownMenu, Select) is used as-is; `style-src 'self'` stays strict and is proven by the Playwright CSP smoke (build checks relaxed 2026-11-23). Storybook for docs. Astro consumes the CSS only.

## Problem
Tokens are copy-pasted (web == miti, light only; admin has a separate verdict set), primitives are hand-built per app, no dark theme, no radius/shadow tokens, two hand-rolled dialogs. [verified: web/src/styles/tokens.css identical to miti; web/src/styles/app.css 145 lines of `.btn`/`.auth-form`; frontend/src/tokens/tokens.css separate]

## Goals / Non-Goals
**Goals**
- Single versioned source for tokens, theme, components, font.
- Light + dark automatic; AA contrast enforced by test.
- CSP-clean (`style-src 'self'`), privacy-clean (no storage/network/remote font).
- Minimum component set SP2 needs; shadcn CLI updates stay possible.
- Usable by React apps and CSS-only Astro.

**Non-Goals**
- Manual theme toggle (needs storage; deferred). npm registry publishing. Migrating any app (SP2-4). Full shadcn catalogue, charts, ScrollArea, Sonner.

## Requirements
1. **Layout**: `src/tokens/{tokens.ts,tokens.css}` (source of truth + generated parity test, same pattern as admin `tokens.test.ts`), `src/styles/{theme.css,base.css,fonts.css}`, `src/components/ui/*` (shadcn), `src/components/onolys/*`, `src/lib/cn.ts` (`clsx`+`tailwind-merge`), `fonts/inter-latin-wght-normal.woff2`.
2. **Build** (`tsc`/tsup, ESM only + `.d.ts`; React/Radix/`class-variance-authority` as peers/deps). CSS shipped as plain files, not bundled into JS. `exports`: `.` (components), `./theme.css`, `./tokens.css`, `./base.css`, `./fonts.css`, `./tokens` (TS), `./components.json`.
3. **Tailwind scan**: consumer CSS: `@import "tailwindcss"; @import "@onolys/ui/theme.css"; @source "../node_modules/@onolys/ui/dist";`. Components ship class strings in `dist`, so `@source` is required (Tailwind v4 skips node_modules by default). Consumers must run Tailwind v4 (`@tailwindcss/vite`).
4. **Tokens**: shadcn semantic names + Onolys extras, declared as CSS vars in `:root` and re-declared in `@media (prefers-color-scheme: dark)`; `@theme inline` maps them to Tailwind colors (`bg-primary`, etc.). No `.dark` class dependence. Radius/shadow tokens added (`--radius: .5rem`; current UI uses 6px).
5. **Contrast test**: vitest parses `tokens.ts`, computes WCAG ratios for each fg/bg pair in both themes: text 4.5:1, large/UI/focus ring 3:1. CI fails below AA.
6. **Components, 44px**: every interactive default size `min-h-11` (44px); icon buttons 44x44. Focus ring 3px `--ring` (matches today's `outline: 3px solid accent`). `prefers-reduced-motion` honoured in base.css.
7. **Privacy**: no storage, network, absolute URLs, `dangerouslySetInnerHTML`; package CI runs a port of web's `privacy.test.ts` scan over `src/`. ≤0 console calls in components.
8. **CSP-safe Radix**: see Architecture.
9. **Docs**: Storybook per component, light/dark via `prefers-color-scheme` emulation, a11y addon.
10. **CI**: lint (eslint + jsx-a11y), typecheck, vitest + RTL, contrast test, Storybook a11y (axe) test-runner (`@axe-core/playwright` devDep, approved 2026-11-23, also used for Storybook/Playwright checks), build, CSP smoke (Playwright against built Storybook/fixture with `style-src 'self'` header; fail on CSP violations).
11. **Release**: see Decisions.

## Architecture
**Component set (minimum for SP2, [assumption: SP2 scope from verified web inventory])**

| Group | Components | Replaces |
|---|---|---|
| shadcn | Button, Input, Label, Textarea, Select, Checkbox, Tabs, Card, Badge, Alert, Table, Dialog, AlertDialog, DropdownMenu, Separator, Skeleton, Tooltip | `.btn`, auth-form, settings/Modal, DeleteDialog, AccountMenu, tables, tabs |
| Onolys | AppHeader (+AccountMenu slot), Footer, ScoreBadge (good/fair/low), UsageMeter, SkipLink, Page/Section | app.css chrome, chips, usage meter |
| Later | RadioGroup, Switch, Toast | not needed by SP2 evidence; add on demand |

Select = Radix Select (shadcn Select) for consistent styling [RESOLVED: 2026-11-23 — Radix Select; native fallback only if CSP smoke fails]. Fallback: styled native `<select>` only if the Playwright CSP smoke shows Radix Select breaking under `style-src 'self'`. Tooltip optional until used.

**CSP-compatible Radix.** `react-remove-scroll-bar` injects a `<style>` on Dialog/AlertDialog/DropdownMenu(modal)/Popover/Select, which `style-src 'self'` blocks. Choices: (a) DropdownMenu `modal={false}`; (b) Dialog/AlertDialog built on Radix Dialog with the scroll-lock replaced by our own `body[data-scroll-locked]` class in base.css (CSS file, no inline style) and Radix's `RemoveScroll` bypassed; (c) fallback: native `<dialog showModal()>` (already used on landing, no style injection, built-in focus trap and inert). Popper positioning writes via CSSOM style props (allowed). ScrollArea excluded. Owner 2026-11-23: build/hosting checks may be adjusted, so prefer (b) Radix Dialog/AlertDialog with the `build.test.ts` check changed as needed; native `<dialog>` (c) only if the CSP smoke fails. CSP smoke is the gate. [RESOLVED: owner 2026-11-23 — prefer Radix Dialog/AlertDialog with build check adjusted; native <dialog> only if CSP smoke fails; remaining task-level check = runtime CSP verification]

**Dark derivation.** Keep teal #0b5f5a as light `--primary`. Dark: surfaces from the teal hue at low chroma (bg ~#0f1514, card ~#151d1c, border ~#2a3736); `--primary` lightened (~#5fc4b8, text-on-primary dark ink) for AA on dark; score colors inverted (dark tint bg + light fg); footer tone stays dark in both. Exact values tuned by the contrast test, not guessed here.

**Token mapping**

| Current | Semantic |
|---|---|
| --color-background #fff / --color-text #171c1c | --background / --foreground |
| --color-accent #0b5f5a / --color-on-accent | --primary / --primary-foreground |
| gray-50 / gray-100 | --muted / --accent (shadcn hover surface) |
| gray-600 | --muted-foreground |
| gray-300 | --border, --input |
| accent (focus) | --ring |
| score-low #8a3030 | --destructive (+ --destructive-foreground) |
| (new) | --card, --popover, --secondary, --radius |
| score-good/fair/low + -background | --score-good/-fair/-low(-bg) |
| tone-hero..benefits, footer(+text/link/muted) | --tone-*, --footer-* |
| verdict-*, role-*, selected-claim-bg (admin) | --verdict-*, --role-*, --selected (shipped now, dark values added; consumed in SP4) |
| --space-*, font sizes, --hdr, --gutter | kept as `--space-*`, `--text-*`, `--header-h`, `--gutter` in `@theme` |

Compat: ship `legacy.css` aliasing old `--color-*` names so SP2/SP3 can migrate incrementally [OPEN: or drop].

**Astro.** `import "@onolys/ui/theme.css"` plus Tailwind v4 Vite plugin in `astro.config` (Astro 7 supports `vite.plugins`). CSS-only; no React needed. Islands (e.g. SignupDialog) later add `@astrojs/react` + the same package. Fonts: package `fonts.css` replaces `@fontsource-variable/inter`.

**shadcn updates.** `components.json` at repo root (style, `tailwind.css` -> `src/styles/theme.css`, aliases to `src/components`, `cssVariables: true`). `npx shadcn@latest diff/add` is run inside onolys-ui only; diffs reviewed in PR, then released. Consumers never run the CLI for these components.

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| 1 | Git-dep install | Commit built `dist/` on release tag commit only (release workflow builds, commits to a detached tag commit, not main) | `prepare` script | `prepare` forces consumers (CI, Astro, Firebase) to install devDeps + build per install: slower, fragile on Node/npm differences, and npm git-dep `prepare` needs dev deps resolved. Tag-with-dist = zero build on install, deterministic. Cost: release workflow complexity |
| 2 | Dark mode | `@media (prefers-color-scheme: dark)` vars, no `.dark` class | class + JS toggle | No storage allowed; automatic per brief |
| 3 | Docs | Storybook | Ladle | Maintained a11y addon + test-runner; Ladle lighter but weaker a11y. [OPEN: Storybook 10 + Vite 8 compat to verify] |
| 4 | Modules | ESM only, peers: react >=19, tailwindcss 4 | dual CJS | All consumers are Vite ESM |
| 5 | Select | Radix Select (shadcn); native styled `<select>` only if CSP smoke fails (owner-delegated 2026-11-23) | Native styled | Consistent styling now that build checks are relaxed; CSP smoke is the gate |
| 6 | Versioning | semver, `CHANGELOG.md` (Keep a Changelog), pre-1.0 minor = may break; consumers pin tags | floating `main` | Reproducible builds |
| 7 | Local dev | `file:../onolys-ui` or `npm link` (`npm run build:watch`) | publish snapshots | No registry |
| 8 | Release | Tag `vX.Y.Z` triggers workflow: CI gate, build, commit dist to tag, GitHub Release notes | manual | Repeatable; Renovate/Dependabot optional later |
| 9 | Font | `woff2` shipped in package, `@font-face` in `fonts.css` with relative URL | per-app copy | One copy; consumer bundlers emit hashed asset (same-origin, font-src 'self') |
| 10 | Variants | cva + tailwind-merge (shadcn standard) | CSS modules | Matches shadcn |
| 11 | Build checks vs Radix | Owner 2026-11-23: build/hosting checks may be changed or removed when they block the design system (no one uses prod); CSP stays strict (`style-src 'self'`), proven by Playwright CSP smoke; prefer Radix Dialog/AlertDialog, native `<dialog>` only if smoke fails | Keep checks, bypass RemoveScroll / native dialog | Unblocks Radix; CSP strictness still verified at runtime |

## Manual steps
- Owner: create public GitHub repo `Onolys/onolys-ui`, enable Actions, branch protection on `main`.
- Owner: approve if CSP ever needs relaxing (not planned).

## Risks / Open Questions
- [RESOLVED: owner 2026-11-23 — prefer Radix Dialog/AlertDialog with the build check adjusted; native `<dialog>` only if the CSP smoke fails] Dialog scroll lock. Only the runtime CSP verification remains as a task-level check.
- [OPEN] Verify at implementation: current shadcn CLI conventions for Tailwind v4 (`@theme inline`, `tw-animate-css` dep, `data-slot` attrs, React 19 ref handling); Storybook/Vite 8/TS 6-7 compat; Tailwind `@source` resolution through git-dep symlink-free install.
- [OPEN] TS version: web TS 6.0.3, admin TS 7; emitted `.d.ts` must typecheck under both.
- [OPEN] Node 22 + `npm install github:` with committed dist: confirm no `prepare` runs (no `prepare` script defined).
- [OPEN] Keep `legacy.css` aliases or force-migrate.
- [OPEN] Hosting `font-src 'self'`: fonts bundled as assets, verify no data: inlining (Vite `assetsInlineLimit`) in consumers; woff2 > 4KB so ok, confirm in SP2.
- [RESOLVED: spec] Public repo + git dep needs no tokens.
- [DEFERRED] Manual theme toggle, Toast/Sonner, RadioGroup/Switch, admin tokens merge (SP4), Renovate.

## Acceptance Criteria
1. `npm i github:Onolys/onolys-ui#v0.1.0` in a clean Vite+Tailwind v4 fixture installs without build and renders Button/Dialog styled with the teal primary.
2. Same fixture served with `style-src 'self'` (Playwright): zero CSP violations opening Dialog, AlertDialog, DropdownMenu, Select (Select failing = fall back to styled native `<select>`).
3. Contrast test passes in light and dark for all documented pairs; fails on a deliberately bad token (negative test).
4. Dark theme applies under `prefers-color-scheme: dark`, no JS.
5. All interactive components have >=44px hit area (test).
6. Privacy scan over `src/` passes; no remote fonts.
7. Astro fixture builds with `theme.css` only and shows tokens/font.
8. CI green: lint, typecheck, tests, axe, build; tag workflow produces release with dist.
9. Storybook lists all components in both themes; `npx shadcn diff` runs against `components.json`.
