# Infra pipeline: Terraform plan on PRs, apply on merge

Nobody runs `terraform apply` by hand. [`.github/workflows/terraform.yml`](../../.github/workflows/terraform.yml) plans every environment on each PR and applies the same saved plan after merge. The repository and its Actions logs are public, so nothing prints plan attribute values or output values.

| Environment | Terraform root | State | Plan (PR and main) | Apply (main only) |
|---|---|---|---|---|
| prod (`onolys`) | `infra/` (legacy root) | `gs://onolys-tfstate/infra` | `terraform-plan@onolys` | `terraform-apply@onolys`, after approval of GitHub Environment `production` |
| staging (`onolys-staging`) | `infra/isolated-environment` + `examples/backend-staging.hcl.example`, `examples/environment-staging.tfvars.example` | `gs://onolys-staging-tfstate/environment` | `terraform-plan@onolys-staging` | `terraform-apply@onolys-staging`, automatic |
| eval (`onolys-eval`) | same root + `backend-eval.hcl.example`, `environment-eval.tfvars.example` | `gs://onolys-eval-tfstate/environment` | `terraform-plan@onolys-eval` | `terraform-apply@onolys-eval`, automatic |

## Flow

1. PR touching `infra/**` (or the workflow or `scripts/ci/tf_*.py`): `fmt -check`, `validate` and `terraform test` run in `ci.yml` (job `infra`, part of the `required` gate). `terraform.yml` then runs `terraform plan` per environment in parallel (each job under 5 minutes: plugin cache, `-lockfile=readonly`, `-lock=false`) and creates or updates one PR comment listing resource addresses and actions (`delete` and `replace` first, truncated), plus the names of changed outputs. Plan failures show a redacted error excerpt and fail the job. Fork PRs are skipped.
2. Merge to `main`: each environment plans again (same read-only plan identity), the saved plan is copied to the private state bucket under `plans/` and only its SHA-256 travels in a run artifact. `apply-nonprod` (staging and eval) downloads that plan, verifies the hash and runs `terraform apply <plan>`. `apply-prod` waits for the `production` environment approval, then does the same. A plan older than the current state is rejected by Terraform ("saved plan is stale"): re-run the workflow. Apply jobs do not cancel in progress (one concurrency group per environment, 20 minute timeout: applies are deploy-style jobs, only plan jobs carry the 5 minute budget). The plan object is deleted after apply.
3. `workflow_dispatch` on `main` runs the same plan then apply, for a re-run after an owner fix.

Terraform is pinned to `1.9.8` (`~> 1.9.8` in both `versions.tf`). Providers come from the committed `.terraform.lock.hcl` files.

## Inputs: no secrets, no local tfvars

- The gitignored operator tfvars on the ops machine are not used. Staging and eval read the versioned `examples/environment-*.tfvars.example`; prod uses the variable defaults of `infra/variables.tf` (no secrets there). The old local `resend_secret_wired = { staging = ..., prod = ... }` form no longer validates: the variable accepts only the key `prod`.
- Deploy-managed values (`git_sha`, `llm_provider`, `llm_model`, `llm_effort`) are written by the deploy workflows to the Cloud Run env, and Terraform owns the same env vars (a single env entry cannot be `ignore_changes`). `scripts/ci/tf_live_inputs.py` reads them from the live `onolys-worker-<env>` / `onolys-api-<env>` services into `live.auto.tfvars.json` before every plan, so a plan shows no spurious change and an apply never resets a deployed commit. A service that does not exist yet falls back to the defaults. A deploy that lands between the plan and the approved apply can be rolled back by that apply: approve promptly or re-run.
- Secrets never enter Terraform: only Secret Manager references. Values are seeded out of band (`infra/scripts/seed-secrets.py`). The workflows hold no provider keys and no service account keys; auth is GitHub OIDC to Workload Identity Federation.

## Identities (`infra/modules/terraform-ci`)

Per project, one module call (`infra/terraform-ci.tf` for prod, `infra/isolated-environment/terraform-ci.tf` for staging and eval) creates:

- `terraform-plan`: metadata-only. Bound through its own pool `github-plan` (provider admits repository `Onolys/onolys` events `pull_request` and pushes to `refs/heads/main`). Roles are read-only service viewers plus a custom role of `get`/`list` permissions; it deliberately has no `roles/viewer` or `roles/datastore.viewer`, which could read Firestore documents and audio objects, because any same-repo PR workflow can obtain it. It reads state, and may only create (never overwrite or delete) objects under `plans/` in the state bucket. If a first plan reports a missing read permission, add the role through `plan_extra_roles` in the module call.
- `terraform-apply`: effectively project admin (it manages IAM, WIF, Cloud Run, Firestore, secrets, Hosting; `projectIamAdmin` can grant itself anything). The control is who can impersonate it: staging and eval only `refs/heads/main` inside the existing main-only `github` pool; prod only jobs in the `production` Environment (the same selector as `deployer-prod`, in the existing `github` pool, whose provider is pinned to the repository). The `production` environment already restricts deployment branches to `main` and `v*`.
- No service account keys exist (a test enforces it).

## Bootstrap (one time, from an operator machine)

The identities must exist before the workflow can authenticate, so the first apply of these resources is manual and targeted. Initialize each root as described in [isolated environments](../implementation/isolated-environments.md), use the operator tfvars, review the plan, then:

```bash
# prod (infra/)
terraform -chdir=infra apply -var-file=<legacy tfvars> -target=module.terraform_ci
# staging, eval (infra/isolated-environment, matching backend and TF_DATA_DIR)
terraform -chdir=infra/isolated-environment apply -var-file=<env tfvars> -target=module.terraform_ci
```

Targeted applies are for this bootstrap only. Then set the repository variables from `terraform output -json terraform_ci` of each root (Settings, Secrets and variables, Actions, Variables):

| Variable | Value |
|---|---|
| `TF_<ENV>_PLAN_WIF_PROVIDER`, `TF_<ENV>_PLAN_SA` | `plan_wif_provider`, `plan_service_account` |
| `TF_<ENV>_APPLY_WIF_PROVIDER`, `TF_<ENV>_APPLY_SA` | `apply_wif_provider`, `apply_service_account` |

`<ENV>` is `PROD`, `STAGING` or `EVAL`. While a variable pair is unset, that environment's plan is skipped with a notice and its apply is skipped with a warning (so merging before bootstrap does not break anything, and nothing is applied either).

## Owner steps

- GitHub, Settings, Environments, `production`: keep **Required reviewers** set (it is, with deployment branches `main` and `v*`). That approval is what authorizes a prod apply; it is shared with `deploy-prod`.
- Optionally make the `terraform` plan jobs required checks in branch protection (they are separate from the `required` aggregator in `ci.yml`).
- Review the apply role list in `infra/modules/terraform-ci/variables.tf` once; it is broad by necessity.

## Run a plan locally (read-only)

```bash
export TF_DATA_DIR="$HOME/.cache/onolys-terraform/staging"   # one directory per environment
terraform -chdir=infra/isolated-environment init -backend-config=examples/backend-staging.hcl.example
terraform -chdir=infra/isolated-environment plan -lock=false -var-file=examples/environment-staging.tfvars.example
```

For prod, run in `infra/` (no backend flag). Pass the live `git_sha` and `llm_*` as described in [infra.md](infra.md) or generate them with `python3 scripts/ci/tf_live_inputs.py --root legacy --env prod --project onolys --out infra/live.auto.tfvars.json` (delete it afterwards). To inspect the saved plan of a run before approving prod: `gcloud storage cp gs://onolys-tfstate/plans/<run_id>-<attempt>-prod.tfplan . && terraform -chdir=infra show <file>` (plan files hold variable values: keep them private).

## Tests

`scripts/ci/test_terraform_pipeline.py` (workflow contract: triggers, `environment: production`, pinned action SHAs, `id-token: write` only where needed, concurrency, no keys, summary and live-input helpers), `infra/scripts/test_terraform_ci.py` (module wiring), `infra/isolated-environment/tests/isolation.tftest.hcl` (mocked plan), `scripts/ci/test_changes.sh` (infra gate) and `actionlint`.
