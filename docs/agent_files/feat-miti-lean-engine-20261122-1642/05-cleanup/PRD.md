---
status: approved
summary: Phase 3 cleanup (breaking changes fine, prod unused) - tag `iaudit-archive` at 1cc7321, then delete eaudit/paudit/evaluation/core, protocols/, eval/, backend/ and their CI/docs; rewrite mission/AGENTS/README/architecture to MITI-only; regenerate uv.lock.
date: 2026-11-22
---
# PRD: SP05 Cleanup + docs (Phase 3)

Repo/branch: Onolys/onolys (local `iaudit`) / `feat/miti-lean-engine` · Depends on: SP02 (api on `onolys_miti`), SP04 (admin shell), SP01, SP03 (web path fixes) · Blocks: SP06
Owns: deletions below; `pyproject.toml`, `uv.lock`, `.github/workflows/{ci,nightly}.yml`, `scripts/ci/{changes.sh,test_changes.sh,check_config.sh,test_check_config.sh}`, `scripts/{dev.sh,README.md}`, `.dockerignore`, root docs (`AGENTS.md`, `README.md`, `docs/{mission,architecture}.md`, `docs/{concepts,implementation,reference,decisions,testing,examples,contracts}/**`). Not owned: `engines/miti`, `api/src`, `web/src` features, `admin/**`, `frontend/**`. `infra/` is owned here for the cleanup in R7 (admin-only parts stay with SP04).

## TL;DR
Tag first, delete second. `git tag iaudit-archive 1cc7321` (current `origin/main` = merge base of this branch, [verified: `git rev-list 1cc7321..origin/main` = 0]), push to origin, then remove everything that is not MITI. One PR commit per step so a revert is easy. The deletion is gated by greps proving nothing kept imports the removed paths; SP02/SP03/SP04 must have landed on the branch. Docs are rewritten to a MITI-only scope; eaudit-only docs are deleted, mixed docs are trimmed.

## Problem
- Repo is still "Interview Evidence Auditor": `README.md`, `AGENTS.md` (engine list `eaudit`/`paudit`/`caudit`), `docs/mission.md` (196 lines of evidence audit) [verified].
- Dead packages inflate CI: jobs `eaudit`, `core`, `paudit`, `evaluation`, nightly `eval-oracle`, plus `changes.sh` flags/DEPS for them [verified: ci.yml, nightly.yml, changes.sh].
- Kept code still names the old layout in comments/paths (see R2 sweep), which would dangle after deletion.

## Goals / Non-Goals
**Goals:** nobody uses prod, so breaking changes are fine (owner 2026-11-22): no backward-compat, no deploy ordering. Archive tag pushed; removed dirs gone; CI/workspace/lock consistent and green; docs describe only MITI coding; `check_links.py` green; kept-part references to removed paths = 0.
**Non-Goals:** building the iaudit repo (SP06, blocked on owner's GitHub link); code changes in api/web/admin/engines/miti beyond path fixes below; rewriting `docs/agent_files/` history; renaming GCP projects or the buckets holding Terraform state; renaming this repo/folder on GitHub.

## Requirements
**R1. Archive tag (first commit-free step).**
- `git fetch origin && git tag -a iaudit-archive 1cc7321 -m "Last commit holding eaudit, paudit, evaluation, core, protocols/, eval/, old admin UI; source for the iaudit repo"` then `git push origin iaudit-archive`. If `origin/main` moved before SP05 runs, still tag `1cc7321` unless the extra commits matter to iaudit (default: no). Verify `git ls-remote --tags origin iaudit-archive` and that the tag holds `engines/eaudit`, `eval/`, `frontend/src/eval`. Never move the tag; tags are immutable by convention. Owner approved tagging and pushing `iaudit-archive` (2026-11-22). If the push is refused (permission/protection) or the tag already exists on another commit, record BLOCKED and continue.
- Tag, not a branch: a branch invites commits and is deleted by `dev-cleanup`; the tag survives squash merge.

**R2. Delete list + reference evidence** (all `[verified]` at 1cc7321; implementer re-runs the greps, which must be empty before each `git rm`).

| Delete | Kept-side references found today (must be fixed by owner SP or here) |
|---|---|
| `engines/{eaudit,paudit,evaluation,core}` (4 pkgs) | `api/pyproject.toml` (3 deps + sources) and ~29 `api/tests` + ~20 `api/src` imports -> SP02. `admin/backend` (`eaudit`,`core`,`paudit`) -> SP04. `api/tests/{test_real_flow,test_run_artifacts,test_live_real_mode}.py` `sys.path` into `engines/evaluation/tests`; `test_adapters.py`/`test_live_real_mode.py` read `engines/{evaluation,paudit}/schemas` -> SP02 (point at `engines/miti`). `web/package.json` `gen:api` and `web/src/mocks/fixtures/schema.test.ts` read `engines/evaluation/schemas/report.schema.json` and `protocols/miti-4.2.1/fixtures` -> SP03/this PR repoints to `engines/miti/{schemas,data/fixtures}` |
| `protocols/` | `api/Dockerfile:35` `COPY protocols`, `PAUDIT_PROTOCOLS_DIR` (also `api/tests/test_rating.py:430`, `adapters/real.py`, `rating.py`, `voice/scenarios.py` docstrings/reads) -> SP02; `admin/backend/Dockerfile` -> SP04; `deploy-admin.yml` paths, `test_deploy_admin.sh:16`, `test_admin_image.sh:48`, `changes.sh` `PAUDIT_EXTRA_RE` -> SP04/R3 |
| `eval/` (own pyproject + uv.lock, excluded from workspace) | `.dockerignore` (`eval`, `**/eval`), `scripts/dev.sh`/`scripts/README.md` `[eval]` entry (port 8100), `frontend/src/eval` (SP04 deletes), `docs/reference/eval-*.md`. No workflow runs `eval/` [verified] |
| `backend/` | 0 tracked files, empty dir: `rmdir` only |
| Root eaudit contracts: `docs/contracts/{audit-request,audit-response,error-response}.schema.json`, `docs/contracts/examples/` | Only `scripts/ci/check_config.sh:21` + `test_check_config.sh:7` and `api/Dockerfile:39` (`COPY docs/contracts/*.schema.json`); `IAUDIT_CONTRACTS_DIR` read nowhere in `api/src`. **Keep `docs/contracts/public/**`** (api generates it, web uses it) |
| `engines/*/README.md`, `eval/README.md` | go with their dirs |

- Order: (1) repoint residual kept-side refs, (2) `git rm -r`, (3) `rg -n "engines/(core|paudit|eaudit|evaluation)|protocols/|PAUDIT_PROTOCOLS|onolys_core|onolys_evaluation|\beaudit\b|\bpaudit\b|iaudit_eval|eval/" -g '!docs/agent_files/**' -g '!uv.lock' .` -> hits only in historical ADRs (R5) and `README`-style lines being rewritten. `docs/agent_files/**` is excluded from the grep and from `check_links.py` [verified: skips `docs/agent_files/`].
- `api/Dockerfile`: implementer verifies at coding time which `COPY` lines (`protocols`, `docs/contracts/*.schema.json`, `config`) still resolve after SP02 and removes only dangling ones, plus old `PAUDIT_PROTOCOLS_DIR` / `IAUDIT_CONTRACTS_DIR` `ENV` lines (SP04 does the same in the admin Dockerfile).
- `.dockerignore`: drop `eval`, `**/eval`, `**/datasets`; keep `!docs/contracts` only if api still copies it (R4 default: api copies `docs/contracts/public`? decide with SP02; else drop).
- `.claude/` and thepass plugin lines in README stay.

**R3. CI and scripts.**
- `ci.yml`: remove `env.EAUDIT_DIR` and jobs `eaudit`, `core`, `paudit`, `evaluation` and their `changes` outputs; add job `miti` (copy the `core` job shape): `uv sync --frozen --package onolys-miti`, `ruff check engines/miti`, `pytest engines/miti -m "not live" --cov=engines/miti/src`, coverage summary. The job is added here, not in SP01 (owner 2026-11-22); SP01 only writes the unit tests. Check every `needs:` list and any aggregate/required-check job that names removed jobs (`api-coverage`, final gate) [implementer greps `needs:`].
- `changes.sh`: PACKAGES = `miti:engines/miti:python`, `api`, `admin-auth`, `admin-backend`, `frontend`, `web`, `infra`. `PY_SHARED_RE='^(pyproject\.toml|uv\.lock)'` (drop `engines/core/`). Delete `PAUDIT_EXTRA_RE`. `WEB_EXTRA_RE` -> `engines/miti/schemas/report\.schema\.json`. DEPS: `api:miti`, `admin-backend:admin-auth` (SP04 already sets the latter; reconcile, don't duplicate). Comments updated. `FRONTEND_EXTRA_RE`/admin extras: SP04 owns; just verify.
- `test_changes.sh`: rewrite cases for the new flag list (`miti=…`); keep the shared-path, FORCE_ALL, and dependent-propagation cases (api reruns when `engines/miti` changes). `test_changes_deps.py` needs no logic change (reads pyprojects) [verified: SP04].
- `nightly.yml`: delete job `eval-oracle` (eaudit eval, `python -m eval.run`); **keep** `api-real-mode` (uses `GEMINI_API_KEY`, api only). File stays; no empty workflow.
- Branch protection does not require checks by name (owner 2026-11-22): nothing to update in GitHub settings for the removed jobs.
- `ANTHROPIC_API_KEY`: used by no workflow; only infra `llm_secrets` default, `seed-secrets.py`, `check-staging.py` and `scripts/dev.sh` warning [verified]. It feeds the `claude` routes preset, so **leave it** (not a repo secret to remove). Nothing to delete in GitHub settings.
- Deploy workflows: `deploy-admin.yml` path triggers handled by SP04. `deploy-staging/prod`, `_deploy-cloudrun`, `pr-preview*` contain no `engines/`, `protocols/`, `eval` refs [verified: grep]; no change.
- `check_config.sh`/`test_check_config.sh`: drop the `audit-request audit-response error-response` loop and its image check (R2); keep `config/*/{routes,stt_providers}.yaml` checks.
- `scripts/dev.sh`: drop the `backend` launch (`engines/eaudit`, line 130) and `eval` entry; `scripts/README.md` table updated. Keep api/web/admin launchers.

**R4. Workspace.** Root `pyproject.toml`: members `["engines/*","api","admin/*"]` resolves to `engines/miti`, `api`, `admin/auth`, `admin/backend` once old engines are gone, so only the stale header comment changes; drop `exclude = ["eval"]` (dir gone). `uv lock` regenerated (never hand-merge), `uv sync --frozen` per package in CI proves it; lock must not mention `onolys-core|paudit|evaluation|eaudit|iaudit-eval`. `api/Dockerfile` workspace manifest layer: SP02 owns the switch; SP05 verifies the image still builds (CI `api-image`).

**R4b. Infra cleanup now (owner 2026-11-22).** (a) Verify `infra/` has no `engines/`, `protocols/`, `PAUDIT_*`, `IAUDIT_*` refs and no `paudit`/`iaudit`/`eaudit` in resource names, labels, descriptions, comments (today: none except the admin bits SP04 removes; `ROUTES_FILE`/`DEFAULT_PRESET` stay for api+worker). (b) Anything else found: rename/remove in Terraform, including renames that force resource replacement (prod unused); do NOT rename GCP projects or the buckets holding Terraform state. (c) Old Cloud Run env vars `PAUDIT_PROTOCOLS_DIR` / `IAUDIT_CONTRACTS_DIR` are not set in Terraform [verified: no hits in `infra/`]; they only come from Dockerfile `ENV` lines (removed per R2/SP04), so they disappear at next image deploy. (d) `terraform apply` for staging and prod run by the agent (allowed, owner 2026-11-22); `terraform plan` clean afterwards. If credentials are missing at run time, record BLOCKED, keep going. SP04 owns the admin LLM secret env, `ROUTES_FILE`, and `admin_llm` IAM removal.

**R4c. Naming sweep (owner 2026-11-22).** Remove `paudit`/`iaudit`/`eaudit` naming from kept files: `scripts/dev.sh` (`IAUDIT_PIPELINE`, `IAUDIT_BACKEND_URL`, `IAUDIT_EVAL_PORT`), `scripts/README.md`, CI (`ci.yml`, `nightly.yml`, `changes.sh`, `test_changes.sh`, `check_config.sh`), `config/*/routes.yaml` + `stt_providers.yaml` comments (route names `paudit_code`/`paudit_globals` -> `miti_code`/`miti_globals` are SP02; SP05 only sweeps comments and verifies configs match), infra names/labels (R4b), docs, root `README.md` (title "Interview Evidence Auditor" -> "Onolys MITI"), `.dockerignore`, package metadata. Historical text allowed only in `docs/agent_files/**`, superseded ADR banners, ADR 0025 and the archive note. Final grep: `rg -ni "iaudit|paudit|eaudit|interview evidence"` excluding `docs/agent_files/**`, `uv.lock` hits only the allowed places.

**R5. Docs** (judgment by grep counts above; "eaudit-ish" = mentions of eaudit/paudit/evaluation/core/eval/protocols).

| Action | Files |
|---|---|
| Rewrite to MITI-only | `docs/mission.md` (~196 -> short: who, what, MITI 4.2.1 coding, report + tips, non-goals, no official-MITI claim), `AGENTS.md` (scope = MITI coding only, no engine list; docs table drops `engines/` core wording and the "verdicts/concern types mirror mission" line), `README.md` (title Onolys; links to mission, `engines/miti`, `web/`, `api/`), `docs/architecture.md` (api -> `onolys_miti`, STT/LLM/voice, web, admin shell) |
| Delete (eaudit/review-ui only) | `docs/concepts/{how-an-audit-decides,limits-of-an-audit,missing-role,review-ui,severity-and-frequency}.md`; `docs/implementation/{assembler,check,eval-server,frontend,link,pipeline,prep-atomize}.md`; `docs/reference/{eval-api,eval-ui,review-ui}.md`; `docs/testing/{evaluation,frontend}.md`; `docs/examples/` (eaudit curl/python/mock/real; public-API examples live in `docs/reference/public-api.md`); `docs/decisions/0001-0016` (eaudit design, pre-reset) |
| Trim | `docs/reference/{backend-api,configuration,testing,staging-e2e}.md`, `docs/testing/{local-setup,running-tests,pre-release-checklist,latency}.md`, `docs/implementation/{llm-client,logging-and-phi}.md`: remove eaudit/eval sections and package names; point to `engines/miti`; `backend-api.md` -> admin shell `/v1/me` only (coordinate SP04 note) |
| Keep | `docs/reference/{infra,public-api,warnings,web-email-actions}.md`, `docs/implementation/infra-staging-first-apply.md`, `docs/testing/fuzz-and-mutation.md`, `docs/decisions/{0020-0022,0024}`, `docs/contracts/public/**`, `docs/agent_files/**` |
| Keep + supersede note | ADRs `0017`, `0018`, `0019`, `0023`: add one-line banner "Superseded by lean-engine decision (D1)"; add new ADR `0025-miti-only-lean-engine` (reverses 0017/0018 protocol-agnostic engines, records tag name). Never edit history bodies |
| Regenerate | `docs/*/README.md` indexes after deletions; `docs/contracts/README.md` rewritten to a pointer to `public/` (current 287 lines are eaudit) |

- `check_links.py` must pass after deletions: fix inbound links from kept docs to deleted ones. Run it before and after.
- External READMEs (small edits, outside repo): `/root/projects/README.md` row `onolys/iaudit` and `/root/projects/onolys/README.md` row `iaudit` -> "Onolys: clinician MI practice sessions, MITI 4.2.1 coding, report + tips (api, web, admin shell). Archive of the evidence-audit engines at tag `iaudit-archive`." Local folder stays `iaudit` unless owner renames (note in text).

**R6. What SP06 needs from the tag** (documented in ADR 0025, not built here)
- Tag `iaudit-archive` -> `1cc7321`, holds: `engines/{core,eaudit,paudit,evaluation}`, `protocols/`, `eval/` (+datasets, TofuEval), old `frontend/` review/eval UI, `backend/` (empty), eaudit docs/contracts, `docs/agent_files/` history, root `pyproject.toml`/`uv.lock`, CI jobs/nightly at that commit.
- Recipe: `git clone --no-local <onolys> iaudit && git checkout iaudit-archive` (or `git filter-repo` to keep history), then in the new repo delete api/, web/, admin/, infra/ etc. SP06 owns what to keep; SP05 only guarantees the tag and that history `docs/agent_files/` remains.

## Architecture
```
Before: api/admin -> core, paudit, evaluation, eaudit ; protocols/ ; eval/ ; CI x4 pkgs
After : api -> onolys_miti (engines/miti, data inside) ; admin shell (no engines) ; web ; infra
Archive: tag iaudit-archive (1cc7321) -> future Onolys/iaudit repo (SP06)
```
Sequence: tag -> repoint residual refs -> delete dirs -> CI/scripts -> `uv lock` -> docs -> link check -> external READMEs.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | Archive mechanism | Annotated tag `iaudit-archive` on `1cc7321`, pushed | Branch; fork; separate copy of dirs | Immutable, no upkeep, survives squash merge; commit is the last one holding everything (incl. old admin UI SP04 removes) |
| D2 | When to delete | Now, not waiting on the SP06 link | Wait | Locked; tag makes it safe |
| D3 | `docs/agent_files/` | Keep all history | Prune eaudit-era folders | Locked default; excluded from link check and greps; costs nothing |
| D4 | Old ADRs | Keep 0017-0019, 0023 with superseded banner; delete 0001-0016 (eaudit) | Keep all; delete all | History of the MITI decisions is still useful; 0001-0016 describe a deleted engine and are in the tag |
| D5 | Nightly | Delete `eval-oracle`, keep `api-real-mode` | Delete file | Real-mode live check still valid |
| D6 | `ANTHROPIC_API_KEY` | Leave | Remove from infra | Needed by `claude` preset; not workflow-only |
| D7 | Eaudit contract files | Delete (root `audit-*`, `error-response`, `examples/`), keep `public/` | Keep all | Only referenced by a config check and a Docker COPY, no runtime read |
| D8 | `uv.lock` | Regenerate once, last, after rebase on SP01-04 | Merge by hand | Conflicts certain; lock is derived |
| D9 | Commit granularity | One commit per R (tag step has no commit) | One big commit | Revertable; matches commit discipline |

## Manual steps (owner)
- None. (Tag push approved; branch protection does not require checks by name; terraform apply is agent-run.)
- SP06 needs the owner's GitHub link (not this SP).

## Risks / Open Questions
- [RESOLVED: archive tag `iaudit-archive` on 1cc7321 push to origin approved; `git ls-remote` showed only `prod-*` tags; record BLOCKED if push refused, owner 2026-11-22] (OPEN-1)
- [RESOLVED: branch protection does not require checks by name; no manual step, owner 2026-11-22] (OPEN-2)
- [RESOLVED: implementer verifies at coding time; default: remove only dangling `api/Dockerfile` COPY lines after SP02 and verify image build, owner 2026-11-22] (OPEN-3)
- [RESOLVED: implementer verifies at coding time; default: `infra/` has no package/path refs [verified today: none]; cleanup per R4b is now in scope, owner 2026-11-22] (OPEN-4)
- [RESOLVED: infra cleanup happens now; agent runs `terraform apply` staging+prod; BLOCKED only if credentials missing, owner 2026-11-22]
- [RESOLVED: full rename sweep away from paudit/iaudit/eaudit across repo, R4c; infra renames forcing replacement fine; keep GCP projects and state buckets, owner 2026-11-22]
- [RESOLVED: prod unused, breaking changes fine, no compat or deploy ordering, owner 2026-11-22]
- [RESOLVED: keep `docs/agent_files/`, D3]
- [RESOLVED: `ANTHROPIC_API_KEY` not nightly-only, D6]
- [DEFERRED] Renaming local folder `iaudit` / GitHub repo; rewriting `web` docs; trimming `Report` model.
- Risk: deleting before SP02/03/04 land breaks the branch. Mitigation: precondition grep in R2; SP05 runs last.
- Risk: `uv.lock` drift/rebase conflicts. Mitigation: D8.
- Risk: docs deletion leaves dangling inbound links. Mitigation: `check_links.py` in CI and locally.

## Acceptance Criteria
1. `git ls-remote --tags origin iaudit-archive` shows a tag resolving to `1cc7321`; `git ls-tree -r --name-only iaudit-archive | rg "^(engines/eaudit|eval|protocols)/"` non-empty.
2. `engines/{eaudit,paudit,evaluation,core}`, `protocols/`, `eval/`, `backend/` absent; `rg` from R2 returns hits only in `docs/agent_files/**`, superseded ADR banners and ADR 0025. R4c final grep (`iaudit|paudit|eaudit|interview evidence`) hits only those same places.
3. `uv lock --check` passes; lock has no `onolys-core|onolys-paudit|onolys-evaluation|eaudit|iaudit-eval`; workspace members = `engines/miti`, `api`, `admin/auth`, `admin/backend`.
4. `bash scripts/ci/test_changes.sh`, `python3 scripts/ci/test_changes_deps.py`, `bash scripts/ci/test_check_config.sh`, `python3 scripts/ci/check_links.py` pass; actionlint clean; ci.yml has job `miti` and none of the four removed.
5. CI on the PR green (miti, api*, admin-*, web, frontend); `nightly.yml` has only `api-real-mode`.
6. `README.md`, `AGENTS.md`, `docs/mission.md`, `docs/architecture.md` contain no `eaudit|paudit|caudit|Interview Evidence`; docs READMEs list only existing files.
7. `terraform plan` clean for staging and prod after the agent-run apply (or recorded BLOCKED on missing credentials); no `PAUDIT_*`/`IAUDIT_*` env in Dockerfiles or Cloud Run.
8. `/root/projects/README.md` and `/root/projects/onolys/README.md` descriptions updated.
