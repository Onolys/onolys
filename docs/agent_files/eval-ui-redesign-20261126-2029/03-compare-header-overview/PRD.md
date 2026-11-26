---
status: approved
summary: Compare shared header (summary cards, tabs, combo legend), failed-combo handling, and the Overview tab (verdict, leaderboard, heatmap)
date: 2026-11-26
---
# PRD 03 — Compare header + Overview

## TL;DR
Goal of Compare: help the user pick the best model/engine combo. The header becomes compact summary cards; Overview leads with a verdict and a leaderboard where failed combos are shaded red and never "best"; the heatmap is secondary. Visual target: `../mockups/overview.html` (+ PNG), copy per `../mockups/docs/audit.html`. Mockups are too tall: build denser than mockups.

## Problem
`CompareApp.tsx` header prints jumbled text ("Human labels … gi: paired 0 of 1 persuade: paired 0 of 1 … Coverage"); table headers are buttons; notes are body-size paragraphs; legends are 4 separate paragraphs; tabs scroll horizontally (`overflow-x:auto`).

## Goals / Non-Goals
Goals: below. Non-goals: new metrics (UI computes none), other tabs (SP04/05), dark mode. Backend touched only if `best` flags currently include failed combos (see Decisions 2).

## Requirements
Shown by default vs behind toggle (Header, all tabs):
- Default: title "Compare - <run name>" + "Back to run" link + partial badge; 4 compact summary cards in one row (wrap on narrow): Sessions (n, attempts, combos), Human labels (chips), Coverage (one chip per session "paired x of y", amber if incomplete; collapses to "4 of 5 sessions complete" chip when all but few are full), Excluded (failed combos + code); tabs (Overview, Deep dive, More analysis, Line view); combo legend once (letter tag + model + engine/tier/effort; failed flagged).
- Behind toggle: per-session coverage chips beyond the first 3 incomplete ones ("Show all"); combo legend details (tier/effort) collapse to tooltip on narrow screens; Config opens popup.

Overview:
- Default: verdict (1-2 sentences, n tags; excluded-combo note muted small); leaderboard (DataTable: sortable plain headers with arrows; best = star + "best"; failed row shaded gentle red and excluded from best for cost/time/fails/accuracy; inline cost/time mini bars); one muted leaderboard note block (column meanings; "Sessions have equal weight; repeats averaged first"; "Time may read short for retried units").
- Behind toggle (collapsed): Metric heatmap ("Show metric heatmap"; rows grouped counts/globals/ratios; big = avg miss, small = signed bias; one legend row), heatmap data table, column definitions.

Failed/invalid combos: row shaded gentle red, "failed" chip with code (e.g. `invalid_parameters`), excluded from every "best" computation; still visible so users see why.

## Architecture
Edit `eval/web/src/compare/CompareApp.tsx`, `Overview.tsx`, `compare.css`/`overview.css`; add `compare/ComparisonHeader.tsx`, `ComboLegend.tsx`, `Leaderboard.tsx`, `MetricHeatmap.tsx`. Data from existing `/compare` payloads (`compareTypes.ts`, fixtures `compare/fixtures/overview.json`). Tabs: plain `role=tablist`, wrapping, no scroll. ComboLegend is shared by SP04/05 via the header (rendered once above tabs).

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| 1 | Heatmap default | collapsed behind toggle | shown | bias to less; leaderboard answers the goal |
| 2 | Best excludes failed | trust payload flags; if backend `best` includes failed combos, fix in eval/backend compare computation, test-first | UI recompute | UI computes no metric |
| 3 | Coverage chips | collapsed summary + show incomplete | all chips | density |
| 4 | Mini bars | cost/time inline bars in leaderboard | none | recommendation in graphs spec |

## Manual steps
None.

## Risks / Open Questions
- [RESOLVED: default - verify backend best-flag handling of failed combos in task 1; fix only that if wrong]
- [RESOLVED: default - Playwright deferred; unit-level overflow guard]
- Risk: tests in `Overview.test.tsx`, `CompareApp.test.tsx`, `responsive.test.tsx` assert old DOM; update test-first.

## Acceptance Criteria
- Header title exactly "Compare - <name>"; summary cards, no jumbled text; tabs no horizontal scroll.
- Table headers are `th` with sort arrows; failed combo row shaded and never starred; "best" respects exclusion on each metric.
- Notes muted; heatmap collapsed by default and opens on toggle; no ids in button labels.
- RTL tests + overflow guard + `npm test/typecheck/lint/build` green (backend pytest for task 1 if changed).
