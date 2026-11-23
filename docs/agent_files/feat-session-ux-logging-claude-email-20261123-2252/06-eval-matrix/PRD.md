---
status: draft
summary: Eval runs pick model -> tier -> effort (all multi-select, validated cartesian product x engines x repeats + human unit), built into per-unit routes from config/models.yaml, retried up to 3x for transient errors, with a per-report combo table and a cross-report Summary view.
date: 2026-11-23
---
# PRD: SP06 Eval model -> tier -> effort matrix

Repo/branch: Onolys/onolys (local `iaudit`) / `feat/session-ux-logging-claude-email` · Depends on: SP01 (`config/models.yaml`, `llm/models.py`; Phase 2), SP03 (`is_transient`, soft: local shim until it lands) · Owns: `eval/backend/src/onolys_eval_backend/{runs.py,read_runs.py,catalog.py,services.py}`, `eval/backend/tests/*`, `eval/web/src/{NewRun.tsx,Runs.tsx,api.ts,app.css}` + tests, `engines/core/src/onolys_engine_core/llm/routes.py` (add `combo_routes` only), `docs/reference/eval-site.md` (picker/matrix section)

## TL;DR
Replace the eval "Presets" picker with three multi-selects: **model** (Gemini/Claude) -> **tier** (e.g. `claude-sonnet-5-5`) -> **effort**. The server expands engines x valid (model,tier,effort) combos x repeats, plus one human unit per dataset session, and refuses runs over 499 units. Each combo becomes a per-unit route set (LiteLLM id, `reasoning_effort`, caps from `models.yaml`). Units retry up to 3 times on transient errors only. Results: a combo-per-row table per report and a new Summary view (MAE, within-1) across reports.

## Problem
- Eval varies models only through named presets (`RunRequest.presets`, `runs.py:79`; `/v1/options` returns presets, `catalog.py:73-110`), so tier/effort pairs need a YAML edit per experiment. [verified]
- Units are `engines x presets x repeats` (`runs.py:284-300`); the 499 check exists twice (`:248-252`, `:259-267`) and failure is a generic 422. [verified]
- Human is an ordinary checkbox (`NewRun.tsx:104,173`; default-ticked via `catalog.py:108`); nothing locks it client- or server-side (the brief's `NewRun.tsx:113` is the Start-gating line, not a toggle). [verified]
- `execute_unit` (`runs.py:451-555`) has no unit retry: any exception becomes `failed` / `engine_failed`. The LLM client already retries inside one call (`max_retries`, 429 backoff; `litellm_client.py:~280-335`); this is a second, outer layer. [verified]
- CompareView puts metrics in rows and one column group per engine x preset (`Runs.tsx:15-32`, `read_runs.py:89-170`); the MAE column is across sessions only. Cross-session comparison exists only as `compare.aggregates`, unused as a view. [verified]

## Goals / Non-Goals
**Goals:** valid-combo picker; server-authoritative expansion/validation; humans always compared on datasets; unit retry; readable per-report and cross-report results; old runs still open; tests with no live API.
**Non-goals:** cross-run comparison; transcript/STT changes (reused as-is); editing models.yaml from the UI; per-stage model mixing (a combo applies to all LLM routes of the unit); the main-app failure UX (SP03); cost caps.

## Requirements
**R1 Options.** `GET /v1/options` (exists, `catalog.py:73`) returns `models: [{id,label,context_tokens,max_output_tokens,tiers:[{id,efforts,default_effort}]}]` from SP01's loader (`services.models`, loaded from `MODELS_FILE`/`config/models.yaml`; eval image already copies `config/`, SP01 evidence). `presets` is removed from the response. `defaults.<mode>.selection` = the combo of the resolved default `mid` route (tier + `reasoning_effort`), labelled "(prod)"; no hard-coded names.
**R2 Request.** `RunRequest.presets` -> `selection: {models:[str], tiers:[str], efforts:[str]}` (extra=forbid, so legacy `presets` bodies 422). Valid combos = `{(m,t,e) : t in tiers, t belongs to m in models, e in selection.efforts, e in tier.efforts}`. 422 with a specific message when: unknown id; a selected model with no selected tier; a selected tier whose model is not selected; an effort allowed by no selected tier; empty product while any non-human engine is selected. Combos skipped because a tier lacks an effort are silently dropped (returned in the preview, see R5). Repeats stay 1|3.
**R3 Units.** One pure function `plan_units(sessions, engines, combos, repeats)` replaces both count checks and the loop at `runs.py:284-300`. Unit = `{session_id, engine, combo:{model,tier,effort}, combo_key:"claude/claude-sonnet-5-5/low", repeat, ...}`; human unit has no combo. Count = sessions x (1 human + non-human engines x combos x repeats). `> 499` raises `RunTooLarge(count)` -> 422 body `"Run has N units; the maximum is 499. Remove sessions, combos or repeats."`.
**R4 Human lock.** Dataset input: server adds `human` to `engines` when absent (also on rerun of a dataset run) and the response echoes final engines. UI: Human checkbox `checked disabled` in dataset mode. Upload mode: unchanged (human only with gold). [OPEN] dataset sessions without gold: confirm `has_gold` is always true for shipped datasets; else mark that unit `skipped: no_gold`.
**R5 Count preview.** NewRun computes the same function client-side from `/v1/options` and shows "N units = S sessions x (1 human + E engines x C combos x R repeats)", a collapsible combo list, and "skipped: gemini-4-carbon has no xhigh". N > 499: Start disabled, inline message identical to R3. Server stays authoritative.
**R6 Routing.** `routes.py: combo_routes(base: dict[str,Route], model, tier, effort) -> dict[str,Route]` (pure). `base` = `resolve_preset(default_preset)` routes. For every route (cheap/mid/strong/miti_*/tips/oneshot): `litellm_id=f"{provider}/{tier}"`, `api_key_env`, `caching_mode`, `supports_temperature` and `context_tokens` from the model block (context = model max, no picker); `max_output_tokens=min(tier max, EFFORT_OUTPUT_CAP[effort])` with initial caps low 16000, medium 32000, high 48000, xhigh/max 64000 (thinking tokens count against it); `timeout_s=300`; `extra_params` = base minus `reasoning_effort`, plus `reasoning_effort=<effort>`; `structured_output_mode`, concurrency and retries inherited. Executed via the existing `LiteLLMClient(LLMConfig(routes=routes))` (`runs.py:499`); engines read `client.routes` (`miti/run.py:220`, `oneshot/engine.py:26`), so `params["preset"]` becomes `None`. Run stores `resolved_combos` (combo_key -> route litellm_id/effort/caps); the drift guard at `runs.py:491-497` compares these instead of `resolved_presets`.
**R7 Retry.** In `execute_unit`, wrap the engine call in <=3 attempts sharing the existing 840 s budget; sleep 5 s then 20 s (x0.5-1.0 jitter, `services.sleep` injectable); no retry if remaining budget < 120 s. Retry only when `is_retryable(exc)`: walk `__cause__/__context__` (miti wraps the real error in `AllRunsFailed`, `run.py:326`); retryable = `LLMTimeout`, `LLMRateLimited`, `LLMUnavailable` without `no_retry` (5xx/overload). Permanent: `LLMBadOutput` (incl. truncation), `OutputInvalid`, `InputError`, `ConfigError`, `_ExecutionConfigChanged`, auth/400/404 provider errors. Usage from failed attempts is summed into the one `finish_unit`. Unit stores `attempts` and `error:{code,retryable}` with code in `llm_unavailable|llm_rate_limited|llm_timeout|output_invalid|engine_failed`. Other units are untouched (each is its own task). Classification reuses SP03's `onolys_engine_core.llm.errors.is_transient(exc: LLMError)` (reads SP02's `http_status`/`error_type`; no api import) on each `LLMError` found in the cause-chain walk; `runs.py` owns only the walk and the `OutputInvalid`/`InputError`/`ConfigError`/`_ExecutionConfigChanged` permanent list. If SP06 lands before SP03, a thin local `is_retryable()` applies the same rule and is replaced by the import.
**R8 Compare (per report).** `build_compare` keys cells by `(engine, combo_key)` and adds per-session `cell.error` (MAE/bias per metric via `compare()` on that session's successful units; `error: null` if no human or no success). Failures show `failed` count + error code. Web: table transposed to **rows = engine x combo, columns = metrics** (value, then diff vs human beneath it, then the session error); sticky first column, horizontal scroll (up to ~50 combos). Human is the first row.
**R9 Summary view.** New `SummaryView` tab beside Compare, from existing `compare.aggregates` (renamed key `combo_key`): rows = engine x combo; columns = MAE per count/global/summary, `within_1` for the 4 globals (only globals have it, `metrics.py:106-121`), `n` sessions, failed units, tokens and est. cost per combo. Sortable by any column; best MAE per column highlighted. Only shown when `has_human`.
**R10 Legacy runs.** Stored runs have `presets`/unit `preset` and no `combo`. Read path derives `combo_key = "preset:<name>"` (display "preset: claude (legacy)"), so detail, compare, history and Summary work unchanged. Rerun of a legacy run keeps saved input and engines but opens the picker empty with a notice; legacy runs cannot be re-created. `execute_unit` keeps the preset branch until in-flight legacy units drain, then it is deleted [DEFERRED].
**R11 Preset retirement (eval only).** Remove `claude` preset from `config/staging/routes.yaml` once `grep` shows no reference outside eval; `test-*` presets and prod file untouched.
**R12 Tests (no live API).** See Acceptance.

## Architecture
```
models.yaml ─► models.py ─► /v1/options ─► NewRun pickers ──► POST /v1/runs {selection}
                              │                                    │ validate + plan_units (≤499)
                              └─► combo_routes(base,model,tier,effort)   ▼
Firestore unit{engine,combo_key,repeat} ─► Cloud Task ─► execute_unit
   attempt loop(≤3, transient only) ─► LiteLLMClient(routes=combo_routes) ─► engine ─► Scores
read_runs.build_compare ─► cells[(engine,combo_key)] + per-session error + aggregates ─► Compare / Summary
```
Shared files: `config/models.yaml` + `llm/models.py` (SP01 owns schema; SP06 only reads; any new key needs SP01 sign-off), `routes.py` (SP01 edits `_apply_env`; SP06 adds only `combo_routes`/`EFFORT_OUTPUT_CAP`), error classification (SP03), unit log context run_id/unit_id/combo_key/attempt (SP02).

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | Request shape | Three independent lists, server filters to valid combos | Explicit combo list from client | Matches the locked multi-select UX; one validation path |
| D2 | Combo scope | One combo applies to all LLM routes of a unit | Per-stage mixes | Keeps cell = one comparable config |
| D3 | Unit identity | `combo_key` string `model/tier/effort` + structured `combo` | Hash id | Human-readable in table, Firestore, logs |
| D4 | Human lock | Server auto-adds `human` for datasets | Reject requests lacking it | Rerun of old runs works; response echoes result |
| D5 | Retry location | In-process attempt loop in `execute_unit`, shared 840 s budget | Re-enqueue with `delay_seconds` (queue supports it, `queue.py:13`) | No state-machine changes; failed-attempt cost lands in one finish. Fallback if timeouts dominate |
| D6 | Retry classification | Walk cause chain, transient classes only | Retry all non-validation errors | Avoids paying for deterministic failures (brief, retry only where it can succeed) |
| D7 | Summary data | Reuse `compare.aggregates` | New endpoint / cross-run store | Already computed on read; cross-run deferred |
| D8 | Table orientation | Combos as rows, metrics as columns | Keep metrics rows | ~50 combos unreadable as columns |
| D9 | Output cap by effort | Table in code, capped by tier max | Always tier max (128K) | Bounds cost/latency; thinking needs headroom |
| D10 | Legacy runs | Derive `preset:<name>` combo keys on read; no migration | Backfill Firestore | Read-only, no data risk |

## Risks / Open Questions
- [OPEN] LiteLLM may not map `xhigh`/`max` (Claude) or `xhigh` (Gemini) from `reasoning_effort` (SP01 open item). The client sends `drop_params: True` (`litellm_client.py:~196`), so an unsupported value would be silently dropped and the unit mislabeled. Gate: one live smoke per provider x effort before enabling it in the picker, checking reasoning-token usage differs; unsupported efforts are removed from `models.yaml` (or mapped via a per-effort param table, needs SP01 sign-off).
- [OPEN] `EFFORT_OUTPUT_CAP` and `timeout_s=300` are initial guesses; truncation (`finish_reason=length` -> `LLMBadOutput`, permanent) at high effort is the likely first failure. Tune after smoke.
- [OPEN] Anthropic non-streaming with large `max_tokens` may be rejected by the SDK's long-request guard; confirm with the 64K cap on Sonnet/Opus.
- [OPEN] Do all shipped dataset sessions have gold (R4)?
- [RESOLVED: aligned with SP03 — retry predicate is `is_transient` from engine-core (SP03 R2/D8), not a SP06-local rule; 400/401/403/404 permanent, 408/429/5xx/529 transient, so 429 and overload retry, auth/404 do not.]
- Risk: client/server count drift; mitigated by shared fixtures in tests. Risk: 499 cap blocks big sweeps (e.g. 20 sessions x 25 combos) - user splits runs. [RESOLVED: Claude default - no auto-split, per brief].
- [DEFERRED] Cross-run Summary; re-enqueue retry (D5); deletion of legacy preset branch; cost-per-combo ranking beyond the Summary column.

## Acceptance Criteria
1. `/v1/options` returns models->tiers->efforts matching `models.yaml`; no `presets`; default combo equals the resolved `mid` route.
2. Request validation table-tested: valid, unknown id, tier without selected model, model without tier, effort unsupported by every tier, partially supported effort (dropped), empty product, 499 ok / 500 rejected with the exact message.
3. Dataset run without `human` in body still gets human units; UI checkbox is disabled-checked.
4. `combo_routes` snapshot: Claude -> `anthropic/<tier>`, no temperature, `reasoning_effort=<e>`, `ANTHROPIC_API_KEY`, `anthropic_ephemeral`, context 1M; Gemini -> `gemini/<tier>`, Gemini caps; drift guard fires when `models.yaml` changes after queueing.
5. Retry with a scripted fake `llm_factory` + fake `sleep`: 503 then success = 1 retry, done, `attempts=2`; 3x 429 = failed after 3 with usage of all attempts; `LLMBadOutput`/auth/`AllRunsFailed(cause=auth)` = 1 attempt; sibling units unaffected; <120 s budget = no retry.
6. Compare/Summary read tests: new run with 2 sessions x 3 combos yields per-session `error` and correct MAE/within-1 (hand-computed fixture); a stored legacy-preset run still renders with `preset:` labels.
7. Web (vitest): model deselect drops its tiers; effort list = union of selected tiers' efforts; count text matches server fixture; >499 disables Start with message; legacy rerun shows notice; Summary sorts and highlights best.
8. Manual live smoke (owner-run, not CI): one unit per provider x effort on one session; outputs recorded in the task notes.
