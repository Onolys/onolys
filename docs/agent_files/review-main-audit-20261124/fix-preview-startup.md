# PR preview startup regression repair

Branch: `fix/review-findings`. Scope: PR #58 preview startup after the mode-aware configuration checks.

## Evidence and cause

The preview run reported that revision `onolys-api-staging-pr-58-1daef86-50-1` failed to listen on port 8080. This is deployment evidence provided by the orchestrator, not a direct inspection of container logs.

A deterministic offline reproduction ran the actual `pr_preview.sh env-overrides` helper, merged its output with a nonsecret staging configuration, and called `Settings.from_env`. Both this test and an explicit staging combined configuration failed before the repair with `ConfigError: SERVICE_MODE=combined is only allowed for local or test` (2 failed, 106 deselected). This establishes the source-level startup regression; no cloud reads, deployments, or other cloud mutations were needed.

## Change

`PR_PREVIEW=true` explicitly opts into combined mode only with staging environment, stub providers, and the staging database. Identity Platform authentication, keyed logging, and deployed project, region, bucket, and voice settings remain required. The in-process queue does not require Cloud Tasks configuration. Other deployment profiles retain their existing checks and production cannot opt into preview mode.

The preview helper sets the flag. Staging explicitly resets it to false because preview deployment merges the shared service template and the restoration workflow can be canceled. The Terraform API template also declares false, keeping that reset consistent with infrastructure configuration. Existing no-traffic, digest pinning, template restoration, and cleanup guards remain intact.

## Verification

- `/tmp/iaudit-review-venv/bin/pytest api/tests/test_config.py api/tests/test_factory.py api/tests/test_healthz_cors.py -q`: 126 passed in 1.07s. Includes actual preview-helper output loaded by Settings, startup and health response with injected offline storage, in-process queue selection, Identity Platform auth, invalid preview profiles, missing deployed dependencies, and missing/false/malformed opt-in.
- `bash scripts/ci/test_pr_preview.sh`: exit 0, including shared-template reset, no-traffic, restoration, cleanup and actionlint guards.
- `bash scripts/ci/test_deploy_prod.sh`: exit 0, including staging-image provenance and deployment guards.
- `bash scripts/ci/check_config.sh`: config guard: ok.
- `bash scripts/ci/test_check_config.sh`: all seven guard scenarios passed.
- `/tmp/iaudit-review-venv/bin/pytest scripts/ci/test_check_no_llm_keys_in_pr_workflows.py scripts/ci/test_workflow_checkout_before_auth.py scripts/ci/test_workflow_run_guard.py -q`: 5 passed in 0.18s.
- `/tmp/iaudit-review-venv/bin/ruff check api`: All checks passed!
- `actionlint .github/workflows/pr-preview.yml .github/workflows/deploy-staging.yml`: exit 0.
- `terraform fmt -check infra/modules/environment/services.tf`: exit 0.
- `git diff --check`: exit 0.

No push or manual deployment performed. Remote preview verification remains with the orchestrator after its authorized push.
