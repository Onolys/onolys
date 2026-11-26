---
status: draft
summary: 6 tasks for Compare header and Overview
date: 2026-11-26
---
# Tasks: Compare header + Overview
Source of truth: `PRD.md`. Depends on SP01. Test-first, one commit each; run only impacted tests. CI exists (eval-web, eval-backend jobs).

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Verify/fix "best" excludes failed combos in payload | none | done |
| 2 | ComparisonHeader (title, summary cards, partial badge) | SP01 | done |
| 3 | Tabs (no scroll) + ComboLegend once | 2 | done |
| 4 | Verdict + Leaderboard | 1, 3 | in-progress |
| 5 | Metric heatmap behind toggle | 4 | in-progress |
| 6 | Update Overview/CompareApp/responsive tests, overflow check | 2, 3, 4, 5 | todo |

## Task 1 — Verify/fix "best" excludes failed combos
What it is: check eval/backend compare computation and fixtures: failed/invalid combos (e.g. `invalid_parameters`) must not be flagged best for cost, time, fails, accuracy.
What changes: only if wrong, minimal backend fix + payload fixture update.
Done when: pytest case with a failed combo that would otherwise win each metric; fixture updated; if already correct, a regression test is added and no code change.

## Task 2 — ComparisonHeader
What it is: title "Compare - <name>", Back to run link, partial badge, four summary cards (Sessions, Human labels, Coverage, Excluded) replacing the jumbled text; Config opens popup.
Done when: tests for exact title, card contents from fixture, coverage chips amber when incomplete, "Show all" toggle, excluded card lists failed combo + code.

## Task 3 — Tabs and ComboLegend
What it is: wrapping `tablist` without overflow; combo legend rendered once above tabs (letter tag, model, engine/tier/effort, failed flagged).
Done when: tests for tab switching, aria, legend once not per tab, failed flag; overflow guard green.

## Task 4 — Verdict + Leaderboard
What it is: verdict sentence with n tags; leaderboard DataTable with sortable plain headers, best star + "best", failed row shaded red and excluded from best, inline cost/time mini bars, one muted notes block.
Done when: tests: sort each column, best marks, failed row tone/chip, mini bars present, notes muted, header cells are not buttons.

## Task 5 — Metric heatmap behind toggle
What it is: heatmap grid (rows grouped counts/globals/ratios; big avg miss, small signed bias; tolerance green; best outline), single legend row, collapsed by default, data table behind "Show data".
Done when: tests: collapsed by default, opens on toggle, legend single, cells show n, best outline, failed combo column marked.

## Task 6 — Tests refresh and overflow check
What it is: update Overview, CompareApp, responsive tests to new DOM; add structure test (fixed layout, no overflow-x) for the compare header/overview.
Done when: all compare tests for these files green, `typecheck/lint/build` green.
