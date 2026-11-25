---
status: draft
summary: SP03 eval environment — 3rd module instance, eval login on prod auth, legacy eval + all admin removed, budget dropped; offline build/tests only
date: 2026-11-25
---
# Tasks: SP03 Eval environment (Terraform)
Source of truth: docs/agent_files/session-report-ux-20261124-1738/03-eval-environment/PRD.md. All PRD items are [RESOLVED]; no [OPEN]. Agents build and run offline tests only (no apply, no deploy, no live LLM/STT runs); R6a allowlist copy runs first.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Allowlist secret copy (R6a) | — | done |
| 2 | Prod `verify_claims` + eval-backend allowlist auth; delete `eval/auth` | — | done |
| 3 | Prod `web/src/auth` seams (behaviour-neutral) | — | done |
| 4 | Eval web on prod login (alias, de-admin) | 3 | done |
| 5 | Module variables, `moved` blocks, `module "eval"` | — | done |
| 6 | Eval backend service, worker, queue sizing, secrets, seed script | 1, 5 | done |
| 7 | Remove legacy staging eval; keep datasets bucket read-only | 5, 6 | done |
| 8 | Eval hosting, authorized domains, web config outputs | 4, 7 | done |
| 9 | Remove all admin infra, tests, docs | 1, 4, 6, 8 | done |
| 10 | Drop Terraform budget | — | done |
| 11 | Deploy pipeline (workflows, firebase.json, deployer IAM) | 6, 7, 8 | done |
| 12 | CI wiring and final acceptance sweep | 2, 4, 9, 10, 11 | done |

## Task 1 — Allowlist secret copy (R6a)
What it is: Eval's login allowlist must survive deletion of the admin secret. Decisions 12, R6a.
What changes: Using gcloud/ADC, create shell `eval-allowed-emails-eval` if missing (same replication as `modules/environment/secrets.tf`), copy latest version from `admin-allowed-emails-staging` by pipe (value never materialised), verify by sha256 printing only match/mismatch. Add a temporary Terraform `import {}` block for the module secret resource. Emails never printed, logged, committed or written to docs/PR text.
Done when: hash check reports `match` (or the step is reported blocked with the two owner commands as fallback); import block present; a static test/grep shows no email-like strings or secret values in the diff. No terraform apply run.

## Task 2 — Prod `verify_claims` + eval-backend allowlist auth; delete `eval/auth`
What it is: Swap the eval backend onto the prod api auth so the `eval/auth` package can go. R14, Decision 19.
What changes: Add additive `verify_claims(token) -> dict` to `api/src/onolys_api/auth/idtoken.py` (shared decode path, `verify` unchanged). Add `eval/backend/.../allowlist.py` (401 no token, 403 `not_allowlisted`, lower-cased email, startup refuses empty `EVAL_ALLOWED_EMAILS`, no token/email logging). Rewire `app.py`, `auth.py`, `config.py`; backend depends on `onolys-api`; drop `EVAL_AUTH*`, `ADMIN_*`, `admin_claims`. Delete `eval/auth/**`; fix `pyproject.toml`, `eval/backend/pyproject.toml`, Dockerfile COPY lines, regenerate `uv.lock` offline.
Done when: new `verify_claims` tests plus existing api auth tests pass; eval/backend allowlist tests with a fake verifier pass (401, 403 unverified, 403 not-allowlisted, 200); `uv sync --frozen` works; no `onolys-admin-auth` left in lock/Dockerfile/pyproject.

## Task 3 — Prod `web/src/auth` seams (behaviour-neutral)
What it is: Make prod auth reusable without behaviour change. R10c(1), Decision 17.
What changes: `AuthProvider` gets optional `onSignOut` (prod `App` passes `clearJobs`); `createFirebaseAuthService` gets an optional `emailApi` so server-sent email flows are optional. No other prod changes.
Done when: all existing `web` tests pass untouched; new tests cover `onSignOut` called on sign-out and the service working without `emailApi`.

## Task 4 — Eval web on prod login (alias, de-admin)
What it is: Eval signs in with the prod app's login, one auth copy. R10c(2-3), R10d.
What changes: Vite/tsconfig alias `@prod-auth` to `web/src/auth` (and `components/classes`), `resolve.dedupe` for react/react-dom/react-router/firebase/react-query; add matching-pinned `react-router`, `@tanstack/react-query`, `openapi-fetch` to `eval/web`. `main.tsx` builds the prod auth service with prod web-app config (auth domain `eval.onolys.com`), wraps in prod provider/guard and Login; link to app.onolys.com for signup/verify/reset. Delete eval's own `src/auth/{AuthGate,firebase,session,fakeProvider,types}`; `authFetch` takes token from prod service; add 403 "no access" screen with sign-out (no "administrator" wording); adjust `Root` wrapper line. Replace `admin.onolys.com` in `config.ts`, `hosting.test.ts`, CSP in `eval/web/firebase.json`, README.
Done when: `eval/web` `npm test`, typecheck and build pass; a test proves one copy of React/firebase in the bundle; 403 screen test passes; `web` tests still pass.

## Task 5 — Module variables, `moved` blocks, `module "eval"`
What it is: Third module instance without churn for staging/prod. R1, R2, R3, Decisions 1-6.
What changes: `env` validation adds `eval`; new module vars `eval_mode`, `runtime_env`, `eval_backend_enabled`, `eval_cors_origins`, `public_api_enabled`, `max_active_runs` with defaults equal to current behaviour; conditional env via existing `dynamic` blocks; `count` on api/api_public/voice/voice_public/voice SA+IAM with `moved` blocks; outputs via `one()`. Add root vars (`eval_worker_concurrency`=2, `eval_worker_max_instances`=4, `eval_llm_secrets`, `eval_git_sha`) and `module "eval"` (db `eval`, delete protection, alerts off, caps 1000000/1000, `runtime_env="staging"`, `public_api_enabled=false`).
Done when: `terraform fmt -check`, `init -backend=false`, `validate` pass; static tests assert defaults unchanged, `moved` blocks present, no `allUsers` on eval worker, `datastore.user` condition names db `eval`.

## Task 6 — Eval backend service, worker, queue sizing, secrets, seed script
What it is: Runtime of the eval environment. R4, R5, R6, Decisions 4, 13, 14.
What changes: `eval_backend` Cloud Run service on the module `api` SA (platform env, `CORS_ORIGINS`, `SERVICE_URL`/`TASKS_OIDC_AUDIENCE`, `EVAL_ALLOWED_EMAILS` from secret, placeholder image with `ignore_changes`, min instances 0, `allUsers` invoker); emit `DATASETS_BUCKET`, `EVAL_MAX_SESSIONS_IN_FLIGHT`, `EVAL_OWNER_UID`. Worker-eval with `EVAL_MODE=true`; queue dispatch cap = concurrency x max instances. Secret shells for eval llm/stt, `uid-hmac-key-eval`, `resend-api-key-eval`, `eval-allowed-emails-eval`. `seed-secrets.py`: `--env eval`, `--allowlist` replacing `--admin`.
Done when: static tests pass for: eval backend env has no `ADMIN_*`/`EVAL_AUTH*`; dispatch cap >= 2 x `length(eval_llm_secrets)` + 2; `seed-secrets.py` accepts `--env eval` and `--allowlist` (updated `test_seed_secrets.py`); validate passes.

## Task 7 — Remove legacy staging eval; keep datasets bucket read-only
What it is: Delete the staging-bound eval service now (single step). R7, R9, Decision 7.
What changes: Delete legacy eval-backend-staging service, queue, SAs, IAM (`eval_datastore/speech/objects/stt_uploads/provider/allowlist`), deployer grants, `eval_env`/`eval_service_url`, `eval_enabled`. `eval.tf` keeps datasets bucket `onolys-eval-data-staging` (address unchanged) plus `objectViewer` for module `eval` api SA; add Speech-agent read on `eval-uploads/` of `onolys-audio-eval` (prefix-conditioned). Hosting site/domain lose `count` gates with `moved` blocks. Update/delete `test_eval_service.py`, `test_eval_bucket.py`.
Done when: validate passes; tests assert datasets IAM is `objectViewer` only, no write grant, `moved` blocks present, legacy resources absent.

## Task 8 — Eval hosting, authorized domains, web config outputs
What it is: Eval login infra on the prod pool. R10a-b, Decision 18.
What changes: Authorized domains add `eval.onolys.com` and `onolys-eval-staging.web.app` unconditionally; no new Firebase web app; optional derived `web_env_eval` output (prod values, auth domain `eval.onolys.com`) for docs.
Done when: static tests assert both domains authorized and no `google_firebase_web_app.eval`; validate passes.

## Task 9 — Remove all admin infra, tests, docs
What it is: Zero admin left. R13, Decision 11. Runs only after Task 1 hash match and Tasks 4/6/8 are in.
What changes: Delete admin hosting sites, domain and DNS entry, admin web apps/config sources, `web_env_admin_*` outputs, admin vars, `admin_backend` service/SA/secret/IAM/invoker/outputs, deployer admin entries, `.firebaserc` admin targets, admin tests (`test_admin_env_wiring`, `test_admin_enabled_per_env`, `test_deployer_admin_iam`), admin cases in `test_custom_domain`, `test_voice_service`, `test_check_staging`; remove admin text in `docs/reference/*`. Keep the prod web app and Google `*.admin` role names.
Done when: validate and remaining infra static tests pass; `grep -rniI admin infra eval web/src/auth .github` shows only the allowed Google role names and the `admin/v2` REST path; no `admin-allowed-emails*`, `ADMIN_STAGING_*`, `admin.onolys.com`.

## Task 10 — Drop Terraform budget
What it is: Console-set limits must not be overwritten. R15, Decision 15.
What changes: Delete `google_billing_budget.monthly`, `monthly_budget_usd`, `billing_account_id`, root `data.google_project.this`; add `removed` block with `destroy = false`; keep `owner_email` channel and `alert_email`; update `docs/reference/infra.md` budget text.
Done when: static test asserts no budget/`monthly_budget_usd`/`billing_account_id` in `infra/` and the channel is still referenced by staging/prod alerts; validate passes.

## Task 11 — Deploy pipeline (workflows, firebase.json, deployer IAM)
What it is: Ship worker-eval and eval-backend by CI. R8, R11, Decisions 9, 16.
What changes: `_deploy-cloudrun.yml` accepts `eval` (deployer-staging, same digest as staging); `deploy-eval.yml` targets `onolys-eval-backend-eval`, uses `PROD_VITE_FIREBASE_{API_KEY,APP_ID}` and literal auth domain `eval.onolys.com`, deploys `firestore:eval`; `firebase.json` gains the `eval` database entry; `deployer.tf` adds `eval_services`/`eval_runtime_sas` grants and `datastore.indexAdmin` conditioned on db `eval`; update `scripts/ci/test_deploy_eval.sh`.
Done when: `test_deploy_eval.sh` and deployer static tests pass; workflow YAML lints/validates; no `ADMIN_STAGING_*` in workflows.

## Task 12 — CI wiring and final acceptance sweep
What it is: CI covers changed/new packages and the removed job. Acceptance Criteria.
What changes: `ci.yml`: remove `admin-auth` job, its `needs`, changes output and the infra step sync lines (use a surviving package if `infra/scripts` tests still need python deps); `eval-web` job installs/typechecks with prod sources; `scripts/ci/changes.sh` updates (`EVAL_WEB_EXTRA_RE` gains `web/src/auth|web/src/api/client.ts|web/src/components/classes`, drop stale `frontend/`; `eval-backend` deps become `api core miti oneshot eval`). Final sweep: confirm acceptance greps and static tests.
Done when: `changes.sh` tests pass; CI YAML valid; affected suites only (infra static tests, eval/backend, eval/web, api auth, web) green offline; terraform fmt/validate pass; no secret/email in the diff.

## Owner steps (not tasks)
1. Review; `terraform plan` (staging/prod only admin deletions + `moved` + budget `removed`; eval adds; legacy destroys; allowlist imported); then apply.
2. Seed eval provider keys: `seed-secrets.py --env eval` (values from environment).
3. After first apply: remove the temporary `import {}` block (follow-up commit).
4. Delete stale `ADMIN_STAGING_VITE_FIREBASE_*` GitHub variables (no new variables needed).
5. Console: add `https://eval.onolys.com/__/auth/handler` to the Firebase OAuth web client redirect URIs.
6. Optional: remove stale `admin.onolys.com` CNAME at the registrar.
7. Run the first eval yourself (no live LLM/STT by agents).
8. Final, after all SPs deployed: set Anthropic monthly spend limit and a Google Cloud billing budget in consoles.
9. If gcloud access is missing for Task 1: run the two R6a commands before applying.
