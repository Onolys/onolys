---
status: approved
summary: api swaps every import to `onolys_miti`, narrows Stage to code/tips/assemble, stops passing a rating or coded span to the engine (rating endpoints stay), renames paudit/iaudit names (routes, env vars, report keys), and ships an image with no old engines. Breaking changes OK, no backward compat.
date: 2026-11-22
---
# PRD: SP02 api switches to engines/miti

Repo/branch: Onolys/onolys (local `iaudit`) / `feat/miti-lean-engine` · Depends on: SP01 · Blocks: SP03 (web), SP05 (cleanup)
Owns: `api/**` (src, tests, `pyproject.toml`, `Dockerfile`, `openapi.json`, `README.md`), root `uv.lock`, `config/{prod,staging}/routes.yaml` (route rename only), `infra/` (leftover env var cleanup, R5). Not owned: `engines/**`, `web/`, `admin/`, `protocols/`, CI files.

## TL;DR
One atomic change: all `onolys_core|paudit|onolys_evaluation|eaudit` imports in `api/` (src + tests) become `onolys_miti`; `RealEvaluation` calls `run_miti` (no pack, no rating). Stages become `code|tips|assemble`. Rating endpoints/storage/gate stay, but the run ignores the card, and the run no longer passes a `coded_span`: the engine picks it (whole session <= 20 min, else seeded random 20-min window; passes `seed=session_id`, see SP01 R7). All paudit/iaudit/eaudit names go: LLM routes `miti_code`/`miti_globals` (`config/*/routes.yaml`, staging presets, tests), env vars, `run_info.miti` report key (`report.local.schema.json` and `openapi.json` updated). No backward compat (nobody uses prod): old stored data may be wiped or ignored. Image installs `onolys-miti` only. **Run gate (resolved):** the first run is gated on a submitted rating and `change_goal` enters via that card; SP03 sends it via `PUT /rating` `no_rating` from the upload screen (card carries `change_goal` only), no api change [OPEN-1 RESOLVED].

## Problem
- api imports 4 old packages. [verified: `git grep` in `api/src`: `onolys_core` in 17 files, `paudit` in `adapters/real.py`, `jobs/run.py` (via evaluation), `rating.py`; `onolys_evaluation` in `adapters/real.py`, `jobs/run.py`, `rating.py`; `eaudit` by name in `adapters/error_map.py`, `adapters/fake.py`, `jobs/machine.py`, `jobs/run.py`]. Tests: 31 of ~70 files touch them [grep -c].
- `Stage = Literal["paudit","eaudit","tips","compare","assemble"]` and `STAGE_WEIGHTS` model a pipeline that no longer exists. [verified: `adapters/base.py:20`, `jobs/machine.py:53`]
- Image copies `engines/{core,eaudit,paudit,evaluation}`, `protocols/`, `docs/contracts/*.schema.json` for eaudit. [verified: `api/Dockerfile`]
- `rating.py` and `voice/scenarios.py` read the pack from disk via `paudit.pack.load_pack` + `PAUDIT_PROTOCOLS_DIR`; `app.py:346` loads it at startup.

## Goals / Non-Goals
**Goals**
- `git grep -E "onolys_core|paudit|onolys_evaluation|eaudit" api/` empty (except historical comments reworded; test-enforced for `src` and `tests`).
- Runs, ratings, voice, STT behave as today from the client's view, apart from stage names and the renamed report keys.
- No old-data handling: stored sessions/reports with old names or comparison fields may break or be wiped (owner 2026-11-22).
- Image without old engines, `protocols/`, eaudit contracts.

**Non-Goals**
- Removing rating routes/models/flags (kept for later). Report model trimming. Web changes (SP03). Admin (SP04). Deleting old packages or `protocols/` (SP05). Backward compatibility of any kind.

## Requirements
**R1. Import swap (one pass, never mixed; D2 of SP01)**

| File(s) | Change |
|---|---|
| `adapters/{base,real,fake,__init__}.py`, `app.py`, `audio.py`, `auth/deps.py`, `config.py`, `logs.py`, `presets.py`, `repo/*`, `routes/*`, `jobs/*`, `voice/*` | `onolys_core.X` -> `onolys_miti.X` (same submodule names per SP01 R1: `errors, transcript, stt{,.fixture,.base,.select,.google_chirp}, voice{,.fixture,.select,.gemini_live_vertex}, llm{,.routes,.errors}, safe_log, run_info, context.RunContext`). `PackRef` import deleted. |
| `adapters/real.py` | delete `PACK_REF`, `pack_loader`; `RealEvaluation(run_miti=None, llm_factory=...)`; `_ENGINE_PARAMS` drops `coded_span` and `whole_second_span` use goes (engine picks the span; adds `seed`); call `run_miti(rctx, transcript, speaker_map, engine_params, progress_cb)`; return `EvaluationOutput(report, artifacts)` unchanged shape. `RUN_DEADLINE_S=8*60` stays (api owns it). |
| `adapters/error_map.py` | `AllRunsFailed/CodePassFailed/GlobalsPassFailed` need no explicit import (matched as `OnolysError`, code `run_failed`); drop `PackError` branch and `_named(exc,"eaudit","DeadlineExceeded")`; `TimeoutError` stays. LLM-cause unwrapping stays. Public codes unchanged. |
| `jobs/run.py` | `report_schema_path` from `onolys_miti.report`; `LOCAL_REPORT_SCHEMA` fallback kept. Engine params: stop reading `session.coded_span` (line ~163); add `seed=session_id`. |
| `rating.py`, `voice/scenarios.py`, `app.py:346` | `validate_rating`, `is_no_rating`, `Issue`, rating schema and scenarios dir come from `onolys_miti` data accessors, no `load_pack`, no `PAUDIT_PROTOCOLS_DIR`. Accessor names: [RESOLVED: implementer verifies at coding time, default: SP01 lists them in its README]. |
| `config/{prod,staging}/routes.yaml`, staging presets, `test_staging_presets`, any api test naming routes | `paudit_code`/`paudit_globals` -> `miti_code`/`miti_globals` (matches SP01 R6). No migration; prod config edited directly. Env vars `IAUDIT_MODEL_*`/`IAUDIT_LLM_*` -> `MITI_*` wherever api/Dockerfile/tests set them. |
| error codes/strings, log fields, artifact names | no `paudit`/`iaudit`/`eaudit` text; public error `code`s that never carried those names are unchanged. |

**R2. Adapter seam and stages**
- `Evaluation.run(ctx, transcript, speaker_map, params, progress_cb=None)`: `pack` and `rating` params removed. `jobs/run.py` stops loading the rating card (`get_rating` block) and no longer passes it. `run_doc.rating_id` is still recorded on the run (history only).
- `Stage = Literal["code","tips","assemble"]` (matches SP01 D6). `STAGE_WEIGHTS = {"code": 40, "tips": 8, "assemble": 3}` (45 + 51 = 96, under the 99 cap; old sum 55 would overshoot to the cap). `progress_cb` already ignores unknown stages [verified: `jobs/run.py` `if stage not in STAGE_WEIGHTS: return`], so a stale name can never write progress or break a run.
- `FakeEvaluation` emits `code, tips, assemble`; no `eaudit` logic. Markers: `[fail:paudit]` renamed `[fail:code]` (fails run + session, `AdapterError("code_failed")` maps to `internal_error`), `[fail:tips]` kept (report + `tips_failed` warning); `[fail:eaudit]` removed. Fake builds the no-rating report shape (`has_clinician_rating:false`, `diff.status:"not_rated"`, `reasons_audit:{status:"skipped"}`, `run_info.miti`, no `run_info.eaudit`), identical to SP01 R3; fake span = whole session. Fake `ctx`, `rating`, `seed` ignored.
- Artifacts written: `{uid}/{sid}/runs/{run_id}/{code,tips}.json` (`ARTIFACTS=("code","tips")`). Nothing reads artifacts back [verified: grep of `artifacts_prefix`/`paudit.json` finds only `jobs/run.py`], so old `paudit.json`/`eaudit.json` blobs are ignored (or wiped).

**R3. Rating flow (decided: ignored by the run, never waited on by the engine)**
- Engine never sees a rating. Rating routes, `RatingDoc`, `ratings/` Firestore docs, flags `rating_submitted`/`has_rating`, `rating_final` 409, `validate_rating` unchanged. [verified: only `jobs/run.py:157-160` reads a rating card on the run path.]
- State machine does require it today: `start_first_run` (fake + firestore) returns `not_ready` unless `transcript_ready && speaker_confirmed && rating_submitted` [verified: `repo/fake.py:582`, `repo/firestore.py:758`]. `POST /runs` (re-run / held run) does not require a rating but 409s `rating_final` once a report exists. So no run is blocked by the engine, but the **first run is blocked until the web submits a final rating** (a "no rating" revision counts). This is also the only path that sets `change_goal` on the session (`routes/rating.py:132-138`; no other writer [verified: grep]); `change_goal` is required on `final=true`. `coded_span` is no longer collected (engine picks it); the field/route handling stays and is simply never sent by the web.
- SP02 default: leave the gate untouched (no API behavior change, easy to review) and dependency handled by SP03 (Option A) [OPEN-1 RESOLVED].

**R4. Report contract**
- `ReportView.report` is `dict[str, Any]` stored verbatim and served without re-validation on read [verified: `routes/runs.py:96`; `report_validator` only used in `jobs/run.py` on write]. Old stored reports are not handled specially (wipe or ignore).
- New output is the SP01 no-rating report with the SP01 R6/R7 key changes (`run_info.paudit` -> `run_info.miti`, `run_info.eaudit` removed, `run_info.miti.span` added). Update `report.local.schema.json` (src + `tests/schemas`) accordingly, regenerate `openapi.json`/`docs/contracts/public/*` if they embed those keys (`python -m onolys_api.contracts --check` green after regeneration). `schema_version` stays `"0.0.1"` (no consumers to version for).
- Write-time validation reads `onolys_miti` `report.schema.json` (replaces `onolys_evaluation.report.schema_path`).

**R5. Packaging**
- `api/pyproject.toml`: deps `onolys-miti[stt-google,voice-gemini]`; `[tool.uv.sources] onolys-miti = {workspace = true}`; drop core/evaluation/paudit. mutmut `also_copy` drops `../protocols`. `uv lock` updated (`uv.lock` only; old packages stay workspace members until SP05 but are not api deps).
- `api/Dockerfile`: manifest layer copies `engines/miti/pyproject.toml` + `api/pyproject.toml` only, but uv needs every member's manifest to resolve the workspace while old members exist: keep their manifest COPY lines until SP05 (manifests only, not installed). Source layer copies `engines/miti` + `api/src` only. Remove `COPY protocols`, `COPY docs/contracts`, `PAUDIT_PROTOCOLS_DIR`, `IAUDIT_CONTRACTS_DIR`. `config/` still copied (routes/presets/STT/voice yaml). Acceptance check: `pip list`/`python -c "import paudit"` fails in the image.
- Env vars `PAUDIT_PROTOCOLS_DIR`/`IAUDIT_CONTRACTS_DIR` are removed from the Dockerfile `ENV`. Cleanup of old Cloud Run env vars is part of this work: remove any `PAUDIT_*`/`IAUDIT_*`/`EAUDIT_*` var from `infra/` (grep at this commit finds none in `infra/`, so the vars come from the image `ENV`) and from the live service, `terraform apply` allowed (owner 2026-11-22, nobody uses prod). Verify with `gcloud run services describe` after deploy [OPEN-5 RESOLVED].

**R6. Tests**
- Mechanical import swap: `test_{adapters,audio_integration,auth,config,delete,errors,first_run,interviews,logging,machine,rating,real_stt,repo_contract,scenario_loader_errors,scenarios,sessions,staging_presets,transcribe,validate,voice_relay,voice_relay_gaps,worker,acceptance_*}`.
- Rewritten: `test_real_flow`, `test_run_artifacts`, `test_real_evaluation`, `test_live_real_mode`, `test_run` (stage assertions: `{"code","tips","assemble"}`, artifacts `code,tips`, progress ends 100), `test_staging_presets` (route names `miti_*`), `test_error_map` (drop `importorskip("eaudit")`, `EauditDeadline`, eaudit case; keep `AllRunsFailed`-from-LLM unwrapping from `onolys_miti.errors`), `test_machine` (stage weights).
- They import fixtures from `engines/evaluation/tests` (`_make_fixtures`, `test_tips`) via `sys.path` [verified]. Replace with fixtures published by SP01 under `engines/miti` (path [RESOLVED: implementer verifies at coding time, default: SP01 README lists it]); never import from old engines.
- `test_adapters`: schema paths become `engines/miti/.../report.schema.json`; paudit-result schema test dropped with `tests/schemas/paudit-result.local.schema.json`. Fake parity: one test runs `FakeEvaluation` and `RealEvaluation` (FixtureClient) and asserts same top-level keys + Stage sequence + schema validity.
- New: `test_no_old_imports` (git grep style over `api/src`, `api/tests` for imports and the `paudit|iaudit|eaudit` names); `test_span_not_passed` (engine params carry `seed`, never `coded_span`); `test_rating_ignored` (a run started with a submitted full card and with none yields identical report modulo volatile keys and never calls the engine with a rating).
- Live path: `test_live_real_mode.py` (`-m live`, manual/nightly) runs the real flow with `run_miti`; FULL_RATING fixture dropped; no-rating only.

## Architecture
```
worker run task -> jobs/run._evaluate -> Evaluation.run(rctx, transcript, {"subject":..}, params, progress_cb)
   RealEvaluation -> onolys_miti.run_miti (stages code|tips|assemble) -> EvaluationOutput(report, artifacts{code,tips})
   progress_cb(stage,status) -> session_status.step=stage ; progress = 45 + sum(weights) (<=96, 100 at report_ready)
first run gate (unchanged): transcript_ready & speaker_confirmed & rating_submitted -> run (rating not read)
```
Firestore: `session_status.step` is transient (`None` once a run ends [verified: `advance(..., step=None)`]), so no migration. Old persisted `runs/*.stage` values and blobs are ignored or wiped. Web reads `step` as `string|null` [verified: `firestoreListener.ts:50`]; the only stage-keyed code is `RUN_SUBLABELS` in `web/src/features/session/timeline.ts` (+ `mocks/stateMachine.ts`), updated in SP03 to the new names only. No deploy-order or in-flight-run handling (nobody uses prod).

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | Rating vs run | Engine ignores rating; routes/storage/gate unchanged | Remove gate now; delete rating routes | Locked: keep for later; minimal API behavior change; gate change entangles SP03; see resolution of [OPEN-1] (Option A) |
| D2 | Seam signature | Drop `pack` and `rating` from `Evaluation.run` | Keep as ignored params | Dead params invite misuse; all callers are in api |
| D3 | Stage names | `code,tips,assemble` end-to-end (adapter, weights, fake) | Map new->old names at the seam | Honest names; no mapping layer to delete later |
| D4 | Stage weights | 40/8/3 | Keep 25/15/8/4/3 | Old table needs stages that no longer exist; sum stays under cap |
| D5 | Artifact blob names | `code.json`, `tips.json` | Keep `paudit.json` | Nothing reads them; names match the engine; old blobs ignored |
| D6 | Report contract | Schema/openapi updated for SP01 R6/R7 key renames; no version bump | Keep `run_info.paudit`; bump `schema_version` | Names follow the engine (owner 2026-11-22); no consumers to protect |
| D7 | Fake markers | `[fail:code]`, `[fail:tips]`; drop `[fail:eaudit]` | Keep old marker names | Names follow stages; web mock/e2e titles updated in SP03 |
| D8 | Pack data access | Accessors from `onolys_miti`, no env var | Keep `PAUDIT_PROTOCOLS_DIR` | Wheel is self-contained (SP01 D3) |
| D10 | Coded span | Not an api input; `seed=session_id` passed, engine picks | api computes span; keep user span | Single implementation in SP01 R7 for all callers (owner 2026-11-22) |
| D11 | Route/env/key names | Renamed to miti, no migration | Keep old names | Owner 2026-11-22: breaking is fine |
| D9 | Old workspace members | Stay in lock/workspace until SP05; not deps of api | Remove now | SP04/SP05 ordering |

## Risks / Open Questions
- [RESOLVED: Option A — upload screen sends change goal + optional span via PUT /rating no_rating in one submit; no api change (see 03-web PRD), owner 2026-11-22] (OPEN-1) **Run gate and inputs.** Original problem: hiding the rating card (SP03) stops first runs and loses `change_goal`/`coded_span` (R3). Options: (A) SP03 keeps a minimal setup form (change goal, coded span, "Skip rating") posting to the existing `PUT /rating` (`no_rating:true`); no api change. (B) SP02 relaxes the gate to `transcript_ready && speaker_confirmed` behind `REQUIRE_RATING_SUBMIT` (default true) and adds a way to set `change_goal`/`coded_span` (e.g. `PATCH /sessions/{id}`), `rating_final` still keyed on report existence. Settled on A. Also verify `change_goal` may be empty for MITI quality.
- [RESOLVED: implementer verifies at coding time, default: SP01 README lists them, owner 2026-11-22] (OPEN-2) SP01 interface gaps api needs: accessors for report schema path, rating schema/`validate_rating(obj, final)` without a `Pack` arg, scenarios dir, `Issue`; fixtures for api tests (`_make_fixtures` replacement incl. `good_practice`); `RunContext` and `whole_second_span` import paths. Ask SP01 to list them in its README.
- [RESOLVED: not needed, nobody uses prod, owner 2026-11-22] (OPEN-3) In-flight runs / deploy order.
- [RESOLVED: rename to `miti_code`/`miti_globals` now in `config/*/routes.yaml`, staging presets, tests; prod config updated directly, no migration, owner 2026-11-22] (OPEN-4)
- [RESOLVED: clean up now as part of this work, `terraform apply` allowed, owner 2026-11-22] (OPEN-5) Old Cloud Run env vars; see R5.
- [RESOLVED: implementer verifies at coding time, default: measure with `docker build`, owner 2026-11-22] (OPEN-6) Image size/memory.
- [RESOLVED: dropped, no backward compat, owner 2026-11-22] Old reports with comparison fields: not handled.
- [RESOLVED: `step` is transient, cleared at run end] No Firestore migration for stage names.
- [DEFERRED] Removing rating routes/flags/`RatingDoc`; trimming the Report model.

## Acceptance Criteria
- `uv sync --frozen --package onolys-api` resolves with `onolys-miti` only; `uv run --package onolys-api pytest api/tests -m "not live"` passes; ruff clean.
- `git grep -iE "onolys_core|paudit|iaudit|onolys_evaluation|eaudit" api/src api/tests config` returns nothing (test-enforced for src/tests); routes are `miti_code`/`miti_globals`.
- No `PAUDIT_*`/`IAUDIT_*`/`EAUDIT_*` env var in the Dockerfile, `infra/` or the live Cloud Run service (checked after `terraform apply`).
- Docker image builds; `python -c "import paudit"`, `import onolys_core`, `import eaudit`, `import onolys_evaluation` all fail inside it; `/app/protocols` absent; app boots with `SERVICE_MODE=combined ADAPTERS=stub` and `real` (fixture providers).
- Run via `ADAPTERS=real` + FixtureClient: progress steps observed `code, tips, assemble`; progress monotonic to 99 then 100; artifacts `code.json`, `tips.json`; report validates against the miti schema and `report.local.schema.json`.
- Run started with and without a submitted rating produces the same report shape; engine called without a rating.
- Engine params carry `seed` (session id) and no `coded_span`; the report records the engine-chosen span.
- `openapi.json` and `docs/contracts/public/*` regenerated for the key renames (`contracts --check` green); fake and real adapters pass the parity test; `/rating` PUT/GET tests unchanged and green.
- Coding failure -> run + session `failed`, `internal_error` (LLM cause -> `upstream_unavailable`, retried); tips failure -> report with warning.
