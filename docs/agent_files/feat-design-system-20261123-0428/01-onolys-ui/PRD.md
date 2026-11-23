---
status: draft
summary: New public repo Onolys/onolys-ui publishing @onolys/ui (tokens light/dark, Tailwind v4 theme, shadcn-owned + Onolys components) as a tag-pinned git dependency, CSP-safe.
date: 2026-11-23
---
# PRD: 01 @onolys/ui shared design system

Repo/branch: new repo `Onolys/onolys-ui` (public), `main` + tags `vX.Y.Z` (design docs live in iaudit `feat/design-system`) · Depends on: none · Owns: whole `onolys-ui` repo (`src/tokens`, `src/styles`, `src/components`, `src/lib/cn.ts`, `components.json`, `fonts/`, `.storybook/`, `.github/workflows/`, `CHANGELOG.md`, `dist/`)

## TL;DR
One repo, one package. Ships CSS (tokens + Tailwind v4 `@theme`, light and dark via `prefers-color-scheme`), ESM + types for React components (shadcn code we own, plus Onolys components), and self-hosted Inter. Consumers install `github:Onolys/onolys-ui#vX.Y.Z`. Built `dist/` is committed only on the tag commit (no `prepare` build in consumers). Radix Dialog/AlertDialog use a custom CSS scroll lock, DropdownMenu is nonmodal, and Select uses styled native `<select>` with `<option>` children; `style-src 'self'` stays strict and is proven by the Playwright CSP smoke (build checks relaxed 2026-11-23). Storybook for docs. Astro consumes the CSS only.

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

Select = styled native `<select>` with native `<option>` children. [VERIFIED: Task 7, 2026-11-23 — Radix Select produced two inline `style-src-elem` violations under `style-src 'self'`; user delegated the policy choice and the orchestrator retained strict CSP, activating the approved native fallback.] The public API exports Select and its native props; Radix-only Select helper exports are removed. Browser selection smoke remains required in consumer fixtures and the app. Tooltip optional until used.

**CSP-compatible Radix.** Task 7 retained Radix Dialog/AlertDialog with `RemoveScroll` bypassed and custom CSS `body[data-scroll-locked]` locking in base.css; focus trapping and Escape behavior remain verified. DropdownMenu uses `modal={false}`. The Chromium smoke observed no CSP violations for these shipped overlays and the native Select; Radix Select separately produced two inline `style-src-elem` violations, so its native fallback is now the supported API. Popper positioning uses CSSOM style props. ScrollArea remains excluded. User delegated the policy choice; the orchestrator kept `style-src 'self'` strict with no relaxation. App/consumer runtime CSP smoke remains a release gate.

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

Compat: ship `legacy.css` aliasing old `--color-*` names so SP2/SP3 can migrate incrementally [RESOLVED: orchestrator default 2026-11-23 — keep `legacy.css` aliases for the migration period, removed in SP2's final cleanup phase; verified in Task 4].

**Astro.** `import "@onolys/ui/theme.css"` plus Tailwind v4 Vite plugin in `astro.config` (Astro 7 supports `vite.plugins`). CSS-only; no React needed. Islands (e.g. SignupDialog) later add `@astrojs/react` + the same package. Fonts: package `fonts.css` replaces `@fontsource-variable/inter`.

**shadcn updates.** `components.json` at repo root (style, `tailwind.css` -> `src/styles/theme.css`, aliases to `src/components`, `cssVariables: true`). `npx shadcn@latest diff/add` is run inside onolys-ui only; diffs reviewed in PR, then released. Consumers never run the CLI for these components.

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| 1 | Git-dep install | Commit built `dist/` on release tag commit only (release workflow builds, commits to a detached tag commit, not main) | `prepare` script | `prepare` forces consumers (CI, Astro, Firebase) to install devDeps + build per install: slower, fragile on Node/npm differences, and npm git-dep `prepare` needs dev deps resolved. Tag-with-dist = zero build on install, deterministic. Cost: release workflow complexity |
| 2 | Dark mode | `@media (prefers-color-scheme: dark)` vars, no `.dark` class | class + JS toggle | No storage allowed; automatic per brief |
| 3 | Docs | Storybook | Ladle | Maintained a11y addon + test-runner; Ladle lighter but weaker a11y. [VERIFIED: Task 2, 2026-11-23 — Storybook 10.6.8 builds on Vite 8.3.8; onolys-ui commit 2aba4f3b01ac6c803b08771460154553ee6676b6] |
| 4 | Modules | ESM only, peers: react >=19, tailwindcss 4 | dual CJS | All consumers are Vite ESM |
| 5 | Select | Styled native `<select>` with `<option>` children; no Radix-only helper exports | Radix Select | Task 7 Chromium measured two inline `style-src-elem` violations under strict `style-src 'self'`; user delegated policy choice and orchestrator retained strict CSP, activating native fallback; app browser selection smoke still required |
| 6 | Versioning | semver, `CHANGELOG.md` (Keep a Changelog), pre-1.0 minor = may break; consumers pin tags | floating `main` | Reproducible builds |
| 7 | Local dev | `file:../onolys-ui` or `npm link` (`npm run build:watch`) | publish snapshots | No registry |
| 8 | Release | Tag `vX.Y.Z` triggers workflow: CI gate, build, commit dist to tag, GitHub Release notes | manual | Repeatable; Renovate/Dependabot optional later |
| 9 | Font | `woff2` shipped in package, `@font-face` in `fonts.css` with relative URL | per-app copy | One copy; consumer bundlers emit hashed asset (same-origin, font-src 'self') |
| 10 | Variants | cva + tailwind-merge (shadcn standard) | CSS modules | Matches shadcn |
| 11 | Build checks vs Radix | Owner 2026-11-23: build/hosting checks may be changed or removed when they block the design system (no one uses prod); CSP stays strict (`style-src 'self'`), proven by Playwright CSP smoke; prefer Radix Dialog/AlertDialog, native `<dialog>` only if smoke fails | Keep checks, bypass RemoveScroll / native dialog | Unblocks Radix; CSP strictness still verified at runtime |
| 12 | Orchestrator defaults 2026-11-23 | Storybook 10.6.8 builds on Vite 8.3.8 (Task 2 verified); shadcn 4.23.0 `diff` and `add --diff` work, using new-york, blank Tailwind config, CSS vars, `@theme inline`, `tw-animate-css`, `data-slot`, React 19 ref props (Task 2 verified); `.d.ts` from TS 6.0.x, fixtures under TS 6 + 7; dist on tag commits only, no `prepare`, git+https install smoke on Node 22; woff2 files + consumer `assetsInlineLimit`; `legacy.css` kept until SP2 final cleanup | Owner delegated open items to orchestrator | Recommended defaults; each verified by a named task in TASKS.md |

## Manual steps
- Owner: create public GitHub repo `Onolys/onolys-ui`, enable Actions, branch protection on `main`.
- Owner: approve if CSP ever needs relaxing (not planned).

## Risks / Open Questions
- [RESOLVED: owner 2026-11-23 — prefer Radix Dialog/AlertDialog with the build check adjusted; native `<dialog>` only if the CSP smoke fails] Dialog scroll lock. Only the runtime CSP verification remains as a task-level check.
- [RESOLVED: orchestrator default 2026-11-23 — follow current shadcn CLI conventions for Tailwind v4 (`components.json` in package, `@theme inline` tokens, `tw-animate-css`, `data-slot`, React 19 refs); Storybook/Vite 8 compat decided by the setup spike; verified in Task 2] Tailwind `@source` through a symlink-free git install is proven in Task 11 and Task 13.
- [RESOLVED: orchestrator default 2026-11-23 — emit `.d.ts` compiled with the lowest consumer TS (6.0.x); typecheck a fixture under TS 6 and TS 7 in CI; verified in Task 10]
- [RESOLVED: orchestrator default 2026-11-23 — commit built dist only on release tag commits, no `prepare` script; consumer-install smoke in CI (Node 22, `npm install github:Onolys/onolys-ui#<tag>` via git+https); verified in Task 13]
- [RESOLVED: orchestrator default 2026-11-23 — keep `legacy.css` aliases for the migration period, removed in SP2's final cleanup phase; verified in Task 4]
- [RESOLVED: orchestrator default 2026-11-23 — fonts shipped as woff2 files; consumers set Vite `assetsInlineLimit` so fonts are never `data:` URIs (`font-src 'self'`); verified in Task 11] SP2 re-confirms in the app.
- [RESOLVED: spec] Public repo + git dep needs no tokens.
- [DEFERRED] Manual theme toggle, Toast/Sonner, RadioGroup/Switch, admin tokens merge (SP4), Renovate.

## Acceptance Criteria
1. `npm i github:Onolys/onolys-ui#v0.1.0` in a clean Vite+Tailwind v4 fixture installs without build and renders Button/Dialog styled with the teal primary.
2. Same fixture served with `style-src 'self'` (Playwright): zero CSP violations opening Dialog, AlertDialog, nonmodal DropdownMenu, and selecting an option using styled native Select.
3. Contrast test passes in light and dark for all documented pairs; fails on a deliberately bad token (negative test).
4. Dark theme applies under `prefers-color-scheme: dark`, no JS.
5. All interactive components have >=44px hit area (test).
6. Privacy scan over `src/` passes; no remote fonts.
7. Astro fixture builds with `theme.css` only and shows tokens/font.
8. CI green: lint, typecheck, tests, axe, build; tag workflow produces release with dist.
9. Storybook lists all components in both themes; `npx shadcn diff` runs against `components.json`.
