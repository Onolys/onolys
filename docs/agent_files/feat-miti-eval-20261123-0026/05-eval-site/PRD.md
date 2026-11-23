---
status: draft
summary: eval.onolys.com (staging) = new SPA `eval/web` + Cloud Run `eval/backend` (allowlist auth reused). Runs fan out as Cloud Tasks units (session x engine x preset x repeat), engines called in-process via the SP3 registry, results in staging Firestore, compare table via SP2 metrics, history page with rerun.
date: 2026-11-23
---
# PRD: SP5 Eval site (eval.onolys.com)

Repo/branch: Onolys/onolys (local `iaudit`) / `feat/miti-eval` · Depends on: SP1 (transcript.v1, .txt parser, coded_span), SP2 (`onolys_eval` gold/metrics/bucket layout), SP3 (registry, `list_presets`, `RunContext`), SP4 (oneshot engine, validate+retry; PRD not yet written, interface assumed below) · Owns: `eval/backend/**` (new uv member), `eval/web/**` (new), `.github/workflows/deploy-eval.yml`, eval jobs in `ci.yml`, `scripts/ci/{changes.sh,test_changes*,test_deploy_eval.sh}` (eval lines), `infra/{main,domains,identity,variables,deployer}.tf` and `infra/modules/environment/{services,secrets,main,variables}.tf` (eval parts), `firestore.rules` (comment only), `docs/reference/eval-site.md` (new)

## TL;DR
A founders-only staging site to run engines against stored datasets (with human gold) or one uploaded audio/transcript, pick any engine x preset combination, and compare results in one table with error vs human. Own SPA (`eval/web`), own Cloud Run service (`eval/backend`) that imports the engine packages and executes work as Cloud Tasks units, so long runs survive browser close. Auth = `onolys_admin_auth` + `admin_allowed_emails`. No usage limits, no cost cap. Every run is saved and can be rerun.

## Problem
No way to measure engines against expert coding or against each other. The main app has usage limits, one engine, no gold data, and its jobs are shaped around one session. Eval needs many units per run, user-chosen engine and preset, and gold comparison. Facts [verified]: engine entry is `run_miti`; `RunInfo` already has input/output/cache tokens and optional `cost_usd`; API uses Cloud Tasks + a worker service (`TASKS_QUEUE`, `WORKER_URL`, STT start then re-enqueued polls in `jobs/transcribe.py`); admin = Cloud Run `onolys-admin-backend-<env>` + Hosting site `onolys-admin-staging` + domain in `infra/domains.tf`; admin frontend lives in `frontend/` (stripped to a shell by the admin-shell PRD); `firestore.rules` already denies all client access except `session_status`.

## Goals / Non-Goals
**Goals:** dataset mode and upload mode; Engine and Preset multi-selects with "(prod)" labels and defaults; background runs with live progress; one compare table; saved run history with rerun; tokens + rough $ per run; staging-only, allowlist-only.
**Non-goals:** prod eval; usage limits or cost caps; editing prompts/presets in the UI; utterance-level alignment; running via `api/`; sharing runs with non-allowlisted users; multi-user concurrency control beyond a queue cap.

## Requirements
**R1 Frontend.** New `eval/web` (Vite + React + TS, same toolchain as `web/`). Auth modules (Firebase sign-in, AuthGate, `authFetch`, 401/403 handling) copied from `frontend/src/auth`/`transport/authFetch.ts`, not imported (no shared npm package yet, see [OPEN]). Screens:
1. *New run*: mode toggle. Dataset: dataset dropdown, session multi-select (default all). Upload: file picker (audio, `.json`, `.txt`), optional gold file, change goal and language fields, speaker-pick step if roles unknown. Common: Engine multi-select, Preset multi-select, "runs per cell" 1|3, optional coded-span override (upload only; dataset uses its manifest span), Start. Shows planned unit count before start.
2. *Run progress*: per-unit status grid (queued/running/done/failed + stage), polling every 3 s, Cancel.
3. *Compare*: see R6.
4. *History*: table of runs (date, input, engines, presets, status, cost), open, "Rerun with different engines/presets" (prefills New run from saved input).
**R2 Dropdown behaviour.** Items come from `GET /v1/options`. Engines: Human score, MITI lean, One-shot, future registry engines; presets: `list_presets` minus `test-*`. The prod engine and prod preset carry "(prod)" in both. Defaults: dataset = Human + prod engine + prod preset; upload = prod engine + prod preset (Human listed only when a gold file is attached); all untickable. Human ignores the preset axis.
**R3 Backend API** (`/v1`, all behind `AdminAuthMiddleware`, CORS outermost; mirrors admin backend `create_app(env, verifier)`):
`GET /me` · `GET /options` · `GET /datasets` (lists `datasets/*/manifest.json` in bucket) · `GET /datasets/{id}` (sessions, gold present, span) · `POST /uploads` (multipart: input file, optional gold file; validates; returns `upload_id`) · `POST /uploads/{id}/speakers` (clinician pick) · `POST /runs` (body: input ref, engines, presets, repeats, change_goal, language, coded_span) · `GET /runs` · `GET /runs/{id}` (status + units + compare) · `POST /runs/{id}/cancel` · `POST /runs/{id}/rerun` (new run, same input). Internal, not allowlist-auth: `POST /internal/tasks/{unit|transcribe}` verified by Cloud Tasks OIDC token (SA + audience).
**R4 Input handling.** Dataset sessions load `transcript.json` + `gold.json` from the bucket (SP2 layout). Upload: file validated (size/type caps, SP1 parsers; `.json` against transcript.v1, `.txt` via SP1 parser; gold against `gold.v1`), stored at `uploads/<upload_id>/{input.*,gold.json,transcript.json}` in `onolys-eval-data-staging`, record in Firestore, never deleted automatically (reruns). Audio: `transcribe` task = `onolys_miti.stt` `start` then self re-enqueued `poll` tasks (15 s), result saved as transcript.v1; same STT params as prod; audio is copied in the eval bucket (Chirp needs a GCS URI; STT service agent gets read on `uploads/`). Roles unknown (audio, or `.txt` with `Name:` prefixes): run waits in `awaiting_speakers`; UI shows speakers with sample lines, user picks clinician (reuses SP1's speaker-gate helper, or the API's logic if only there, see [OPEN]).
**R5 Execution.** `POST /runs` expands units = session x engine x preset x repeat (Human = one unit per session, no LLM), writes `eval_runs/{id}` + `units`, enqueues one Cloud Task per unit to `eval-runs` queue targeting the same service. Handler: build `RunContext` (no usage-limit code path exists in eval), pick engine via `EngineRegistry`, apply preset through core route resolution, call `engine.run(...)`, then the SP4 API-layer `validate_output` + retry-once loop (assumed to live in a reusable function in `onolys_engine_core` or `onolys_api`; eval calls it, does not reimplement), adapt to `Scores` (`scores_from_report` or the engine's adapter), store result. Unit state transitions are idempotent (redelivered task with `done` state exits 200). Last unit to finish (Firestore transaction on a counter) sets run status `done` | `partial` | `failed`; Cancel flips run flag, pending units no-op. Queue config: `max_concurrent_dispatches=4`, retries 2 for 5xx only (LLM failures are recorded as unit failure, not retried by the queue), dispatch deadline 900 s.
**R6 Compare table.** Rows: 10 behavior counts, 4 globals, summaries (R:Q, %CR; always recomputed from counts via SP2 metrics). Columns: Human (if present) then each engine x preset cell (repeats shown as mean with a min-max range, one expandable detail). Per-session view and, in dataset mode, per-session diff vs Human plus an average-error column (MAE per count/global/summary from `aggregate`). No Human: side-by-side only, no error columns. Failed units shown as such, excluded from MAE with n shown. Also shows per-run tokens and rough $ (R8). Output JSON viewable per unit.
**R7 Persistence.** Staging Firestore (database `staging`), collections: `eval_uploads/{id}` (name, kind, bucket paths, has_gold, created_by, created_at), `eval_runs/{id}` (input ref or dataset+sessions, engines, presets, repeats, change_goal, coded_span, status, created_by/at, engine git sha(s), per-engine `version`, resolved preset to model map, `usage` totals, `cost_usd_est`), `eval_runs/{id}/units/{uid}` (session, engine, preset, repeat, status, stage, error code, `scores` (`Scores`), `run_info` (tokens, durations), `output` inline up to 500 KB else `output_ref` to `runs/<run_id>/<uid>.json` in the bucket). Rules: client access stays denied (default rule); only a comment is added. Backend uses the Admin SDK. Index file gets `eval_runs(created_at desc)`.
**R8 Tokens and $.** Tokens summed from `EngineResult.run_info` (SP3/SP4 must expose input/output/cache tokens; MITI already has them in `RunInfo`). $ = `run_info.cost_usd` when set (litellm cost), else tokens x `eval/backend/prices.yaml` per resolved model; shown as "~$" and labelled estimate. STT cost not included.
**R9 Auth.** `ADMIN_AUTH=on` fixed, `ADMIN_ALLOWED_EMAILS` from the existing secret `admin_allowed_emails`; empty allowlist fails startup (as admin). Anonymous 401, non-allowlisted 403.
**R10 Infra** (staging only, flag `eval_enabled`): Hosting site `onolys-eval-staging` + `google_firebase_hosting_custom_domain` `eval.onolys.com` (domains.tf); Identity Platform authorized domains add `eval.onolys.com` and `onolys-eval-staging.web.app` (identity.tf); reuse the `admin_staging` Firebase web app config for the SPA (no new web app); Cloud Run `onolys-eval-backend-staging` (own SA, `allUsers` invoker like admin since app-level auth, timeout 900 s, 2 CPU / 2 Gi, concurrency 4, max instances 5); env: `ENV`, `ADMIN_*`, `EVAL_BUCKET`, `TASKS_QUEUE`, `SERVICE_URL`, `PROD_ENGINE`, `DEFAULT_PRESET` (same value prod uses), `ROUTES_FILE`; secrets: `admin_allowed_emails` accessor + the worker's LLM provider secrets (`worker_provider_secrets`); Cloud Tasks queue `onolys-eval-runs-staging` + SA `roles/cloudtasks.enqueuer`, tasks OIDC SA with `run.invoker`; bucket IAM on `onolys-eval-data-staging` (SP2 creates the bucket): eval SA `objectUser`; STT service agent `objectViewer` on `uploads/` via IAM condition; Firestore `datastore.user` and Speech `speech.client` for the eval SA; CORS origins `https://onolys-eval-staging.web.app`, `https://eval.onolys.com`; deployer SA gets eval service name/SA entries (deployer.tf). Agent runs `terraform apply` for staging (same authority as admin-shell R11); BLOCKED if credentials missing.
**R11 Deploy.** `deploy-eval.yml` copied from `deploy-admin.yml` (build image, deploy backend, set CORS origin, build SPA with `VITE_EVAL_API_URL` + existing `ADMIN_STAGING_VITE_FIREBASE_*` vars, deploy Hosting, smoke: anonymous `GET /v1/me` -> 401). Image: `eval/backend`, `eval/core`, `admin/auth`, `engines/*`, `config/`, protocols pack; asserts no dataset files in image.
**R12 Tests.** Backend: auth matrix, options (prod flags, Human only with gold), run expansion (counts, Human single), idempotent unit redelivery, cancel, last-unit finalisation, upload validation, bucket/Firestore via fakes. Frontend: dropdown defaults per mode, planned-count, compare table with/without Human, auth gate. One live smoke (manual) per AC.

## Architecture
```
Browser eval.onolys.com ── Firebase Hosting (onolys-eval-staging, eval/web)
   └ Bearer ID token ─► Cloud Run onolys-eval-backend-staging
        CORS -> AdminAuthMiddleware -> /v1/*          /internal/tasks/* (OIDC)
        │ create run: Firestore eval_runs + units ; enqueue 1 task/unit
        ▼
   Cloud Tasks onolys-eval-runs-staging ─(HTTP, OIDC)─► same service
        unit: bucket transcript+gold ─► EngineRegistry.get(engine).run(ctx, transcript, params)
              ─► validate+retry (SP4) ─► Scores ─► Firestore unit doc
        audio: transcribe task (STT start, poll re-enqueue) ─► uploads/<id>/transcript.json
   GCS onolys-eval-data-staging: datasets/ (SP2) · uploads/ · runs/
   Compare: onolys_eval.metrics.compare/aggregate on read (cheap, pure)
```
Interface assumptions until SP4 lands: `EngineRegistry.engines()` and `list_presets(...)` as in SP3; `EngineResult{output, run_info{tokens, cost_usd?}}`; one callable `run_validated(engine, ctx, transcript, params)` implementing SP4 validate + retry-once; per-engine Scores adapter exposed by the engine or registered in `onolys_eval`. Shared with other SPs: registry + prod flags (SP3), `Scores`/`compare`/`aggregate`/`gold.v1`/bucket layout (SP2), parsers (SP1), `uv.lock`/root `pyproject.toml` (`eval/*` glob already added by SP2), `changes.sh`, `ci.yml`, `infra/` files also edited by SP2 (bucket).

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| D1 | Frontend location | New `eval/web` app, auth code copied | Route set in `frontend/` (admin shell) | Admin shell PRD strips `frontend/` to a login page; separate site and deploy; copying 5 small files beats a shared package now |
| D2 | Call engines | In-process via SP3 registry | HTTP to `api/` | api has sessions, usage limits, no oneshot, no preset choice; engines are Python packages |
| D3 | Background mechanism | Cloud Tasks, 1 task per unit, to the same service | In-process async (CPU throttled after response, lost on restart); Cloud Run Jobs (per-run startup, harder per-unit status) | Matches api/worker pattern; per-unit retry, parallelism cap, run survives tab close |
| D4 | Run storage | Firestore staging + bucket for big outputs | Bucket only | Query history, transactions for finalisation |
| D5 | STT | Reuse `onolys_miti.stt` directly with poll-chain | Call api STT jobs | No api session coupling |
| D6 | Firebase web app | Reuse `admin_staging` web app config | New app | Same project and allowlist; fewer resources |
| D7 | Human engine | Pseudo-engine in eval backend, returns gold as Scores | Registry engine | Not a real engine; needs no LLM |
| D8 | Unit granularity | session x engine x preset x repeat | Per run | Parallel, partial results, cheap retry |
| D9 | Metrics compute | On read from stored Scores | Stored | Metrics code can evolve without rerun |

## Manual steps (owner)
- Create DNS record(s) for `eval.onolys.com` from the Hosting custom-domain output (if not automatable); wait for cert.
- Confirm the repo variables `ADMIN_STAGING_VITE_FIREBASE_*` are set (already used by admin); no new secrets.
- Confirm the prod preset to mark "(prod)" if it should differ from staging's `DEFAULT_PRESET`.
- Raise LLM provider quota if 96-unit runs hit rate limits.

## Risks / Open Questions
- [OPEN] Unit duration for lean MITI (1 session) unknown; 900 s dispatch deadline assumed enough, measure in the SP2 spike. A 100+ unit run at concurrency 4 may take over an hour. Fallback: raise dispatch deadline (max 30 min) or queue concurrency.
- [OPEN] "(prod)" meaning: staging's `DEFAULT_PRESET`/`PROD_ENGINE` env vs the prod environment's. Default: pass the prod value in via Terraform variable so the label is truthful.
- [OPEN] Speaker-gate logic: where it lives after SP1/SP3 (api only vs core). Default: SP1 puts a pure helper in core; otherwise reimplement a minimal "pick the clinician" UI without auto-guess.
- [OPEN] Per-engine `Scores` adapter location (engine package vs `onolys_eval`); SP4 PRD to confirm. Default: `onolys_eval.adapters` registry keyed by engine name.
- [OPEN] STT cost and Vertex/Gemini quota roles for the eval SA; copy from worker SA, verify at apply.
- [OPEN] Price table source for $ when litellm cost is absent; default hand-maintained `prices.yaml`, labelled estimate.
- [OPEN] Shared auth package for `frontend/` and `eval/web`; default copy now, extract if a third site appears.
- [OPEN] Gold file attached to an upload when its coded_span differs from the chosen span: default use the gold's span and warn.
- [OPEN] Uploaded PHI-like real recordings in the staging bucket: retention/deletion not defined (history keeps them). Default: keep, add manual delete later.
- [OPEN] Is the Hosting custom domain for a non-prod site subject to Firebase verification quirks (admin did it already, same flow assumed).
- [DEFERRED] Run cancel of in-flight LLM calls; export compare to CSV; per-engine configurable params in UI; prod eval; MI-TAGS/AnnoMI datasets; utterance alignment.

## Acceptance Criteria
1. Anonymous call to eval backend `/v1/me` = 401; non-allowlisted account sees "Not allowed"; allowlisted account sees the New run screen on eval.onolys.com.
2. Dataset mode with defaults on `casaa-miti421-video2013` (8 sessions) completes: Human + MITI lean (prod) + prod preset = 8 + 8 units; compare table shows counts, globals, R:Q, %CR, per-session diff and MAE equal to `onolys_eval.metrics` on the same data.
3. Selecting 2 engines x 2 presets x "3 runs" yields the expected unit count shown before start; mean and range shown per cell; killing the browser tab mid-run and reopening the run still completes it.
4. Upload a `.txt` transcript without gold: run completes, side-by-side table without error columns; attach a gold file: Human column and error appear. Upload an audio file: STT runs, speaker pick step shown, then run completes.
5. Every run appears in History with input, engine versions/git sha, resolved presets and models, date, tokens and ~$; Rerun creates a new run on the same saved input with a different engine/preset set.
6. No usage-limit code is reached by eval (test asserts no import of the API limits module); main app limits unchanged.
7. `terraform plan` clean after apply; bucket denies anonymous reads; image contains no dataset files; deploy-eval workflow green with the 401 smoke.
