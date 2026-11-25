---
status: draft
summary: Give the one prod run pipeline an internal-only `is_eval` path (eval fields on RunDoc, engine + route override, eval-mode guard, caps bypass, public models reject unknown fields) so eval can reuse it; prod behaviour unchanged. Agents build and test offline only (no apply, no deploy, no live LLM/STT runs); the owner runs the first eval.
date: 2026-11-25
---
# PRD: SP04 Prod run path gets `is_eval`

Repo/branch: Onolys/iaudit / `session-report-ux` · Depends on: none (Phase 1; builds on SP01's pinned RunDoc, already on this branch) · Owns: `api/src/onolys_api/{repo/{models,base,firestore,fake}.py, routes/runs.py (begin_run split), routes/{sessions,speakers,rating,transcript}.py (request models only), jobs/{run,first_run}.py, adapters/real.py, engines.py, config.py (EVAL_MODE only)}`, `api/pyproject.toml` + `api/Dockerfile` (add `onolys-oneshot`), `api/openapi.json` + `docs/contracts/public/` (regenerated) · SP03 owns infra and the `ENV=eval` value; SP05 owns eval API, sessions, scheduler and is the only caller of `is_eval`.

## TL;DR
Eval units must run through the prod run handler, but today the worker can only run `settings.prod_engine` with a preset's routes [verified: `adapters/real.py:144-147`]. This SP adds (1) an optional `eval` block on `RunDoc`, (2) an internal `create_run(..., is_eval=...)` that refuses unless `EVAL_MODE=true`, (3) worker support for `engine` + `route_override` only when that block exists, (4) caps bypass for eval runs, (5) `extra="forbid"` on public request bodies (all bodies if clients stay clean, else `RunRequest`/`CreateSessionRequest`). Eval runs use `n_runs=1`; drift-failed runs stay failed; the worker adds no retry logic of its own (SP05 owns the retry policy, see R4a). No public API shape change; prod runs are byte-for-byte what they are today.

## Problem
| Gap | Evidence |
|---|---|
| Run creation is inline in the route (`begin_run`) and the repo txns (`start_run`/`start_first_run`); no internal entry, no eval fields | [verified: `routes/runs.py:148-235`, `firestore.py:1094,1182`] |
| A second run on a session is blocked: `has_final_report` -> 409 `rating_final`; `RERUN_STATES=("awaiting_input",)`; `failed` is terminal for users | [verified: `routes/runs.py:52,165`, `jobs/machine.py:90`] |
| Worker engine = `prod_engine`, routes = preset only; registry holds only `MitiEngine`; api image/pyproject has no `onolys-oneshot` | [verified: `engines.py:11`, `api/pyproject.toml:7-8`, `api/Dockerfile:15-21`] |
| Public request models have no `ConfigDict`; unknown fields are silently ignored, not rejected | [verified: `grep ConfigDict|forbid` finds none in `api/src`; `RunRequest` `routes/runs.py:57`] |
| Start txns charge caps and the per-user concurrent limit (`max_active_runs`), which would throttle eval | [verified: `limits.py:106-116`, `firestore.py:1148`] |
| First-run gate auto-starts a run when transcript + speaker + rating exist; in eval it would add an unwanted default run | [verified: `jobs/first_run.py:31-47`, callers in `routes/{speakers,rating,transcript}.py`] |

## Goals / Non-Goals
**Goals:** eval runs are ordinary RunDocs the one worker executes with a chosen engine/route; flag unreachable from the public API; old RunDocs and prod runs unchanged; provenance recorded.
**Non-goals:** eval API, sessions/transcript creation, scheduler, grouping doc, delete (SP05); Terraform, `ENV=eval`, queue, bucket (SP03); compare reads (SP06); web changes; changing report schemas or engine output; migrating old data.

## Requirements
**R1 Eval block on RunDoc.** `RunDoc.eval: EvalRunInfo | None = None` (absent on prod runs). `EvalRunInfo`: `eval_run_id`, `combo_key`, `repeat`, `engine` (`"miti"` or `"oneshot:<variant>"`, eval's current ids), `route_override: {provider, model, tier, effort} | None`, `resolved_route` (snapshot: litellm_id, effort, max_output_tokens, context_tokens, supports_temperature, caching_mode, as eval's `_combo_snapshot`), `engine_version`. One nested field (one presence test, one thing to keep out of public views) holding exactly the locked field set. Written only in the create txn (`txn.create`); no code path updates it (write-once). Old docs parse: field defaults None, `Doc` ignores nothing it needs [verified: `models.py:41`, `RunDoc` plain `BaseModel`].
**R2 Internal creation.** Extract the body of `begin_run` into `create_run(app, uid, sid, spec, *, is_eval=False, eval_spec=None, retry_max=None)` used by `POST /runs`, retry and SP05. `is_eval=True` requires `settings.eval_mode`, else raise `EvalDisabled` (internal exception, never a public code; logged without values). `is_eval=False` with an `eval_spec` is a programming error (raise). Public routes always pass `is_eval=False`.
**R3 Repo txn.** `start_run` gains `eval: EvalRunInfo | None = None`; when set it: (a) accepts `report_ready` and `failed` in `allowed_states` (create_run passes them; the route's `has_final_report` guard is skipped for eval), (b) skips `decide_start` entirely (no day cap, no concurrent check), (c) writes `counted=False`, no `usage` write, (d) writes the block. All other bookkeeping (state `running`, `active_runs`, release, `first_run_id`) unchanged, so release/sweep code needs no eval branch. `fake.py` mirrors. SP01 pins (speaker, goal, sha, language, span) are copied as today; transcript sha mismatch -> `not_ready` as today.
**R4a Retry and failure policy (owned by SP05; this SP adds nothing).** Owner 2026-11-25: an internal error gets 1 retry; rate-limit/overload (429/529) is handled by backoff; a run's failure never affects other runs; 5 consecutive failed runs for one provider skip that provider for the rest of that eval run. All of this is scheduler logic in SP05 (new RunDocs per attempt); the worker/`start_run` here only runs one RunDoc and keeps `failed` terminal. SP05 depends on the LLM layer already handling rate limits: [verified: `engines/core/src/onolys_engine_core/llm/litellm_client.py:147-148,255-259,311,352-375`] the client sets litellm `num_retries=0` and does its own retrying: a 429/529 (`_is_rate_limit`) is re-sent in `_once_rate_limited` with exponential backoff `route.backoff_s * 2**waits` (jittered, honours `retry-after`) until the request deadline (or one route timeout) and does NOT consume `route.max_retries` (default 3, `routes.py:68`); timeouts/bad output/unavailable use `attempts = 1 + route.max_retries` with `backoff_s` doubling. So rate-limit backoff comes from prod's engine layer for free; SP05 adds the run-level 1 retry for internal errors only, and must not retry drift failures.

**R4 Worker.** `_evaluate` adds `engine` and `route_override` to `params` only when `run_doc.eval` is set; with no block `params` is identical to today (test asserts equality). Block present while `EVAL_MODE` is off -> `PermanentError("internal_error")`, log `reason=eval_mode_off`. Eval-only drift guard: `run_doc.code_version != settings.git_sha` or engine/route snapshot differs from what the worker rebuilds -> `internal_error`, log `reason=eval_config_drift` (carries over eval's `_ExecutionConfigChanged`). A run failed by drift stays `failed`: it is NOT retried or re-created (SP05's single internal-error retry excludes `eval_config_drift` and `eval_mode_off`; rate-limit/overload is already backed off inside the LLM client, R4a).
**R5 Engine + route mapping.** `engines.py` gains `resolve_engine(settings, engine_id)`: `miti` -> registry; `oneshot:<variant>` -> `OneshotEngine(config=variant)` only when `eval_mode` (eval's `_bound_engines` moves here; SP05 deletes the copy). `RealEvaluation.run` ignores `engine`/`route_override` unless `settings.eval_mode`; with an override it builds routes as `combo_routes(resolve_preset(preset)[0], model, tier, effort)` (core, shared with eval today: `eval/backend runs.py:596-600`) with `model` from `models.yaml` via `load_models(models_path(...))` (`config/` ships in the image [verified: `api/Dockerfile:32`]). Add `config` to `_ENGINE_PARAMS` for oneshot. Unknown engine/model/tier/effort -> `InputError` (-> `internal_error`).
**R6 Settings.** `Settings.eval_mode: bool = False`, env `EVAL_MODE`, strict `true|false` parse. Default off everywhere; only SP03's eval deployment sets it. In eval mode `maybe_start_first_run` returns immediately (sessions are started only by SP05).
**R7 Public rejection.** All public request bodies get `model_config = ConfigDict(extra="forbid")`: `RunRequest`, `CreateSessionRequest`, `ConfirmRequest`, `RatingRequest` and the rest under `routes/`. Regenerate `api/openapi.json` and `docs/contracts/public/` (`python -m onolys_api.contracts`); assert no `eval`, `engine`, `route_override`, `combo_key`, `eval_run_id` appears in either, and `RunView`/`_view` (explicit field list, `routes/runs.py:116-122`) never serialises `eval`. Provenance lives in `RunDoc.eval`, not `run_info` (which `RunView` exposes).
**R7a Names / auth.** [RESOLVED: owner 2026-11-25 — eval uses the prod app's login, one copy] SP03 deletes the `eval/auth` package (`onolys_admin_auth`) and all `ADMIN_*` env; eval backend authenticates through the prod api auth (`onolys_api.auth`) plus an `EVAL_ALLOWED_EMAILS` allowlist [see SP03 R14]. This SP touches none of that; it only adds `EVAL_MODE`. No `ADMIN_*`, `onolys_admin_auth` or `EVAL_AUTH*` name appears in this SP's code or tests (current PRD text had none to change [verified: grep of this file]).

**R8 Packaging.** `onolys-oneshot` added to `api` deps and Dockerfile source/manifest (same image for both deployments); registered/used only under `eval_mode`.

## Architecture
```
SP05 eval API (allowlist) --create_run(is_eval=True, eval_spec)--> [EVAL_MODE guard]
public POST /runs, /retry --create_run(is_eval=False)-----------> repo.start_run(eval=None|block)
                                                                       |
Cloud Task(run) -> jobs/run.py::_evaluate --params(+engine,route_override iff run_doc.eval)--> RealEvaluation
                         --> resolve_engine / combo_routes --> run_validated(engine's own schema) --> ReportDoc
```
Report validation: the worker validates against the chosen engine's own `output_schema()` inside `run_validated`; `RealEvaluation.validates_output=True` skips the bridge [verified: `adapters/validated.py:35-45`]. The MITI-specific schema in `validated.py` applies only to fake adapters. Stored `ReportDoc.report` is an untyped dict, and `schema_version` falls back to `""` (oneshot schema has none) [verified: `run.py:266-269`, `oneshot .../schema.json`]. So miti and `oneshot:miti` (the only two engines eval registers, `services.py:registry`) both pass; no prod schema change. `miti_lean` is a scorer in `eval/core`, not an engine [verified: `adapters.py:13`]. Missing artifacts (`code`, `tips`) are already skipped [verified: `run.py:253-256`].

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| 1 | Where eval fields live | One nested `RunDoc.eval` | Six flat optional fields | One presence check; trivial to keep out of views; same locked field set |
| 2 | Caps for eval | Bypass `decide_start`, `counted=False`, keep `active_runs` bookkeeping | Huge `EVAL_CAP_DAY`/`MAX_ACTIVE_RUNS` in config only; skip bookkeeping | Config-only throttles by accident if mis-set; skipping bookkeeping needs eval branches in release/sweep |
| 3 | Flag security | Function-level `eval_mode` check + worker re-check + RealEvaluation re-check | Route-level check only | Three independent points; no public model carries the fields (R7) |
| 4 | Unknown fields | `extra="forbid"` on public bodies | Keep ignoring | Locked by proposal decision 2; ignoring already blocks setting but hides client typos |
| 5 | Eval re-run states | `is_eval` allows `report_ready`/`failed`, skips `rating_final` guard | Make public rules looser | Public rules (final rating, failure terminal) stay untouched |
| 6 | First-run gate in eval | Off when `eval_mode` | Let it fire | Gate would create an extra default-preset run |
| 7 | Provenance | `resolved_route` + `engine_version` on block, `code_version` on RunDoc | Put in `run_info` | `run_info` is public; drift guard needs the snapshot at creation |
| 8 | Session/Transcript eval fields (`dataset_id`, `dataset_session_id`) | SP05 adds them when it creates sessions; SP04 adds none | Add here | Nothing in the run path reads them; keeps SP04 diff minimal. `models.py` edits are additive and in different classes |
| 10 | Retries | none in this SP; LLM client already backs off 429/529; SP05 does 1 internal-error retry, provider skip after 5 consecutive failures | worker-level retry; new retry layer | prod engine layer already covers rate limits [verified: R4a]; keeps the worker diff minimal |
| 9 | Alerts/metrics | No code change; eval alerts off via SP03's `alerts_enabled` | Tag/skip eval in code | Alerts are per-environment [verified: `infra/modules/environment/alerts.tf:3`]; separate database already isolates |

## Risks / Open Questions
- [RESOLVED: owner — default (forbid on all bodies if clean, else only RunRequest/CreateSessionRequest)] `extra="forbid"` vs existing clients. Check: grep `web/` generated client + `test_public_contract`; forbid on all bodies if clean, otherwise only `RunRequest` and `CreateSessionRequest` plus a test that extras on the others are dropped.
- [RESOLVED: owner 2026-11-25 — keep strict guard; drift-failed runs stay failed, are not retried or re-created; SP05 retry policy: internal error 1 retry (never drift), rate-limit/overload backoff (already in the LLM client), failures never affect other runs, 5 consecutive failed runs per provider skip it for the rest of the eval run] A deploy during a long eval run fails its in-flight runs (`code_version` changes); the owner re-runs by creating a new eval run.
- [RESOLVED: owner 2026-11-25 — `n_runs=1`, no re-attempt inside a run; repeats are separate runs] The worker passes `n_runs=1` for eval runs.
- [RESOLVED: owner 2026-11-25 — default: SP05 sets `session.preset` to the eval `DEFAULT_PRESET`; `route_override` applies on top]
- [RESOLVED: owner 2026-11-25 — default: no index here] SP05's grouping doc stores RunDoc ids, so no collection-group index on `eval.eval_run_id`.
- [RESOLVED: no prod schema change] Which engines pass validation today: see Architecture.
- [RESOLVED: SP03] `config.py` `ENVS` lacks `eval` [verified: `config.py:10`]; SP03 adds it, SP04 only adds `eval_mode`.
- [RESOLVED: owner 2026-11-25 — default: deferred to SP07] Web rendering of non-MITI reports.
- [RESOLVED: owner 2026-11-25 — no live runs: agents build and test offline only; owner runs the first eval]

## Acceptance Criteria
- Prod path with `EVAL_MODE` unset: `create_run(is_eval=False)` writes a RunDoc identical to today's (no `eval` key); worker `params` equal today's; caps and `rating_final` behaviour unchanged (existing `test_start_run`, `test_run_input_snapshot`, `test_first_run`, `test_retry` pass untouched).
- `is_eval=True` with `EVAL_MODE` off raises `EvalDisabled`, writes nothing; with it on, writes the block once, skips caps, allows a run on a `report_ready` and on a `failed` session.
- Worker: block + eval mode off -> `internal_error`, `reason=eval_mode_off`; override changes the routes passed to the engine (fake LLM factory, offline); `oneshot:miti` run stores a report; drift -> `eval_config_drift`.
- Public: `POST /runs` with `engine`/`route_override`/`eval` -> 422; regenerated OpenAPI and `public/` schemas contain no eval names; `GET /runs` never returns `eval`.
- A RunDoc stored without `eval` loads; a doc with `eval` round-trips; `eval` is not updated by `update_run` callers.
- Eval mode: transcript/speaker/rating routes do not start a first run.
- Drift-failed eval run stays `failed`; nothing in this SP re-creates it. Eval runs pass `n_runs=1`. No retry code is added here (retry policy is SP05's, R4a); no `ADMIN_*`/`onolys_admin_auth`/`EVAL_AUTH*` name in this SP's diff.
- All tests offline: fake repo, fake LLM/`llm_factory`, no keys, no live runs; Firestore-emulator contract test for `start_run` only where the existing suite already runs it.
