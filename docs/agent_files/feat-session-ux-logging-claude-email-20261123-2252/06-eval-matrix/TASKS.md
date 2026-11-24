---
status: draft
summary: 10 tasks - options from models.yaml, combo_routes, request validation + plan_units + human lock, run wiring, unit retry, compare/legacy read path, picker UI, compare/summary UI, preset retirement + docs, owner live smoke.
date: 2026-11-23
---
# Tasks: SP06 Eval model -> tier -> effort matrix
Source of truth: docs/agent_files/feat-session-ux-logging-claude-email-20261123-2252/06-eval-matrix/PRD.md. All PRD Open Questions are RESOLVED or DEFERRED (none OPEN). Depends on SP01 (`config/models.yaml`, `llm/models.py`) and softly on SP03 (`is_transient`; local shim until it lands). All tests use no live API (fake `llm_factory`, fake `sleep`, fixtures). No `xhigh` anywhere. No CI workflow change is required.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | /v1/options from models.yaml | SP01 T1 | done |
| 2 | combo_routes + effort output caps | SP01 T1, T5 | done |
| 3 | Selection request, validation, plan_units, human lock | 1 | done |
| 4 | Run execution on combo routes + drift guard | 2, 3 | done |
| 5 | Unit retry on transient errors | 4 | done |
| 6 | Compare per combo, per-session error, legacy read path | 4 | done |
| 7 | NewRun pickers, count preview, human lock UI | 1, 3, 6 | done |
| 8 | Compare table transpose + Summary view | 6 | done |
| 9 | Preset retirement + eval-site docs | 4, 7, 8 | done |
| 10 | Owner live smoke (provider x effort) | 4, 7 | todo |

## Task 1 — /v1/options from models.yaml
What it is / what it means: The picker's data source becomes the shared model config instead of named presets. Traces to R1, D1.
What changes at a high level: `catalog.py` returns `models: [{id,label,context_tokens,max_output_tokens,tiers:[{id,efforts,default_effort}]}]` from SP01's loader via `services.models`; `presets` is removed. `defaults.<mode>.selection` is the combo of the resolved default `mid` route (tier + `reasoning_effort`), labelled "(prod)", with no hard-coded names.
Done when: tests pass that `/v1/options` matches `models.yaml` (models -> tiers -> efforts), has no `presets`, and the default combo equals the resolved `mid` route (AC1). The eval image is confirmed to include `config/` (SP01 evidence).

## Task 2 — combo_routes + effort output caps
What it is / what it means: A pure function that turns (model, tier, effort) into a full per-unit route set. Traces to R6, D2, D9.
What changes at a high level: In `routes.py` add only `combo_routes(base, model, tier, effort)` and `EFFORT_OUTPUT_CAP` (low 16000, medium 32000, high 48000, max 64000). Every route gets `provider/tier` id, key env, caching mode, temperature support and context from the model block; `max_output_tokens=min(tier max, cap)`, `timeout_s=300`, `reasoning_effort` set in `extra_params`; structured-output mode, concurrency and retries inherited from base.
Done when: snapshot tests pass for Claude (`anthropic/<tier>`, no temperature, `reasoning_effort`, `ANTHROPIC_API_KEY`, `anthropic_ephemeral`, context 1M) and Gemini (`gemini/<tier>`, Gemini caps); cap is bounded by tier max; the base routes input is not mutated (AC4 part 1).

## Task 3 — Selection request, validation, plan_units, human lock
What it is / what it means: The server becomes the single authority for which runs are allowed and how many units they make. Traces to R2, R3, R4, D1, D3, D4.
What changes at a high level: `RunRequest.presets` becomes `selection {models,tiers,efforts}` (extra=forbid). Validation yields the valid combo set and specific 422 messages; combos dropped for an unsupported effort are returned for the preview. A pure `plan_units(sessions, engines, combos, repeats)` replaces both 499 checks and the unit loop, producing `combo`/`combo_key` units and raising `RunTooLarge` with the exact message. Dataset runs (including reruns) get `human` auto-added and the response echoes final engines. Verify `has_gold` for all shipped dataset sessions; otherwise mark that unit `skipped: no_gold`.
Done when: table tests pass for valid, unknown id, tier without model, model without tier, unsupported effort, partially supported effort (dropped), empty product, 499 ok, 500 rejected with exact message, legacy `presets` body 422; a dataset body without `human` still gets human units; the gold check result is recorded in task notes (AC2, AC3 server part).

## Task 4 — Run execution on combo routes + drift guard
What it is / what it means: Units actually run on the chosen combo. Traces to R6, D2, D3.
What changes at a high level: `execute_unit` builds `LiteLLMClient(LLMConfig(routes=combo_routes(...)))` from the unit's combo, with `params["preset"]=None`. Runs store `resolved_combos` (combo_key -> litellm id/effort/caps); the drift guard compares these instead of `resolved_presets`. The legacy preset branch stays until drained [DEFERRED deletion]. SP02's unit log context (run_id, unit_id, combo_key, attempt) is added only if SP02 has landed.
Done when: tests pass that a queued unit executes with the expected routes, `resolved_combos` is stored at create, the drift guard fires when `models.yaml` changes after queueing (AC4 part 2), and a legacy preset unit still executes through the old branch.

## Task 5 — Unit retry on transient errors
What it is / what it means: A second, outer retry layer so a brief provider outage does not fail a unit. Traces to R7, D5, D6.
What changes at a high level: In `execute_unit`, wrap the engine call in at most 3 attempts inside the existing 840 s budget; sleep 5 s then 20 s with jitter via injectable `services.sleep`; no retry if remaining budget is under 120 s. Retry only when the cause-chain walk finds a transient `LLMError` (SP03's `is_transient`; local `is_retryable()` shim if SP03 is not yet in). Permanent list: `OutputInvalid`, `InputError`, `ConfigError`, `_ExecutionConfigChanged`, `LLMBadOutput`, auth/400/404. Sum usage across attempts into the single `finish_unit`; store `attempts` and `error:{code,retryable}`.
Done when: tests with a scripted fake `llm_factory` and fake `sleep` pass: 503 then success = 1 retry, done, `attempts=2`; 3x 429 = failed after 3 with all attempts' usage; `LLMBadOutput`, auth and `AllRunsFailed(cause=auth)` = 1 attempt; sibling units unaffected; under 120 s budget = no retry (AC5).

## Task 6 — Compare per combo, per-session error, legacy read path
What it is / what it means: Backend results keyed by engine x combo, with an error figure per session and old runs still readable. Traces to R8, R9 (data), R10, D7, D10.
What changes at a high level: `read_runs.build_compare` keys cells by `(engine, combo_key)` and adds per-session `cell.error` (MAE/bias per metric on that session's successful units; null when no human or no success), plus failed count and error code. `compare.aggregates` is keyed by `combo_key` and also exposes `within_1` (globals only), `n`, failed units, tokens and est. cost. Stored legacy runs derive `combo_key="preset:<name>"` with display "preset: claude (legacy)" on read, no migration; rerun of a legacy run keeps input and engines but flags the picker as empty.
Done when: read tests pass on a hand-computed fixture of 2 sessions x 3 combos (per-session error, MAE, within-1) and on a stored legacy-preset run rendering `preset:` labels in detail, compare, history and aggregates (AC6).

## Task 7 — NewRun pickers, count preview, human lock UI
What it is / what it means: The user-facing replacement of the Presets picker. Traces to R4 (UI), R5, R10, D1, D4.
What changes at a high level: `NewRun.tsx`/`api.ts` get three multi-selects (model -> tier -> effort); deselecting a model drops its tiers, the effort list is the union of selected tiers' efforts. The same `plan_units` logic runs client-side and shows "N units = S sessions x (1 human + E engines x C combos x R repeats)", a collapsible combo list and the skipped list. N > 499 disables Start with the server's exact message. Human checkbox is `checked disabled` in dataset mode; upload mode unchanged. Legacy rerun opens the picker empty with a notice. The client count and server share fixtures to prevent drift.
Done when: vitest tests pass for model deselect dropping tiers, effort union, count text matching the shared server fixture, >499 disabling Start with message, disabled-checked Human in dataset mode, and the legacy rerun notice (AC3 UI part, AC7).

## Task 8 — Compare table transpose + Summary view
What it is / what it means: Readable results at ~50 combos, and a cross-report ranking. Traces to R8 (web), R9, D7, D8.
What changes at a high level: `Runs.tsx`/`app.css` transpose Compare to rows = engine x combo (Human first), columns = metrics (value, diff vs human beneath, session error), sticky first column, horizontal scroll, failed count and code shown. New `SummaryView` tab beside Compare from `compare.aggregates`: MAE per count/global/summary, `within_1` for globals, `n`, failed units, tokens, est. cost; sortable by any column, best MAE per column highlighted; shown only when `has_human`.
Done when: vitest tests pass for the transposed table (Human first, diff and error rendered, failures shown) and Summary (sorting, best-per-column highlight, hidden without human, legacy label rendered) (AC7).

## Task 9 — Preset retirement + eval-site docs
What it is / what it means: Clean up the old preset path in eval and document the new picker. Traces to R11, R10, D10.
What changes at a high level: Run a repo-wide grep for `claude` preset references; if none remain outside eval, remove the `claude` preset from `config/staging/routes.yaml` (leave `test-*` presets and the prod file untouched). Update the picker/matrix section of `docs/reference/eval-site.md` (selection model, 499 cap, human lock, retry, Summary, legacy runs, effort caps).
Done when: the grep result is recorded; routes consistency tests (SP01) and eval backend tests still pass; prod routes diff empty; docs cover the listed items. If the grep finds other references, the preset is kept and this is noted.

## Task 10 — Owner live smoke (provider x effort)
What it is / what it means: The only step using a real API; gates enabling efforts and tunes guesses. Traces to the Risks section (max gate, caps, timeout, SDK long-request guard), AC8.
What changes at a high level: No new code unless the smoke fails. Run one unit per provider x effort (including Claude `max`) on one session, check reasoning-token usage differs by effort, confirm the 64K cap on Sonnet/Opus is accepted, and tune `EFFORT_OUTPUT_CAP`/`timeout_s` if truncation occurs. Remove or hide any unsupported effort (e.g. `max`) from `models.yaml`/picker (SP01 sign-off for the schema).
Done when: outputs recorded in task notes for every provider x effort; unsupported efforts removed; any tuned caps committed with updated tests.

## Owner steps
- Task 10 live smoke is owner-run (needs provider keys/staging); results go in the task notes.
- SP01 sign-off if any new `models.yaml` key or per-effort param mapping is needed.
