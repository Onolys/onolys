---
status: draft
summary: One Terraform root with per-env folders, Firebase config in firebase/, runtime YAML beside tfvars, infra tests 19 to 3; 12 tasks, agent runs plan then apply, moved blocks removed after.
date: 2026-11-28
---
# Tasks: 09 Infra per environment

Source of truth: /root/projects/onolys/onolys/.worktrees/refactor/revamp/docs/agent_files/refactor-revamp-20261128-0102/09-infra-per-env/PRD.md. Runs last (01 → 03 → 04 → 06 → 09; 02 supplies the Auth emulator block, 08 is a soft consumer of `firebase/`). One commit per task; after each batch run `terraform validate/test`, impacted pytest, `actionlint`, `check_config.sh`. CI applies nothing; only the agent applies (Tasks 10-11). Firebase path resolution follows the owner's spike-4 decision (default: `--config firebase/firebase.json` resolves rules/indexes beside the config). Full suite runs only in dev-ship.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Move Firebase config to `firebase/`; repoint emulator and deploy commands (R6) | none | todo |
| 2 | Move runtime YAML to `infra/<env>/`; Dockerfile, dockerignore, loader/test paths, `check_config.sh` (R5) | none | todo |
| 3 | Module cleanup: drop eval-tool inputs and resources (R4) | none | todo |
| 4 | Derive the address table and env-difference inventory (R2, R3) | 3 | todo |
| 5 | Merge into one root with env folders, `tf.sh`, `state_identity` (R1, R2) | 3, 4 | todo |
| 6 | `moved` blocks, `identity-config.py` cleanup, staging identity provisioner (R3, O4) | 5 | todo |
| 7 | `terraform test`: merge isolation tests, port 3 security checks (R7) | 5 | todo |
| 8 | Script and test pruning; delete bootstrap, install-tools, examples (R7) | 7 | todo |
| 9 | Infra CI job and path filters (R8) | 1, 2, 7, 8 | todo |
| 10 | Pre-apply state checks and plan gate, staging then prod (Manual steps 1-3) | 6, 9 | todo |
| 11 | Apply staging then prod; second plan empty; deploy-staging check (steps 4-5) | 10 | todo |
| 12 | Follow-up: delete moved blocks and hand-over leftovers; acceptance sweep (R3, R9, AC1-7) | 11 | todo |

## Task 1 — Firebase config to `firebase/`
What it is / what it means: Firebase config is in six places with two emulator ports; it becomes one folder and one config (PRD R6, D9-D11).
What changes at a high level: `git mv` `firestore.rules`, `api/firestore.indexes.json`, `firestore-rules-test/` into `firebase/` (rules-test, default port 8080). Write one `firebase/firebase.json`: `(default)` and `staging` databases, emulators Firestore 8080 + Auth 9099 (carrying 02's Auth block), ui off, no `eval` entry. Delete root `firebase.json`, `.firebaserc`, `api/firebase.json`. Repoint every `--config` in CI `api-emulator`, `api-flaky`, `api-rules`, `nightly.yml`, `deploy-prod`, `deploy-staging`, and 08's web/api emulator commands; update `.dockerignore` and path filters to `firebase/`. If spike 4 failed, apply the owner's decision.
Done when: `firebase emulators:exec --config firebase/firebase.json --only firestore,auth` runs the api emulator tests and `rules-test` green; `actionlint` clean; grep for `api/firebase.json|firestore-rules-test` outside `docs/` is 0.

## Task 2 — Runtime YAML into env folders
What it is / what it means: Per-env YAML sits far from its tfvars; it moves next to them while the image keeps `/app/config/<env>/` so no Cloud Run env var changes (R5, D6-D8).
What changes at a high level: `git mv` `config/{prod,staging}/*.yaml` to `infra/{prod,staging}/` (04 owns `routes.yaml` content; only move it) and `config/models.yaml` to `infra/models.yaml`; delete `config/`. `api/Dockerfile` COPY lines read from `infra/` into the unchanged image paths; `.dockerignore` re-includes `infra/models.yaml` and `infra/*/*.yaml`. Repoint dev/test default paths (`models.py`, `probe_llm.py`, ~12 tests) to `infra/<env>/...` through one helper per package. `check_config.sh` checks the new repo paths and the unchanged image paths, adding `voice_providers.yaml`.
Done when: `check_config.sh` and `check_config.sh --image` pass; impacted api/engine pytest pass; `git grep -nE "config/(prod|staging|models)"` outside `docs/` and `/app/config/` is 0.

## Task 3 — Module cleanup
What it is / what it means: `modules/environment` still carries eval-tool gates that prod/staging never set (R4).
What changes at a high level: Remove `eval_mode`, `eval_backend_enabled`, `eval_cors_origins`, `datasets_bucket`, `eval_max_per_provider`, `eval_owner_uid`, `runtime_env`, `public_api_enabled`, the eval service and its allowlist secret, plus `max_active_runs` and `speech_object_prefix` if only eval set them. Keep `eval_cap_day` (product daily cap). `ENV` becomes `var.env`. Update module callers and module tests accordingly.
Done when: `terraform validate` passes in the then-existing roots; the plan for prod and staging shows no Cloud Run env diff from these removals (offline: module `terraform test` passes with remaining runs); grep for the removed names in `infra/` is 0 except `eval_cap_day`.

## Task 4 — Address table and env-difference inventory
What it is / what it means: Before merging, every address that changes and every env difference must be written down so moved blocks and flags are not guessed (R2 Task-1 table, R3).
What changes at a high level: Compare the prod root and `isolated-environment` and produce one working table: resource, unified address, gate (tfvars value or flag), moved block. Cover module `prod`→`environment`, `hosting_site.app`→`.this`, newly counted `x`→`x[0]`, `api[0]`→`api`, apis list, WIF condition/mapping, deployer principal, registry role, identity provisioner, domain, notification channel, previews, cross-project readers, `google_firebase_project`. Anything not expressible as a value without a live IAM change is marked env-gated file. Table is kept in the task log, not a doc.
Done when: every address difference between the two roots appears in the table; no row implies an IAM convergence; table reviewed against `terraform state list` outputs if available read-only.

## Task 5 — One root, env folders, `tf.sh`
What it is / what it means: The merge itself: one root at `infra/`, two separate states, env data under `infra/<env>/` (R1, R2, D1-D2, D5).
What changes at a high level: Unify `variables/main/versions/outputs/identity/deployer/domains/previews/monitoring` per the table; `var.environment` in {prod, staging}, partial `backend "gcs" {}`, project validation for both. Add committed `infra/<env>/backend.hcl` and `terraform.tfvars` (`*.tfvars` leaves `.gitignore`; `live.tfvars` stays ignored). Write `infra/tf.sh <env> <cmd>` (per-env `TF_DATA_DIR`, `init -reconfigure`, var-files). Add `terraform_data.state_identity` for both. Delete `infra/isolated-environment/`. Env differences stay as values or few flags, not scattered `environment ==`.
Done when: `infra/tf.sh prod validate` and `infra/tf.sh staging validate` pass offline; `terraform fmt -check -recursive` clean; wrong-env plan fails fast via `state_identity`.

## Task 6 — Moved blocks, identity script, staging provisioner
What it is / what it means: Plan-proven state moves, the deliberate `identity-config.py` cleanup, and staging parity for the identity provisioner (R3, O4).
What changes at a high level: Add `moved` blocks for every row in Task 4's table (one set serves both states). Remove the "PRD R4"/"SP00" comments from `infra/scripts/identity-config.py` (its hash trigger will replace prod `identity_policy`, accepted). Enable the password-policy/email-URL provisioner for staging via tfvars.
Done when: `terraform validate` passes with the blocks; `identity-config.py` test passes; plan expectations are documented in the task log (moves, `state_identity` add, prod `identity_policy` replace, staging provisioner add, nothing else); real plans run in Task 10.

## Task 7 — `terraform test`
What it is / what it means: Plan assertions test values and survive refactors, unlike `.tf` text greps (R7, D12).
What changes at a high level: Write `infra/tests/environment.tftest.hcl` with mocked providers: merge `isolation.tftest.hcl` (drop eval runs, add prod); port voice SA holds only expected grants, deployer Firebase IAM (the real-403 regression), and prod deployer admitting only the `production` principal. Delete `isolation.tftest.hcl` and the ported `.py` tests.
Done when: `terraform test` passes offline for both envs; each ported assertion fails when its target value is deliberately changed (check once, revert).

## Task 8 — Script and test pruning
What it is / what it means: Cut the infra test set 19 → 3 and remove dead scripts (R7, D13).
What changes at a high level: Delete `bootstrap.sh`, `bootstrap/main.tf`, `install-tools.sh`, the 6 `*.example` files, the eight text-grep tests, `test_eval_backend_service.py`, `test_eval_module.py`. Keep `create-test-user.py`, `identity-config.py`, `seed-secrets.py` and their three tests; drop `seed-secrets.py`'s eval `--allowlist` path. Keep `.terraform-version`. Update `infra/README.md` only for paths it breaks; no other docs.
Done when: `pytest infra/scripts` runs exactly 3 tests, green; no `.tf` text-grep test remains; `infra/` holds the R1 tree.

## Task 9 — Infra CI job and path filters
What it is / what it means: CI proves the new root without applying anything (R8).
What changes at a high level: `infra` job runs `fmt -check -recursive`, `init -backend=false`, `validate`, `terraform test`, then the 3 Python tests. Path filters per R8: `infra` = `infra/**/*.{tf,tfvars,hcl}` and `infra/{scripts,tests}/**`; `api` also `infra/models.yaml`, `infra/*/*.yaml`; rules job on `firebase/**`. `pr-preview.yml` drops `config/**`.
Done when: `actionlint` clean; filter outputs match expectation on sample diffs (tf-only, yaml-only, firebase-only); no CI step applies Terraform.

## Task 10 — State checks and plan gate
What it is / what it means: Proves every live-state step is a no-op before anything applies (Manual steps 1-3, AC5). Agent runs this; no owner step.
What changes at a high level: Nothing in the repo. Confirm prod state lacks `google_secret_manager_secret.provider` and `google_billing_budget.monthly` (else apply the current root once to forget them). Run `identity-config.py --domains-only --dry-run --remove-domain <retired list>`; real run if it prints a PATCH. Plan staging then prod with live `git_sha`/`llm_*` in `live.tfvars`.
Done when: plans show only the moves, `state_identity` add, prod `identity_policy` replace, staging provisioner add, and empty Cloud Run env diff; any other `google_*` add/change/destroy stops the task and is reported.

## Task 11 — Apply and verify
What it is / what it means: The agent applies the approved plans (D3-D5, step 4-5).
What changes at a high level: `infra/tf.sh staging apply`, then prod. Re-plan each. Trigger or observe the next `deploy-staging` to exercise `firebase/` and the new image.
Done when: second plan is "No changes" for both envs; deploy-staging Firestore step succeeds and `check_config.sh --image` passes.

## Task 12 — Follow-up cleanup and acceptance
What it is / what it means: Temporary scaffolding goes; AC1-7 verified (R3, R9).
What changes at a high level: Delete all `moved` blocks; delete 01's `removed {}` blocks, `retired_authorized_domains`, `app_staging_site_id` (state-checked, plan-gated, empty plan); keep `deployer_staging` prod-only. Confirm 03's hand-over items are gone. Run the AC greps.
Done when: `terraform validate`/`test` pass; plans for both envs still "No changes"; AC1 grep is 0 outside `docs/`; `infra/scripts` has 3 tests; AC1-7 recorded.

Owner-only: none credential-gated. The owner's spike-4 decision (Task 1) arrives before 02 starts via the spikes report.
