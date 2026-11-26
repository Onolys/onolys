---
status: draft
summary: 7 tasks for Deep dive
date: 2026-11-26
---
# Tasks: Deep dive
Source of truth: `PRD.md`. Depends on SP01 and SP03 (header/legend). Test-first, one commit each; run only impacted tests. CI exists.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Combo selector card | SP03 | done |
| 2 | Globals dot plot card | 1 | done |
| 3 | Miss-bucket bars (toggle) | 2 | done |
| 4 | Counts per code small multiples | 1 | done |
| 5 | P/R/F1 table + confusion grid (toggle) | 1 | done |
| 6 | Reasoning roll-up + Show data twins | 2, 4, 5 | done |
| 7 | Page composition, test refresh, overflow check | 2-6 | done |

## Task 1 — Combo selector card
What it is: toggle chips per combo (ComboTag), "paired x of y", Human always on, failed combo greyed and disabled, default top 3 by Count error.
Done when: tests for default selection, toggling, failed disabled, paired text.

## Task 2 — Globals dot plot card
What it is: one card per global; visx-scale dot plot with left label gutter, lanes per series, hollow Human circle, shapes per combo, dashed human line, legend, avg miss / within ±1 chips, one-sentence caption.
Done when: geometry tests (gutter, no symbol collision, ticks above plot), chips values from fixture, legend, data table behind "Show data".

## Task 3 — Miss-bucket bars
What it is: 100% stacked bars per combo (same / off 1 / off 2+) with avg miss and within ±1 numbers; collapsed behind a toggle.
Done when: tests: collapsed by default, segment widths proportional to counts, labels with text counts, legend.

## Task 4 — Counts per code small multiples
What it is: cards per code with grouped horizontal bars Human vs selected combos, bias chip tones (green ≤10%, amber 10-20%, red >20%), one muted note.
Done when: tests for bar proportions, chip tone/text ("under-counts 21%"), n shown.

## Task 5 — P/R/F1 table + confusion grid
What it is: DataTable with inline F1 bars (P/R sub-text); confusion grid (human rows × combo columns, multi column, switchable combo, cell click navigates to Line view) behind a toggle; message naming the missing side when no line-level output.
Done when: tests: table sort, F1 bar widths, confusion defaults collapsed, combo switch, click navigation call, missing-output message.

## Task 6 — Reasoning roll-up and data twins
What it is: per-code accordion (Human count + combo snippets, loads on request, "withheld" when empty), one muted note; every chart's table twin behind "Show data".
Done when: tests: lazy load on expand, withheld text, twin collapsed.

## Task 7 — Composition, test refresh, overflow
What it is: assemble DeepDive in the order in PRD, remove old markup/CSS, update `DeepDive.test.tsx`/`responsive.test.tsx`.
Done when: tests green, overflow guard green, typecheck/lint/build green.
