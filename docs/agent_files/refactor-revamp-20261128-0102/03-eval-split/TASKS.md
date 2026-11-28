---
status: draft
summary: Eval split in 11 tasks - tag engine-v0, build Onolys/onolys-eval from history, wire deps/CI/deploy/Terraform there, cut over, then delete eval here.
date: 2026-11-28
---
# Tasks: 03 Eval split

Source of truth: /root/projects/onolys/onolys/.worktrees/refactor/revamp/docs/agent_files/refactor-revamp-20261128-0102/03-eval-split/PRD.md. Work happens in two repos: the new public `Onolys/onolys-eval` (tasks 2-8) and this repo (tasks 1, 9-11). Removal here happens only after the cut-over succeeds (task 8) and before 04 starts. No rollback: if the first deploy fails, fix forward in the new repo. Spike 3 PASSED (O3 resolved, D-D): uv git-subdirectory deps work; only a re-check at the real `engine-v0` tag remains (task 1). Eval keeps its own sessions, auth verifier and named `eval` Firestore database, frozen at `engine-v0`; changes there belong to 10 (O1, D-A, D-B). Per owner rule 17, tests of CI/deploy tooling (shell and Python script tests) are not ported; `actionlint` plus the deploy smoke are the check. Full suites run only in dev-ship; each task runs its own tests.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Verify preconditions; tag `engine-v0`; re-check uv lock (R1, O3) | 01, 02 | todo |
| 2 | Create new repo from eval history (R2) | 1 | todo |
| 3 | Wire dependencies on `engine-v0` and fix paths (R3) | 2 | todo |
| 4 | New repo CI (R4) | 3 | todo |
| 5 | Config, Firebase, rules and docs copies (R6, R8) | 2 | todo |
| 6 | Port deploy workflow and CI scripts, no tooling tests (R5) | 3, 5 | todo |
| 7 | Copy Terraform; plan = no changes (R7) | 5 | todo |
| 8 | Cut-over: identity apply, deploy, verify (Manual steps 3-5) | 4, 6, 7 | todo |
| 9 | Removal here: workflows, scripts, workspace (R9) | 8 | todo |
| 10 | Removal here: eval dirs, Firebase, Terraform examples, tests, docs line (R9, R8) | 9 | todo |
| 11 | Acceptance sweep and post-merge cleanup | 10 | todo |

## Task 1 — Verify preconditions; tag `engine-v0`; re-check uv lock
What it is / what it means: The new repo pins api + engines + config to one immutable snapshot (PRD R1, D1). The tag must be cut after 01 and 02 land, so eval and `@onolys/common` v0.4.0 are already clean.
What changes at a high level: Confirm 01 and 02 are merged on `refactor/revamp` and pushed. Create an annotated tag `engine-v0` on that commit and push it. Never move it afterwards. Owner pushes if the agent cannot.
Done when: tag exists on the remote and the tagged tree contains `api/`, `engines/{core,miti,oneshot}`, `config/` and the `eval/` manifests; a fresh checkout of the tag builds `api/Dockerfile` (image build proves the frozen lock still resolves); a scratch `uv lock` of the four git-subdirectory deps at `engine-v0` resolves with only git sources (O3 re-check, D-D; no wheels fallback needed).

## Task 2 — Create new repo from eval history
What it is / what it means: Eval keeps its blame history in its own PUBLIC repo (PRD R2, D2, D3, D4).
What changes at a high level: Agent creates `Onolys/onolys-eval` (public), allows Actions, creates the `eval` GitHub environment. In a fresh clone run `git filter-repo` keeping `eval/`, `deploy-eval.yml` and the four eval-only CI scripts, flattening `eval/` to the root (`core/ backend/ web/ datasets/ fixtures/`), stripping blobs over 500 KB (old `test_data.zip`). Push to `main`. Apply the mechanical path fixes (`parents[3]` constants, `test_repo_guard` prefix, `package-lock` exemption). Non-English converters move untouched.
Done when: `git log --follow` shows eval history; no blob over 500 KB in history; ported `test_repo_guard` passes (datasets stay out of the public repo); path-sensitive eval tests that do not need the engine pass.

## Task 3 — Wire dependencies on `engine-v0`
What it is / what it means: Eval imports api and the three engine packages, so all four are explicit pinned git sources (PRD R3). Web already uses `@onolys/common#v0.4.0` (02).
What changes at a high level: New root `pyproject.toml` with workspace members `core` and `backend`; `onolys-api`, `onolys-engine-core`, `onolys-miti` (extras as today), `onolys-oneshot` as explicit git-subdirectory sources at tag `engine-v0` (no registry; the repo is public, so no token; sources are not honoured transitively, hence all four). Commit a new `uv.lock`. Confirm no `@prod-*`, `web/src` or workspace-path dependency remains.
Done when: `uv sync --frozen` works with this repo absent and the lock holds only git sources; `pytest` for `core` and `backend`, `ruff`, and web typecheck/lint/test/build all pass in the new repo.

## Task 4 — New repo CI
What it is / what it means: The new repo needs its own CI so tests run on push and PR (PRD R4; dev-common CI default).
What changes at a high level: `ci.yml` with the `eval-core`, `eval-backend`, `eval-web` jobs ported, plus actionlint and the config guard (`check_config.sh`). Every job must finish within 5 minutes (lower today's `timeout-minutes: 10`); `eval-web` tests run under `firebase emulators:exec --only auth` (02). Run everything on every push (or simple paths-filter); no `changes.sh`. Add an image-build step that builds `backend/Dockerfile` in the flat layout (context = repo root, `config/` copied into the image) directly with `docker build`; the `test_eval_image.sh` script is not ported (rule 17, tooling test). Deploy trigger later depends on this workflow's green on `main`.
Done when: `ci.yml` runs green on a PR in the new repo, each job within 5 minutes; `actionlint` passes; the CI image-build step builds `backend/Dockerfile`; eval core, backend and web jobs include the ported `test_repo_guard`.

## Task 5 — Config, Firebase, rules and docs copies
What it is / what it means: Eval keeps its own copies of shared files (PRD R6, R8, D11, D12; copies [ACCEPTED]).
What changes at a high level: Copy `config/models.yaml` and `config/staging/{routes,stt_providers}.yaml` to `config/`. Add own self-contained root `firebase.json` (Hosting `eval-staging`, Firestore named `eval` database copied verbatim, plus an Auth emulator block, port 9099, mirroring 02's; no reference to this repo's `api/firebase.json`; no `(default)` switch here, 10 does it), `.firebaserc`, a snapshot `firestore.indexes.json`, and deny-all Firestore rules (O4). Copy `docs/rules/{coding-rules,design-rules}.md` (eval's `design-rules.md` first line reads "`web/`" only), eval docs, eval parts of `isolated-environments.md`, plus short `AGENTS.md` and `CLAUDE.md` (`@AGENTS.md`).
Done when: tests that read `config/` (e.g. catalog test) pass; Firestore rules file is deny-all (no test of it: config, rule 17); `firebase.json` has the Auth emulator block and its target names match the deploy workflow.

## Task 6 — Port deploy workflow and CI scripts
What it is / what it means: Same pipeline, same service names and Hosting site, now from the new repo (PRD R5, O5).
What changes at a high level: Port `deploy-eval.yml` keeping job names, services (`onolys-eval-backend-eval`, `onolys-worker-eval`), site `onolys-eval-app`, target `eval-staging`, smoke. Worker image: shallow-clone `engine-v0` into `snapshot/`, overlay eval `config/`, build `snapshot/api/Dockerfile`. Both images get the eval repo SHA as `GIT_SHA`. Drop "install prod web deps". Copy `_deploy-cloudrun.yml` trimmed to eval (dead `vars.DEPLOYER_STAGING_SA` fallback removed) and the runtime scripts (`release_target.py` eval role only, `check_config.sh` staging only, `verify_staging_release.cjs`, `set_eval_origin.sh`). Spec ids at old `deploy-eval.yml:93` reworded. Do NOT port `test_deploy_eval.sh` (already failing), `test_eval_image.sh`, `test_hosting_targets.sh`, `test_workflow_run_guard.py` or the verify-script test. Variable names unchanged.
Done when: `actionlint` passes on all ported workflows; no ported tooling-test scripts and no `DEPLOYER_STAGING_SA` reference remain; a dry-read of the workflow shows identical `GIT_SHA` for backend and worker images.

## Task 7 — Copy Terraform; plan = no changes
What it is / what it means: Infra is copied verbatim against the same state so no resource moves (PRD R7, D8). Copies are [ACCEPTED].
What changes at a high level: Copy `infra/isolated-environment/` (root, `tests/`, eval examples), `infra/modules/environment/`, and `infra/scripts/{create-test-user,seed-secrets,identity-config}.py` with their tests to `infra/`. `identity-config.py` is copied unedited. Keep backend bucket/prefix; no `(default)` database switch (10 does it). Agent runs `terraform init` and `plan` with `github_repository` still the old value.
Done when: copied infra tests and `terraform fmt -check` / `validate` pass; `identity-config.py` is byte-identical to the original; `terraform plan` against live state reports no changes (gate). If the agent lacks eval-project credentials, this step goes to the owner.

## Task 8 — Cut-over: identity apply, deploy, verify
What it is / what it means: Move the live eval pipeline to the new repo with the old one still intact (PRD Manual steps 3-5, D9, D10).
What changes at a high level: Set `EVAL_*` and `GCP_REGION` repo variables in the new repo (owner if `gh` lacks rights). Set `github_repository = "Onolys/onolys-eval"` and apply (agent), moving WIF trust. `gh workflow disable deploy-eval` here, run `deploy-eval` via `workflow_dispatch` in the new repo. On failure, fix forward in the new repo.
Done when: smoke passes (`/v1/me` 401, CSP lists backend); same service names and URLs; `eval.onolys.com` loads in a browser; one small eval run completes end to end; backend and worker revisions carry the same `GIT_SHA`.

## Task 9 — Removal here: workflows, scripts, workspace
What it is / what it means: Delete the eval pipeline pieces from this repo, in one PR with task 10 (PRD R9).
What changes at a high level: Delete `deploy-eval.yml`; remove eval jobs, `changes` flags, `needs` entries, the `onolys_eval` import loop and `! -e /app/eval` checks from `ci.yml`. Delete the four eval-only scripts (including `test_deploy_eval.sh`, so its failing line-141 check and the dead-fallback assertion go with it), the eval role in `release_target.py` and its test, `eval/web` in `test_hosting_targets.sh`, any eval mapping left in `required_gate.py`. Drop `eval/*` workspace members, eval lines in `.dockerignore`/`.gitignore`, `api/Dockerfile` eval COPYs, and `pr-preview.yml` eval paths. Run `uv lock` (only `onolys-eval*` entries may vanish).
Done when: `actionlint` passes; `uv lock --check` clean with only eval packages removed; impacted script tests (`test_release_targets.py`, hosting-targets test) pass; api image builds and starts.

## Task 10 — Removal here: eval dirs, Firebase, Terraform examples, tests, docs line
What it is / what it means: Remove the rest of eval and fix the tests that name it (PRD R9, R8). Kept for 09/06: `isolated-environment/bootstrap`, module `eval_*` variables and module eval tests; no `.tf` edits.
What changes at a high level: Delete `eval/`. Remove the `onolys-eval` target from root `.firebaserc` and the `eval` database from `firebase.json`. Delete `examples/{backend-eval.hcl,environment-eval.tfvars}.example` and adjust `infra/scripts/test_isolated_environment.py:90`. Fix `api/tests/test_dev_script_and_image.py:142`, `api/tests/test_logging.py:293`, `engines/core/tests/test_json_logging.py:186`. Edit the single docs line in `docs/rules/design-rules.md` ("`web/`, `eval/web`" to `web/`).
Done when: the three fixed tests, `test_isolated_environment.py` and `pytest infra/scripts` pass; `terraform fmt -check`/`validate` unaffected; `git diff` shows zero `.tf` edits and one docs line changed.

## Task 11 — Acceptance sweep and post-merge cleanup
What it is / what it means: Prove the PRD acceptance criteria and finish the cloud-side tidy.
What changes at a high level: No new edits unless a check fails. Run `git grep -il "onolys_eval\|eval/" -- . ':!docs'` and review hits; `uv lock --check`; CI green. After the removal PR merges, the agent deletes the now-unused `EVAL_*` repo variables here and adds the eval repo ruleset (owner if no rights).
Done when: all acceptance criteria hold (tag, new repo green, no big blobs, plan no-op earlier recorded, deploy smoke, this repo grep clean, no `.tf` edits); CI on the removal PR passes.

Owner-only: push tag `engine-v0` and create repo/vars/ruleset if the agent lacks rights; eval-project credentials for Terraform plan/apply if missing; delete old `EVAL_*` variables if `gh` lacks rights.
