---
status: approved
summary: Redesign the eval Run page (header, status chips, usage tiles, unit table, config/error/output popups)
date: 2026-11-26
---
# PRD 02 — Run page

## TL;DR
Run page becomes: title "Run - <name>", a summary card (copyable run id, Logs link, actions), status chips + progress bar, usage tiles, alerts strip, and a searchable/filterable/sortable unit table with popups for config, errors and output. Target visuals: `../mockups/run.html`, `config-popup.html`, `error-popup.html` (+ PNGs); copy per `../mockups/docs/audit.html` (Run page + Popups).

## Problem
`RunView` (`eval/web/src/Runs.tsx`) renders `Run {name||id}`, a plain "running · 1/3 runs done · …" line, loose buttons, token/cost as text, a unit table with "View JSON {unit_id}" buttons, failures as bare codes (e.g. `invalid_parameters`), and config via `RunConfigDialog`. Breaks design rules 1, 3, 4, 6.

## Goals / Non-Goals
Goals: items below. Non-goals: backend changes (only the stored error code exists; no error-detail storage), History page redesign (it only reuses the new Config popup), dark mode.

## Requirements
Shown by default vs behind toggle:
- Default: title + muted description; summary card (run id with copy, "Logs" link, buttons Config / Compare / Rerun… / Cancel); status chips (overall status, done of total, running, queued, failed, cancelled; zero counts muted) + progress bar; usage tiles (input tokens, output tokens, est. cost, started/elapsed); alerts strip (hidden when empty: provider skipped/busy, cancel requested, partial, run-level error); unit table with search + status filter, one-line explainer, muted footnote.
- Behind popup/toggle: full config (popup: key-fact tiles, combo list, raw JSON behind a disclosure + Copy); unit JSON ("View JSON" popup, title "Unit output", unit id inside); failed-unit error (popup); unpriced units list (inside cost tile tooltip/popover); extra columns (Tier, Effort, Attempt) hide on narrow screens.

Detail:
- Title "Run - <run name>" (dash required); fall back to run id when unnamed.
- Unit table columns: Session, Engine, Model, Tier, Effort, Attempt, Status (chip), Stage, Result. Fixed layout, ellipsis + tooltip, no horizontal scroll, stacked cards <760px. Search across all text columns; status filter; every column sortable with up/down arrows (plain headers). Human reference runs once; explainer: "One unit = session x engine x model/tier/effort x attempt. Human reference runs once."
- Result cell: done → "View JSON" (no id); failed → red error-code badge opening the error popup; running → mini progress; skipped → "n/a" + reason. Failed rows get gentle red shade.
- Error popup (mockup `error-popup.html`): title "Unit <id> failed", chips (code, stage, HTTP if known, retryable if known), plain-language explanation, full error block + Copy, one-line fix hint. Stored today: error code only. A catalog maps known codes (`invalid_parameters`, `provider_unavailable`, `provider_error`, `rate_limited`, `timeout`, `internal_error`, `provider_skipped`, others found in `eval/backend` `_error_code`) to {title, explanation, fix hint}; unknown codes show the code verbatim with a generic hint. Do not add backend error-detail storage.
- Logs: Cloud Logging, project `onolys-eval`, service `onolys-worker-eval`. Worker logs carry unit `run_id` + `session_id`, not the eval group id. Run-level "Logs" link filters `resource.labels.service_name="onolys-worker-eval" AND jsonPayload.run_id=("id1" OR "id2" …)` over the group's unit run ids (cap ~40 ids to stay under URL limits, else filter by the unit-id prefix if shared, else show first 40 + note); per-unit "Logs" icon link in the error popup/row actions with that unit's `run_id`. URL form `https://console.cloud.google.com/logs/query;query=<encoded>;duration=P14D?project=onolys-eval` (as `docs/reference/logging.md`; project/service are constants in one config file).
- Config popup shared with History, Compare (every "Config" entry point): tiles for dataset, sessions, attempts, goal, language, versions; combo list with tags; raw JSON behind disclosure + Copy.
- Copy: apply the audit: cut "Rerun with different engines/presets" → "Rerun…"; drop duplicated "N/M runs done" next to heading; cost note muted: "Cost is an estimate. Speech-to-text is not included."

## Architecture
Rewrite `RunView`/`RunStatus` composition using SP01 primitives; split `Runs.tsx` run-detail parts into `eval/web/src/run/` (`RunHeader`, `RunStatusChips`, `UsageTiles`, `AlertsStrip`, `UnitTable`, `ErrorPopup`, `UnitOutputPopup`, `errorCatalog.ts`, `logsUrl.ts`). `RunConfigDialog` is rebuilt on `AppDialog` with the same props so History keeps working. API types unchanged (`RunSummary`, unit rows in `api.ts`).

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| 1 | Logs link grain | run-level OR of unit run ids + per-unit link | group id filter | group id is not in worker logs |
| 2 | Unit run_id source | assume unit's `unit_id` is the worker `run_id`; verify in code, else fall back to `session_id` filter | new backend field | no backend change |
| 3 | Error detail | catalog keyed by stored code | store detail | out of scope |
| 4 | Narrow screens | stacked cards | hide columns only | rule 1 |

## Manual steps
Owner may confirm the Cloud Logging project/service constants in staging/prod (project `onolys-eval`, service `onolys-worker-eval` as given).

## Risks / Open Questions
- [RESOLVED: default - unit_id == worker run_id; task 2 verifies from eval/backend worker code and falls back to session_id if not]
- [RESOLVED: default - cap 40 ids in the run-level logs query]
- [RESOLVED: default - Playwright deferred; unit-level overflow guard]
- [RESOLVED: default - run-level Logs link shown for every status, including queued, where unit ids may be empty it is disabled with a tooltip]
- Risk: existing Runs/RunStatus/RunLifecycle tests assert old copy; update them test-first.

## Acceptance Criteria
- Title text exact "Run - <name>"; run id copyable; no id in any button label.
- Status line replaced by chips + progress bar; token/cost tiles; alerts hidden when empty.
- Unit table: search, filter, all columns sortable (aria-sort), no `overflow-x`, long values ellipsis + title; "View JSON" opens popup titled "Unit output" containing the unit id; error badge opens popup with code, explanation, fix hint, copyable full error.
- Config opens in a popup from run page and History.
- RTL tests for each; overflow guard green; `npm test/typecheck/lint/build` green.
