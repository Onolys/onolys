---
status: draft
summary: One Terraform root (infra/) for prod + staging with a folder per env holding its tfvars, backend and runtime YAML; config/ and isolated-environment/ deleted; Firebase config in one firebase/ folder; infra tests pruned 19 to 3 Python + terraform test. Two states stay separate; every address change is a plan-proven moved block; the agent runs plan, then apply.
date: 2026-11-28
---
# PRD: 09 Infra per environment

Repo/branch: Onolys/onolys / `refactor/revamp` · Depends on: 01 (hard), 03 (hard: eval gone), 04 (routes.yaml shape), 06 (api eval code and loaders gone), 02 (Auth emulator) · Owns: `infra/**`, `config/**` (deleted), `firestore.rules`, `firestore-rules-test/`, root `firebase.json` + `.firebaserc`, `api/firebase.json`, `api/firestore.indexes.json`, Firestore/emulator/config lines in `.github/workflows/*`, `api/Dockerfile` (config COPY), `.dockerignore`, `scripts/ci/check_config.sh`, path filters naming `config/`/`infra/`/`firestore*`.

**Order assumption:** 01 → 03 → 04 → 06 → 09. 04 edits `config/*/routes.yaml` in place (drops `miti_code`/`miti_globals`/`tips`/`oneshot`); 09 then only `git mv`s them and fixes paths. 06 may change how api loads STT/voice but not the three discovery names below; if it does, 09 follows.

## TL;DR
Prod and staging become one Terraform root with two separate states (one backend file per env), so no state is merged. Resource addresses that differ between the old roots are mapped with `moved` blocks: state-only, shown by `terraform plan`, applied by the agent, then deleted. Each env folder also holds the runtime YAML the images bake in; the image keeps its `/app/config/<env>/` layout so no Cloud Run env var changes. Firestore rules, indexes, emulator config and rules tests move to `firebase/`. Every env uses the `(default)` Firestore database of its own project (owner D-B): staging's named `staging` database is replaced by `(default)` and deleted, data and all.

## Problem
| Gap | Evidence |
|---|---|
| Two roots duplicate WIF pool/provider, deployer SA, identity, apis, Artifact Registry, hosting site (632 + 766 lines) and differ in resource names (`module.prod` vs `module.environment`, `hosting_site.app` vs `.this`) | [verified: `infra/*.tf`, `infra/isolated-environment/*.tf`] |
| Separate states today: prod `onolys-tfstate/infra`, staging `onolys-staging-tfstate/environment`; eval's is in its own project | [verified: `infra/versions.tf`, `examples/backend-*.hcl.example`] |
| Per-env YAML sits in `config/`, far from the env's tfvars; `stt_providers.yaml` is byte-identical in both envs, `voice_providers.yaml` differs by one comment | [verified: `diff config/prod config/staging`] |
| Each env has its own GCP project with one database but names differ (prod `onolys`/`(default)`, staging `onolys-staging`/`staging`, eval `onolys-eval`/`eval`; leftovers of the old shared project) [verified live]. The emulator auto-loads rules only with exactly one firestore entry (firebase-tools 15.37.0 "does not support multiple databases yet"); today's 3-db `firebase.json` loads NO rules in the emulator | [verified: spike 4] |
| Firebase config is in 6 places with two emulator ports: root `firebase.json` (3 DBs incl. `eval`, port 8081), `api/firebase.json` (8080), `firestore.rules`, `api/firestore.indexes.json`, `firestore-rules-test/`, root `.firebaserc` whose hosting targets no config uses | [verified: `git ls-files`; `deploy-*` always pass `--project`] |
| Module still carries eval-tool gates (`eval_mode`, `eval_backend_enabled`, `eval_cors_origins`, `datasets_bucket`, `eval_max_per_provider`, `eval_owner_uid`, `runtime_env`, `public_api_enabled`, eval service, allowlist secret) | [verified: `modules/environment/{variables,services,secrets,main}.tf`] |
| 19 infra tests; 16 grep `.tf` text and break on every restructure; no test runs `terraform test` for prod | [verified: `ls infra/scripts/test_*.py`] |

How the api finds YAML today: Terraform sets `ROUTES_FILE=config/<env>/routes.yaml` and `VOICE_PROVIDERS_FILE=config/<env>/voice_providers.yaml` (relative to image `WORKDIR /app`); `stt_providers.yaml` is looked up next to `ROUTES_FILE`; `models.yaml` at `<ROUTES_FILE dir>/../models.yaml` or `MODELS_FILE`. The image holds all of `config/` because prod promotes the image staging built [verified: `services.tf:13`, `voice.tf:15`, `core/config.py`, `llm/models.py:57-63`, `api/Dockerfile` `COPY config`].

## Goals / Non-Goals
**Goals:** one root, env folders, no `config/`, no `isolated-environment/`, one `firebase/`, fewer and sturdier infra tests; every live-state-touching step proven no-op by plan (the agent applies), except the staging identity provisioner, a deliberate live change.
**Non-goals:** converging prod/staging IAM or WIF models (live change; only the identity provisioner converges, O4); changing YAML content (04/05); web hosting config (`web/firebase.json`, `web/.firebaserc`: 07, 08); eval Terraform (03 copied it); docs edits; applying anything.

## Requirements
**R1 Target tree.**
```
infra/
  main.tf variables.tf versions.tf outputs.tf identity.tf deployer.tf domains.tf previews.tf monitoring.tf   # the one root
  tf.sh  README.md  .terraform-version  .terraform.lock.hcl  .gitignore
  tests/environment.tftest.hcl      # terraform test, mocked providers
  modules/environment/              # services secrets alerts voice main variables outputs
  scripts/ create-test-user.py identity-config.py seed-secrets.py + their 3 tests
  models.yaml                       # shared model catalog (sibling of the env dirs)
  prod/    backend.hcl terraform.tfvars routes.yaml stt_providers.yaml voice_providers.yaml
  staging/ backend.hcl terraform.tfvars routes.yaml stt_providers.yaml voice_providers.yaml
firebase/  firebase.json firestore.rules firestore.indexes.json rules-test/
```
62 files in `infra/` become 32 (+ 7 YAML from `config/`). Real tfvars and backend files are committed (no secrets; `*.tfvars` leaves `.gitignore`; operator-local `live.tfvars` per env stays ignored for deploy-drifted `git_sha`/`llm_*`). The 6 `*.example` files go.

**R2 One root, two states.** `var.environment` in {prod, staging}; `backend "gcs" {}` partial; `infra/tf.sh <env> <cmd>` sets `TF_DATA_DIR=infra/<env>/.terraform`, runs `init -reconfigure -backend-config=<env>/backend.hcl`, and adds `-var-file=<env>/terraform.tfvars` (+ `live.tfvars` if present), so one checkout cannot plan staging against prod state (`tf.sh` is ~10 lines of vendor flags, not a framework). `project` validation covers both (`onolys` for prod, `onolys-staging`); No `terraform_data.state_identity` (guard against operator mix-up, adds a prod state change; [RESOLVED 2026-11-28: owner rule 17]: `tf.sh` plus the `project` validation are enough, and the agent always runs `tf.sh`). Env differences are tfvars values or a few flags, never `environment ==` scattered in code: apis list, WIF `attribute_condition` and mapping, deployer principal (prod: `attribute.environment/production`; staging: repository), image-registry role, identity policy provisioner (now on in both envs, O4), custom domain, notification channel, PR previews, cross-project readers, `google_firebase_project`. Task 1 produces the table *resource → unified address → gate → moved block* from the two roots; any difference that cannot be written as a value without a live IAM change stays in an env-gated file.

**R3 Moves.** `moved` blocks map every address that changes (module `prod`→`environment`; `hosting_site.app`→`.this`; newly counted resources `x`→`x[0]`; module `api[0]`→`api` once `public_api_enabled` is gone). A moved block whose `from` is absent in a state is ignored, so one block set serves both states. They are deleted in a follow-up commit after the agent applies both envs (rule 16).

**R4 Module cleanup.** Remove the eval-tool variables and resources listed in Problem, plus `max_active_runs` and `speech_object_prefix` if only eval sets them. Keep `eval_cap_day`: it is the product's daily evaluations cap, not the eval tool [verified: `api/config.py:173`, `repo/limits.py:28`]. `ENV` becomes `var.env`. Prod/staging never set the removed inputs, so these deletions are no-ops.

**R5 Runtime YAML.** `git mv config/{prod,staging}/*.yaml infra/{prod,staging}/`, `config/models.yaml` → `infra/models.yaml`; `config/` and `isolated-environment/` deleted. Dockerfile: `COPY infra/models.yaml /app/config/models.yaml`, `COPY infra/prod/*.yaml /app/config/prod/`, same for staging; `.dockerignore` re-includes `infra/models.yaml` and `infra/*/*.yaml`. Loader names and Terraform env values do not change. Dev/test default paths (`models.py:62`, `probe_llm.py:23`, ~12 tests reading `config/...`) become `infra/<env>/...`; tests read through one helper per package. `check_config.sh` checks the new repo paths and the unchanged image paths (adds `voice_providers.yaml`).

**R6 Firebase.** `git mv` to `firebase/`: `firestore.rules`, `api/firestore.indexes.json` → `firestore.indexes.json`, `firestore-rules-test/` → `rules-test/`. One `firebase/firebase.json`: ONE `firestore` entry in object form (`rules` + `indexes`, no `database` key = `(default)`), `emulators` firestore 8080 + auth 9099, ui off. The emulator then auto-loads the rules (no special test config); deploy picks the env with `--project` (spike 4: rules/indexes resolve beside `--config`, object form works). `rules-test/` still loads `firestore.rules` explicitly via `@firebase/rules-unit-testing` (standard, unchanged). `api/firebase.json`, root `firebase.json` and `.firebaserc` are deleted. Every call becomes `--config firebase/firebase.json`: CI `api-emulator`, `api-flaky`, `api-rules` (rules test default port 8081 → 8080), `nightly.yml`, `deploy-prod` and `deploy-staging` (`--only firestore --project <env project>`, no database id); `.dockerignore` and path filters name `firebase/`. firebase-tools resolves `rules`/`indexes` and `.firebaserc` next to the `--config` file [verified: `test_hosting_targets.sh` header; `web/firebase.json` `public: dist` deployed with `--config web/...`], and `.firebaserc` is not needed because `--project` is always passed.

**R6b Database names (owner D-B, 2026-11-28).** Staging: module `google_firestore_database.db` becomes `(default)` (drop `var.database_id`); plan shows replace of the named `staging` database and dependent index resources, then create `(default)`; the named database is deleted outright. Owner: existing staging/eval records may be deleted (staging holds 1 test doc): no export, backup or data migration step. Prod is already `(default)` (no-op). Remove `FIRESTORE_DATABASE` env from `services.tf`/`voice.tf` (api drops the setting, 06) and `VITE_FIRESTORE_DATABASE` from `deploy-staging.yml`, `pr-preview.yml`, `deploy-prod.yml`, `infra/identity.tf` and its test (web code reading it: 08). Eval: its Terraform copy and `firebase.json` live in the eval repo after 03, so the same switch (create `(default)` in `onolys-eval`, delete named `eval`) is done there by 10. Staging order: agent plans, applies (database replaced), then deploys the image without the setting; a short Firestore gap on non-prod staging is accepted.
**R6c Email rate TTL removed ([RESOLVED 2026-11-28: owner], with 06 R10).** Delete `google_firestore_field.email_rate_ttl` (`infra/modules/environment/main.tf` ~l.203: TTL on `email_rate.expires_at`) and its comment; the plan for each env shows one destroy of that field (TTL policy only; the limiter is gone, leftover `email_rate` docs are harmless and may be deleted by the owner). No Terraform sets `CLIENT_IP_TRUSTED_HOPS` [verified: grep infra → 0 matches]. `worker_auth_email` IAM and the Resend wiring stay (email is still sent).
**R7 Scripts and tests.** 
| File | Action |
|---|---|
| `bootstrap.sh`, `bootstrap/main.tf` | delete (buckets exist; its local state is the owner's, untouched; a stale `eval` entry would plan to destroy a `prevent_destroy` bucket) |
| `install-tools.sh` | delete (no caller [verified: grep]; `.terraform-version` stays) |
| `create-test-user.py` + test | keep |
| `identity-config.py` + test | keep; runs for both envs (staging gains prod's password-policy/email-URL provisioner, O4) |
| `seed-secrets.py` + test | keep; drop the eval `--allowlist` path |
| `check-staging.py`, `test_{check_staging,no_admin,budget_removed,nightly_gemini_secret}.py` | already gone (01) |
| `test_eval_backend_service.py`, `test_eval_module.py` | delete (03 hand-over) |
| `test_{auth_email_wiring,custom_domain,legacy_prod_drift,legacy_root_prod_only,isolated_environment,provider_secrets_per_env,sweep_scheduler,uid_hmac_wiring}.py` | delete: text-grep of `.tf`, restates what `validate` + review see |
| `test_voice_service.py` (SA holds only expected grants), `test_deployer_firebase_iam.py` (regression of a real 403), prod-deployer-only-`production` principal (from `legacy_root_prod_only`) | port to `tests/environment.tftest.hcl` as plan assertions; delete the `.py` |
`tests/isolation.tftest.hcl` merges into it (drop the eval runs, add prod). Result: 19 → 3 Python tests.

**R8 CI.** `infra` job runs `fmt -check -recursive`, `init -backend=false`, `validate`, `terraform test`, then the 3 Python tests. 01's path filter: `infra` = `infra/**/*.{tf,tfvars,hcl}`, `infra/{scripts,tests}/**`; `api` also = `infra/models.yaml`, `infra/*/*.yaml`; rules job runs on `firebase/**`. `pr-preview.yml` drops `config/**`. No CI job applies Terraform [verified: ci.yml].

**R9 Hand-overs.** From 01: `removed {}` blocks (delete after the agent's state check, plan-gated); `retired_authorized_domains` + `app_staging_site_id` (delete after the agent's dry-run is empty); `.firebaserc` (R6); `firebase.json` has one entry (R6) so the `staging` entry goes with the DB (R6b); `examples/*prod*` (gone with the examples); `deployer_staging` SA stays as a prod-only resource [DEFERRED]. From 03: eval examples, module `eval_*` vars, eval module tests, bootstrap `eval` entry, `test_isolated_environment.py:90`, eval root parts (custom domain, datasets bucket, eval cors).

## Architecture
```
infra/<env>/{backend.hcl,terraform.tfvars} --tf.sh--> infra/*.tf (one root) --> modules/environment --> Cloud Run env: ROUTES_FILE=config/<env>/routes.yaml
infra/<env>/*.yaml + infra/models.yaml --api/Dockerfile COPY--> image /app/config/<env>/*.yaml, /app/config/models.yaml  (unchanged paths)
firebase/firebase.json --> emulators:exec (api tests, rules-test, web) and deploy --only firestore:<db>
```
Batches: (1) Firebase move + workflows, (2) runtime YAML + Dockerfile + tests paths, (3) module cleanup, (4) root merge + moved blocks + tftest, (5) test/script pruning. After each: `terraform validate/test`, impacted pytest, `actionlint`, `check_config.sh`. (4) cannot be proven offline: agent plan gate before apply.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| 1 | Root shape | One root at `infra/`, env data in `infra/<env>/` | Thin per-env roots over one module; workspaces | Locked; workspaces share one backend bucket, and the envs live in different projects/buckets |
| 2 | State | Keep two states, one per env | Merge into one state | Different projects; one state would join locks and blast radius; address moves stay inside each state |
| 3 | Address changes | `moved` blocks, removed after both applies | `state mv`, import, fresh state | Reviewed in git, shown by plan, state-only |
| 4 | Env differences | tfvars values, few flags; no IAM convergence | Converge WIF/deployer model now | Convergence changes live IAM, so not a no-op |
| 5 | Env switching | `tf.sh` + `TF_DATA_DIR` per env | Manual `-reconfigure`; `state_identity` resource | Mix-up fails fast; no extra resource (rule 17, no guard for rare operator error) |
| 6 | Image path | Keep `/app/config/<env>/` | Mirror `infra/` in the image | A new `ROUTES_FILE` value must land together with its image; keeping paths removes that ordering hazard |
| 7 | `models.yaml` | `infra/models.yaml` beside the env dirs | Per-env copies; engine package data | Keeps `<routes dir>/../models.yaml` rule; env-invariant; stays in `infra/` (O2) |
| 8 | STT/voice YAML | Per-env copies (locked) | One shared file | Identical today, but staging can trial a provider first |
| 9 | Firebase home | Root `firebase/` | `infra/firebase/`, `data/` | Not Terraform; used by api, web, CI |
| 10 | Emulators | One `firebase.json`, Firestore 8080, Auth 9099 | Keep two configs/ports | One place; jobs run sequentially |
| 11 | `.firebaserc` | Delete | Move into `firebase/` | No target is used; `--project` always set |
| 12 | Tests | Keep 3 logic tests, port 3 security checks to `terraform test`, cut 8 | Keep all; delete all | Text greps break on refactors; plan assertions test values |
| 13 | Bootstrap | Delete both | Keep prod-only | One-shot, already run; history is the archive |
| 14 | `deployer_staging` | Keep, prod-only | Move deploy-prod `resolve` to the staging deployer | Staging provider admits only `refs/heads/main`; `resolve` runs on tags [verified: `isolated-environment/deployer.tf`] |

## Manual steps
None for the owner. Apply procedure (agent):
1. Before the PR merges: `terraform state list` on prod must lack `google_secret_manager_secret.provider` and `google_billing_budget.monthly` (01 step 2); else apply the current root once to forget them.
2. `identity-config.py --domains-only --dry-run --remove-domain <retired list>` prints no PATCH; else run it for real.
3. After merge, staging first, then prod: `infra/tf.sh <env> plan` with live `git_sha`/`llm_*` in `live.tfvars`. Expected: only N moves, staging Firestore database replaced by `(default)` (R6b; data discarded, owner-approved), `FIRESTORE_DATABASE` env removed from Cloud Run services, prod `identity_policy` replaced (09 cleans `identity-config.py` itself, removing the "PRD R4"/"SP00" comments, so its hash trigger fires; the replace is accepted in the plan; step 2 makes the re-run empty), and staging gains the identity password-policy/email-URL provisioner (O4, live change). Any other add/change/destroy of a `google_*` resource: stop and report.
4. `apply` (state only plus the staging provisioner), staging then prod. A follow-up commit deletes the moved blocks.
5. Next `deploy-staging` exercises `firebase/` and the new image; confirm its Firestore step and `check_config.sh --image`.

## Risks / Open Questions
- Rules cited: 10, 16, 17 (`moved`/`removed` blocks, `terraform test`, `firebase` emulator auto-rules and `@firebase/rules-unit-testing` are the vendor mechanisms; rules tests unchanged).
- Risk: a wrong moved block plans destroy + create of a hosting site, WIF pool or custom domain. Mitigation: plan gate in 3; nothing applies in CI.
- Risk: `terraform test` with mocks cannot see live drift or provider quirks; only the real plan proves no-op.
- Risk: 04/06 land tests and Dockerfile lines that still say `config/`. Mitigation: AC grep, 09 last.
- [RESOLVED: keep] O1: `create-test-user.py` stays.
- [RESOLVED: stays in `infra/`] O2: `models.yaml` is not moved into the engine package; 04 keeps `MODELS_FILE`.
- [RESOLVED: spike 4 PARTIAL + owner D-B 2026-11-28] O3: rules/indexes resolve beside `--config` (object or single-db form). The multi-db emulator limitation is removed by one `(default)` database per env (R6/R6b). Deploy dry-run and indexes still need proof against the real staging project (plan + first `deploy-staging`). The 3-db array form and `working-directory` options are dropped.
- [RESOLVED: owner 2026-11-28] No data migration for staging/eval Firestore or other staging/eval stored data; delete named databases outright.
- [RESOLVED: staging gets prod's provisioner] O4: staging identity gets prod's password-policy/email-URL provisioner. Live change, applied by the agent after plan (see Manual steps).
- [DEFERRED] Move deploy-prod `resolve` off `deployer_staging` (needs a read-only identity in the staging project); WIF/IAM convergence; replacing `git_sha`/`llm_*` Terraform ownership.
- [RESOLVED: verified] States are separate today; `EVAL_CAP_DAY` stays; `.firebaserc` unused.

## Acceptance Criteria
1. `config/`, `infra/isolated-environment/`, root `firebase.json`/`.firebaserc`, `api/firebase.json`, `firestore-rules-test/` do not exist; `git grep -nE "config/(prod|staging|models)|isolated-environment|firestore-rules-test|api/firebase\.json"` outside `docs/` returns 0 (image paths `/app/config/` excepted).
2. `infra/tf.sh {prod,staging} validate` and `terraform test` pass offline; `terraform fmt -check -recursive` clean.
3. Image: `check_config.sh --image` passes; Cloud Run env diff in the plan is only the removal of `FIRESTORE_DATABASE`.
4. `emulators:exec --config firebase/firebase.json --only firestore,auth` runs api emulator tests and `rules-test` green; `firebase.json` has exactly one firestore entry; `git grep -nE "FIRESTORE_DATABASE|firestore_database|database_id" -- . ':!docs'` returns 0; staging has only the `(default)` database.
5. Plans show only moves, the `email_rate_ttl` destroy (R6c), prod `identity_policy` replace, staging identity provisioner add; after apply, a second plan is "No changes".
6. `infra/scripts` has 3 Python tests; no `.tf` text-grep tests remain.
7. Moved blocks deleted after both applies.
