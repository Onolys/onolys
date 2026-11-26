---
status: approved
summary: Deep dive tab as cards with styled charts (dot plot, miss buckets, count small multiples, P/R/F1, confusion grid, reasoning), secondary content behind toggles
date: 2026-11-26
---
# PRD 04 — Deep dive

## TL;DR
Restyle `DeepDive.tsx` into cards matching `../mockups/deepdive.html` (+ PNG) at higher density. Primary: globals dot plots, counts per code, P/R/F1. Secondary behind toggles: miss-bucket bars, confusion grid, reasoning roll-up, data tables. All graphs kept.

## Problem
Charts exist (PR #63) but are barely styled; the dot-plot labels overlap; "How to read" paragraphs are long; data tables are inline.

## Goals / Non-Goals
Goals: below. Non-goals: new metrics or payload fields (UI computes nothing); other tabs.

## Requirements
Shown by default vs behind toggle:
- Default: combo toggle chips with "paired x of y" (Human always shown; top 3 by Count error preselected; failed combo greyed, not selectable); Globals: one card per global with dot plot, legend, avg miss / within ±1 chips (one-sentence caption); Counts per code: small-multiple cards (bars Human vs selected combos + bias chip, e.g. "under-counts 21%"), one muted note; Per-line agreement: P/R/F1 table with inline F1 bars (selected combos).
- Behind toggle (collapsed): "How far off are the ratings?" miss-bucket 100% stacked bars (same / off 1 / off 2+) per global; Confusion grid (human rows × combo columns, switchable combo, multi-code column, cell click → Line view); Reasoning roll-up accordion (per code, Human count + combo snippets, loaded on request); every chart's data table ("Show data").

Dot plot spec: reserve a fixed left gutter (row labels), plot area to its right, axis ticks above the plot only, one vertical lane per series so symbols never overlap, Human = hollow circle, combos = distinct shape + letter + colour, dashed line at the human rating. Scales via SP01 chart helpers. viewBox scaling, no horizontal scroll; cards stack to one column below ~760px.
Missing line-level output → one message naming the missing side (no empty grid).

## Architecture
Edit `compare/DeepDive.tsx`, `deepDive.css`; new `compare/charts/{GlobalsDotPlot,MissBuckets,CountBars,PrfTable,ConfusionGrid,ReasoningRollup}.tsx` using SP01 `ChartFrame`, `Chip`, `Disclosure`, `ComboTag`, `chart/*`. Data: existing endpoints (`deepDive.json`, `reasoning.json`, `lines.json` fixtures); no API changes.

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| 1 | Dot plot | visx scales + SVG | hand-rolled | SP01 decision |
| 2 | Bars, confusion, heatmap-like | CSS grid | lib | light |
| 3 | Miss buckets | behind toggle | default | bias to less; chips already give avg miss/±1 |
| 4 | Confusion | behind toggle | default | detail view |
| 5 | Selected combos | top 3 by count error, as today | all | density |

## Manual steps
None.

## Risks / Open Questions
- [RESOLVED: default - failed combos (e.g. C invalid_parameters) appear greyed in the selector and are excluded from charts]
- [RESOLVED: default - Playwright deferred; unit-level overflow guard]
- Risk: jsdom cannot verify label overlap; test lane/gutter geometry numerically (computed positions do not collide).

## Acceptance Criteria
- Dot plot geometry test: label gutter width > 0, no two symbols in a row share a lane, labels outside plot area.
- Defaults list above holds (toggled sections collapsed; opening each works); data tables behind "Show data".
- Bias chip tones green ≤10%, amber 10-20%, red >20% (as mockup), text + icon not colour alone.
- No `overflow-x`; RTL + overflow guard + `npm test/typecheck/lint/build` green.
