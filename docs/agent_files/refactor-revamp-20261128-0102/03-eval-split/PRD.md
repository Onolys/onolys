---
status: draft
summary: Move eval/ (core, backend, web, datasets, fixtures) with its deploy workflow, Terraform root and eval-only CI into a new repo Onolys/onolys-eval, pinned to an immutable pre-revamp snapshot tag of api + engines; behaviour identical, same cloud project, same Terraform state, then delete eval from this repo.
date: 2026-11-28
---
# PRD: 03 Eval split (eval into its own repo)

Repo/branch: Onolys/onolys / `refactor/revamp` (removal) and new Onolys/onolys-eval (`main`) · Depends on: 00 (rules docs to copy), 01 (eval purged in place first), 02 (eval/web on `@onolys/ui` v0.4.0, no `@prod-*`) · Owns: `eval/**`, `.github/workflows/deploy-eval.yml`, eval jobs in `ci.yml`, eval-only `scripts/ci/*`, eval examples in `infra/isolated-environment/examples/`, eval lines in `uv.lock`/root `pyproject.toml`/`.dockerignore`/`.gitignore`/`pr-preview.yml`/`api/Dockerfile`/`firebase.json`/`.firebaserc`; the whole new repo. Does not own: api/engine code (04-06), Terraform module/root restructure (08), eval refactors (09), docs (frozen).

## TL;DR
Eval is not just "engine + sign-in + sessions". It also imports `onolys_api` in 41 lines and its worker is the api image in `EVAL_MODE`. So the pin must be a **whole pre-revamp snapshot** (api + core + miti + oneshot), tagged `eval-base-v0` before 04 starts. The new repo gets eval's history (`git filter-repo`), its Terraform copied verbatim against the **same state bucket**, and is deployed to the **same cloud project and URLs**. Order: tag, build repo, owner wires identity, deploy from new repo, only then delete here. The "own sessions" cut is handed to 09 (O1).

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
**Goals:** eval builds, tests, deploys and runs from its own repo with no behaviour change; this repo has no `eval/`, no eval workflow, no eval Terraform entry points; 04-08 free to rewrite api/engines/infra; eval site down for minutes at most.
**Non-goals:** any eval refactor (metrics/charts/converters/YAML = 09); own-session model (O1); trimming staging/prod parts from the copied Terraform; Terraform root merge (08); docs changes; non-English work; deleting live cloud resources.

## Requirements
**R1 Snapshot tag (this repo).** After 01 and 02 are merged on the branch and pushed, tag that commit `eval-base-v0` (annotated). Never move it. It keeps `eval/` manifests, so `api/Dockerfile` (which copies them for the frozen lock) still builds at the tag. Brief's name `engine-v0` is replaced because the tag holds api too.

**R2 New repo from history.** `git filter-repo` on a fresh clone: keep `eval/`, `.github/workflows/deploy-eval.yml`, `scripts/ci/{set_eval_origin.sh,test_deploy_eval.sh,test_eval_image.sh,test_workflow_run_guard.py}`; `--path-rename eval/:` (flatten: `core/ backend/ web/ datasets/ fixtures/` at root); `--strip-blobs-bigger-than 500K` (old `eval/tests/datasets/tofueval/.../test_data.zip` is in history [verified: `git rev-list --objects`]). Shared files are copied fresh in one adaptation commit (R4-R7). Mechanical path fixes: `parents[3]` constants in tests, `test_repo_guard` `eval/` prefix, `eval/web/package-lock.json` exemption.

**R3 Dependencies.** Root `pyproject.toml` workspace members `core`, `backend`; four git sources, all at `eval-base-v0` (no registry; this repo is public [verified: `gh repo view` PUBLIC], so no deploy key or token):
```toml
onolys-api         = { git = "https://github.com/Onolys/onolys", subdirectory = "api",             tag = "eval-base-v0" }
onolys-engine-core = { git = "...", subdirectory = "engines/core",    tag = "eval-base-v0" }
onolys-miti        = { git = "...", subdirectory = "engines/miti",    tag = "eval-base-v0" }   # extras stt-google, voice-gemini as today
onolys-oneshot     = { git = "...", subdirectory = "engines/oneshot", tag = "eval-base-v0" }
```
All four are explicit because `tool.uv.sources` of a git dependency is not honoured transitively [OPEN O3]. New `uv.lock` committed. Web: `@onolys/ui#v0.4.0` already (02).

**R4 CI (new repo).** `ci.yml` = today's `eval-core`, `eval-backend`, `eval-web` jobs plus actionlint and a config guard; path routing via `paths-filter` or none (small repo, run all). No `changes.sh`. `test_eval_image.sh` builds `backend/Dockerfile` in the new layout (context = repo root, `config/` copied into the image).

**R5 Deploy (new repo).** `deploy-eval.yml` ported: same jobs, same service names (`onolys-eval-backend-eval`, `onolys-worker-eval`), same Hosting site `onolys-eval-app` and target `eval-staging`, same smoke. Changes: (a) worker image: shallow-clone `eval-base-v0` into `snapshot/`, overlay the eval repo's `config/`, build `snapshot/api/Dockerfile`; (b) **both images get the eval repo's SHA** as `GIT_SHA` (the worker drift guard compares `RunDoc.code_version` with it); (c) drop "install prod web deps"; (d) `scripts/ci/{release_target.py (eval role only), check_config.sh (staging only), verify_staging_release.cjs + test, set_eval_origin.sh, test_hosting_targets.sh (eval/web dir only), test_workflow_run_guard.py}` copied; `_deploy-cloudrun.yml` copied and trimmed to eval. GitHub environment `eval`. Vars keep names (`EVAL_GCP_PROJECT`, `EVAL_WIF_PROVIDER`, `EVAL_DEPLOYER_SA`, `EVAL_HOSTING_SITE`, `EVAL_VITE_FIREBASE_*`, `GCP_REGION`); no GitHub secrets exist [verified: no `secrets.` use besides `inherit`].

**R6 Config and Firebase.** Copy `config/models.yaml`, `config/staging/{routes,stt_providers}.yaml` to `config/` (a fork, not a link; 08 will move the originals). Own `firebase.json` (Hosting `eval-staging` + Firestore `eval` database), `.firebaserc`, snapshot copies of `firestore.rules` and `firestore.indexes.json` (the eval DB uses api's schema, same indexes).

**R7 Terraform.** Copy `infra/isolated-environment/` (root, `tests/`, eval examples) and `infra/modules/environment/` verbatim to `infra/`, plus `infra/scripts/{create-test-user,seed-secrets,identity-config}.py` and their tests; same `backend "gcs"` bucket/prefix, same resource addresses, so no `state mv`. Gate: owner runs `terraform plan` from the new repo: **no changes** (with `github_repository` still the old value). Only then set `github_repository = "Onolys/onolys-eval"` and apply (moves the WIF trust). Trimming staging/prod branches from the copy is deferred.

**R8 Docs and rules.** Copy `docs/rules/{coding-rules,design-rules}.md` (00), `docs/reference/eval-site.md`, `eval-datasets.md`, `docs/implementation/isolated-environments.md` (eval parts) and a short `AGENTS.md` + `CLAUDE.md` (`@AGENTS.md`) into the new repo. In this repo edit exactly one docs line: `docs/rules/design-rules.md` "Apply to every UI: `web/`, `eval/web`" -> `web/` (00 deferred it here). Other stale eval mentions in `docs/` are [DEFERRED].

**R9 Removal (this repo, one PR, after cut-over succeeds and before 04 starts).**
| Remove / edit | Where |
|---|---|
| `eval/`; `deploy-eval.yml`; eval jobs, `changes` flags and `needs` entries in `ci.yml`; the `onolys_eval` loop and `! -e /app/eval` checks (api image) | `.github/workflows/ci.yml` |
| eval-only scripts | `set_eval_origin.sh`, `test_deploy_eval.sh`, `test_eval_image.sh`, `test_workflow_run_guard.py`; eval role in `release_target.py` + `test_release_targets.py`; `eval/web` in `test_hosting_targets.sh`; eval mapping in `required_gate.py` (verify none left after 01) |
| workspace | root `pyproject.toml` members `eval/*`; `uv lock` must only drop `onolys-eval*` entries; `.dockerignore`, `.gitignore` eval lines; `api/Dockerfile` eval manifest COPYs; `pr-preview.yml` paths `eval/*/pyproject.toml` |
| tests that name eval | `api/tests/test_dev_script_and_image.py:142` (members), `api/tests/test_logging.py:293` (Dockerfile list), `engines/core/tests/test_json_logging.py:186` (module name) |
| Firebase/identity | root `.firebaserc` `onolys-eval` target, `firebase.json` `eval` database entry |
| Terraform | delete `examples/{backend-eval.hcl,environment-eval.tfvars}.example`; adjust `infra/scripts/test_isolated_environment.py:90` (reads the tfvars example). Module/root code untouched (08) |
Kept for 08/06: `isolated-environment/bootstrap` (`eval` in `projects` map; removing it would plan to destroy a `prevent_destroy` state bucket), module `eval_*` variables, eval tests of the module.

## Architecture
```
Onolys/onolys                                  Onolys/onolys-eval (new)
  tag eval-base-v0 (api, engines/*, config, eval/ manifests)
        ^  git deps (api, core, miti, oneshot)        core/ backend/ web/ datasets/ fixtures/ config/ infra/ .github/
        |  + worker image = snapshot/api/Dockerfile + eval config/ overlay
        +------------------------------------------- deploy-eval.yml --WIF--> GCP project onolys-eval (unchanged)
                                                       backend, worker (same images' services), Hosting onolys-eval-app, Firestore db eval
                                                     Terraform state: gs://onolys-eval-tfstate/environment (unchanged)
```
Deploy trigger stays "CI green on main, then deploy" inside the new repo.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| 1 | Pin | One immutable tag `eval-base-v0` for api + 3 engine packages | Engine-only tag; registry release; per-package tags | Eval imports api and runs on the api worker; tags make 04-06 free of eval; no registry cost |
| 2 | History | `filter-repo` of eval paths, flatten, strip big blobs | Fresh copy | Keeps blame for 21 eval commits; cheap; blob strip handles the one leak risk |
| 3 | Visibility | Private repo [OPEN O2] | Public like this repo | Founders-only tool; names project/ids; deps are public so CI needs no token |
| 4 | Layout | Flatten (`core/`, `backend/`...) | Keep `eval/` nesting | A few mechanical path fixes now beats a permanent odd nesting; 09 restructures anyway |
| 5 | Shared features | No shared Python package; eval keeps its own auth/Firestore/storage/queue/uploads untouched | Extract a shared package now | Rule 5 puts these in the product; a package forces 06's design early. 09 decides after 06 (re-pin to a post-06 tag or keep copies) |
| 6 | Own sessions cut | Hand to 09, first item [OPEN O1] | Do in 03 | Needs an eval run path replacing api's worker (`jobs/run.py`, `create_run`) = a rewrite, not a move; also needs 06's data layer |
| 7 | Non-English datasets | Move `midas-es`, `phac-fr` untouched | Drop | Metadata only (manifests, converters); dropping is a 09 call |
| 8 | Terraform | Copy verbatim, same backend and addresses, plan-no-op gate | New state; `terraform state mv`; import | Zero risk to live eval project; no state surgery |
| 9 | Cut-over | New repo deployed and verified first; old workflow disabled just before; then delete | Delete first | Eval never has zero working pipeline; rollback = re-enable old workflow |
| 10 | Identity | Re-point existing WIF provider via `github_repository` | Second provider for both repos | One owner apply; old repo is retired anyway |
| 11 | Docs | Copy needed docs; leave originals | Move | Docs frozen; no broken links here |

## Manual steps
1. Create `Onolys/onolys-eval` (private), allow Actions, create GitHub environment `eval`.
2. Push tag `eval-base-v0` (and the branch commit it names) if the agent cannot.
3. Copy the `EVAL_*` / `GCP_REGION` repo variables from this repo to the new repo (names in R5).
4. From the new repo, with eval-project credentials: `terraform init` (existing backend), `plan` = no changes; then apply with `github_repository = "Onolys/onolys-eval"`.
5. Pick a window with **no eval run in progress**. `gh workflow disable deploy-eval` here, run `deploy-eval` in the new repo (`workflow_dispatch`), browser-check `eval.onolys.com`, start one small run.
6. After the merged removal PR: delete the now-unused `EVAL_*` variables here; add the eval repo ruleset; retire nothing in GCP.

## Risks / Open Questions
- [OPEN] O1: "own sessions" (stop writing api `SessionDoc`s) moves to 09 as its first item. Default: yes. It deviates from the locked text; confirm. Until then eval stays on `eval-base-v0`.
- [OPEN] O2: new repo private vs public. Default private.
- [OPEN] O3: uv resolution of four git subdirectory deps whose own pyprojects use `workspace = true` (~75% confident it works with explicit sources; not run). First task is a spike; fallback: build wheels in CI from the tag and install from a path.
- [OPEN] O4: Firestore rules for the eval DB: snapshot copy of prod rules (default) vs deny-all (the eval site uses no browser Firestore; unverified here).
- [OPEN] O5: worker image from tag + `config/` overlay (default) vs keep config baked at the tag.
- [DEFERRED] Trim staging/prod branches from the copied Terraform module; rename `EVAL_*` vars; rewrite stale eval docs here; `bootstrap` eval entry (08).
- Risk: drift guard fails runs if backend and worker `GIT_SHA` differ, or a deploy lands mid-run. Mitigation: R5(b), idle window.
- Risk: dataset content in history. Mitigation: blob strip, `test_repo_guard` ported, private repo.
- Risk: two roots applying one state. Mitigation: eval examples deleted here (R9); GCS lock.
- Risk: freeze means eval changes between tag and cut-over must be re-copied; keep the window short, no eval commits during it.
- Handed on: 06 deletes all api eval-mode code (`Settings.eval_mode`, `RunDoc.eval`/`EvalRunInfo`, `create_run(is_eval)`, `EvalDisabled`, `engines.resolve_engine/eval_snapshot`, `jobs/run.py` drift branch, `first_run` skip, `adapters/real.py` override); 04/05 decide oneshot's api dependency; 08 removes module `eval_*` vars, eval parts of the root, bootstrap `eval`, eval tests; 09 owns O1 and eval's use of shared modules.

## Acceptance Criteria
- Tag `eval-base-v0` exists on a pushed commit containing `api/`, `engines/{core,miti,oneshot}`, `config/`.
- New repo: `uv sync --frozen`, backend/core pytest, ruff, web typecheck/lint/test/build all green with this repo absent; no `@prod-*`, `web/src`, or workspace-path dependency.
- `git log --follow` shows eval history; no blob over 500 KB; `test_repo_guard` passes.
- `terraform plan` from the new repo against the live state shows no changes before the WIF apply.
- After deploy from the new repo: smoke passes (`/v1/me` 401, CSP lists backend), same service names and URLs, one small eval run completes end to end, backend and worker revisions carry the same `GIT_SHA`.
- This repo: `git grep -il "onolys_eval\|eval/" -- . ':!docs'` returns only intentional hits; `uv lock --check` clean and only eval packages removed; CI green; api image still builds and starts; zero `.tf` module/root edits.
