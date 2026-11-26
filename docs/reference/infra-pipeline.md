# Infra pipeline: Terraform plan on PRs, infra applied inside each deploy

Nobody runs `terraform apply` by hand (manual apply is for bootstrap and break-glass only, see [ADR 0026](../decisions/0026-terraform-plan-apply-in-ci.md)). Pull requests get a read-only plan. Infrastructure changes are applied by the deploy pipeline of each environment, in the same run as the app and before it: **infra plan at the commit being deployed, infra apply only if that plan has changes, then the app deploy**. So the infrastructure an app version needs is always in place before that version runs, and a rollback takes the infrastructure back with the app. The repository and its Actions logs are public, so nothing prints plan attribute values or output values.

| Environment | Terraform root and state | Pipeline (trigger) | Approval |
|---|---|---|---|
| staging (`onolys-staging`) | `infra/isolated-environment` + `examples/backend-staging.hcl.example`, `examples/environment-staging.tfvars.example`; `gs://onolys-staging-tfstate/environment` | [`deploy-staging.yml`](../../.github/workflows/deploy-staging.yml): automatic after CI passes on `main` (`workflow_run`), or dispatch on `main` | none |
| eval (`onolys-eval`) | same root + `backend-eval.hcl.example`, `environment-eval.tfvars.example`; `gs://onolys-eval-tfstate/environment` | [`deploy-eval.yml`](../../.github/workflows/deploy-eval.yml): automatic after CI passes on `main` (`workflow_run`), or dispatch on `main`, like staging | none |
| prod (`onolys`) | `infra/` (legacy root); `gs://onolys-tfstate/infra` | [`deploy-prod.yml`](../../.github/workflows/deploy-prod.yml): dispatch on `main` (release, promote, rollback by `sha` or `version`) or a pushed `v*` tag | GitHub Environment `production` (required reviewer): one click for infra and app |

## Pull requests

PRs touching `infra/**` (or the plan/apply actions, `terraform.yml`, `scripts/ci/tf_*.py`): `fmt -check`, `validate` and `terraform test` run in `ci.yml` (jobs `infra` and `infra-isolated`, 5 minutes each, part of the `required` gate). [`terraform.yml`](../../.github/workflows/terraform.yml) then plans every environment in parallel (each job under 5 minutes: plugin cache, `-lockfile=readonly`, `-lock=false`) and creates or updates one PR comment listing resource addresses and actions (`delete`, `replace` and `forget` first, truncated) plus the names of changed outputs. A failed plan shows a redacted error excerpt and fails its job. Fork PRs are skipped. Nothing is applied from a PR. `workflow_dispatch` on `main` runs the same read-only plans (results in the run summary), for example to look for drift. Do not make the path-filtered plan jobs required checks: a required check that its path filter skips blocks every non-infra PR.

## Deploy pipelines

Each deploy workflow has two infra jobs, both built from shared composite actions ([`terraform-plan`](../../.github/actions/terraform-plan/action.yml), [`terraform-apply`](../../.github/actions/terraform-apply/action.yml)):

1. **`infra-plan`** runs after the job that admits the release (`build` for staging and eval, `resolve` for prod). It checks out the workflow's own ref (helper scripts, actions) and, under `target/`, the commit being deployed (its Terraform files only), reads the live deploy-managed inputs (below), plans, and writes the per-resource summary to the job summary. A plan with changes is copied to the private state bucket under `plans/`; only its SHA-256, object name and the hash of the live inputs travel, as job outputs. Read-only identity, no approval, 5 minutes.
2. **`infra-apply`** runs only when that plan has changes. It re-checks the live inputs, downloads the saved plan, verifies its hash and runs `terraform apply <plan>` (Terraform rejects a plan older than the current state: "saved plan is stale"). The saved plan is deleted after a successful apply. 20 minutes (deploy-style job).
3. **App jobs** (unchanged steps) then run. Every job after the infra jobs uses `if: ${{ !cancelled() && ... }}` with an explicit `needs.<job>.result` check for each need: `success` for app jobs, `success` or `skipped` for the infra jobs. (The default `success()` would skip the app whenever an infra job is skipped, and `always()` would deploy after a failed apply.)

| Situation | Infra jobs | App deploy |
|---|---|---|
| `TF_<ENV>_ENABLED` not `true` (today) | both skipped | runs exactly as before this pipeline |
| plan has no changes | apply skipped | runs |
| plan has changes | apply runs first | runs after a successful apply |
| plan fails, or is blocked (below) | apply skipped | does not run |
| apply fails | | does not run (prod: the app jobs fail in their wait step; nothing is deployed and no `prod-*` tag is created) |

**Prod: one approval.** GitHub asks for approval each time a job that references a protected environment starts; jobs that are waiting at the same moment are approved with one click (the existing app jobs already rely on this). So `infra-apply` and the five app jobs (api, worker, voice, rules, web) all reference `production` and all have the same `needs` (`resolve`, `infra-plan`): they wait together and one click releases infra and app. Ordering cannot use `needs` (an app job that started after `infra-apply` would ask a second time), so each app job's first step, after approval, polls this run's job list (`GITHUB_TOKEN`, `actions: read`) until the job named `infra-apply` has finished: success, continue; anything else, fail without deploying. That step runs only when the plan has changes; with no changes `infra-apply` is skipped and needs no approval. Rejecting the review rejects infra and app together. The reviewer reads the plan in the `infra-plan` job summary before clicking. The waiting app jobs hold a runner for up to 25 minutes (their timeouts grow by 25 minutes only when they wait). The WIF conditions are unchanged by this: the apply identity still requires a `production` job of `deploy-prod.yml`.

**Prod promote and rollback** (`sha` or `version` input, or a `v*` tag) plan and apply the infrastructure of the target commit too. Before approving a rollback, read the plan: it undoes infrastructure added after that commit. A plan that destroys or forgets anything in `module.terraform_ci` (the pipeline's own identities, e.g. a rollback to a commit from before this pipeline) is **blocked**: the plan job fails and nothing deploys. To roll back the app only in that case, set `TF_PROD_ENABLED` to anything but `true` for that run, then back; or apply by hand (break-glass).

**Retries:** use **Re-run all jobs** (a fresh plan), never "Re-run failed jobs". A failed apply keeps its saved plan for inspection; a lifecycle rule on the state buckets deletes everything under `plans/` after 7 days (`infra/bootstrap.sh` for prod, `infra/isolated-environment/bootstrap` for staging and eval). No plan travels in a run artifact; the PR comment's summary artifacts are kept 7 days.

Why composite actions, not a reusable workflow: the apply identity's WIF provider matches the OIDC claim `job_workflow_ref`, which for a job of a reusable workflow names the reusable file, not the deploy workflow. Composite actions keep the claim on `deploy-<env>.yml`.

## Inputs: no secrets, no local tfvars

- The gitignored operator tfvars on the ops machine are not used. Staging and eval read the versioned `examples/environment-*.tfvars.example`; prod uses the variable defaults of `infra/variables.tf` (no secrets there). The examples must match live: on 2026-11-26 staging's example said `resend_secret_wired = false` while live staging has `RESEND_API_KEY` wired on api and worker (`resend-api-key-staging`, checked with `gcloud run services describe`); it now says `true`. Eval's example matched (no Resend wiring). The old local `resend_secret_wired = { staging = ..., prod = ... }` form no longer validates: the legacy variable accepts only the key `prod`.
- Deploy-managed values (`git_sha`, `llm_provider`, `llm_model`, `llm_effort`) are written by the deploy workflows to the Cloud Run env, and Terraform owns the same env vars (a single env entry cannot be `ignore_changes`). `scripts/ci/tf_live_inputs.py` reads them from the live services into `live.auto.tfvars.json` before every plan, so a plan shows no spurious change. In a deploy run the infra jobs read the values of the previous deploy; the app jobs of the same run then set the new ones. Limitation: `git_sha` is one Terraform variable per environment (shared by api, worker and voice), so it is read from the worker only (a differing api sha produces a warning). A service that does not exist yet falls back to the defaults.
- **Drift guard (kept).** The plan records a hash of those live values; the apply re-reads them and aborts with "re-run to re-plan" if they differ, so a change that landed between plan and apply is never rolled back. Within one environment, deploy runs no longer race: each deploy workflow has one concurrency group (`deploy-staging`, `deploy-eval`, `deploy-prod`, never cancelling a running deploy), and the app jobs of the same run start only after the apply. What can still land in between, mostly during a long prod approval wait, is a change outside the pipeline: a manual `gcloud run deploy` or `gcloud run services update` (break-glass). PR previews (`pr-preview.yml`) change the staging api's template but not the values read (the worker's `GIT_SHA`, the api's `LLM_*`). The check is cheap, so it stays as defence in depth rather than the primary guard.
- Secrets never enter Terraform: only Secret Manager references. Values are seeded out of band (`infra/scripts/seed-secrets.py`). The workflows hold no provider keys and no service account keys; auth is GitHub OIDC to Workload Identity Federation. The only runtime Python dependencies of the prod apply (`infra/scripts/identity-config.py`: `google-auth`, `requests`) come from `scripts/ci/tf-apply-requirements.txt` (exact versions, `--require-hashes`, installed before the cloud token exists; regenerate with `uv pip compile scripts/ci/tf-apply-requirements.in --generate-hashes --python-version 3.12 -o scripts/ci/tf-apply-requirements.txt`).

## Identities (`infra/modules/terraform-ci`)

Per project, one module call (`infra/terraform-ci.tf` for prod, `infra/isolated-environment/terraform-ci.tf` for staging and eval) creates two service accounts and two dedicated WIF pools. The pools are separate from the deployers' `github` pool because a principalSet binds every provider of its pool.

- **`terraform-plan`** (pool/provider `github-plan`): reachable from same-repo pull requests, so it is metadata-only. Its provider admits repository `Onolys/onolys` jobs of `terraform.yml` for `pull_request` and `workflow_dispatch`, and jobs of the project's deploy workflow for its trigger events (prod `deploy-prod.yml`: `push`, `workflow_dispatch`; staging/eval `deploy-<env>.yml`: `workflow_run`, `workflow_dispatch`). A PR can edit a workflow file, which is exactly why the identity holds no data access. Roles (all verified with `gcloud iam roles describe` and snapshotted in `infra/modules/terraform-ci/plan-role-permissions.snapshot.json`): `run.viewer`, `secretmanager.viewer` (no `versions.access`), `cloudscheduler.viewer`, `iam.serviceAccountViewer`, `iam.roleViewer`, `iam.workloadIdentityPoolViewer`, `firebasehosting.viewer`, plus a custom role of exact `get`/`list` permissions (buckets, Firestore databases/indexes, Cloud Tasks queues, Artifact Registry repositories, alert policies, notification channels, log-based metrics, Identity Platform config, Service Usage, project IAM). Deliberately excluded because they read data: `roles/viewer`, `datastore.viewer`, `firebaseauth.viewer` (`users.get`: any PR could dump all Auth users), `cloudtasks.viewer` (`tasks.get/list`: task bodies hold uid, sid, email), `iam.securityReviewer` (`logging.logEntries.list`, `storage.objects.list`, `tasks.list`), `monitoring.viewer` (`timeSeries.list`), `artifactregistry.reader` (image download). It reads state, and may only create (never overwrite or delete) objects under `plans/` in the state bucket. If a plan reports a missing read permission, add it through `plan_extra_permissions` (get/list only) or `plan_extra_roles` (`*.viewer` roles only) in the module call, never a broad role. Both are validated against [`plan-deny.json`](../../infra/modules/terraform-ci/plan-deny.json) (data-read permissions such as `datastore.entities.*`, `storage.objects.*`, `firebaseauth.users.*`, `cloudtasks.tasks.*`, `logging.logEntries.*`, `secretmanager.versions.access`, and the data-reading viewer roles), the same list the permission tests use.
- **`terraform-apply`** (pool/provider `github-apply`): effectively project admin (IAM, WIF, Cloud Run, Firestore, secrets, Hosting; `projectIamAdmin` can grant itself anything). The control is who can impersonate it. The provider admits only repository `Onolys/onolys` and the project's own deploy workflow:
  - staging, eval: `job_workflow_ref == Onolys/onolys/.github/workflows/deploy-<env>.yml@refs/heads/main`, `ref == refs/heads/main`, events `workflow_run` or `workflow_dispatch`. A `workflow_run` job's token carries `ref` = the default branch and `job_workflow_ref` = the deploy file at `refs/heads/main` (the staging deployer provider already relies on `ref == refs/heads/main` for these runs). Binding: principalSet `attribute.workflow_ref/<that ref>`.
  - prod: `job_workflow_ref` = `deploy-prod.yml@refs/heads/main` or `deploy-prod.yml@refs/tags/v...`, `ref` = `refs/heads/main` or `refs/tags/v...`, events `push` (tags) or `workflow_dispatch`, and `environment == 'production'`. Because the tag ref varies, the binding is the principalSet `attribute.repository/Onolys/onolys` of this dedicated single-provider pool, and the provider condition is the gate.
  - The `environment` claim proves the job ran in `production`; the reviewer requirement is the environment's protection rule, an owner setting (GitHub would create an unknown environment automatically, without protection, the first time a job names it; `production` exists and is protected: required reviewer, deployment refs `main` and `v*` tags, verified 2026-11-26). Keep that rule in place: without it the condition still passes.
  - A `v*` tag can be pushed by anyone with write access onto any commit, and its run uses that commit's workflow file; the same is true of the existing prod app deployer. The approval is the control, and `resolve` refuses any commit whose image never ran on staging.
- Both service accounts and WIF names are derived deterministically (`scripts/ci/tf_identity.py`): the provider is the existing `WIF_PROVIDER` / `STAGING_WIF_PROVIDER` / `EVAL_WIF_PROVIDER` value with `github` replaced by `github-plan` / `github-apply`, the account is `terraform-<kind>@<project>.iam.gserviceaccount.com`. The deployers' providers and bindings are untouched.
- Resource coverage: `infra/modules/terraform-ci/resource-permissions.json` maps every `google_*` resource and data type in both roots to the plan permission and the apply role/permission that cover it; `infra/scripts/test_terraform_ci_permissions.py` fails when a type is unmapped, when a plan permission is not granted, when a denied permission appears in the plan roles, or when an apply role lacks a mapped permission. Add a row when adding a resource type.
- No service account keys exist (a test enforces it).

## Owner setup, in order

Until the last step nothing infra runs: deploys behave exactly as before and PR plan comments say "Not configured" for each environment.

1. **Prerequisite read-only plans** (operator machine, `-lock=false`, see "Run a plan locally" below). Each must show changes **only** in `module.terraform_ci` (its creates); anything else would be applied by the first pipeline run of that environment:
   - prod, `infra/` with the variable defaults plus the live `git_sha` / `llm_*` (`tf_live_inputs.py`, below). Done 2026-11-26 with the operator tfvars: only the 40 `module.terraform_ci` creates (the legacy destroy of the old staging/eval resources is complete, see [isolated environments](../implementation/isolated-environments.md)). Re-check before bootstrap, now with the defaults CI uses.
   - staging and eval, `infra/isolated-environment` with **the example tfvars CI uses** (`examples/environment-<env>.tfvars.example`) and the live `git_sha` / `llm_*`, not the operator's own tfvars. Fix the example (in a PR) if the plan shows any other change.
2. **Bootstrap the identities** (one-time targeted applies; the identities must exist before CI can authenticate). Initialize each root as described in [isolated environments](../implementation/isolated-environments.md), review the plan, then:

   ```bash
   # prod (infra/)
   terraform -chdir=infra apply -var-file=<legacy tfvars> -target=module.terraform_ci
   # staging, eval (infra/isolated-environment, matching backend and TF_DATA_DIR)
   terraform -chdir=infra/isolated-environment apply -var-file=<env tfvars> -target=module.terraform_ci
   # state buckets: 7-day lifecycle for plans/ (prod: re-run the idempotent script; staging/eval: apply the bootstrap root)
   bash infra/bootstrap.sh
   terraform -chdir=infra/isolated-environment/bootstrap apply
   ```

   Targeted applies are for this bootstrap only.
3. **Check the `production` environment** (Settings, Environments): required reviewer, deployment branches and tags limited to `main` and `v*`. Already so on 2026-11-26; nothing else to create (no separate infra environment).
4. **Enable, one environment at a time, last.** The deploy variables `WIF_PROVIDER`, `STAGING_WIF_PROVIDER`, `EVAL_WIF_PROVIDER` already exist and are reused; the only new variables are the flags:

   ```bash
   gh variable set TF_STAGING_ENABLED --body true   # next staging deploy plans (and applies if needed) before the app
   gh variable set TF_EVAL_ENABLED --body true
   gh variable set TF_PROD_ENABLED --body true      # last
   ```

   After each, open or update an `infra/` PR to see that environment's plan comment, and watch its next deploy run.
5. Review the apply role list in `infra/modules/terraform-ci/variables.tf` once; it is broad by necessity.

## Run a plan locally (read-only)

```bash
export TF_DATA_DIR="$HOME/.cache/onolys-terraform/staging"   # one directory per environment
python3 scripts/ci/tf_live_inputs.py --root isolated --env staging --project onolys-staging --out infra/isolated-environment/live.auto.tfvars.json
terraform -chdir=infra/isolated-environment init -backend-config=examples/backend-staging.hcl.example
terraform -chdir=infra/isolated-environment plan -lock=false -var-file=examples/environment-staging.tfvars.example
rm infra/isolated-environment/live.auto.tfvars.json
```

For prod, run in `infra/` (no backend flag) after `python3 scripts/ci/tf_live_inputs.py --root legacy --env prod --project onolys --out infra/live.auto.tfvars.json` (delete it afterwards). To inspect a saved plan of a run before approving prod: `gcloud storage cp gs://onolys-tfstate/plans/<run_id>-<attempt>-prod.tfplan . && terraform -chdir=infra show <file>` (plan files hold variable values: keep them private).

Terraform is pinned to `1.9.8` (`~> 1.9.8` in both `versions.tf`). Providers come from the committed `.terraform.lock.hcl` files.

## Tests

`scripts/ci/test_terraform_pipeline.py` (terraform.yml is plan-only; plan/apply action contract; per deploy workflow: infra jobs, explicit `!cancelled()` and per-need result checks, scenarios evaluated from the real `if:` expressions (disabled, no changes, changes, failed plan, failed apply), prod one-approval structure and the wait step's behaviour; pinned action SHAs, no keys, drift guard, summary and protected-identity guard, identity and live-input helpers), `scripts/ci/test_deploy_prod.sh`, `test_deploy_eval.sh`, `test_deploy_staging.py`, `test_release_targets.py`, `infra/scripts/test_terraform_ci.py` (module wiring, provider conditions, lifecycle), `infra/scripts/test_terraform_ci_permissions.py` (resource-to-permission table, shared deny list), `infra/isolated-environment/tests/isolation.tftest.hcl` and `terraform_ci.tftest.hcl` (mocked plans: staging, eval and prod provider conditions and bindings, `plan_extra_*` deny validations), `scripts/ci/test_changes.sh` (infra gate) and `actionlint`.
