---
status: draft
summary: Four read-only Compare screens (Overview, Deep dive, More analysis, Line view) in eval/web, fed by SP06 endpoints, drawn with hand-rolled SVG/CSS (no chart library), reached from History and run detail, replacing the old embedded Compare/Summary tables. Also adds a confirmed Cancel action on History and run detail (copy: runs already in progress will finish; no new runs start), a "Partial — cancelled at <time>, X of Y runs done" badge on History, run detail and Compare, and a clear notice when a provider was skipped after repeated failures ("Gemini skipped after 5 failures in a row — provider may be down"), with skipped cells shown as n/a; screens show live progress when reopened because eval runs are fully server-driven (the browser never drives a run).
date: 2026-11-25
---
# PRD: SP07 Compare screens

Repo/branch: Onolys/iaudit / `session-report-ux` · Depends on: SP06 (endpoints and payload shapes; SP05 owns the URL prefix) · Owns (files): new `eval/web/src/compare/` (`CompareApp.tsx`, `Overview.tsx`, `DeepDive.tsx`, `MoreAnalysis.tsx`, `LineView.tsx`, `charts/*.tsx`, `compareApi.ts`, `compareUrl.ts`, `compare.css`, `*.test.tsx`, `fixtures/`); edits to `Root.tsx`, `Runs.tsx`, `api.ts` (`cancelled_at` on `RunSummary`), `app.css`, `Runs.test.tsx`, `Root.test.tsx`, `eval/web/README.md`. No backend edits.

## TL;DR
Today a finished run shows one wide per-unit table and a MAE "Summary" tab inside run detail. SP07 replaces it with a separate Compare area that answers three questions in order: which combo is closest to human (Overview), where and why (Deep dive, More analysis), and what happened on this line (Line view). The UI only renders SP06 payloads: it computes no metric, picks no winner, and prints every text verbatim from saved data. Charts are small hand-drawn SVG/CSS pieces, so the bundle does not grow.

## Problem
| Gap | Evidence |
|---|---|
| Compare is a per-session table plus MAE summary embedded in run detail; no leaderboard, heatmap, line view, n or cohort | [verified: `eval/web/src/Runs.tsx:71-123,192`] |
| It consumes `RunDetail.compare`, a shape SP06 removes | [verified: `api.ts:57-73`; SP06 Owns `read_runs.py` compare key] |
| No route to Compare from History; no deep links between levels | [verified: `Root.tsx` handles only `?run=` and `?view=history`] |

## Goals / Non-Goals
**Goals:** the approved Overview, Deep dive, More analysis and Line view; linked drill-down; Cancel with confirmation and honest copy (in-flight runs finish); honest partial (cancelled) display; a visible provider-skipped notice and n/a skipped cells; honest empty and partial states; 320-1,280 px, keyboard and screen-reader usable; offline fixture tests.
**Non-goals:** any calculation or wording of verdicts (SP06); run creation, rerun, delete, the cancel endpoint/semantics and the provider breaker/backoff (SP04/05; SP07 only displays them); the sign-in screen and auth code (SP03 shares the prod sign-in; SP07 keeps the existing auth wrap in `Root.tsx` and writes none); driving or polling a run to make it progress; cross-run compare; composite score; export; editing labels; prompt versioning.

## Requirements

**Entry and shell**
- History rows and run detail get a "Compare" link (real `<a href>`, plain click uses the app's pushState navigation like the existing run link). Enabled for `done` and `partial` runs (including cancelled-with-results); for `queued/running/failed/cancelled` (nothing completed) and `deleting` it is replaced by status text ("Compare opens when the run has finished results"). A running run's Compare is not offered (SP06 caches running runs for 10 s only).
- Compare header: run name, the Partial badge when partial (below), "N sessions, R repeats", label coverage ("Human labels: all counts, 4 globals" from `label_coverage`), a Back to run link, and a four-tab bar (Overview, Deep dive, More analysis, Line view). Tabs use `role=tablist` with arrow-key navigation; the selected tab is in the URL.
- Combo legend shared by all tabs: short labels A, B, C... mapped to provider/model/tier/effort exactly as `combo_labels` gives. Label letters follow the API order and never change between tabs.
- Every chart has a short "How to read" caption directly under it (fixed UI copy, plain words, one to three sentences) and a table twin (visually-hidden or toggle) so colour and shape are never the only signal.

**Leave the page, Cancel and Partial (all eval-run screens)**
- Nothing in the browser drives a run: no screen calls anything to make a run progress; polling is read-only. The owner can close the browser or leave the page and the eval keeps running to completion [SP05 R6]. Reopening History or a run detail shows the live current status and counters from the server (fresh fetch on open). History refreshes non-terminal rows read-only every 3 s while any is `queued|running` and stops when none is (abort on unmount); run detail already polls [verified: `Runs.tsx:144-163`, `POLL_MS`].
- Cancel button: run detail keeps its "Cancel run" button [verified: `Runs.tsx:180`] and History `RunActions` gets a "Cancel run" item [verified: `RunActions` `Runs.tsx:23-31` has Rerun/Config only]; both shown only for `queued|running` and not already `cancel_requested`. Click opens a confirm dialog (`@onolys/ui` Dialog, focus trapped, Esc closes without cancelling, focus returns): "Stop this eval run? Runs already finished are kept and can be compared. Runs already in progress will finish; no new runs start." Buttons "Cancel run" (confirm) and "Keep running". After confirm, while `cancel_requested` and not yet terminal, History and run detail show the note "Cancelled — runs already in progress will finish; no new runs start." (owner copy); no "stopped" wording anywhere, because nothing in progress is stopped (SP05 R7). Allowed for any allowlisted user (same as delete). Confirm calls `api.cancel`; the control disables and the status reads "cancelling" (existing label [verified: `Runs.tsx:11`]) until the server reports terminal (when the in-flight runs have finished). Cancel is idempotent: a repeat or a cancel on a finished run returns the current status and the UI just shows it; errors show `role=alert` with Retry.
- Partial badge: when `status=partial` and `cancelled_at` is set: "Partial — cancelled at <time>, X of Y runs done" (X = `done_units`, Y = `total_units` exactly as the API returns them, the same counters as the progress line [verified: `Runs.tsx:179`]; whether human reference units are included is SP05's definition and SP07 never recomputes it); when `skipped_units` > 0 it appends ", Z skipped"; `partial` without `cancelled_at` reads "Partial — X of Y runs done" (some runs failed or were skipped). Shown in the History Status cell, run-detail heading, and Compare header, using words and a symbol, not colour alone. `cancelled` (none completed) reads "Cancelled — no runs completed" and has no Compare link. Compare screens on a partial run show the API's `coverage` and `excluded` (reason `cancelled`) verbatim next to the cohort line, so the missing runs and n are visible.
- **Provider skipped notice.** When the run detail/History payload has `provider_skips[]` (SP05) or Compare has `coverage.skipped_providers` (SP06), show the notice "<Provider> skipped after N failures in a row — provider may be down" (e.g. "Gemini skipped after 5 failures in a row — provider may be down"; N from the payload, provider display name from one small map, unknown id shown as is) with a warning symbol and words, not colour alone: on run detail (above the unit table), in the History row's Status cell (short form "Gemini skipped after 5 failures"), and in the Compare header next to the cohort line. Skipped cells render as n/a with the API reason ("skipped: provider unavailable"), never blank or 0; run-detail unit rows show status "skipped"; a combo whose provider is skipped is labelled in the leaderboard and heatmap column header ("skipped") and has no best/winner mark. While a provider is backing off (SP05 R6b, `provider_cooldowns[]`, unit status `waiting`) run detail shows a quiet note "<Provider> is busy — waiting to retry"; no client logic, display only.

**1. Overview** (SP06 `/compare/overview`)
- Verdict line: render `verdict.text` clauses as given; show each clause's n via `claims`; no client rewording. If absent or `has_human=false`: "No human reference in this run" and the screen shows only the operational columns (failures, cost, time) with no error columns.
- Sortable leaderboard (default Count error ascending; click or Enter/Space on a column header, `aria-sort`): Count error, Globals within +-1, Line match accuracy, Line match macro F1, Fails, Cost, Time. Best per column marked with a star and the word "best" (not colour only). Cells show value plus `n of cohort` ("11 paired of 12"); n/a cells show the API's reason text.
- Heatmap: first column Human (raw values), then one compact column per combo (A, B, C), frozen row labels, horizontal scroll past 8 combos, legend beside. Rows in order: 10 codes, 4 globals, R:Q, %CR. Big number = `value`; small = `off` and signed `bias` ("off 0.9 · +0.4"). Green fill when `within_tolerance` (0.6 lines / 0.4 points); outline when `best`; `n` printed in every cell; a 1-session cell looks like any other except its visible `n=1`. Signed numbers keep their sign; colour encodes size only. Globals: `value` is null, so the cell headline is `off` ("off 0.5"), per-interview ratings are one click away. R:Q and %CR: no green (tolerance null), best outline still shown. n/a cell: text "n/a" plus the API reason, never blank or 0.
- Click or Enter on a heatmap cell opens Deep dive scrolled to that row, with that combo preselected. Click on a combo letter selects it in Deep dive.
- Footnotes from the API (`footnotes`: retried-run time note, excluded sessions) printed verbatim under the table.

**2. Deep dive** (SP06 `/compare/deep-dive`)
- Picker: Human is fixed; default selection top 3 combos by Count error (the API orders), checkbox list to add or remove any combo; the choice is in the URL (`combos=`). Changing it re-fetches, because SP06 computes cohorts over the requested set; the cohort line ("paired X of Y") updates.
- Globals: per global, a dot chart, one row per interview, Human dot plus one dot per selected combo (shape and letter differ, not just colour), with average miss and within +-1 beside it; plus same / off-by-1 / off-by-2+ stacked bars per combo.
- Counts: per code grouped bars (Human next to each combo) and a bias word from `bias_pct` ("over-counts by 12%"), or "n/a" with reason.
- Per-line agreement (hidden with the exact message "no line-level output (human / <combo> / both)" naming the missing side from `missing`): precision / recall / F1 table per code per combo with `codes_labeled` of 10 printed; confusion grid for one combo at a time via a switch, plus the `multi` bucket as its own labelled cell/row so totals match. Clicking a grid cell or a bucket bar opens Line view filtered to that human code and combo code (`code=`, `combo=`, `only=disagree`, session = first session with such lines, session list shown).
- Reasoning roll-up: per code, panel per combo, count from the payload; snippets load on demand through `/compare/reasoning` (50 per page, "Load more"), verbatim; `""` shows "withheld". Human column shows counts and any gold note present.

**3. More analysis** (SP06 `/compare/analysis`)
- Cost vs accuracy frontier: scatter, x cost per run, y Count error; frontier combos joined by a line; unpriced combos listed under the chart with their reason, not plotted.
- Human-vs-human baseline: card showing the API's text ("n/a - needs a second human coder, not in this dataset") in every current dataset; never a number.
- Reliability table: same MITI level, repeat agreement, failures, time (n/a text from the API).
- Head-to-head: matrix of "X closer than Y on N of M sessions" plus ties.
- Interviews x combos grid: session Count error cells with `repeats`; row header links to that session's Line view.
- Error vs length: scatter per (session, combo), x turns, y Count error (words as a toggle).

**4. Line view** (SP06 `/compare/sessions/{sid}/lines`, `.../lines/{turn_id}`)
- Session picker (from `cohorts`/session list); transcript turns with speaker and text exactly as returned, lanes Human + selected combos. Past 5 combos each line collapses to chips of only the disagreeing combos plus "+N agree", expandable per line. A turn without a human label shows a blank human lane cell, not "none".
- Filters: only disagreements, by code, by combo (all in URL). Disagreeing lines are highlighted with a mark (symbol, not colour alone).
- Click or Enter on a line opens a dialog (focus trapped, Esc closes, focus returns): line text, human code (+ note), each combo's code, its rationale verbatim, "k of r repeats agree".
- Per-session globals table below: human vs each combo rating, the combo's reason, and cited evidence lines.
- Engines with no line output: lane reads "no line-level output" and stays empty. No human line labels: whole view replaced by "no line-level output (human)".

**Empty, partial, error states** (all screens)
| State | Behaviour |
|---|---|
| Loading | `role=status` "Loading ..." per tab; skeleton not required |
| Request failed | `role=alert` with message and Retry, tab-local (other tabs keep working) |
| 404 | "Run not found" with link to History |
| 409 `transcript_changed` | Line view only: "The saved transcript changed since this run; lines cannot be shown." |
| `has_human=false` | Overview operational-only; Deep dive, line parts and "More analysis" error charts show "no human reference" |
| Partial labels (e.g. AnnoMI) | Per-cell n/a with the API reason; `codes_labeled` shown |
| Combo with failed runs | Shown in the cohort line and Fails column; excluded values say why |
| Partial (cancelled) run | Badge + `coverage`/`excluded` text on Compare; Compare opens on completed runs only |
| Provider skipped | Notice on run detail, History row and Compare header; skipped cells n/a with reason; combo labelled "skipped" |
| Cancel request fails | `role=alert` with Retry; status unchanged |
| 409 `no_completed_runs` / `not_finished` | "No completed runs to compare yet" with link back to run |

## Architecture
**Routes.** Root keeps its history/pushState query-param navigation (no router added). New params: `?run=<id>&view=compare&tab=overview|deep|more|lines` plus `combos`, `code`, `metric`, `session`, `turn`, `only`. `compareUrl.ts` parses and builds these (pure, tested); `Root.navigate` stops deleting `view` when `view=compare`. Browser back works between tabs and drill-downs; pasted links restore state.

**Components.** `CompareApp` (header, tabs, legend, URL state) -> one component per tab -> chart components (`Heatmap`, `DotRows`, `StackedBars`, `GroupedBars`, `ConfusionGrid`, `Scatter`, `LaneTable`), each pure props-in/markup-out, each with a table twin. Existing UI kit `@onolys/ui` Button/Input/Dialog are reused; existing `.table-scroll` and sticky-row-label pattern are reused (`app.css:35,45`).

**Data fetching.** `compareApi.ts` adds typed functions to `createEvalApi` using the existing authenticated `request`, with `AbortController` per call [verified: `Runs.tsx` poll pattern]. One fetch per tab on first open, cached in `CompareApp` state keyed by `(tab, combos)`; reasoning snippets and line popups are fetched on demand. All responses are validated shallowly (required keys, number-or-null); unknown shape shows the tab-local error instead of rendering guesses. No client-side metric maths, sorting of leaderboard only.

**Chart approach: hand-rolled SVG + CSS grid, no library.** `package.json` has no chart dependency [verified]; the charts needed are bars, dots, a grid and two scatters. A library (e.g. Recharts, ~100+ kB gzip plus d3 parts) would add weight, harder keyboard focus and table-twin control, and styling that fights Tailwind 4 theme tokens. Hand-rolled SVG gives exact keyboard/ARIA control, deterministic jsdom tests (text and attributes), and zero new dependency or supply-chain risk. Cost: more code; mitigated by sharing one scale helper and one legend component.

**Responsive.** Heatmap, grids and tables sit in `.table-scroll` regions (`tabindex=0`, labelled) with sticky row labels; below 760 px charts reflow to one column and the leaderboard becomes stacked cards (same `data-label` pattern as `history-table`, `runs.css:22-39`). Lines wrap with `overflow-wrap: anywhere`.

**Cancel and partial in code.** `api.ts`: `RunSummary.cancelled_at?: string | null`; the existing `cancel` stays. `Runs.tsx`: shared `CancelRunDialog`, `PartialBadge`, and a History poll hook; `statusLabel` extended for the partial text. Terminal test `terminal()` already treats `partial` as terminal [verified: `Runs.tsx:9`].

**Removed** (listed so nothing lingers): `CompareView`, `SummaryView`, `sortValue`, the Compare tab bar and its call in `RunView` (`Runs.tsx:62-123,192`); types `CompareCell`, `CompareAggregate`, `Compare`, `ErrorMetric`/`Aggregate` if unused, and `RunDetail.compare` (`api.ts:57-73`); `table.matrix` CSS (`app.css:45-47`) if unused after removal; tests that render `CompareView`/`SummaryView` (`Runs.test.tsx:20-40,211-214`) and the `compare:` fixture key (`Root.test.tsx:47`); README line about "comparison screens attach at that boundary". Unit progress table, Config dialog and rerun stay unchanged; the run-detail Cancel button keeps its place but gains the confirm dialog.

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| 1 | Charts | Hand-rolled SVG/CSS | Recharts / visx | No chart dep today; simple chart set; a11y and test control |
| 2 | Routing | Extend query params, no router | Add react-router | Matches existing app; deep links need only params |
| 3 | Tabs vs one long page | Four tabs, URL-addressed | Scroll page | Heavy payloads load per tab; matches SP06 endpoints |
| 4 | Compare page vs run detail | Separate `view=compare` page | Keep inside run detail | Run detail stays a progress page; Compare gets room |
| 5 | Deep-dive subset | Refetch on picker change | Slice Overview data | SP06 cohort is over requested set |
| 6 | Cell display | Value big, `off` + bias small | One number | Owner-approved mockup |
| 7 | Metric logic | None in UI | Derive in client | One source of truth (SP06) |

## Risks / Open Questions
- [RESOLVED: owner 2026-11-25 — default: `value=null`, `off` is the headline ("off 0.5"), per-interview ratings only in Deep dive] Heatmap globals.
- [RESOLVED: owner 2026-11-25 — default: never green, `best` outline still shown, legend says "no tolerance set for ratios"] R:Q / %CR `within_tolerance=null`.
- [RESOLVED: owner 2026-11-25 — default: the session with the most matching lines, session picker shown with counts] Line view session list for a cell/bar drill-down.
- [RESOLVED: owner 2026-11-25 — default: unit tests assert structure (scroll regions, no fixed widths); owner round 2: no live runs, so the recorded browser check at 320, 768, 1,280 px is done by the owner after deploy] Viewport verification.
- [RESOLVED: owner 2026-11-25 — default: plain paragraph, claims as small "n=" tags] Verdict text styling.
- [RESOLVED: owner — default] Endpoint prefix `/v1/eval-runs/{id}/compare/*` behind the eval allowlist auth; client reads it from one constant.
- [RESOLVED: owner 2026-11-25 — default: A..Z then AA, AB] Combo letters past 26.
- [RESOLVED: owner 2026-11-25 — leave the page; eval is fully server-driven; screens show live status on reopen] See "Leave the page".
- [RESOLVED: owner 2026-11-25 — Cancel button with confirm dialog, any allowlisted user, state `partial` (or `cancelled` if none completed), Partial badge on History, run detail, Compare] See "Leave the page, Cancel and Partial".
- [RESOLVED: owner 2026-11-25 (round 2) — default] "X of Y runs done": render the API's `done_units`/`total_units` as the progress line does; SP05/SP06 acceptance pins whether human units are in them.
- [RESOLVED: owner 2026-11-25 (round 2) — Cancel copy: "Cancelled — runs already in progress will finish; no new runs start."; no prod worker edit] See "Leave the page, Cancel and Partial".
- [RESOLVED: owner 2026-11-25 (round 2) — a provider skipped after 5 failures in a row shows a clear notice on run detail, History row and Compare; skipped cells n/a] See "Provider skipped notice".
- [RESOLVED: owner 2026-11-25 (round 2) — eval uses the prod login (shared sign-in from `web/src/auth`, SP03); SP07 keeps `Root.tsx`'s auth wrap and fixtures aligned with it, no own auth code] Sign-in.
- [DEFERRED] Export/print, cross-run compare, saved views.

## Acceptance Criteria
Fixture-driven (`eval/web/src/compare/fixtures/`, copies of SP06 payload shapes; fake fetch; no network; existing `vitest` + jsdom).
- History and run detail show a Compare link for done/partial runs, none for running/failed/cancelled/deleting; link opens `view=compare&tab=overview`; run detail has no embedded compare table.
- Overview: leaderboard sorts on header click/keyboard with `aria-sort`; best cells show star plus "best"; every heatmap cell contains its `n`; `n=1` cell is coloured like others; off 0.6 (lines) and 0.4 (points) render green, 0.61 and 0.41 do not; globals show `off` headline; R:Q has no green; n/a cells show the API reason, never blank or 0; signed bias renders with its sign.
- Heatmap Human column first, row labels sticky, 9 combos create a horizontal scroll region.
- Cell click lands on Deep dive with that code row and combo selected (URL asserts).
- Deep dive defaults to 3 combos, picker adds a 4th and triggers a refetch with `combos=`; confusion grid totals plus `multi` equal aligned lines; cell click opens Line view with `code`/`combo`/`only` set.
- Missing line output renders "no line-level output (human)", "(<combo>)" and "(both)" in the three cases; no line chart rendered.
- Line view: 6 combos collapse to chips + "+N agree"; blank human cell is not "none"; popup shows verbatim text, rationale (`""` -> "withheld"), "2 of 3 repeats agree"; Esc closes and returns focus; transcript text is never altered (string equality with fixture).
- More analysis: baseline shows the API's n/a text; unpriced combo listed, not plotted; frontier points match the payload flags.
- Leave the page: opening History/run detail with a `running` fixture shows current status and counters; History polling refreshes `running` rows and stops when none is active; no call other than reads is made for progress (fake fetch asserts only GETs).
- Cancel: History item and run-detail button appear only for `queued|running` and not `cancel_requested`; click opens the confirm dialog with the copy "Runs already in progress will finish; no new runs start." (focus trapped, Esc closes without calling the API, focus returns); after confirm the "Cancelled — runs already in progress will finish; no new runs start." note shows until terminal and no text claims in-flight runs are stopped; confirm POSTs cancel once, shows "cancelling", and a double-click sends one request; cancel on a finished run (409/no-op reply) just shows the status; failure shows alert + Retry.
- Partial: `partial` + `cancelled_at` renders "Partial — cancelled at <time>, X of Y runs done" on History, run detail and Compare header; `partial` without `cancelled_at` renders the failure variant; `cancelled` renders "Cancelled — no runs completed" with no Compare link; Compare on a partial fixture shows `coverage` and `excluded` (reason `cancelled`).
- Provider skipped: a fixture with `provider_skips=[{provider: gemini, after_failures: 5}]` shows "Gemini skipped after 5 failures in a row — provider may be down" on run detail, a short form in the History row and the full text in the Compare header; skipped unit rows say "skipped"; skipped cells are n/a with the API reason (not blank, not 0); the skipped combo has no best mark; `waiting`/cooldown fixture shows "Gemini is busy — waiting to retry"; a `partial` run with `skipped_units` shows ", Z skipped" in the badge.
- Sign-in: `Root.test.tsx` fixtures use the shared prod sign-in gate (SP03) with the fake auth provider; no test imports an `onolys_admin_auth`/eval-own `AuthGate` copy.
- States: loading, tab-local error with Retry, 404, `transcript_changed`, `has_human=false`, partial labels each have a test.
- Accessibility: tabs arrow-navigable; every chart has a "How to read" caption and a table twin; axe-style lint (`jsx-a11y`) passes; no information by colour alone (marks/words present).
- Viewport (offline): jsdom structure tests assert no fixed widths and labelled scroll regions at 320/768/1,280 px class breakpoints; the recorded browser check at 320, 768, 1,280 px is the owner's after deploy (agents do no live run or deploy).
- `npm run typecheck`, `lint`, `test`, `build` pass; bundle size delta recorded in the PR (expected small, no new dependency).
- All tests offline: agents build and run offline tests only (fixtures, fake fetch); no deploy, no terraform apply, no live LLM/STT eval run (the owner runs the first eval).
