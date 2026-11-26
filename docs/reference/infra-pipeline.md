# Infra pipeline: Terraform plan on PRs, apply on merge

Nobody runs `terraform apply` by hand (manual apply is for bootstrap and break-glass only, see [ADR 0026](../decisions/0026-terraform-plan-apply-in-ci.md)). [`.github/workflows/terraform.yml`](../../.github/workflows/terraform.yml) plans every environment on each PR and applies the same saved plan after merge. The repository and its Actions logs are public, so nothing prints plan attribute values or output values.

| Environment | Terraform root | State | Plan (PR and main) | Apply (main only) |
|---|---|---|---|---|
| prod (`onolys`) | `infra/` (legacy root) | `gs://onolys-tfstate/infra` | `terraform-plan@onolys` | `terraform-apply@onolys`, only when prod has changes, after approval of GitHub Environment `terraform-prod` |
| staging (`onolys-staging`) | `infra/isolated-environment` + `examples/backend-staging.hcl.example`, `examples/environment-staging.tfvars.example` | `gs://onolys-staging-tfstate/environment` | `terraform-plan@onolys-staging` | `terraform-apply@onolys-staging`, automatic |
| eval (`onolys-eval`) | same root + `backend-eval.hcl.example`, `environment-eval.tfvars.example` | `gs://onolys-eval-tfstate/environment` | `terraform-plan@onolys-eval` | `terraform-apply@onolys-eval`, automatic |

## Flow

1. PR touching `infra/**` (or the workflow, the apply action or `scripts/ci/tf_*.py`): `fmt -check`, `validate` and `terraform test` run in `ci.yml` (jobs `infra` and `infra-isolated`, 5 minutes each, both part of the `required` gate). `terraform.yml` then runs `terraform plan` per environment in parallel (each job under 5 minutes: plugin cache, `-lockfile=readonly`, `-lock=false`) and creates or updates one PR comment listing resource addresses and actions (`delete`, `replace` and `forget` first, truncated), plus the names of changed outputs. Plan failures show a redacted error excerpt and fail the job; a failure of the summary script also fails the step. Fork PRs are skipped.
2. Merge to `main`: each environment plans again (same read-only plan identity). The saved plan is copied to the private state bucket under `plans/`; only its SHA-256 and the hash of the deploy-managed inputs travel in a run artifact (`tf-meta-<env>`). Job `gate` reads those artifacts and exposes `staging_changes`, `eval_changes` and `prod_changes`. Each apply job depends only on `gate` and on its own flag:
   - `apply-staging`, `apply-eval`: automatic when that environment has changes.
   - `apply-prod`: only when prod has changes (an unconfigured or unchanged prod never asks for approval), then waits for the `terraform-prod` environment approval.
   The environments are independent: a failed plan or apply in one does not block the others, and prod does not wait for staging or eval (separate projects and state; nothing in the prod plan reads them). Each apply downloads its plan, verifies the hash, re-reads the live deploy-managed inputs (see below), and runs `terraform apply <plan>`. A plan older than the current state is rejected by Terraform ("saved plan is stale"). The steps live in the composite action [`.github/actions/terraform-apply`](../../.github/actions/terraform-apply/action.yml) (a composite action, not a reusable workflow, because the apply identities are bound to the `terraform.yml` workflow claim and the job's Environment, which a reusable workflow would change). Apply jobs do not cancel in progress (one concurrency group per environment, 20 minute timeout: applies are deploy-style jobs, only plan jobs carry the 5 minute budget).
3. Retries: use **Re-run all jobs** (a fresh plan), never "Re-run failed jobs". The plan object is deleted after a successful apply; a failed apply keeps it for inspection, and a lifecycle rule on the state buckets deletes everything under `plans/` after 7 days (`infra/bootstrap.sh` for prod, `infra/isolated-environment/bootstrap` for staging and eval).
4. `workflow_dispatch` runs the same plan then apply, and only on `main`, for a re-run after an owner fix.

Terraform is pinned to `1.9.8` (`~> 1.9.8` in both `versions.tf`). Providers come from the committed `.terraform.lock.hcl` files. Do not make the path-filtered `terraform` plan jobs required checks: a required check that is skipped by its path filter blocks every non-infra PR. The infra safety net on PRs is the `required` gate (`infra`, `infra-isolated`) plus review of the plan comment.

## Inputs: no secrets, no local tfvars

- The gitignored operator tfvars on the ops machine are not used. Staging and eval read the versioned `examples/environment-*.tfvars.example`; prod uses the variable defaults of `infra/variables.tf` (no secrets there). The old local `resend_secret_wired = { staging = ..., prod = ... }` form no longer validates: the variable accepts only the key `prod`.
- Deploy-managed values (`git_sha`, `llm_provider`, `llm_model`, `llm_effort`) are written by the deploy workflows to the Cloud Run env, and Terraform owns the same env vars (a single env entry cannot be `ignore_changes`). `scripts/ci/tf_live_inputs.py` reads them from the live services into `live.auto.tfvars.json` before every plan, so a plan shows no spurious change. The plan job records a hash of those values in `tf-meta`; the apply job re-reads them and aborts with "re-run to re-plan" if they differ, so a deploy that lands between the plan (or the prod approval) and the apply is never rolled back. Limitation: `git_sha` is one Terraform variable per environment (shared by api, worker and voice), so it is read from the worker only (a differing api sha produces a warning); a per-service sha cannot be expressed without changing the variable. A service that does not exist yet falls back to the defaults.
- Secrets never enter Terraform: only Secret Manager references. Values are seeded out of band (`infra/scripts/seed-secrets.py`). The workflows hold no provider keys and no service account keys; auth is GitHub OIDC to Workload Identity Federation. The only runtime Python dependencies of the apply (`infra/scripts/identity-config.py`: `google-auth`, `requests`) come from `scripts/ci/tf-apply-requirements.txt` (exact versions, `--require-hashes`, installed before the cloud token exists; regenerate with `uv pip compile scripts/ci/tf-apply-requirements.in --generate-hashes --python-version 3.12 -o scripts/ci/tf-apply-requirements.txt`).

## Identities (`infra/modules/terraform-ci`)

Per project, one module call (`infra/terraform-ci.tf` for prod, `infra/isolated-environment/terraform-ci.tf` for staging and eval) creates two service accounts and two dedicated WIF pools. The pools are separate from the deployers' `github` pool because a principalSet binds every provider of its pool.

- `terraform-plan` (pool/provider `github-plan`): reachable from same-repo pull requests, so it is metadata-only. The provider admits repository `Onolys/onolys` events `pull_request`, `push` and `workflow_dispatch` whose `job_workflow_ref` starts with `Onolys/onolys/.github/workflows/terraform.yml@` (no "any event on main"). A PR can edit that workflow file, which is exactly why the identity holds no data access. Roles (all verified with `gcloud iam roles describe` and snapshotted in `infra/modules/terraform-ci/plan-role-permissions.snapshot.json`): `run.viewer`, `secretmanager.viewer` (no `versions.access`), `cloudscheduler.viewer`, `iam.serviceAccountViewer`, `iam.roleViewer`, `iam.workloadIdentityPoolViewer`, `firebasehosting.viewer`, plus a custom role of exact `get`/`list` permissions (buckets, Firestore databases/indexes, Cloud Tasks queues, Artifact Registry repositories, alert policies, notification channels, log-based metrics, Identity Platform config, Service Usage, project IAM). Deliberately excluded because they read data: `roles/viewer`, `datastore.viewer`, `firebaseauth.viewer` (`users.get`: any PR could dump all Auth users), `cloudtasks.viewer` (`tasks.get/list`: task bodies hold uid, sid, email), `iam.securityReviewer` (`logging.logEntries.list`, `storage.objects.list`, `tasks.list`), `monitoring.viewer` (`timeSeries.list`), `artifactregistry.reader` (image download). It reads state, and may only create (never overwrite or delete) objects under `plans/` in the state bucket. If a first plan reports a missing read permission, add it through `plan_extra_permissions` (get/list only, validated) in the module call, never a broad role.
- `terraform-apply` (pool/provider `github-apply`): effectively project admin (IAM, WIF, Cloud Run, Firestore, secrets, Hosting; `projectIamAdmin` can grant itself anything). The control is who can impersonate it: the provider admits only repository `Onolys/onolys`, `refs/heads/main`, events `push` or `workflow_dispatch`, and `job_workflow_ref == Onolys/onolys/.github/workflows/terraform.yml@refs/heads/main`; for prod it additionally requires `assertion.environment == 'terraform-prod'`, so the cloud token itself needs the reviewer approval. The service account binding is the principalSet `attribute.workflow_ref/<that ref>`. The deployers' providers and bindings are untouched.
- Both service accounts and WIF names are derived deterministically (`scripts/ci/tf_identity.py`): the provider is the existing `WIF_PROVIDER` / `STAGING_WIF_PROVIDER` / `EVAL_WIF_PROVIDER` value with `github` replaced by `github-plan` / `github-apply`, the account is `terraform-<kind>@<project>.iam.gserviceaccount.com`.
- Resource coverage: `infra/modules/terraform-ci/resource-permissions.json` maps every `google_*` resource and data type in both roots to the plan permission and the apply role/permission that cover it; `infra/scripts/test_terraform_ci_permissions.py` fails when a type is unmapped, when a plan permission is not granted, when a data-read permission (denylist) appears in the plan roles, or when an apply role lacks a mapped permission. Add a row when adding a resource type.
- No service account keys exist (a test enforces it).

## Bootstrap (one time, from an operator machine)

Prerequisite check (done 2026-11-26 with a read-only `terraform plan -lock=false`, operator tfvars): the pending legacy destroy of the old staging/eval resources in `infra/` is complete. The prod plan then showed only the 40 `module.terraform_ci` creates and no other change. Re-check before the first apply: the plan of `infra/` must show nothing outside `module.terraform_ci`, otherwise the first CI apply would also run the legacy destroy (see [isolated environments](../implementation/isolated-environments.md)).

The identities must exist before the workflow can authenticate, so their first apply is manual and targeted. Initialize each root as described in [isolated environments](../implementation/isolated-environments.md), use the operator tfvars, review the plan, then:

```bash
# prod (infra/)
terraform -chdir=infra apply -var-file=<legacy tfvars> -target=module.terraform_ci
# staging, eval (infra/isolated-environment, matching backend and TF_DATA_DIR)
terraform -chdir=infra/isolated-environment apply -var-file=<env tfvars> -target=module.terraform_ci
# state buckets: 7-day lifecycle for plans/ (prod: re-run the idempotent script; staging/eval: apply the bootstrap root)
bash infra/bootstrap.sh
terraform -chdir=infra/isolated-environment/bootstrap apply
```

Targeted applies are for this bootstrap only. Then set the repository **variables** (Settings, Secrets and variables, Actions, Variables). The deploy variables `WIF_PROVIDER`, `STAGING_WIF_PROVIDER` and `EVAL_WIF_PROVIDER` already exist and are reused; the only new variables are the enable flags:

```bash
gh variable set TF_STAGING_ENABLED --body true
gh variable set TF_EVAL_ENABLED --body true
gh variable set TF_PROD_ENABLED --body true   # last, after the terraform-prod environment exists
```

While a flag is not `true`, that environment's plan is skipped with a notice and nothing is applied (merging before bootstrap breaks nothing).

## Owner steps

- Create the GitHub Environment **`terraform-prod`** (separate from `production`, which gates app deploys), with required reviewers, no self-review, and deployment branches limited to `main`. Without it the prod apply job cannot get a cloud token (the provider requires the environment claim). With `gh` (replace the user id; `gh api users/<login> --jq .id`):

  ```bash
  gh api -X PUT repos/Onolys/onolys/environments/terraform-prod --input - <<'JSON'
  {"prevent_self_review": true,
   "reviewers": [{"type": "User", "id": 0}],
   "deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
  JSON
  gh api -X POST repos/Onolys/onolys/environments/terraform-prod/deployment-branch-policies -f name=main -f type=branch
  ```

- The `production` environment is unchanged and no longer authorizes Terraform applies.
- Review the apply role list in `infra/modules/terraform-ci/variables.tf` once; it is broad by necessity.

## Run a plan locally (read-only)

```bash
export TF_DATA_DIR="$HOME/.cache/onolys-terraform/staging"   # one directory per environment
terraform -chdir=infra/isolated-environment init -backend-config=examples/backend-staging.hcl.example
terraform -chdir=infra/isolated-environment plan -lock=false -var-file=examples/environment-staging.tfvars.example
```

For prod, run in `infra/` (no backend flag). Pass the live `git_sha` and `llm_*` as described in [infra.md](infra.md) or generate them with `python3 scripts/ci/tf_live_inputs.py --root legacy --env prod --project onolys --out infra/live.auto.tfvars.json` (delete it afterwards). To inspect the saved plan of a run before approving prod: `gcloud storage cp gs://onolys-tfstate/plans/<run_id>-<attempt>-prod.tfplan . && terraform -chdir=infra show <file>` (plan files hold variable values: keep them private).

## Tests

`scripts/ci/test_terraform_pipeline.py` (workflow and composite action contract: triggers, per-env gating, `environment: terraform-prod`, pinned action SHAs, `id-token: write` only where needed, concurrency, no keys, hash-pinned deps, drift guard, summary, identity and live-input helpers), `infra/scripts/test_terraform_ci.py` (module wiring, pool conditions, lifecycle), `infra/scripts/test_terraform_ci_permissions.py` (resource-to-permission table, no data-read permission in the plan roles), `infra/isolated-environment/tests/isolation.tftest.hcl` (mocked plan), `scripts/ci/test_changes.sh` (infra gate) and `actionlint`.
