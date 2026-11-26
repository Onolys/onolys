---
status: approved
summary: More analysis and Line view tabs as cards, styled charts and toggles
date: 2026-11-26
---
# PRD 05 — More analysis + Line view

## TL;DR
Restyle `MoreAnalysis.tsx` and `LineView.tsx` to `../mockups/more.html` and `lines.html` (+ PNGs), denser. Cost vs accuracy and reliability are the default content for "which combo is best"; the rest sits behind toggles.

## Problem
Scatter, head-to-head, interviews grid and transcript lanes exist but are unstyled; long "How to read" text; failed/unpriced combos not marked.

## Goals / Non-Goals
Goals: below. Non-goals: new metrics/payloads; Human-vs-human baseline compute (stays n/a card).

## Requirements
Shown by default vs behind toggle:
More analysis
- Default: Cost vs accuracy scatter with frontier line (unpriced/failed combos listed under it, muted); Reliability table (repeat agreement, fails, time per combo; failed row shaded red, excluded from best).
- Behind toggle: Error vs interview length (scatter/lines per combo, Turns/Words switch); Head-to-head matrix ("row closer than column on N of M", ties note, colour by win share); Interviews by combo grid (session × combo count error + repeats, session links to Line view); Human-vs-human baseline card (n/a text, needs second coder); data tables.

Line view
- Default: filters (session picker, only-disagreements, code, combo, "N lines differ" chip); transcript lanes (# / speaker chip / line text / Human / one lane per selected combo; disagreements amber + warning mark; one muted note: blank human = no label, text verbatim).
- Behind toggle/popup: Global ratings for the session (table of human vs combo rating chips: green exact, amber off 1, red off 2+; reasoning in a disclosure) behind "Show global ratings"; line popup on click (line text, human code, each combo code + rationale, "k of r repeats agree"); lanes beyond 3 combos behind a combo filter.
Lines table uses fixed layout, long text wraps (no horizontal scroll); on narrow screens each line stacks into a card.

Scatter: SP01 visx scales; points = ComboTag shape+letter+colour; frontier line; labels never overlap (collision nudge or legend-only labels). Error vs length: connect points per combo.

## Architecture
Edit `compare/MoreAnalysis.tsx`, `moreAnalysis.css`, `LineView.tsx`, `lineView.css`; new `compare/charts/{CostAccuracyScatter,ErrorVsLength,HeadToHead,InterviewGrid,ReliabilityTable,BaselineCard}.tsx`, `compare/line/{LineFilters,LaneTable,SessionRatings,LinePopup}.tsx`. Fixtures `analysis.json`, `lines.json`, `turn.json`. No API changes.

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| 1 | Default More-analysis content | scatter + reliability | all | answers best-combo question |
| 2 | Only-disagreements filter default | unchanged (current behaviour) | force on | no behaviour change not asked for |
| 3 | Session ratings | behind toggle | default | bias to less |
| 4 | Baseline card | behind toggle | default | n/a today |

## Manual steps
None.

## Risks / Open Questions
- [RESOLVED: default - only-disagreements default stays as currently implemented]
- [RESOLVED: default - Playwright deferred; unit-level overflow guard]
- Risk: long transcripts; keep rendering as today (paged/limited per existing code), no virtualization added.

## Acceptance Criteria
- Defaults list above holds; toggles open/close; tables behind "Show data".
- Scatter: frontier flags from payload, failed/unpriced listed, labels no overlap (geometry test).
- Line view disagreement rows amber with warning mark (icon + text); popup shows line, human + combo codes + rationale + repeats agree.
- No `overflow-x`; RTL + overflow guard + `npm test/typecheck/lint/build` green.
