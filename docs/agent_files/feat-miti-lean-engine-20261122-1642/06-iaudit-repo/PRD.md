---
status: draft
summary: Create the standalone iaudit repo from tag iaudit-archive via git filter-repo (path-filtered full history), make it build/test standalone with a trimmed CI, update local README rows. BLOCKED on owner's new repo URL.
date: 2026-11-22
---
# PRD: SP06 New iaudit repo from archive (Phase 4)

Repo/branch: new GitHub repo (URL [OPEN], owner-provided) · local clone `/root/projects/onolys/<folder>` ([OPEN-2]) · Depends on: SP05 (tag `iaudit-archive` pushed) + owner's repo URL · Blocks: nothing
Owns: the new repo's content, its `ci.yml`, its README/AGENTS; edits to `/root/projects/README.md` and `/root/projects/onolys/README.md`. Not owned: Onolys/onolys (read-only; SP05 already deleted the code there).

## TL;DR
Clone Onolys/onolys at tag `iaudit-archive` (1cc7321), run `git filter-repo` keeping only evidence-audit paths, push to the owner's empty repo. Then fix standalone build (workspace, CI, docs). No deploy, no cloud secrets; tests only. Cannot start until owner creates the repo and gives URL + push access.

## Problem
- Evidence-audit work (eaudit, paudit, evaluation, core, eval harness, review/eval UI, ADRs 0001-0016) is deleted from Onolys/onolys by SP05; it must live on as its own project.
- The tag alone is not a usable repo: it is full of MITI/api/web/admin/infra code that does not belong, and its CI/workspace assume those.

## Goals / Non-Goals
**Goals:** new repo with iaudit code + path-relevant history; `uv sync`, tests, lint, frontend build/test pass standalone in CI; README says what it is and its relation to Onolys; local README rows updated.
**Non-Goals:** deploying anything; new features; reviving api/web/admin/infra; porting MITI code; rewriting history/PR numbers; renaming Onolys/onolys.

## Requirements
**R1 History.** `git clone --no-local <Onolys/onolys> work && cd work && git checkout iaudit-archive && git filter-repo --path engines/core --path engines/eaudit --path engines/paudit --path engines/evaluation --path eval --path frontend --path protocols --path docs --path pyproject.toml --path uv.lock --path scripts/ci --path .github/workflows/ci.yml --path .github/workflows/nightly.yml --path AGENTS.md --path README.md --path .gitignore --path .claude`. Run in a throwaway clone under the scratchpad, never in the Onolys worktree. Then `git remote add origin <url>` and push `main` (clone is fresh; tags not needed). `filter-repo` must be pre-installed (`pip install git-filter-repo`).
**R2 Prune after filter** (normal commit on top, one per step): from `docs/` delete MITI/platform material (ADRs 0017-0024 except what describes core/paudit/evaluation, `reference/{infra,public-api,web-email-actions,staging-e2e}`, `docs/contracts/public/`, `agent_files/*lean-engine*` and other MITI-platform agent folders); keep `docs/agent_files/` iaudit-era folders as history. Prune MITI-only code that later landed in `engines/core` (voice/usage bits from #45/#47) only if it blocks tests [OPEN-4].
**R3 Standalone build.**
- Root `pyproject.toml`: workspace members `engines/*` only; drop `api`, `admin/*`; `exclude=["eval"]` stays (eval has its own project) [verified at tag: members `["engines/*","api","admin/*"]`, exclude `eval`]. Regenerate `uv.lock` with `uv lock`.
- `ci.yml`: keep jobs `eaudit`, `core`, `paudit`, `evaluation`, `eval` unit tests, `frontend` (npm ci, lint, test, build); delete `api*`, `admin-*`, `web`, `infra`, image/deploy jobs, `changes` flags for them. Simplify `scripts/ci/changes.sh`/`test_changes.sh` accordingly or drop the changes gating and run all jobs (small repo) [OPEN-3].
- `nightly.yml`: keep `eval-oracle` (eaudit eval); delete `api-real-mode`.
- Fix dangling refs: `api/`/`admin/` paths in scripts (`scripts/dev.sh`, `check_config.sh` and `config/`) and docs; `docs/contracts/` kept (audit-*.schema.json + examples); run `check_links.py` and fix broken links to deleted docs.
- Docs: README/AGENTS/mission restored to the iaudit text from the tag (not the MITI rewrite); add a line "extracted from Onolys/onolys@iaudit-archive".
**R4 Secrets/CI.** None deployed. Unit tests are recorded-replay, no network [verified: ADR 0013]. Live eval (nightly) needs `ANTHROPIC_API_KEY` and/or `GEMINI_API_KEY` as GitHub Actions secrets in the new repo; default: add them only if owner wants nightly, else disable nightly (`workflow_dispatch` only). No cloud/WIF/Terraform config.
**R5 Local README.** After clone: add row in `/root/projects/README.md` and `/root/projects/onolys/README.md` for `onolys/<folder>` (new repo URL, "Interview evidence audit: eaudit/paudit engines, evaluation harness, review UI. Extracted from Onolys/onolys@iaudit-archive"); update the `onolys/iaudit` row wording that it now holds only Onolys MITI (SP05 owns that text; reconcile).

## Architecture
```
Onolys/onolys @ iaudit-archive (1cc7321)
   | git filter-repo (paths: engines/{core,eaudit,paudit,evaluation}, eval, frontend, protocols, docs, uv config, CI subset)
   v
new iaudit repo:  engines/* (uv workspace) + eval/ (own project) + frontend/ + protocols/ + docs
CI: python jobs per engine + eval unit + frontend build; nightly eval-oracle (optional)
```
History evidence (`git log origin/main`, 41 commits): #1-#33 are all iaudit; after #33, path-touching commits are few: eaudit (#35 docs, #47), paudit (#35), evaluation (#35, #47), core (#35, #45, #47), eval (#35), frontend (#35), protocols (#35, #45). #36-#49 are mostly MITI platform/api/web/infra and are dropped by the filter except where they touched kept paths.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | History | (a) filter-repo on iaudit-archive, kept paths, full history | (b) truncate at #32/#33 then copy later state; (c) plain snapshot | Owner wants "up to ~#32"; #33 (eaudit v0, contract 0.0.1, taxonomy v2) is iaudit work and post-#33 edits to kept paths are few and relevant; (a) keeps blame/PR trail and drops MITI noise automatically. (b) loses #33 or needs manual merge; (c) loses history |
| D2 | Tip state | Tag state (1cc7321) of kept paths | Reset to #32 content | Post-32 code is what works (taxonomy v2, 0.0.1 contract) |
| D3 | Prune MITI leftovers | Normal commits after filter | Rewrite in filter | Revertable, explicit |
| D4 | CI | Keep per-engine jobs, drop api/admin/web/infra/deploy | Single job | Mirrors existing, low rework |
| D5 | Nightly | Keep eval-oracle, manual-dispatch unless owner adds keys | Delete | Oracle eval is the harness's point |
| D6 | Source repo | Onolys/onolys unchanged (tag is the only link) | Move/fork | SP05 already deletes; tag immutable |

## Manual steps (owner)
1. Create empty GitHub repo (no README/license), choose name and visibility.
2. Give URL; grant Claude/this machine push access (gh auth or deploy key).
3. Optional: add `ANTHROPIC_API_KEY`/`GEMINI_API_KEY` Actions secrets for nightly eval; set branch protection and required checks for the new CI job names.

## Risks / Open Questions
- [OPEN-1] New repo URL/name and push access (BLOCKED on owner; whole SP waits).
- [OPEN-2] Local folder: `/root/projects/onolys/iaudit` already holds Onolys/onolys. Default `/root/projects/onolys/iaudit-legacy`; after owner names the repo, use the repo name instead.
- [OPEN-3] Keep `changes.sh` gating or run everything. Default: run everything (small repo), delete `changes.sh`/tests.
- [OPEN-4] Whether `engines/core` at the tag carries MITI-only code (#45/#47) that needs pruning. Default: check `pytest` after filter; prune only failures.
- [OPEN-5] Nightly secrets, see R4. Default: manual-dispatch only.
- [RESOLVED: history option a, D1]
- [DEFERRED] Renaming packages from `onolys-*` to `iaudit-*`; publishing; deleting the tag from Onolys/onolys.
- Risk: filter drops a path the engines import (e.g. `config/`, `scripts/`). Mitigation: run `uv sync` + tests in the clone before pushing.
- Risk: path-filtered `docs/` links break. Mitigation: `check_links.py`.

## Acceptance Criteria
1. New repo `main` contains `engines/{core,eaudit,paudit,evaluation}`, `eval/`, `frontend/`, `protocols/`, `docs/`; no `api/`, `web/`, `admin/`, `infra/`.
2. `git log --oneline` shows PRs #1-#33 history for kept paths.
3. `uv lock --check`, `uv sync --frozen`, and unit tests for each engine pass; `npm ci && npm run build && npm test` in `frontend/` pass.
4. CI on the first PR/push is green; no job refers to removed packages; `rg -n "onolys_miti|engines/miti|api/|admin/" .github scripts pyproject.toml` has no hits.
5. README states purpose and "extracted from Onolys/onolys@iaudit-archive".
6. `/root/projects/README.md` and `/root/projects/onolys/README.md` have the new row; owner-provided URL recorded.
