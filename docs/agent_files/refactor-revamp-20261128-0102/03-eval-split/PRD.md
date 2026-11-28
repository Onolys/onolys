---
status: draft
summary: Move eval/ (core, backend, web, datasets, fixtures) with its deploy workflow, Terraform root and eval-only CI into a new repo Onolys/onolys-eval, pinned to an immutable pre-revamp snapshot tag of api + engines; behaviour identical, same cloud project, same Terraform state, then delete eval from this repo.
date: 2026-11-28
---
# PRD: 03 Eval split (eval into its own repo)

Repo/branch: Onolys/onolys / `refactor/revamp` (removal) and new Onolys/onolys-eval (`main`) · Depends on: 00 (rules docs to copy), 01 (eval purged in place first), 02 (eval/web on `@onolys/common` v0.4.0, no `@prod-*`) · Owns: `eval/**`, `.github/workflows/deploy-eval.yml`, eval jobs in `ci.yml`, eval-only `scripts/ci/*`, eval examples in `infra/isolated-environment/examples/`, eval lines in `uv.lock`/root `pyproject.toml`/`.dockerignore`/`.gitignore`/`pr-preview.yml`/`api/Dockerfile`/`firebase.json`/`.firebaserc`; the whole new repo. Does not own: api/engine code (04-06), Terraform module/root restructure (09), eval refactors (10), docs (frozen).

## TL;DR
Eval is not just "engine + sign-in + sessions". It also imports `onolys_api` in 41 lines and its worker is the api image in `EVAL_MODE`. So the pin must be a **whole pre-revamp snapshot** (api + core + miti + oneshot), tagged `engine-v0` before 04 starts. The new repo gets eval's history (`git filter-repo`), its Terraform copied verbatim against the **same state bucket**, and is deployed to the **same cloud project and URLs**. Order: tag, build repo, agent wires identity (plan = no changes, then apply), deploy from new repo, only then delete here. No rollback: if the first deploy from the new repo fails, fix forward in the new repo. The "own sessions" cut is handed to 10 (O1).

## Problem
| Gap | Evidence |
|---|---|
| Brainstorm lists 3 ties; there is a 4th: eval/backend depends on api, not just the engine | [verified: `eval/backend/pyproject.toml` `onolys-api`; 41 `from onolys_api` lines, e.g. `routes.runs.create_run`, `repo.models.EvalRunInfo`, `engines.eval_snapshot`, `auth.idtoken`, `factory`, `jobs.queue`; tests use `repo.fake`/`storage.fake`] |
| Eval worker is built from this repo's `api/Dockerfile` and needs api's eval-mode code | [verified: `deploy-eval.yml` `file: api/Dockerfile`; `api/.../config.py:109` `eval_mode`; `jobs/run.py:164` drift guard; `repo/models.py:361` `EvalRunInfo`] |
| Eval imports each dataset session as an api `SessionDoc` | [verified: `eval_sessions.py:14-22`] |
| Shared infra: eval and staging use one Terraform root + module; state for eval lives in the eval project | [verified: `isolated-environment/main.tf` `var.environment`; `examples/backend-eval.hcl.example` bucket `onolys-eval-tfstate`, prefix `environment`] |
| Eval tests/images read repo-root `config/` (`models.yaml`, `staging/routes.yaml`) | [verified: `test_catalog.py:16`, `eval/backend/Dockerfile` `COPY config`] |
| 04-06 would break eval if it stays in the workspace | [verified: root `pyproject.toml` members `eval/*`; `uv.lock` lists eval + eval-backend] |

## Goals / Non-Goals
**Goals:** eval builds, tests, deploys and runs from its own repo with no behaviour change; this repo has no `eval/`, no eval workflow, no eval Terraform entry points; 04-09 free to rewrite api/engines/infra; eval site down for minutes at most.
**Non-goals:** any eval refactor (metrics/charts/converters/YAML = 10); own-session model (O1); trimming staging/prod parts from the copied Terraform; Terraform root merge (09); docs changes; non-English work; deleting live cloud resources.

## Requirements
**R1 Snapshot tag (this repo).** After 01 and 02 are merged on the branch and pushed, tag that commit `engine-v0` (annotated). Never move it. It keeps `eval/` manifests, so `api/Dockerfile` (which copies them for the frozen lock) still builds at the tag. The snapshot still contains api + engine packages + config, as eval needs them; the name is `engine-v0` (owner decision). A second tag `engine-v1` is cut after 04-06 merge, for 10's P4 (not this SP).

**R2 New repo from history.** `git filter-repo` on a fresh clone: keep `eval/`, `.github/workflows/deploy-eval.yml`, `scripts/ci/{set_eval_origin.sh,test_deploy_eval.sh,test_eval_image.sh,test_workflow_run_guard.py}` (history only; the tests are dropped in R5); `--path-rename eval/:` (flatten: `core/ backend/ web/ datasets/ fixtures/` at root); `--strip-blobs-bigger-than 500K` (old `eval/tests/datasets/tofueval/.../test_data.zip` is in history [verified: `git rev-list --objects`]). Shared files are copied fresh in one adaptation commit (R4-R7). Mechanical path fixes: `parents[3]` constants in tests, `test_repo_guard` `eval/` prefix, `eval/web/package-lock.json` exemption.

**R3 Dependencies.** Root `pyproject.toml` workspace members `core`, `backend`; four git sources, all at `engine-v0` (no registry; this repo is public [verified: `gh repo view` PUBLIC], so no deploy key or token):
```toml
onolys-api         = { git = "https://github.com/Onolys/onolys", subdirectory = "api",             tag = "engine-v0" }
onolys-engine-core = { git = "...", subdirectory = "engines/core",    tag = "engine-v0" }
onolys-miti        = { git = "...", subdirectory = "engines/miti",    tag = "engine-v0" }   # extras stt-google, voice-gemini as today
onolys-oneshot     = { git = "...", subdirectory = "engines/oneshot", tag = "engine-v0" }
```
All four are explicit because `tool.uv.sources` of a git dependency is not honoured transitively [RESOLVED O3: spike 3 PASS 2026-11-28 (`../spikes/PRD.md`): uv lock/sync/import of the four git-subdirectory deps works at snapshot 78fc3371, lock has only git sources; re-check once `engine-v0` exists; no fallback needed]. New `uv.lock` committed. Web: `@onolys/common#v0.4.0` already (02).

**R4 CI (new repo).** `ci.yml` = today's `eval-core`, `eval-backend`, `eval-web` jobs plus actionlint and the config guard (`check_config.sh`); every job finishes within 5 minutes (today's `timeout-minutes: 10` is lowered; owner rule 6); `eval-web` runs its tests under `firebase emulators:exec --only auth` (02); path routing via `paths-filter` or none (small repo, run all). No `changes.sh`. A direct `docker build` CI step (no script; `test_eval_image.sh` is not ported, R5) builds `backend/Dockerfile` in the new layout (context = repo root, `config/` copied into the image).

**R5 Deploy (new repo).** `deploy-eval.yml` ported: same jobs, same service names (`onolys-eval-backend-eval`, `onolys-worker-eval`), same Hosting site `onolys-eval-app` and target `eval-staging`, same smoke. Changes: (a) worker image: shallow-clone `engine-v0` into `snapshot/`, overlay the eval repo's `config/`, build `snapshot/api/Dockerfile`; (b) **both images get the eval repo's SHA** as `GIT_SHA` (the worker drift guard compares `RunDoc.code_version` with it); (c) drop "install prod web deps"; (d) `scripts/ci/{release_target.py (eval role only), check_config.sh (staging only), verify_staging_release.cjs, set_eval_origin.sh}` copied; the shell/Python tests of these CI scripts (`test_deploy_eval.sh` (already failing), `test_eval_image.sh`, `test_hosting_targets.sh`, `test_workflow_run_guard.py`, the `verify_staging_release` test) are NOT ported: tests of tooling; `actionlint` plus the deploy smoke are the check [RESOLVED 2026-11-28: owner rule 17] (audit #8); `_deploy-cloudrun.yml` copied and trimmed to eval. [ACCEPTED: owner accepts these copies into the eval repo.] GitHub environment `eval`. Vars keep names (`EVAL_GCP_PROJECT`, `EVAL_WIF_PROVIDER`, `EVAL_DEPLOYER_SA`, `EVAL_HOSTING_SITE`, `EVAL_VITE_FIREBASE_*`, `GCP_REGION`); no GitHub secrets exist [verified: no `secrets.` use besides `inherit`].

**R6 Config and Firebase.** Copy `config/models.yaml`, `config/staging/{routes,stt_providers}.yaml` to `config/` (eval keeps its own copy, [ACCEPTED] by owner; 09 will move the originals). Own `firebase.json` (Hosting `eval-staging` + Firestore `eval` database as today, plus the Auth emulator block on port 9099 that 02 adds for web, so `eval-web` tests can use the Auth emulator; 10 later switches it to one `(default)` entry, owner D-B), `.firebaserc`, a snapshot copy of `firestore.indexes.json` (the eval DB uses api's schema, same indexes) [ACCEPTED copy]. Eval Firestore rules = deny-all (eval backend uses the Admin SDK only; the browser never reads Firestore), so no copy of prod `firestore.rules`; no test of a deny-all rules file (config, rule 17).

**R7 Terraform.** Copy `infra/isolated-environment/` (root, `tests/`, eval examples) and `infra/modules/environment/` verbatim to `infra/`, plus `infra/scripts/{create-test-user,seed-secrets,identity-config}.py` and their tests; same `backend "gcs"` bucket/prefix, same resource addresses, so no `state mv`. `identity-config.py` is copied **unedited** (01 does not touch it; its hash feeds a trigger in `infra/identity.tf:75`, so any edit would show as a plan change; 09 cleans it later). Gate: the agent runs `terraform plan` from the new repo: **no changes** (with `github_repository` still the old value). Only then set `github_repository = "Onolys/onolys-eval"` and the agent applies (moves the WIF trust). Module/infra copies are [ACCEPTED] by owner. Trimming staging/prod branches from the copy is deferred.

**R8 Docs and rules.** Copy (own copy, synced by hand) `docs/rules/{coding-rules,design-rules}.md` (00), `docs/reference/eval-site.md`, `eval-datasets.md`, `docs/implementation/isolated-environments.md` (eval parts) and a short `AGENTS.md` + `CLAUDE.md` (`@AGENTS.md`) into the new repo ([ACCEPTED] copies); eval's copy of `design-rules.md` has its first line reading "`web/`" only (the flattened eval web is `web/`). In this repo edit exactly one docs line: `docs/rules/design-rules.md` "Apply to every UI: `web/`, `eval/web`" -> `web/` (00 deferred it here). Other stale eval mentions in `docs/` are [DEFERRED].

**R9 Removal (this repo, one PR, after cut-over succeeds and before 04 starts).**
| Remove / edit | Where |
|---|---|
| `eval/`; `deploy-eval.yml`; eval jobs, `changes` flags and `needs` entries in `ci.yml`; the `onolys_eval` loop and `! -e /app/eval` checks (api image) | `.github/workflows/ci.yml` |
| eval-only scripts | `set_eval_origin.sh`, `test_deploy_eval.sh`, `test_eval_image.sh`, `test_workflow_run_guard.py`; eval role in `release_target.py` + `test_release_targets.py`; `eval/web` in `test_hosting_targets.sh`; eval mapping in `required_gate.py` (verify none left after 01) |
| workspace | root `pyproject.toml` members `eval/*`; `uv lock` must only drop `onolys-eval*` entries; `.dockerignore`, `.gitignore` eval lines; `api/Dockerfile` eval manifest COPYs; `pr-preview.yml` paths `eval/*/pyproject.toml` |
| tests that name eval | `api/tests/test_dev_script_and_image.py:142` (members), `api/tests/test_logging.py:293` (Dockerfile list), `engines/core/tests/test_json_logging.py:186` (module name) |
| Firebase/identity | root `.firebaserc` `onolys-eval` target, `firebase.json` `eval` database entry |
| Terraform | delete `examples/{backend-eval.hcl,environment-eval.tfvars}.example`; adjust `infra/scripts/test_isolated_environment.py:90` (reads the tfvars example). Module/root code untouched (09) |
Kept for 09/06: `isolated-environment/bootstrap` (`eval` in `projects` map; removing it would plan to destroy a `prevent_destroy` state bucket), module `eval_*` variables, eval tests of the module.

## Architecture
```
Onolys/onolys                                  Onolys/onolys-eval (new)
  tag engine-v0 (api, engines/*, config, eval/ manifests)
        ^  git deps (api, core, miti, oneshot)        core/ backend/ web/ datasets/ fixtures/ config/ infra/ .github/
        |  + worker image = snapshot/api/Dockerfile + eval config/ overlay
        +------------------------------------------- deploy-eval.yml --WIF--> GCP project onolys-eval (unchanged)
                                                       backend, worker (same images' services), Hosting onolys-eval-app, Firestore db eval (-> (default) in 10)
                                                     Terraform state: gs://onolys-eval-tfstate/environment (unchanged)
```
Deploy trigger stays "CI green on main, then deploy" inside the new repo.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| 1 | Pin | One immutable tag `engine-v0` for api + 3 engine packages + config (then `engine-v1` after 04-06 for 10) | Engine-only tag; registry release; per-package tags | Eval imports api and runs on the api worker; tags make 04-06 free of eval; no registry cost |
| 2 | History | `filter-repo` of eval paths, flatten, strip big blobs | Fresh copy | Keeps blame for 21 eval commits; cheap; blob strip handles the one leak risk |
| 3 | Visibility | PUBLIC repo (owner decision) | Private | Like this repo; deps are public so CI needs no token; `test_repo_guard` + blob strip keep datasets out |
| 4 | Layout | Flatten (`core/`, `backend/`...) | Keep `eval/` nesting | A few mechanical path fixes now beats a permanent odd nesting; 10 restructures anyway |
| 5 | Shared features | No shared Python package; eval keeps its own auth/Firestore/storage/queue/uploads untouched | Extract a shared package now | Rule 5 puts these in the product; a package forces 06's design early. 10 decides after 06 (re-pin to a post-06 tag or keep copies) |
| 6 | Own sessions cut | Hand to 10, first item [RESOLVED O1] | Do in 03 | Needs an eval run path replacing api's worker (`jobs/run.py`, `create_run`) = a rewrite, not a move; also needs 06's data layer |
| 7 | Non-English datasets | `midas-es`, `phac-fr` and all non-English converters are deleted (owner decision); keep `phac-en` only (strip non-English parts of `phac.py`). Moved untouched in 03, deleted by 10 (O5) | Move and keep | English only; old eval run data is dropped too, no migration |
| 8 | Terraform | Copy verbatim, same backend and addresses, plan-no-op gate | New state; `terraform state mv`; import | Zero risk to live eval project; no state surgery |
| 9 | Cut-over | New repo deployed and verified first; old workflow disabled just before; then delete. No rollback: if the first deploy fails, fix forward in the new repo (owner decision) | Delete first | Eval has a working pipeline in the new repo before anything is deleted here |
| 10 | Identity | Re-point existing WIF provider via `github_repository` | Second provider for both repos | One apply (by the agent); old repo is retired anyway |
| 11 | Docs | Copy needed docs; leave originals | Move | Docs frozen; no broken links here |
| 12 | Cross-repo copies | Accepted by owner: `infra/modules/environment`, `release_target.py`, `check_config.sh`, `verify_staging_release.cjs`, `set_eval_origin.sh`, `test_hosting_targets.sh`, `_deploy-cloudrun.yml`, `firestore.indexes.json`, docs incl. `isolated-environments.md`, plus `config/` and rules files | Shared package / submodule | Owner accepted the copy cost for a clean split; listed in README "Accepted cross-repo copies" |

## Manual steps
Agents run Terraform plan and apply and other cloud actions (owner granted this); only steps needing credentials the agent lacks stay with the owner.
1. Create `Onolys/onolys-eval` (PUBLIC), allow Actions, create GitHub environment `eval`.
2. Push tag `engine-v0` (and the branch commit it names) if the agent cannot.
3. Copy the `EVAL_*` / `GCP_REGION` repo variables from this repo to the new repo (names in R5).
4. Agent, from the new repo: `terraform init` (existing backend), `plan` = no changes; then apply with `github_repository = "Onolys/onolys-eval"`. Owner steps in only if the agent lacks eval-project credentials.
5. `gh workflow disable deploy-eval` here, run `deploy-eval` in the new repo (`workflow_dispatch`), browser-check `eval.onolys.com`, start one small run. No rollback: if the first deploy fails, fix forward in the new repo.
6. After the merged removal PR: delete the now-unused `EVAL_*` variables here; add the eval repo ruleset; retire nothing in GCP.

## Risks / Open Questions
- [RESOLVED: yes] O1: "own sessions" (stop writing api `SessionDoc`s) moves to 10. Until then eval stays on `engine-v0`.
- [RESOLVED: public] O2: new repo `Onolys/onolys-eval` is PUBLIC.
- [RESOLVED: spike 3 PASS, owner D-D 2026-11-28] O3: uv resolves the four git subdirectory deps (`workspace = true` in their pyprojects); lock has only git sources. Re-run `uv lock` against `engine-v0` once it exists (first task); the wheels fallback is not needed.
- [RESOLVED: deny-all] O4: eval Firestore rules deny-all (Admin SDK only); no copy of prod `firestore.rules`.
- [RESOLVED: yes] O5: worker image = tag + eval's own `config/` overlay.
- [RESOLVED: dropped] Old eval runs/data are dropped; no mapping or migration of old ids or runs. Owner 2026-11-28: any existing staging/eval records may be deleted; no data migration, export or backup.
- [RESOLVED: owner D-B 2026-11-28] Each env uses the `(default)` Firestore database in its own project. 03 moves eval verbatim (still the named `eval` database and `FIRESTORE_DATABASE` setting); the switch to `(default)` (Terraform create `(default)` in `onolys-eval`, delete named `eval`, drop `firestore_database` from eval config, single-entry `firebase.json`) is done in the eval repo by 10, not here.
- [RESOLVED: owner D-A 2026-11-28] Eval backend's use of `onolys_api.auth.idtoken` (custom `IdTokenVerifier`) stays frozen at `engine-v0` here; 10 replaces it with Firebase Admin `verify_id_token` (06 deletes the custom verifier in this repo).
- [DEFERRED] Trim staging/prod branches from the copied Terraform module; rename `EVAL_*` vars; rewrite stale eval docs here; `bootstrap` eval entry (09).
- Risk: drift guard fails runs if backend and worker `GIT_SHA` differ. Mitigation: R5(b). Eval is non-prod: no idle-window planning for a deploy landing mid-run (owner rule 3).
- Risk: dataset content in history. Mitigation: blob strip, `test_repo_guard` ported (repo is public, so this matters).
- Risk: two roots applying one state. Mitigation: eval examples deleted here (R9); GCS lock.
- Rule 17: new repo uses vendor tooling only (`uv`, `terraform`, `firebase-tools`, `actionlint`); cited rules 16, 17. 01 hand-ons: dead `vars.DEPLOYER_STAGING_SA` fallback in `_deploy-cloudrun.yml` and spec ids in `deploy-eval.yml:93` are fixed in the copy (see audit section C).
- Risk: freeze means eval changes between tag and cut-over must be re-copied; keep the window short, no eval commits during it.
- Handed on: 06 deletes all api eval-mode code (`Settings.eval_mode`, `RunDoc.eval`/`EvalRunInfo`, `create_run(is_eval)`, `EvalDisabled`, `engines.resolve_engine/eval_snapshot`, `jobs/run.py` drift branch, `first_run` skip, `adapters/real.py` override); 04/05 decide oneshot's api dependency; 09 removes module `eval_*` vars, eval parts of the root, bootstrap `eval`, eval tests; 10 owns O1 and eval's use of shared modules.

## Acceptance Criteria
- Tag `engine-v0` exists on a pushed commit containing `api/`, `engines/{core,miti,oneshot}`, `config/`.
- New repo: `uv sync --frozen`, backend/core pytest, ruff, web typecheck/lint/test/build all green with this repo absent; no `@prod-*`, `web/src`, or workspace-path dependency.
- `git log --follow` shows eval history; no blob over 500 KB; `test_repo_guard` passes.
- `terraform plan` from the new repo against the live state shows no changes before the WIF apply.
- After deploy from the new repo: smoke passes (`/v1/me` 401, CSP lists backend), same service names and URLs, one small eval run completes end to end, backend and worker revisions carry the same `GIT_SHA`.
- This repo: `git grep -il "onolys_eval\|eval/" -- . ':!docs'` returns only intentional hits; `uv lock --check` clean and only eval packages removed; CI green; api image still builds and starts; zero `.tf` module/root edits.
