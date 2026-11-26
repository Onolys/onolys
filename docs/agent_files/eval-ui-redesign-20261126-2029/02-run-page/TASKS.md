---
status: draft
summary: 8 tasks for the Run page redesign
date: 2026-11-26
---
# Tasks: Run page
Source of truth: `PRD.md`. Depends on SP01 primitives. Test-first, one commit each; run only impacted tests. CI already runs eval-web tests on push/PR, no CI task needed.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Error code catalog | none | done |
| 2 | Logs URL builder | none | done |
| 3 | Config popup rebuild (shared) | SP01 | done |
| 4 | Run header + summary card + copy id + Logs link | 2, 3 | done |
| 5 | Status chips, progress bar, usage tiles, alerts strip | SP01 | done |
| 6 | Unit table (search/filter/sort, result cell, unit output popup) | SP01 | done |
| 7 | Error popup | 1, 2, 6 | done |
| 8 | Page assembly, copy cleanup, update old tests, overflow check | 4, 5, 6, 7 | done |

## Task 1 — Error code catalog
What it is: `run/errorCatalog.ts` mapping stored error codes to {title, explanation, fix hint}; unknown → code + generic hint.
What changes: new module; codes harvested from `eval/backend` `_error_code` and `eval/core` (`invalid_parameters`, `provider_unavailable`, `provider_error`, `rate_limited`, `timeout`, `internal_error`, `provider_skipped`).
Done when: unit tests for each known code, unknown fallback, empty/undefined code.

## Task 2 — Logs URL builder
What it is: `run/logsUrl.ts` building Cloud Logging URLs (project `onolys-eval`, service `onolys-worker-eval`, constants in one place) for one unit run_id and for a list (OR, cap 40 + flag when truncated). First verify in the eval worker code that `unit_id` is what workers log as `run_id`; otherwise use `session_id`.
Done when: unit tests on exact URL/encoding, quoting, cap, empty list returns null; note on verification result in the commit body.

## Task 3 — Config popup rebuild (shared)
What it is: `RunConfigDialog` on `AppDialog`: key-fact tiles, combo list with ComboTags, raw JSON behind a disclosure with Copy. Same props so History and Compare keep working.
Done when: RTL tests: tiles shown, JSON hidden until toggled, Copy works, History config test still green.

## Task 4 — Run header + summary card
What it is: title "Run - <name>" with muted description; summary card with copyable run id, "Logs" link, buttons Config / Compare / Rerun… / Cancel; partial badge.
Done when: tests: exact title, id copy, Logs href from task 2, no id in any button label, Cancel only when cancellable.

## Task 5 — Status chips, progress bar, usage tiles, alerts strip
What it is: chips per state (zero muted), progress bar, tiles for input/output tokens, est. cost, started/elapsed, muted cost note; alerts strip merges provider skip/busy, cancel-requested, partial, run-level error and hides when empty.
Done when: tests for each chip tone/icon, zero muted, progress value, unpriced units listed in cost tile popover, strip hidden on clean runs.

## Task 6 — Unit table
What it is: DataTable with columns Session, Engine, Model, Tier, Effort, Attempt, Status, Stage, Result; search, status filter, all columns sortable; result cell variants; "View JSON" opens "Unit output" popup showing the unit id; one-line explainer + muted footnote.
Done when: tests: sort every column both directions, search, filter, ellipsis title, failed row shaded, button label exactly "View JSON", popup contains id.

## Task 7 — Error popup
What it is: error badge in Result opens popup: title "Unit <id> failed", chips (code/stage/HTTP/retryable when known), explanation + fix hint from catalog, full error block + Copy, per-unit Logs link.
Done when: tests for known code, unknown code, copy, Logs link, focus return to badge.

## Task 8 — Page assembly and cleanup
What it is: compose in `RunView`, remove old plain-text status line and duplicate counts, shorten copy per audit, update `Runs.test`, `RunStatus.test`, `RunLifecycle.test` to the new UI.
Done when: lifecycle test (running → done/failed) green; overflow guard green; page renders fixed-layout table (structure assertion); `npm test/typecheck/lint/build` green.
