---
status: approved
summary: Shared eval/web UI primitives (chips, cards, tiles, modal, toggle, sortable/searchable table, chart lib + theme) used by SP02-05
date: 2026-11-26
---
# PRD 01 — UI primitives and chart setup

## TL;DR
Build the small shared kit every redesigned page uses, plus the chart-library decision. No page changes yet except removing existing horizontal-scroll CSS. Mockups (`../mockups/`) are the visual target; design rules restated below.

## Problem
eval/web has ~3.3k lines of TSX, almost no styling (compare CSS ~100 lines), plain-text status lines, header-as-button tables, `overflow-x:auto` tables (`.table-scroll`, tablists), and charts with overlapping labels. Each page would otherwise re-invent chips/tiles/modals.

## Goals / Non-Goals
Goals: reusable, tested primitives; chart lib + theme; one no-overflow guard. Light mode only (do not add dark variants).
Non-goals: page rewrites (SP02-05); backend changes; new `@onolys/ui` release (primitives live in `eval/web/src/ui/`, candidates for upstreaming later).

## Design rules (restated; source `docs/design-rules.md`, PR #78, plus mockups/docs/rules.html)
1. No horizontal scroll anywhere: wrap, truncate + tooltip/popup, hide low-priority columns, or stack to cards <760px. No `overflow-x:auto|scroll`.
2. Configs open in a modal. 3. Information formatted: chips with icon (never colour alone), cards, stat tiles; failure red/shaded, warning amber, success green, zero muted. 4. Table headers are plain `th` (never buttons); sortable columns show up/down arrows, `aria-sort`, keyboard operable. 5. Notes/caveats muted, 12-13px, below content. 6. Buttons are verbs; IDs go in popup/details, copyable. Titles "Page - name". Tokens from `@onolys/ui`: primary #0b5f5a, success #166534, warning #854d0e, destructive #8a3030, score-good/fair/low, radius .5rem.

## Requirements
- `Chip` (tone: success/warning/danger/neutral/muted/info + icon), `StatTile`, `SummaryCard` (small title, big value, muted sub), `Note` (muted small), `CopyButton`.
- `AppDialog` on `@onolys/ui` Dialog: title, body, footer, close, focus return; `CopyField` for ids/JSON.
- `Disclosure` / `ToggleSection`: collapsed by default, button label is a verb ("Show data", "More"), `aria-expanded`, optional persisted-in-URL state not needed.
- `DataTable`: `table-layout:fixed`, per-column width/priority, ellipsis + `title`, below 760px stacks to labelled cards, plain `th` with sort arrows (`aria-sort`), built-in search box + optional filter slot, `useTableState` (sort/search/filter), row tone (`danger` shades gentle red).
- `ChartFrame` v2: card with title, one-sentence caption, legend slot, "Show data" disclosure holding the table twin; replaces "How to read" paragraph and `.table-scroll`.
- Combo identity helpers: letter tag + shape + colour palette (A,B,C,D…; colour-blind-safe, shape+letter+colour).
- Chart setup: shared scale/axis helpers + theme tokens (see Decisions).
- Overflow guard test: scans all `eval/web/src/**/*.css` and inline styles for `overflow-x: auto|scroll`; fails on match (allowlist empty).

## Architecture
`eval/web/src/ui/` (new): `Chip.tsx StatTile.tsx SummaryCard.tsx Note.tsx CopyButton.tsx AppDialog.tsx Disclosure.tsx DataTable.tsx useTableState.ts ComboTag.tsx chart/ (scales.ts theme.ts Axis.tsx)` + `ui.css` (Tailwind v4 tokens already via `@onolys/ui`). Compare's `ChartFrame` is moved/rewritten to this API; SP03-05 migrate callers (SP01 keeps the old export as a thin re-export so the app still builds until then).

### Chart library evaluation
Needed: dot plot (1-5), miss-bucket stacked bars, small multiples, heatmap, confusion grid, scatter + frontier, line lanes. Heatmap, confusion grid, bars and small multiples are CSS grid/flex (no lib). Only dot plot, scatter and lines need scales/axes.

| Option | Approx gzip added | Fit |
|---|---|---|
| Hand-rolled SVG | 0 KB | works (writeup audit recommendation) but every axis/scale/tick is re-built and tested by hand |
| visx modular (`@visx/scale`, `@visx/shape`, `@visx/axis`, `@visx/group`; d3 deps) | ~15-25 KB | SVG, React-native, tree-shakable, keeps a11y/jsdom control |
| uPlot | ~20 KB | canvas time-series only; no dot plot/heatmap; poor a11y |
| Chart.js (tree-shaken) | ~40-60 KB | canvas; weak a11y/table twins; theming fights tokens |
| Recharts | ~90-110 KB | heavy; theming fights Tailwind |
Numbers are estimates; task 1 measures real ones.

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| 1 | Chart lib | visx modular, SVG only for dot plot/scatter/lines | hand-rolled; Chart.js; Recharts; uPlot | small, SVG, a11y, deterministic tests |
| 2 | Budget | total added chart deps ≤ 40 KB gzip (target ~25); enforced by a size test on the built chunk | no budget | keeps eval bundle light |
| 3 | Bars/grids | CSS grid/flex + inline SVG, no lib | lib bars | lighter, matches mockups |
| 4 | Theme | light only | dark variants | user decision |
| 5 | Location | `eval/web/src/ui/` | upstream into `@onolys/ui` now | avoid a cross-repo release; upstream later |
| 6 | E2E | no Playwright in eval/web today (Playwright lives in `web/`); use unit-level overflow guard + RTL structure tests | add Playwright to eval/web | CI time; `[DEFERRED]` browser-width Playwright at 1440/1024 until eval/web gets e2e infra |

## Manual steps
None.

## Risks / Open Questions
- [RESOLVED: default - visx modular; if a visx package's peer range excludes React 19.3, use `d3-scale` + `d3-shape` directly (same bundle class), same helper API]
- [RESOLVED: default - Playwright checks at 1440/1024 deferred; unit-level overflow guard in every sub-project]
- [RESOLVED: default - primitives stay local, not in @onolys/ui]
- Risk: jsdom has no layout, so real overflow is unmeasured; mitigate with CSS scan + fixed-layout structure tests; manual check at 1440/1024/390 in dev-ship notes.

## Acceptance Criteria
- Each primitive has RTL tests (render, a11y roles, tone/icon, keyboard). DataTable: sort asc/desc/none, search, filter, `aria-sort`, header is not a button, ellipsis `title`.
- Overflow guard passes on the repo and fails on a seeded `overflow-x:auto` fixture.
- Bundle-size test: added chart deps ≤ 40 KB gzip.
- `npm test`, `typecheck`, `lint`, `build` green in eval/web.
