---
status: draft
summary: 8 tasks for More analysis and Line view
date: 2026-11-26
---
# Tasks: More analysis + Line view
Source of truth: `PRD.md`. Depends on SP01 and SP03. Test-first, one commit each; run only impacted tests. CI exists.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Cost vs accuracy scatter | SP03 | done |
| 2 | Reliability table + baseline card | SP03 | done |
| 3 | Error vs length chart (toggle) | 1 | done |
| 4 | Head-to-head + interviews grid (toggle) | 1 | done |
| 5 | More analysis composition + test refresh | 1-4 | done |
| 6 | Line view filters + transcript lanes | SP03 | done |
| 7 | Session ratings (toggle) + line popup | 6 | done |
| 8 | Line view composition, test refresh, overflow check | 6, 7 | done |

## Task 1 — Cost vs accuracy scatter
What it is: visx scatter with frontier line, ComboTag markers, failed/unpriced combos listed muted under it, one-sentence caption, "Show data".
Done when: tests: frontier points from payload flags, failed combo not plotted but listed, label geometry no overlap, table twin collapsed.

## Task 2 — Reliability table + baseline card
What it is: DataTable (repeat agreement, fails, time per combo; sortable, failed row shaded red, not best); baseline card with n/a text.
Done when: tests: sort, failed tone, best exclusion, baseline text.

## Task 3 — Error vs length chart
What it is: scatter/lines per combo with Turns/Words toggle, points connected per combo, behind a toggle.
Done when: tests: collapsed default, Turns/Words switch changes x values, series per combo.

## Task 4 — Head-to-head and interviews grid
What it is: head-to-head matrix coloured by win share with ties note; session × combo grid (count error + repeats) whose session cells link to Line view; both behind toggles.
Done when: tests: collapsed default, values from fixture, session link target, text + colour not colour alone.

## Task 5 — More analysis composition
What it is: order per PRD (scatter, reliability default; others toggles), drop old markup/CSS and "How to read" paragraphs.
Done when: `MoreAnalysis.test.tsx` updated and green; overflow guard green.

## Task 6 — Line view filters and transcript lanes
What it is: filters (session, only-disagreements, code, combo, differing-lines chip); lane table with speaker chips, human lane, one lane per combo, amber disagreements with warning mark, muted note; stacked cards on narrow screens.
Done when: tests: each filter, chip count, disagreement marker, muted note, fixed layout/no overflow structure, wrapping long text.

## Task 7 — Session ratings and line popup
What it is: session global ratings table with exact/off1/off2+ chips behind "Show global ratings", reasoning in disclosure; clicking a line opens popup (line text, human code, combo codes + rationale, "k of r repeats agree").
Done when: tests: collapsed default, chip tones with text, popup content, focus return.

## Task 8 — Line view composition and test refresh
What it is: assemble, remove old CSS, update `LineView.test.tsx`/`responsive.test.tsx`.
Done when: tests green; overflow guard green; `typecheck/lint/build` green.
