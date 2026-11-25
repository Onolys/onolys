# Review fixes: coordinated eval release and Speech IAM

Scope: the two deployment/infra P1 findings from the whole-branch review at `1a5c992`.

## Decisions and changes

- Make eval a callable continuation of staging, after `deploy-worker-eval`, with the staging release concurrency lock held through completion. Remove eval's independent path-gated push and dispatch entrypoints. The manual entrypoint is now `deploy-staging` on current CI-green main, documented in `docs/reference/infra.md`.
- Preserve the exact staging worker image digest. Pass that build's exact tested SHA to every eval checkout, backend build/provenance smoke and backend runtime `GIT_SHA`. Explicit runtime injection replaces Terraform's initial `unset` value.
- Add a pre-auth staging admission guard for both automatic and manual releases: current main SHA, successful exact-SHA push CI, same repository, main branch. This rejects queued older releases instead of permitting a rollback after a newer release. Existing workflow-run fork guards, staging WIF identity and environment scopes remain intact; no PR credentials or new provider secrets.
- Grant `roles/speech.client` to the eval backend's existing `api-eval` identity only, gated by `eval_backend_enabled && env == "eval"`. No staging/prod API IAM changes.

These are coordinated deployment fixes: simply writing backend `GIT_SHA` would still leave permanent drift after a worker-only update. Making the backend workflow callable also removes the independent workflows' completion-order race.

## Test-first evidence

Before implementation:

- `python3 scripts/ci/test_deploy_staging.py`: failed at missing `deploy-eval` job.
- `bash scripts/ci/test_deploy_eval.sh`: failed at missing `workflow_call` contract.
- `python3 -m pytest infra/scripts/test_eval_backend_service.py -q`: 1 failed, 11 passed; missing eval backend Speech grant.
- `node --test scripts/ci/test_verify_staging_release.cjs`: failed because the admission module did not yet exist.

After implementation:

- `bash scripts/ci/test_deploy_eval.sh`: passed Hosting/image/release guards, exact-origin substitution/rejection cases, all 6 Node admission cases, and actionlint. Node cases cover automatic/manual success; stale queued SHA; manual non-main and absent CI; failed/cancelled/foreign/PR/other-branch/wrong-SHA CI; malformed SHA/unexpected event; GitHub API failure.
- `python3 scripts/ci/test_deploy_staging.py`: passed staging configuration guard and one-lock/exact-SHA eval release contracts.
- `python3 -m pytest infra/scripts/test_eval_backend_service.py -q`: 12 passed.
- `python3 -m pytest infra/scripts/test_eval_module.py infra/scripts/test_deployer_eval_iam.py infra/scripts/test_eval_legacy_removal.py -q`: 21 passed.
- `actionlint .github/workflows/deploy-staging.yml .github/workflows/deploy-eval.yml`: passed.
- `python3 scripts/ci/test_workflow_run_guard.py`: passed fork-safety guard.
- `python3 scripts/ci/test_workflow_checkout_before_auth.py`: passed.
- `python3 scripts/ci/check_no_llm_keys_in_pr_workflows.py`: 0 LLM/STT key references in PR-triggered workflows.
- `terraform -chdir=infra fmt -check -recursive`: passed.
- `terraform -chdir=infra init -backend=false -input=false`: passed with previously installed Google/Google Beta 6.50.0 providers; no state/backend access.
- `terraform -chdir=infra validate`: configuration valid.
- `python3 scripts/ci/check_links.py`: 0 broken relative links.

## Limits and owner activation

No plan, apply, cloud deployment, live Speech/LLM call, push, or secret access performed. Static resource gating and validation support staging/prod neutrality; a real plan remains owner-only.

For first activation, drain/cancel historical runs using previous workflow definitions before starting the coordinated release. A new commit cannot retroactively change the lock held by an already running old workflow. Do not rerun historical independent eval deployments afterward. Revisions update sequentially; active evals can still fail the intentional strict drift check during a release. A failed deployment between services requires a new staging dispatch on current CI-green main after correcting the failure. The runbook records this recovery.
