---
status: draft
summary: 8 tasks giving the prod run pipeline an internal-only is_eval path (flag, RunDoc eval block, create_run, engine/route override, worker guards, public extra=forbid), offline tests only.
date: 2026-11-25
---
# Tasks: SP04 Prod run path gets `is_eval`
Source of truth: docs/agent_files/session-report-ux-20261124-1738/04-eval-run-path/PRD.md. Agents build and run offline tests only (fake repo, fake LLM factory, no keys, no deploy, no live runs). Prod behaviour with `EVAL_MODE` unset must stay identical. Retry/breaker/scheduler, eval API, infra and `ENV=eval` belong to SP05/SP03 and are not touched.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | EVAL_MODE setting, oneshot packaging, CI dependency map | none | done |
| 2 | `EvalRunInfo` block on `RunDoc` | none | done |
| 3 | `start_run` eval variant (repo + fake) | 2 | done |
| 4 | `create_run` internal entry + guard | 1, 3 | done |
| 5 | Engine and route resolution | 1 | done |
| 6 | Worker eval params, guards, first-run gate off | 2, 4, 5 | done |
| 7 | Public bodies reject unknown fields; contracts regenerated | 2 | done |
| 8 | Prod-unchanged regression and CI check | 1-7 | done |

## Task 1 — EVAL_MODE setting, oneshot packaging, CI dependency map
What it is / what it means: A strict-parsed `EVAL_MODE` flag, default off, is the single switch for everything eval. `onolys-oneshot` must ship in the api image so `oneshot:<variant>` engines can run (PRD R6, R8; Decision 3).
What changes at a high level: add `eval_mode` to settings (strict `true|false`, only `EVAL_MODE` changes in `config.py`); add `onolys-oneshot` to api dependencies and Dockerfile source/manifest; update the CI changes map (`scripts/ci/changes.sh` DEPS for `api`) and its tests so oneshot changes trigger the api job and the DEPS-vs-pyproject check passes. Lockfile refreshed.
Done when: tests show default False, `true`/`false` parse, other values rejected; `test_changes_deps.py` and `test_changes.sh` pass; `uv sync --frozen` for api resolves; api image build config lists oneshot.

## Task 2 — `EvalRunInfo` block on `RunDoc`
What it is / what it means: Provenance lives in one optional nested field, kept out of public views (R1; Decisions 1, 7).
What changes at a high level: add `EvalRunInfo` (eval_run_id, combo_key, repeat, engine, route_override, resolved_route snapshot, engine_version) and `RunDoc.eval: EvalRunInfo | None = None` in `models.py` (additive). No update path touches it.
Done when: model tests show a RunDoc without `eval` loads, a doc with `eval` round-trips, and `update_run` callers cannot change it (write-once).

## Task 3 — `start_run` eval variant (repo + fake)
What it is / what it means: The create txn can start an eval run on any session state, outside caps, while all other bookkeeping stays as today (R3; Decisions 2, 5).
What changes at a high level: `start_run` takes `eval=`; when set it allows `report_ready`/`failed`, skips `decide_start` (no day cap/concurrent check), writes `counted=False` and no usage, writes the block via `txn.create`. State `running`, `active_runs`, release and `first_run_id` unchanged. `fake.py` mirrors. SP01 pins copied as today; sha mismatch still `not_ready`.
Done when: fake-repo tests cover eval start on `report_ready` and `failed`, no cap/usage effect, block written once, `active_runs` released normally; non-eval path tests (`test_start_run`, `test_run_input_snapshot`) pass untouched. Emulator test for `start_run` only if the existing suite already has one.

## Task 4 — `create_run` internal entry + guard
What it is / what it means: The one place runs are created, usable by public routes (always `is_eval=False`) and later SP05 (R2; Decision 3).
What changes at a high level: extract `begin_run` body into `create_run(app, uid, sid, spec, *, is_eval=False, eval_spec=None, retry_max=None)` in `routes/runs.py`; `POST /runs` and retry call it. `is_eval=True` without `eval_mode` raises internal `EvalDisabled` (logged without values); `eval_spec` with `is_eval=False` raises; for eval the `has_final_report` guard is skipped and `report_ready`/`failed` are passed as allowed states.
Done when: tests show EvalDisabled writes nothing, eval-on writes block and starts from `report_ready`/`failed`, misuse raises, and `test_retry` plus existing run-route tests pass unchanged.

## Task 5 — Engine and route resolution
What it is / what it means: The worker's engine and routes can be chosen per run, only in eval mode (R5; Decision 3).
What changes at a high level: add `resolve_engine(settings, engine_id)` in `engines.py` (`miti` from registry; `oneshot:<variant>` -> `OneshotEngine` only under eval_mode); `RealEvaluation.run` ignores `engine`/`route_override` unless eval_mode, else builds routes via `combo_routes` on the preset with the model from `models.yaml`; add `config` to oneshot engine params. Unknown engine/model/tier/effort -> `InputError`.
Done when: offline tests (fake LLM factory) show override changes routes passed to the engine, `oneshot:miti` stores a report, params ignored with eval_mode off, unknown ids error.

## Task 6 — Worker eval params, guards, first-run gate off
What it is / what it means: `_evaluate` honours the eval block, fails safe on misconfiguration, and eval sessions never auto-start a default run (R4, R6; Decisions 3, 6; resolved: `n_runs=1`, drift-failed stays failed).
What changes at a high level: add `engine`, `route_override`, `n_runs=1` to params only when `run_doc.eval` exists. Block with eval_mode off -> `PermanentError("internal_error")`, `reason=eval_mode_off`. Eval-only drift guard (`code_version` vs `git_sha`, rebuilt engine/route snapshot) -> `internal_error`, `reason=eval_config_drift`. `maybe_start_first_run` returns immediately in eval mode. No retry code added.
Done when: tests assert params identical to today without a block, override reaches RealEvaluation, eval_mode_off and drift reasons logged, drift run stays `failed`, and transcript/speaker/rating routes start no first run in eval mode; `test_first_run` passes untouched.

## Task 7 — Public bodies reject unknown fields; contracts regenerated
What it is / what it means: Eval fields must be unreachable from the public API; unknown fields now 422 (R7; Decision 4; resolved: forbid on all bodies if clients are clean, else `RunRequest`/`CreateSessionRequest` only).
What changes at a high level: grep the `web/` generated client and `test_public_contract` for extra-field usage; apply `extra="forbid"` to all public request models under `routes/` (or the two-model fallback plus a test that extras elsewhere are dropped). Regenerate `api/openapi.json` and `docs/contracts/public/`. Confirm `RunView` never serialises `eval`.
Done when: tests show `POST /runs` with `engine`/`route_override`/`eval` returns 422, regenerated schemas contain none of `eval`, `engine`, `route_override`, `combo_key`, `eval_run_id`, and `GET /runs` never returns `eval`; the CI contracts-up-to-date diff is clean.

## Task 8 — Prod-unchanged regression and CI check
What it is / what it means: Proof that the shared path is unchanged for prod and CI covers every changed package (Acceptance Criteria).
What changes at a high level: no new features. Run impacted tests (api unit, oneshot, any touched suites), ruff, openapi/contracts diff check; confirm `.github/workflows/ci.yml` jobs (`api-unit`, `api-emulator`, oneshot) are triggered by the changed paths; confirm no `ADMIN_*`, `onolys_admin_auth` or `EVAL_AUTH*` name in the diff.
Done when: all offline, no keys, existing `test_start_run`, `test_run_input_snapshot`, `test_first_run`, `test_retry` pass untouched; a prod-path test shows no `eval` key on the RunDoc and identical worker params; grep of the diff for the forbidden names is empty.

Owner steps (not tasks): run the first real eval (live LLM/STT) after SP03 and SP05 land; deploy with `EVAL_MODE=true` only in the eval deployment; no deploy by agents.
