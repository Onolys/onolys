---
status: done
summary: SP07 Tasks 1–9 implemented and offline-verified; review fixes recorded
date: 2026-11-25
---
# Tasks: SP07 Compare screens
Source of truth: /root/projects/onolys/iaudit/.worktrees/session-report-ux/docs/agent_files/session-report-ux-20261124-1738/07-compare-screens/PRD.md. All work is in `eval/web` (no backend edits), offline only: fixtures + fake fetch, vitest/jsdom. CI job `eval-web` in `.github/workflows/ci.yml` already runs `npm ci`, test, typecheck, lint, build on `eval/web` changes, so no workflow task is needed (confirmed). SP03 (shared prod sign-in) lands first; SP05/SP06 payload shapes are consumed via fixtures.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Foundation: types, compare API, URL state, fixtures, old Compare removal | — | done |
| 2 | Cancel with confirm dialog + History live refresh | 1 | done |
| 3 | Partial badge + provider-skipped notices | 1 | done |
| 4 | Compare shell: entry links, header, tabs, legend, states | 1, 3 | done |
| 5 | Overview tab (verdict, leaderboard, heatmap) | 4 | done |
| 6 | Deep dive tab | 5 | done |
| 7 | More analysis tab | 4 | done |
| 8 | Line view tab | 6 | done |
| 9 | Auth alignment, responsive/a11y checks, docs, final gate | 2, 5, 6, 7, 8 | done |

Completion evidence: [implementation](code-2026-11-25-0345.md), [review](review-2026-11-25-0345.md), and [Task 9 verification](task9-verification-20261125.md). Task commits: 1 `9dde098`, 2 `aad8d36`, 3 `1ebb4ec`, 4 `07cd7e7`, 5 `83d78db`, 6 `4def9f2`, 7 `89866a3`, 8 `606bd3f`, 9 `7dcd6eb`. Review fixes: `1a5c992`. Owner checks below remain separate.

## Task 1 — Foundation
What it is / what it means: the plumbing every screen needs, so later tasks only draw UI. Traces to Decisions 2, 7 and the Architecture "Data fetching / Routes / Removed" sections.
What changes at a high level: add typed compare calls to `createEvalApi` behind one prefix constant with shallow shape validation and per-call abort; add `compareUrl.ts` (parse/build `view=compare`, `tab`, `combos`, `code`, `metric`, `session`, `turn`, `only`); stop `Root.navigate` dropping `view` for compare; add `cancelled_at` to `RunSummary`; add fixtures copied from SP06 payload shapes; remove `CompareView`, `SummaryView`, `RunDetail.compare`, unused types/CSS and their tests/fixture key.
Done when: `compareUrl` round-trip tests, `compareApi` tests (valid payload, unknown shape rejected, 404/409 mapped, abort) pass; no reference to the removed compare code remains; existing Runs/Root tests still pass; typecheck/lint green.

## Task 2 — Cancel and live History
What it is / what it means: honest Cancel on History and run detail, and screens that show live status when reopened (eval is server-driven). Traces to Requirements "Leave the page, Cancel" and resolved cancel-copy decisions.
What changes at a high level: shared `CancelRunDialog` (focus trapped, Esc closes without calling API, focus returns) with the exact confirm copy and buttons "Cancel run" / "Keep running"; History action item and run-detail button only for `queued|running` and not `cancel_requested`; after confirm show "cancelling" and the note "Cancelled — runs already in progress will finish; no new runs start."; alert + Retry on failure; idempotent on finished runs; History polls non-terminal rows every 3 s read-only and stops/aborts when none active. No "stopped" wording.
Done when: tests prove visibility rules, dialog copy and focus behaviour, Esc makes no call, double-click sends one POST, note shows until terminal, 409/no-op just shows status, failure shows alert + Retry, polling refreshes `running` rows then stops, and fake fetch sees only GETs for progress.

## Task 3 — Partial badge and provider-skipped notices
What it is / what it means: display-only truthfulness for partial/cancelled runs and skipped providers. Traces to "Partial badge" and "Provider skipped notice" requirements.
What changes at a high level: `PartialBadge` and extended status labels ("Partial — cancelled at <time>, X of Y runs done", ", Z skipped", failure variant, "Cancelled — no runs completed") using API counters verbatim, with symbol plus words; provider-skip notice (full on run detail, short in History Status cell, reusable for Compare header) via one provider display-name map; unit rows show "skipped"; "<Provider> is busy — waiting to retry" for cooldowns.
Done when: tests cover each badge variant on History and run detail, the full/short skip text with Gemini example and unknown-provider fallback, "skipped" unit rows, and the waiting note.

## Task 4 — Compare shell
What it is / what it means: the separate Compare page frame. Traces to Decisions 3, 4 and "Entry and shell".
What changes at a high level: real `<a href>` Compare links on History and run detail (pushState on plain click) for `done`/`partial` only, status text otherwise; `CompareApp` with header (name, Partial badge, session/repeat counts, label coverage, Back link, skip notice, `coverage`/`excluded` text), `role=tablist` with arrow keys and URL-selected tab, shared combo legend (A..Z, AA…), per-tab fetch cache, and the loading/alert-Retry/404/409 `no_completed_runs` states; reusable "How to read" caption plus table-twin pattern.
Done when: link-presence tests for done/partial vs running/failed/cancelled/deleting; tab keyboard and URL tests; partial-run header shows coverage/excluded verbatim; loading, tab-local error with Retry, 404 and 409 states each tested.

## Task 5 — Overview tab
What it is / what it means: "which combo is closest to human". Traces to Decisions 6, 7 and the Overview requirements.
What changes at a high level: verdict paragraph with n tags (no rewording), sortable leaderboard (aria-sort, star + "best", n of cohort, n/a reasons, "skipped" combos have no best), heatmap with Human column first, sticky row labels, scroll region past 8 combos, value/off/bias display, 0.6/0.4 tolerance green, no green for R:Q/%CR, globals headline `off`, per-cell `n`, verbatim footnotes, `has_human=false` operational-only view; cell/letter click navigates to Deep dive.
Done when: tests for sort by click and keyboard, best markers, n in every cell, n=1 styling, 0.6/0.61 and 0.4/0.41 boundaries, signed bias, n/a reasons never blank or 0, 9-combo scroll region, cell click URL, and no-human state.

## Task 6 — Deep dive tab
What it is / what it means: "where and why". Traces to Decision 5 and Deep dive requirements.
What changes at a high level: combo picker (default top 3, URL `combos=`, refetch on change, cohort line updates); globals dot rows and same/off-by-1/off-by-2+ bars; grouped count bars with bias words; per-line precision/recall/F1 with `codes_labeled`, confusion grid with `multi` bucket and cell click to Line view; exact "no line-level output (human / <combo> / both)" message; paged verbatim reasoning roll-up with "withheld" and "Load more".
Done when: tests for default 3 + add 4th refetch with `combos=`, grid totals plus `multi` equal aligned lines, grid click sets `code`/`combo`/`only`, the three missing-output messages with no line chart, reasoning paging and `""` withheld, bias word and n/a reason.

## Task 7 — More analysis tab
What it is / what it means: cost, reliability and baseline context. Traces to More analysis requirements.
What changes at a high level: cost-vs-accuracy scatter with frontier line and unpriced combos listed under it (not plotted), human-vs-human baseline card showing the API's n/a text only, reliability table, head-to-head matrix with ties, interviews x combos grid (row header links to Line view), error-vs-length scatter with turns/words toggle, all with captions and table twins.
Done when: tests for frontier points matching payload flags, unpriced listed not plotted, baseline text verbatim and never a number, head-to-head counts, grid link URL, toggle, and `has_human=false` message.

## Task 8 — Line view tab
What it is / what it means: "what happened on this line". Traces to Line view requirements and Decision 7.
What changes at a high level: session picker with counts (default: most matching lines), transcript with Human + combo lanes, collapse to disagreeing chips plus "+N agree" beyond 5 combos, URL filters (only disagreements, code, combo), non-colour disagreement mark, line dialog with verbatim text/rationale/"k of r repeats agree", per-session globals table with reasons and evidence, empty-lane and no-human states, 409 `transcript_changed` message.
Done when: tests for 6-combo collapse, blank human cell (not "none"), dialog contents and "withheld", Esc closes and returns focus, transcript string equality with fixture, filters in URL, "no line-level output" lane/view, and the 409 message.

## Task 9 — Auth alignment, responsive/a11y, docs, final gate
What it is / what it means: close-out checks for acceptance. Traces to sign-in and viewport/accessibility resolutions.
What changes at a high level: align `Root.test.tsx` fixtures with the SP03 shared sign-in gate (no eval-own AuthGate copy, no own auth code); structural responsive checks (labelled scroll regions, no fixed widths, stacked leaderboard below 760 px); a11y sweep (captions and table twins on every chart, `jsx-a11y` clean); update `eval/web/README.md`; optional local Playwright check at 320/768/1,280 px against a local fixture build only.
Done when: `npm run typecheck`, `lint`, `test`, `build` all pass in `eval/web`; Root tests use the shared gate; structure tests for the three breakpoint classes pass; bundle size delta noted for the PR (no new dependency).

## Owner steps (not tasks)
- Recorded browser check at 320, 768, 1,280 px against the deployed app after deploy.
- Run the first real eval (no agent live runs, deploys or terraform apply).
- Confirm with SP05/SP06 that `done_units`/`total_units` definition (human units) matches the badge expectation.
