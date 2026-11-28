---
status: draft
summary: One Terraform root with per-env folders, Firebase config in firebase/, runtime YAML beside tfvars, infra tests 15 to 3; 13 tasks, every env on its own `(default)` Firestore DB, agent runs plan then apply, moved blocks removed after.
date: 2026-11-28
---
# Tasks: 09 Infra per environment

Source of truth: /root/projects/onolys/onolys/.worktrees/refactor/revamp/docs/agent_files/refactor-revamp-20261128-0102/09-infra-per-env/PRD.md. Runs last (01 → 03 → 04 → 06 → 07/08 → 09; 02 supplies the Auth emulator block in `api/firebase.json`; 06 and 08 are consumers of it, and Task 1 repoints all their `--config api/firebase.json` commands to `firebase/firebase.json`; the eval repo has its own `firebase.json` and is untouched). One commit per task; after each batch run `terraform validate/test`, impacted pytest, `actionlint`, `check_config.sh`. CI applies nothing; only the agent applies (Tasks 10-11). Firebase: one `(default)` Firestore entry (owner D-B), `--config firebase/firebase.json` resolves rules/indexes beside the config, env chosen by `--project`. Full suite runs only in dev-ship.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Move Firebase config to `firebase/`; repoint emulator and deploy commands (R6) | none | todo |
| 2 | Move runtime YAML to `infra/<env>/`; Dockerfile, dockerignore, loader/test paths, `check_config.sh` (R5) | none | todo |
| 3 | Module cleanup: drop eval-tool inputs and resources (R4) | none | todo |
| 13 | Firestore `(default)` DB in staging, drop `FIRESTORE_DATABASE`/`VITE_FIRESTORE_DATABASE`, drop `email_rate_ttl` (R6b, R6c) | 3 | todo |
| 4 | Derive the address table and env-difference inventory (R2, R3) | 3 | todo |
| 5 | Merge into one root with env folders and `tf.sh` (R1, R2) | 3, 4, 13 | todo |
| 6 | `moved` blocks, `identity-config.py` cleanup, staging identity provisioner (R3, O4) | 5 | todo |
| 7 | `terraform test`: merge isolation tests, port 3 security checks (R7) | 5 | todo |
| 8 | Script and test pruning; delete bootstrap, install-tools, examples (R7) | 7 | todo |
| 9 | Infra CI job and path filters (R8) | 1, 2, 7, 8 | todo |
| 10 | Pre-apply state checks and plan gate, staging then prod (Manual steps 1-3) | 6, 9 | todo |
| 11 | Apply staging then prod; second plan empty; deploy-staging check (steps 4-5) | 10 | todo |
| 12 | Follow-up: delete moved blocks and hand-over leftovers; acceptance sweep (R3, R9, AC1-7) | 11 | todo |

## Task 1 — Firebase config to `firebase/`
What it is / what it means: Firebase config is in six places with two emulator ports; it becomes one folder and one config (PRD R6, D9-D11, owner D-B).
What changes at a high level: `git mv` `firestore.rules`, `api/firestore.indexes.json`, `firestore-rules-test/` into `firebase/` (rules-test, default port 8080). Write one `firebase/firebase.json`: exactly ONE `firestore` entry in object form (`rules` + `indexes`, no `database` key), emulators Firestore 8080 + Auth 9099 (carrying 02's Auth block), ui off. Delete root `firebase.json`, `.firebaserc`, `api/firebase.json`. Repoint every `--config` in CI `api-emulator`, `api-rules` (rules test port 8081 to 8080), `nightly.yml`, `deploy-prod`, `deploy-staging` (`--only firestore --project <env project>`, no database id), and every other consumer of `api/firebase.json` (08's `web`/`web-e2e` jobs, `web/package.json` `test`, 06's `dev.sh` `FIREBASE_CONFIG` default, 08's `setup-emulators` action); update `.dockerignore` and path filters to `firebase/`.
Done when: `firebase emulators:exec --config firebase/firebase.json --only firestore,auth` runs the api emulator tests and `rules-test` green (rules auto-load, one firestore entry); `actionlint` clean; grep for `api/firebase.json|firestore-rules-test` outside `docs/` is 0.

## Task 2 — Runtime YAML into env folders
What it is / what it means: Per-env YAML sits far from its tfvars; it moves next to them while the image keeps `/app/config/<env>/` so no Cloud Run env var changes (R5, D6-D8).
What changes at a high level: `git mv` `config/{prod,staging}/*.yaml` to `infra/{prod,staging}/` (04 owns `routes.yaml` content; only move it) and `config/models.yaml` to `infra/models.yaml`; delete `config/`. `api/Dockerfile` COPY lines read from `infra/` into the unchanged image paths; `.dockerignore` re-includes `infra/models.yaml` and `infra/*/*.yaml`. Repoint dev/test default paths (`models.py`, `probe_llm.py`, ~12 tests) to `infra/<env>/...` through one helper per package. `check_config.sh` checks the new repo paths and the unchanged image paths, adding `voice_providers.yaml`.
Done when: `check_config.sh` and `check_config.sh --image` pass; impacted api/engine pytest pass; `git grep -nE "config/(prod|staging|models)"` outside `docs/` and `/app/config/` is 0.

## Task 3 — Module cleanup
What it is / what it means: `modules/environment` still carries eval-tool gates that prod/staging never set (R4).
What changes at a high level: Remove `eval_mode`, `eval_backend_enabled`, `eval_cors_origins`, `datasets_bucket`, `eval_max_per_provider`, `eval_owner_uid`, `runtime_env`, `public_api_enabled`, the eval service and its allowlist secret, plus `max_active_runs` and `speech_object_prefix` if only eval set them. Keep `eval_cap_day` (product daily cap). `ENV` becomes `var.env`. Update module callers and module tests accordingly.
Done when: `terraform validate` passes in the then-existing roots; the plan for prod and staging shows no Cloud Run env diff from these removals (offline: module `terraform test` passes with remaining runs); grep for the removed names in `infra/` is 0 except `eval_cap_day`.

## Task 13 — Firestore `(default)` and `email_rate_ttl` removal
What it is / what it means: Every env uses the `(default)` Firestore database of its own project, and the retired email limiter's TTL policy goes (R6b owner D-B, R6c owner, O3).
What changes at a high level: In the module, `google_firestore_database.db` becomes `(default)` and `var.database_id` goes (prod already `(default)`: no-op; staging plan replaces the named `staging` DB and dependent indexes; no export or migration, owner-approved). Remove `FIRESTORE_DATABASE` from `services.tf`/`voice.tf` and `VITE_FIRESTORE_DATABASE` from `deploy-staging.yml`, `pr-preview.yml`, `deploy-prod.yml`, `infra/identity.tf` and its test. Delete `google_firestore_field.email_rate_ttl` and its comment; `worker_auth_email` IAM and Resend wiring stay. Eval's own switch is done by 10.
Done when: `terraform validate` and `terraform test` pass; `actionlint` clean; `git grep -nE "FIRESTORE_DATABASE|firestore_database|database_id"` outside `docs/` is 0; the real plan expectations (DB replace, env removal, TTL destroy) are logged for Task 10.

## Task 4 — Address table and env-difference inventory
What it is / what it means: Before merging, every address that changes and every env difference must be written down so moved blocks and flags are not guessed (R2 Task-1 table, R3).
What changes at a high level: Compare the prod root and `isolated-environment` and produce one working table: resource, unified address, gate (tfvars value or flag), moved block. Cover module `prod`→`environment`, `hosting_site.app`→`.this`, newly counted `x`→`x[0]`, `api[0]`→`api`, apis list, WIF condition/mapping, deployer principal, registry role, identity provisioner, domain, notification channel, previews, cross-project readers, `google_firebase_project`. Anything not expressible as a value without a live IAM change is marked env-gated file. Table is kept in the task log, not a doc.
Done when: every address difference between the two roots appears in the table; no row implies an IAM convergence; table reviewed against `terraform state list` outputs if available read-only.

## Task 5 — One root, env folders, `tf.sh`
What it is / what it means: The merge itself: one root at `infra/`, two separate states, env data under `infra/<env>/` (R1, R2, D1-D2, D5; `state_identity` dropped).
What changes at a high level: Unify `variables/main/versions/outputs/identity/deployer/domains/previews/monitoring` per the table; `var.environment` in {prod, staging}, partial `backend "gcs" {}`, project validation for both. Add committed `infra/<env>/backend.hcl` and `terraform.tfvars` (`*.tfvars` leaves `.gitignore`; `live.tfvars` stays ignored). Write `infra/tf.sh <env> <cmd>` (per-env `TF_DATA_DIR`, `init -reconfigure`, var-files).  No `terraform_data.state_identity` (dropped, rule 17): `tf.sh` plus `project` validation guard operator mix-up. Delete `infra/isolated-environment/`. Env differences stay as values or few flags, not scattered `environment ==`.
Done when: `infra/tf.sh prod validate` and `infra/tf.sh staging validate` pass offline; `terraform fmt -check -recursive` clean; `tf.sh` pairs each env with its own backend and tfvars (wrong-env project fails `project` validation); no `state_identity` resource exists.

## Task 6 — Moved blocks, identity script, staging provisioner
What it is / what it means: Plan-proven state moves, the deliberate `identity-config.py` cleanup, and staging parity for the identity provisioner (R3, O4).
What changes at a high level: Add `moved` blocks for every row in Task 4's table (one set serves both states). Remove the "PRD R4"/"SP00" comments from `infra/scripts/identity-config.py` (its hash trigger will replace prod `identity_policy`, accepted). Enable the password-policy/email-URL provisioner for staging via tfvars.
Done when: `terraform validate` passes with the blocks; `identity-config.py` test passes; plan expectations are documented in the task log (moves, prod `identity_policy` replace, staging provisioner add, plus Task 13's items; nothing else); real plans run in Task 10.

## Task 7 — `terraform test`
What it is / what it means: Plan assertions test values and survive refactors, unlike `.tf` text greps (R7, D12).
What changes at a high level: Write `infra/tests/environment.tftest.hcl` with mocked providers: merge `isolation.tftest.hcl` (drop eval runs, add prod); port voice SA holds only expected grants, deployer Firebase IAM (the real-403 regression), and prod deployer admitting only the `production` principal. Delete `isolation.tftest.hcl` and the ported `.py` tests.
Done when: `terraform test` passes offline for both envs and contains the three ported assertions.

## Task 8 — Script and test pruning
What it is / what it means: Cut the infra test set 15 → 3 and remove dead scripts (R7, D13).
What changes at a high level: Delete `infra/bootstrap.sh`, `infra/isolated-environment/bootstrap/`, `infra/scripts/install-tools.sh`, the `*.example` files (`infra/terraform.tfvars.example` and `isolated-environment/examples/*`), the eight text-grep tests, `test_eval_backend_service.py`, `test_eval_module.py`. Keep `create-test-user.py`, `identity-config.py`, `seed-secrets.py` and their three tests; drop `seed-secrets.py`'s eval `--allowlist` path. Keep `.terraform-version`. Move `infra/isolated-environment/README.md` to `infra/README.md` and fix only the paths it breaks; no other docs.
Done when: `pytest infra/scripts` runs exactly 3 tests, green; no `.tf` text-grep test remains; `infra/` holds the R1 tree.

## Task 9 — Infra CI job and path filters
What it is / what it means: CI proves the new root without applying anything (R8).
What changes at a high level: `infra` job runs `fmt -check -recursive`, `init -backend=false`, `validate`, `terraform test`, then the 3 Python tests. Path filters per R8: `infra` = `infra/**/*.{tf,tfvars,hcl}` and `infra/{scripts,tests}/**`; `api` also `infra/models.yaml`, `infra/*/*.yaml`; rules job on `firebase/**`. `pr-preview.yml` drops `config/**`.
Done when: `actionlint` clean; filter outputs match expectation on sample diffs (tf-only, yaml-only, firebase-only); no CI step applies Terraform; `infra` job under 5 minutes.

## Task 10 — State checks and plan gate
What it is / what it means: Proves every live-state step is a no-op before anything applies (Manual steps 1-3, AC5). Agent runs this; no owner step.
What changes at a high level: Nothing in the repo. Confirm prod state lacks `google_secret_manager_secret.provider` and `google_billing_budget.monthly` (else apply the current root once to forget them). Run `identity-config.py --domains-only --dry-run --remove-domain <retired list>`; real run if it prints a PATCH. Plan staging then prod with live `git_sha`/`llm_*` in `live.tfvars`.
Done when: plans show only the moves, the `email_rate_ttl` destroy, staging named DB replaced by `(default)` (data discarded, owner-approved) with dependent indexes, `FIRESTORE_DATABASE` removed from Cloud Run env, prod `identity_policy` replace, staging provisioner add; any other `google_*` add/change/destroy stops the task and is reported.

## Task 11 — Apply and verify
What it is / what it means: The agent applies the approved plans (D3-D5, step 4-5).
What changes at a high level: `infra/tf.sh staging apply`, then prod. Re-plan each. Staging order: apply (database replaced), then deploy the image without `FIRESTORE_DATABASE`; a short non-prod gap is accepted. Trigger or observe the next `deploy-staging` to exercise `firebase/` and the new image.
Done when: second plan is "No changes" for both envs; staging has only the `(default)` database; deploy-staging Firestore step (no database id) succeeds and `check_config.sh --image` passes.

## Task 12 — Follow-up cleanup and acceptance
What it is / what it means: Temporary scaffolding goes; AC1-7 verified (R3, R9).
What changes at a high level: Delete all `moved` blocks; delete 01's `removed {}` blocks, `retired_authorized_domains`, `app_staging_site_id` (state-checked, plan-gated, empty plan); keep `deployer_staging` prod-only. Confirm 03's hand-over items are gone. Handle 07's hand-over (PRD R9: `web/.firebaserc` `app-staging` site value; check readers, drop only if unread). Delete the unused GitHub vars `STAGING_VITE_FIREBASE_{API_KEY,APP_ID,AUTH_DOMAIN,MESSAGING_SENDER_ID,STORAGE_BUCKET}` with `gh variable delete` (01 follow-up; agent step, keep `STAGING_VITE_CONTACT_EMAIL`). Run the AC greps, including `FIRESTORE_DATABASE|firestore_database|database_id` = 0 outside `docs/`.
Done when: `terraform validate`/`test` pass; plans for both envs still "No changes"; AC1 grep is 0 outside `docs/`; `infra/scripts` has 3 tests; AC1-7 recorded.

Owner-only: none. `GCP_PROJECT`, `GCP_REGION` and `PROD_LLM_*` GitHub vars are optional by design (`deploy-prod.yml` falls back to `onolys`/`us-central1`; blank `PROD_LLM_*` means the image's defaults), so unset is not a gap and nothing is set here. Stale docs (`infra-staging-first-apply.md`) are docs-freeze, out of scope. Optional: delete leftover `email_rate` docs.
