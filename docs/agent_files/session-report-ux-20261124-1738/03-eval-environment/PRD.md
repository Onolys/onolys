---
status: draft
summary: Add a third instance of infra/modules/environment named `eval` (database `eval`, bucket `onolys-audio-eval`, own queue, worker, allowlisted eval-backend service, EVAL_MODE on, caps effectively off) with opt-in module variables whose defaults leave staging/prod plans unchanged; keep the legacy staging eval service until SP05 cuts over; prepare an owner-run read-only SA runbook.
date: 2026-11-25
---
# PRD: SP03 Eval environment (Terraform)

Repo/branch: Onolys/iaudit / `session-report-ux` · Depends on: none (Phase 1) · Owns: `infra/{main.tf, variables.tf, deployer.tf, eval.tf, eval-services.tf, identity.tf (authorized domains only), modules/environment/*.tf, scripts/*}`, `firebase.json`, `.github/workflows/deploy-eval.yml`, `docs/reference/infra.md`, new `infra/scripts/readonly-sa.md` · No application code (SP04 owns `EVAL_MODE` parsing; SP05 owns the eval backend).

## TL;DR
Eval today is hand-written Terraform bound to the staging database [verified: `infra/eval-services.tf` `FIRESTORE_DATABASE = "staging"`, condition `databases/staging`]. This SP makes eval a third module instance so it runs the same worker image on its own data, queue, bucket and secrets. All new module variables default to "off", so `terraform plan` for `staging`/`prod` shows no change. Legacy eval resources stay until SP05 cuts over, then are removed.

## Problem
| Gap | Evidence |
|---|---|
| Eval shares the staging DB and has its own queue/SA/service, not the pipeline | [verified: `eval-services.tf` queue `onolys-eval-runs-staging`, SA `eval-backend-staging`] |
| Module accepts only `staging\|prod` | [verified: `modules/environment/variables.tf` `env` validation] |
| API `ENVS = (local,test,staging,prod)`; `ROUTES_FILE = config/${env}/routes.yaml`; CI guard checks only staging/prod config dirs | [verified: `api/src/onolys_api/config.py:10`, `services.tf:9`, `scripts/ci/check_config.sh:20`] |
| Caps would throttle eval: `0` does NOT mean off (`day.runs + units > 0` refuses; `active_runs >= 0` is always true); defaults are `EVAL_CAP_DAY=10`, `MAX_ACTIVE_RUNS=1` | [verified: `repo/limits.py:83-92`, `config.py:87-89`] |
| Bucket lifecycle deletes `uploads/` after 1 day | [verified: `modules/environment/main.tf` `lifecycle_rule`] |

## Goals / Non-Goals
**Goals:** `module "eval"` with isolated DB/bucket/queue/SAs/secrets; staging/prod plan-neutral; eval-only surface is allowlist-gated; datasets bucket readable, never writable, by the eval runtime; offline-checkable (`fmt`, `validate`, static tests); owner-run security runbook prepared.
**Non-goals:** eval backend code (SP05), `is_eval` / worker honouring (SP04), eval web UI (SP07), applying anything, seeding secrets, running the read-only SA script, moving/renaming the datasets bucket.

## Requirements
**R1 Module instance.** `main.tf`: `module "eval"` with `env = "eval"`, `database_id = "eval"`, `delete_protection = true`, `alerts_enabled = false`, own `cors_origins` (eval web origins), `app_base_url = ""` (api validator allows unset: auth emails then 503 [verified: `config.py` `_validate_app_base_url` only when set]). Bucket name `onolys-audio-eval` and queue `steps-eval` fall out of the module's `${var.env}` naming [verified: `main.tf` module `audio`, `steps`]. `env` validation becomes `staging|prod|eval`.

**R2 New module variables (all default to current behaviour).**
| Variable | Default | Eval value | Effect |
|---|---|---|---|
| `eval_mode` | `false` | `true` | adds `EVAL_MODE=true` to `platform_env` (api, worker); omitted entirely when false |
| `runtime_env` | `var.env` | `"staging"` | value of `ENV` and the `config/<runtime_env>/` dir; avoids adding `eval` to API `ENVS`, `APP_HOSTS` and `check_config.sh` |
| `eval_backend_enabled` | `false` | `true` | creates the allowlisted eval-backend service (R4) and its grants; also makes `admin_allowed_emails` secret exist (`count = admin_enabled \|\| eval_backend_enabled`, address unchanged) |
| `public_api_enabled` | `true` | `false` | gates `api` + `voice` Cloud Run services and their `allUsers` invokers |
| `max_active_runs` | `null` | `1000` | `MAX_ACTIVE_RUNS` emitted only when non-null |
| `eval_cap_day` (existing) | `10` | `1000000` | caps effectively off |
Root vars (new, defaulted): `eval_worker_concurrency`, `eval_worker_max_instances`, `eval_llm_secrets` (default = `llm_secrets`), `eval_git_sha` (default `"unset"`). Existing maps `admin_enabled`/`git_sha`/`resend_secret_wired` keep their strict `staging|prod` key validation [verified: `variables.tf`]; eval passes scalars.

**R3 Gating existing resources without churn.** `count` on `api`, `api_public`, `voice`, `voice_public` and the voice SA/IAM changes their addresses; add `moved {}` blocks (`x` to `x[0]`) in the module so staging/prod plan reports 0 add/change/destroy. Outputs use `one(...)` like the admin outputs [verified pattern: `outputs.tf` `admin_backend_*`]; `identity.tf` voice outputs/`VITE_VOICE_URL` stay valid because staging/prod keep `public_api_enabled = true`. The `api` SA is kept even when the api service is off (R4 reuses it).

**R4 Eval-backend service (module, like `admin_backend`).** `onolys-eval-backend-${env}` Cloud Run service, runtime SA = the module's `api` SA (identical grants by construction: `datastore.user` on db `eval` only, `objectAdmin` on `onolys-audio-eval`, queue enqueuer, `tasks-invoker` actAs, self `serviceAccountTokenCreator`). Env: `platform_env` + `ADMIN_AUTH=on`, `ADMIN_AUTH_PROJECT`, `ADMIN_CORS_ORIGINS`, `SERVICE_URL`/`TASKS_OIDC_AUDIENCE` (deterministic run.app URL, same pattern as `worker_url`), `ADMIN_ALLOWED_EMAILS` from secret `admin-allowed-emails-eval`. `allUsers` invoker (auth is in-app, same as today [verified: `eval_public`]). Image = placeholder, owned by CI (`ignore_changes`, copied from `services.tf`). Exact env names finalised with SP05; `EvalConfig` today requires `EVAL_BUCKET`, `TASKS_QUEUE`, `TASKS_SA`, `SERVICE_URL`, `PROD_ENGINE`, `DEFAULT_PRESET`, `ROUTES_FILE` and hardcodes `firestore_database="staging"` [verified: `eval/backend/.../config.py`], a SP05 change.

**R5 Worker (module, unchanged shape).** `onolys-worker-eval` from the prod image with `EVAL_MODE=true`, queue `steps-eval`, `max_concurrent_dispatches = worker_concurrency x worker_max_instances` (rule: dispatches must not exceed worker capacity [verified: `docs/reference/infra.md:46`]). The queue cap is the scheduler's ceiling (locked decision 9).

**R6 Secrets.** Module creates shells `<base>-eval` for `eval_llm_secrets`/`stt_secrets` plus `uid-hmac-key-eval`, `resend-api-key-eval`, `admin-allowed-emails-eval`. Values are never in Terraform/state: `seed-secrets.py` gains `eval` in `--env choices` [verified: `seed-secrets.py:113`]. Worker alone reads provider keys; eval-backend reads only HMAC and allowlist.

**R7 Datasets bucket (kept, read-only).** `google_storage_bucket.eval_staging` (`onolys-eval-data-staging`) keeps its Terraform address (a rename would destroy it). Add one `google_storage_bucket_iam_member` `roles/storage.objectViewer` for the `api-eval` SA only. The old `objectUser` write grant and the Speech-agent `uploads/` grant exist only on the legacy SA/service and go with R9. Gold files go under a prefix other than `uploads/` in `onolys-audio-eval` (e.g. `gold/<sha256>`) because of the 1-day lifecycle: constraint handed to SP05.

**R8 Deploy pipeline.** (a) Worker-eval gets the exact image digest staging runs (same promotion pattern as `deploy-prod`; no rebuild, so "same code" is guaranteed) via `_deploy-cloudrun.yml`, which only accepts `staging|prod` today [verified: input check]: extend to `eval`, authenticating as `deployer-staging` (no new deployer SA). (b) Eval-backend image is built from `eval/backend/Dockerfile` as today and deployed to `onolys-eval-backend-eval`; Terraform is image-agnostic [verified: `ignore_changes` on image], so SP05 may switch to a shared image without infra change. (c) `deployer.tf`: `eval_services`/`eval_runtime_sas` locals with `run.developer` and actAs for deployer-staging, plus `datastore.indexAdmin` conditioned on db `eval` [verified: current condition is staging-only, `deployer.tf:130-140`]. (d) `firebase.json` gains `{"database":"eval", rules, indexes}`; `deploy-eval.yml` runs `deploy --only firestore:eval`.

**R9 Legacy cutover (two steps).** Step A (this SP, Phase 1): add `module "eval"` only; legacy `onolys-eval-backend-staging`, `onolys-eval-runs-staging`, `eval-backend-staging`/`eval-tasks-staging` SAs, `eval_*` IAM and old `deploy-eval` target stay and keep working. Step B (after SP05 cutover verified by owner): delete the legacy service, queue, two SAs, `eval_datastore`/`eval_speech`/`eval_objects`/`eval_stt_uploads`/`eval_provider`/`eval_allowlist` IAM, deployer eval grants, `eval_enabled`; update/delete `test_eval_service.py`, `test_eval_bucket.py`. `eval.tf` shrinks to the datasets bucket + R7 grant.

**R10 Eval web hosting (kept).** Same Firebase site `onolys-eval-staging`, domain `eval.onolys.com`, hosting target `eval-staging`, admin-staging Firebase web app [verified: `eval/web/firebase.json`, `.firebaserc`, `domains.tf`, `identity.tf:17`]. `__EVAL_BACKEND_ORIGIN__` CSP is substituted from the deployed URL by `set_eval_origin.sh`, so the new service URL needs no hosting change. Site id keeps the `-staging` misnomer (rename = recreate + DNS re-verify).

**R11 Firestore rules/indexes.** Reuse `firestore.rules` (client deny-all except `session_status`) and `api/firestore.indexes.json` for `eval`. Module-level TTL fields (`email_rate`, `session_status`) apply automatically.

**R12 Owner-only runbook.** `infra/scripts/readonly-sa.md` (prepared, never run by agents): (1) create `claude-readonly` with `datastore.viewer`, `logging.viewer`, `run.viewer`, `monitoring.viewer`; (2) grant the owner `serviceAccountTokenCreator` on it; (3) point machine ADC at impersonation (`gcloud auth application-default login --impersonate-service-account=...`); (4) owner removes personal ADC file, `firebase logout`, revokes machine access in Google Account > Security; (5) verify: a write call is denied, a read succeeds; (6) note: Terraform, secret seeding and `bootstrap.sh` now need the owner's own login. Also note `tfstate` read needs `storage.objectViewer` on `onolys-tfstate` if agents should `plan` (owner decision).

## Architecture
```
GitHub CI --digest(staging image)--> onolys-worker-eval  <--OIDC-- Cloud Tasks steps-eval
          --eval/backend image-----> onolys-eval-backend-eval (allowlist, SA api-eval)
Firebase Hosting onolys-eval-staging (eval.onolys.com) --> eval-backend-eval
eval-backend-eval/worker-eval --> Firestore db `eval` | gs://onolys-audio-eval (runs, gold/) | secrets *-eval
eval-backend-eval --read-only--> gs://onolys-eval-data-staging (datasets)
```
Isolation: DB, bucket, queue, SAs, secrets are per module instance; IAM conditions pin `datastore.user` to db `eval` [verified: `main.tf` `datastore_user`]. No `api`/`voice` service exists in eval, so no public sign-up path can spend eval budget.

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| 1 | Runtime ENV | `runtime_env="staging"` + `EVAL_MODE` | add `eval` to API `ENVS`, `config/eval/`, `APP_HOSTS` | no app/CI-guard change; `EVAL_MODE` is the real discriminator; only PR_PREVIEW/UID_HMAC checks key on `staging` [verified: `config.py:210-224`] |
| 2 | Unused features | gate `api`/`voice` with `public_api_enabled`; alerts off | deploy everything scale-to-zero | a public api with caps off is an open spend path |
| 3 | Plan neutrality | opt-in variables + `moved` blocks | fork the module | one module, one fix path |
| 4 | Eval SA | reuse `api` SA for eval-backend | new `eval-backend-eval` SA | same grants by construction; fewer IAM resources |
| 5 | Caps off | big numbers in config (`1000000`, `1000`) | `0` | `0` blocks everything (see Problem); SP04 may also skip reservation in `EVAL_MODE` |
| 6 | DB deletion | `delete_protection = true` | false like staging | retention = until owner deletes (decision 8) |
| 7 | Legacy removal | after SP05 cutover | now | old service is the only working eval UI until Phase 2; no data to protect but no replacement yet |
| 8 | Hosting | keep site/domain/target | new site `onolys-eval` | no DNS churn |
| 9 | Deployer | reuse `deployer-staging` | new `deployer-eval` | already trusted for eval; narrower than a new WIF principal only if split later |
| 10 | State | same root, same `onolys-tfstate` backend | separate root | module outputs feed `deployer.tf` |

## Manual steps (owner-only)
1. `terraform plan` (owner login): confirm staging/prod show 0 changes (moved only), eval shows adds only; then `terraform apply`.
2. Seed secrets: `ADMIN_ALLOWED_EMAILS="..." python3 infra/scripts/seed-secrets.py --env eval --admin` plus provider keys (values never committed).
3. Set GitHub repo variables/environment for eval deploys if new ones are used.
4. DNS: none new (domain `eval.onolys.com` already exists).
5. Run `infra/scripts/readonly-sa.md` (R12), then Step B of R9 after verifying SP05.

## Risks / Open Questions
- [OPEN] Queue/worker sizing for eval (provider rate limits unknown). Default: `eval_worker_concurrency=2`, `eval_worker_max_instances=10` (20 dispatches), tune after first batch.
- [OPEN] Does a Terraform-created named Firestore database start with deny-all client rules? Default: deploy `firestore.rules` to `eval` regardless (R8d).
- [OPEN] Legacy removal timing: owner may prefer removal now since data is gone. Default: R9 two-step.
- [OPEN] Eval-backend as separate image (today) or `SERVICE_MODE` of the api image. Default: separate image; infra unaffected either way. Decide in SP05.
- [OPEN] Allowlist membership for `eval` (reuse the staging admin emails?). Owner-only value; default: same list.
- [DEFERRED] `monthly_budget_usd` is `20` (alerts only, project-wide [verified: `variables.tf`]); a 216-run batch may exceed it. Owner to adjust after first run.
- [DEFERRED] Removing the PUT CORS block on the datasets bucket until SP05 removes the browser-upload flow.
- [RESOLVED: R3] Plan neutrality via `moved` blocks; cannot be proven offline, so owner plan is the final check.
- Risk: `count` on api/voice must not break `identity.tf` voice outputs (kept by defaults); mitigated by validate plus static tests.
- Risk: provider v6 models `env` as a set; conditional `EVAL_MODE`/`MAX_ACTIVE_RUNS` entries must be added via the existing `dynamic` blocks, not new `env` blocks.

## Acceptance Criteria
- `terraform fmt -check -recursive`, `init -backend=false`, `validate` pass in CI [verified: `ci.yml:596-598`]; `module "eval"` exists with `env="eval"`, `database_id="eval"`.
- Static tests in `infra/scripts/` (offline, extend existing style): module defaults equal current behaviour (`eval_mode=false`, `public_api_enabled=true`, `max_active_runs=null`); `moved` blocks present; eval datasets IAM is `objectViewer` only; no `allUsers` on eval worker; `datastore.user` condition names db `eval`; `seed-secrets.py` accepts `eval`.
- Owner `terraform plan`: staging/prod 0 add/change/destroy; eval creates DB `eval`, bucket `onolys-audio-eval`, queue `steps-eval`, worker, eval-backend.
- No secret value in the diff, state or workflow files; `readonly-sa.md` present and no agent ran it.
- Legacy eval resources untouched until Step B.
