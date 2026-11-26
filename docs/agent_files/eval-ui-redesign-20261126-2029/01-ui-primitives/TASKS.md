---
status: draft
summary: 7 tasks - primitives, DataTable, ChartFrame v2, chart lib + size budget, overflow guard
date: 2026-11-26
---
# Tasks: UI primitives and chart setup
Source of truth: `PRD.md`. Test-first; one commit per task. CI: eval-web job already runs `npm test/typecheck/lint/build` on push/PR (`.github/workflows/ci.yml`), so no CI task needed. Run only impacted tests per task.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Overflow guard test + remove existing overflow-x CSS | none | done |
| 2 | Chip, StatTile, SummaryCard, Note, CopyButton | none | done |
| 3 | AppDialog + CopyField | 2 | done |
| 4 | Disclosure / ToggleSection | 2 | done |
| 5 | DataTable + useTableState | 2 | done |
| 6 | Chart lib install, size budget test, scales/theme/Axis | none | done |
| 7 | ChartFrame v2 + ComboTag (letter/shape/colour) | 4, 6 | done |

## Task 1 — Overflow guard test + remove existing overflow-x CSS
What it is: a vitest that scans `eval/web/src/**/*.css` and inline `style` strings for `overflow-x: auto|scroll`.
What changes: add the test; remove `.table-scroll` overflow and tablist `overflow-x:auto` from `compare/compare.css` (replace with wrap/stack so nothing breaks).
Done when: test fails on a seeded fixture string and passes on the repo; existing compare tests still pass.

## Task 2 — Chip, StatTile, SummaryCard, Note, CopyButton
What it is: small presentational components in `eval/web/src/ui/` per PRD, light-mode tokens, icon + text chips (lucide icons already deduped).
What changes: new files + `ui.css`.
Done when: RTL tests cover tones, icon present with text (not colour alone), muted zero style, Note small/muted class, CopyButton writes to clipboard and shows "Copied".

## Task 3 — AppDialog + CopyField
What it is: modal wrapper over `@onolys/ui` Dialog with title, body, footer, close, focus return; CopyField shows a value with copy action.
Done when: tests for open/close, Escape, focus return, title labelled, CopyField copies; no id placed on trigger API (trigger is caller's verb label).

## Task 4 — Disclosure / ToggleSection
What it is: collapsed-by-default section with verb-labelled toggle, `aria-expanded`, `defaultOpen` prop.
Done when: tests for default collapsed, toggle, content not in DOM (or hidden) when collapsed, keyboard.

## Task 5 — DataTable + useTableState
What it is: fixed-layout table, plain `th` with sort arrows and `aria-sort`, search box, filter slot, ellipsis + `title`, stack-to-cards below 760px, row tone (danger = gentle red).
Done when: tests: sort cycle asc/desc/none on every sortable column, search filters rows, header is a `th` containing no `button` styled as pill (arrow control is keyboard-operable via the th), long cell has `title`, danger row has tone class; overflow guard still green.

## Task 6 — Chart lib install, size budget test, scales/theme/Axis
What it is: add visx modular packages (or d3 fallback per PRD), shared `scales.ts`, `theme.ts` (colours, combo palette tokens), `Axis` with fixed left gutter support.
Done when: test builds the app (as `bundle.test.ts` does) and asserts added chart-dep gzip ≤ 40 KB, one copy of each package; scale helper unit tests (1-5 domain, ticks).

## Task 7 — ChartFrame v2 + ComboTag
What it is: card chart frame (title, one-sentence caption, legend slot, "Show data" disclosure with the table twin, no `.table-scroll`); `ComboTag` = letter + shape + colour.
What changes: old `compare/ChartFrame.tsx` becomes a re-export/adapter so existing callers compile until SP03-05 migrate.
Done when: tests: caption present, data table behind disclosure collapsed, ComboTag renders letter + shape + colour class, existing compare tests green.
