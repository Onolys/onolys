---
status: approved
summary: Eval UI redesign (run + compare pages): index, decisions, shown-by-default lists
date: 2026-11-26
---
# Eval UI redesign
Branch `feat/eval-ui-redesign`. Goal: Compare pages help pick the best model/engine combo; progressive disclosure (less by default, detail behind toggles); design rules (`docs/design-rules.md` on PR #78) applied; light mode only.
Reference: `mockups/` (HTML, PNGs at 1440/390, `mockups/docs/{audit,graphs,rules}.html`). Drive copy: https://drive.google.com/drive/folders/1Hn_FSaczarUlpzrRPWib6Ukzf8bVpXOM. Prior spec: `docs/agent_files/session-report-ux-20261124-1738/{06-compare-calculations,07-compare-screens}/PRD.md` (PR #63). Make everything denser than the mockups.

| # | Sub-project | Tasks | Depends on |
|---|---|---|---|
| 01 | ui-primitives (chips, cards, modal, DataTable, toggle, chart lib + theme, overflow guard) | 7 | none |
| 02 | run-page | 8 | 01 |
| 03 | compare-header-overview | 6 | 01 |
| 04 | deep-dive | 7 | 01, 03 |
| 05 | more-analysis-line-view | 8 | 01, 03 |

Graph: 01 → 02; 01 → 03 → 04, 05 (02 and 03 parallelizable; 04 and 05 parallelizable). Suggested order: 01, then 02 ‖ 03, then 04 ‖ 05.

## Locked decisions
- Chart lib: visx modular (scale/shape/axis/group), SVG only for dot plot/scatter/lines; bars, heatmap, confusion grid are CSS. Budget ≤ 40 KB gzip added (est. 15-25), enforced by a size test. Fallback d3-scale/d3-shape if React 19 peer blocks visx.
- Light mode only. Failed/invalid combos: red-shaded row, excluded from all "best".
- Run title "Run - <name>"; Compare title "Compare - <name>". Error popup uses a code catalog only; no backend error storage. Logs: Cloud Logging project `onolys-eval`, service `onolys-worker-eval`, filter by unit run_id(s).
- Tests test-first; unit-level overflow guard (no `overflow-x` CSS, fixed-layout structure); Playwright at 1440/1024 `[DEFERRED]` until eval/web has e2e infra (Playwright is in `web/` only).

## Shown by default vs behind toggle
- Run page: default = title, summary card (id copy, Logs, actions), status chips + progress, usage tiles, alerts (if any), unit table (search/filter/sort). Behind: config popup, unit JSON popup, error popup, unpriced list, extra columns on narrow screens.
- Compare header (all tabs): default = title, 4 summary cards, tabs, combo legend once. Behind: full per-session coverage ("Show all"), config popup.
- Overview: default = verdict, leaderboard (+ muted notes). Behind: metric heatmap, its data table, column definitions.
- Deep dive: default = combo selector, globals dot plots, counts-per-code small multiples, P/R/F1 table. Behind: miss-bucket bars, confusion grid, reasoning roll-up, all data tables.
- More analysis: default = cost vs accuracy scatter, reliability table. Behind: error vs length, head-to-head, interviews by combo, human baseline, data tables.
- Line view: default = filters + transcript lanes. Behind: session global ratings, line popup (on click), extra combo lanes via filter.

## Cross-cutting resolved defaults
- `[RESOLVED: default - visx; d3 fallback]`, `[RESOLVED: default - Playwright deferred]`, `[RESOLVED: default - primitives local in eval/web/src/ui]`.
- `[RESOLVED: default - unit_id is worker run_id (verify, else session_id); cap 40 ids in run-level logs query]`.
- `[RESOLVED: default - backend change only if best flags include failed combos (SP03 task 1)]`.
- `[RESOLVED: default - heatmap, miss buckets, confusion grid collapsed; only-disagreements default unchanged]`.
- Risk: existing tests assert old DOM/copy; each task updates them test-first.
