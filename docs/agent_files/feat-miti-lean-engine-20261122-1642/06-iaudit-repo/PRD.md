---
status: draft
summary: Code-only archive: create the new iaudit repo from tag iaudit-archive via git filter-repo (path-filtered history), push to owner-given URL, rename local folder iaudit->onolys, clone new repo at iaudit, update README rows. No CI/build. BLOCKED on owner's new repo URL.
date: 2026-11-22
---
# PRD: SP06 New iaudit repo from archive (Phase 4)

Repo/branch: new GitHub repo (URL [OPEN-1], owner-provided) · local clone `/root/projects/onolys/iaudit` (after renaming the existing folder to `/root/projects/onolys/onolys`) · Depends on: SP05 (tag `iaudit-archive` pushed) + owner's repo URL · Blocks: nothing
Owns: the new repo's pushed content; the local folder rename; edits to `/root/projects/README.md` and `/root/projects/onolys/README.md`. Not owned: Onolys/onolys (read-only; SP05 already deleted the code there).

## TL;DR
The new repo only HOLDS THE CODE for later. Clone Onolys/onolys at tag `iaudit-archive` (1cc7321), `git filter-repo` keeping the iaudit paths, push to the owner's empty repo. No CI, no workflow fixes, no build/test passing, no nightly/secrets, no pruning of dangling api/admin refs. Also rename the local Onolys folder and clone the new repo at the old path. Cannot start until owner gives URL + push access.

## Problem
- Evidence-audit work (eaudit, paudit, evaluation, core, eval harness, review/eval UI, ADRs 0001-0016) is deleted from Onolys/onolys by SP05; it must be preserved in its own repo for later.
- The tag alone is not a standalone home; a path-filtered repo with history is.

## Goals / Non-Goals
**Goals:** new repo containing iaudit code + path-relevant history, pushed; local folder layout fixed (`onolys/onolys` = Onolys repo, `onolys/iaudit` = new repo); local README rows updated.
**Non-Goals:** CI/workflows (`ci.yml`, `nightly.yml`, `changes.sh`) edits; making it build, lock, lint or pass tests; secrets; pruning MITI/api/admin leftovers or dangling refs beyond what filter-repo drops; deploying; new features; rewriting history/PR numbers; renaming the GitHub repo Onolys/onolys.

## Requirements
**R1 History.** `git clone --no-local <Onolys/onolys> work && cd work && git checkout iaudit-archive && git filter-repo --path engines/core --path engines/eaudit --path engines/paudit --path engines/evaluation --path eval --path frontend --path protocols --path docs --path pyproject.toml --path uv.lock --path scripts --path AGENTS.md --path README.md --path .gitignore --path .claude`. Run in a throwaway clone under the scratchpad, never in the Onolys worktree. Then `git remote add origin <url>` and push `main` (tags not needed). `filter-repo` must be pre-installed (`pip install git-filter-repo`). Path list is a keep-list for the archive; contents copied as-is (no CI files required).
**R2 Local folder rename (at SP06 time).** The existing `/root/projects/onolys/iaudit` holds Onolys/onolys. Rename it to `/root/projects/onolys/onolys` (the repo's real name), then run `git worktree repair` (main checkout and each worktree) so git worktrees under it resolve. Then clone the new repo to `/root/projects/onolys/iaudit`. Do it only when no open sessions/worktrees are using the old path.
**R3 Local README.** Update `/root/projects/README.md` and `/root/projects/onolys/README.md`: row `onolys/onolys` (Onolys MITI, repo Onolys/onolys) and row `onolys/iaudit` (new repo URL, "Interview evidence audit code archive: eaudit/paudit engines, evaluation harness, review UI. Extracted from Onolys/onolys@iaudit-archive"). Reconcile with the wording SP05 wrote for the old `onolys/iaudit` row.
**R4 Archive note.** Optionally add a one-line "extracted from Onolys/onolys@iaudit-archive; code archive, not built or tested" to the new repo README as a normal commit on top.

## Architecture
```
Onolys/onolys @ iaudit-archive (1cc7321)
   | git filter-repo (keep: engines/{core,eaudit,paudit,evaluation}, eval, frontend, protocols, docs, scripts, root config)
   v
new iaudit repo (code + history only)  --> cloned at /root/projects/onolys/iaudit
local: /root/projects/onolys/iaudit (Onolys) --rename + git worktree repair--> /root/projects/onolys/onolys
```
History evidence (`git log origin/main`, 41 commits): #1-#33 are all iaudit; after #33, path-touching commits are few (eaudit #35/#47, paudit #35, evaluation #35/#47, core #35/#45/#47, eval #35, frontend #35, protocols #35/#45). #36-#49 are mostly MITI platform/api/web/infra and are dropped by the filter except where they touched kept paths.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | History | filter-repo on iaudit-archive, kept paths, full history | truncate at #32/#33; plain snapshot | Keeps blame/PR trail, drops MITI noise automatically |
| D2 | Tip state | Tag state (1cc7321) of kept paths | Reset to #32 | Post-32 code is what works |
| D3 | Scope | Code-only archive: no CI, build, secrets, pruning | Standalone buildable repo | Owner 2026-11-22: only holding code for later |
| D4 | Source repo | Onolys/onolys unchanged (tag is the only link) | Move/fork | SP05 deletes; tag immutable |
| D5 | Local layout | Rename existing folder to `onolys/onolys`, new clone at `onolys/iaudit` | `iaudit-legacy` | Owner 2026-11-22; folder named after real repo |

## Manual steps (owner)
1. Create empty GitHub repo (no README/license), choose name and visibility.
2. Give URL; grant Claude/this machine push access (gh auth or deploy key).

## Risks / Open Questions
- [OPEN-1] New repo URL/name and push access (BLOCKED on owner; whole SP waits).
- [RESOLVED: new clone goes at `/root/projects/onolys/iaudit`; the existing local folder `/root/projects/onolys/iaudit` (holds Onolys/onolys) is first renamed to `/root/projects/onolys/onolys`, worktrees repaired via `git worktree repair`; done at SP06 time; `/root/projects/README.md` + `/root/projects/onolys/README.md` rows updated, owner 2026-11-22] (OPEN-2)
- [RESOLVED: not needed — code-only archive, owner 2026-11-22] (OPEN-3 `changes.sh`, OPEN-4 core pruning, OPEN-5 nightly secrets)
- [RESOLVED: history option a, D1]
- [DEFERRED] Making the repo buildable/CI'd; renaming packages `onolys-*` to `iaudit-*`; publishing; deleting the tag from Onolys/onolys.
- Risk: local rename breaks open git worktrees (`.worktrees/*`, absolute paths in `.git/worktrees/*/gitdir`) and any Claude sessions/tools using the old path. Mitigation: do at SP06 time with no open sessions; `git worktree repair` from the renamed main checkout (pass worktree paths if needed); verify `git worktree list` and `git status` in each.
- Risk: filter drops a path someone later needs. Mitigation: tag `iaudit-archive` stays in Onolys/onolys; re-run filter with more paths.

## Acceptance Criteria
1. New repo `main` pushed to owner URL; contains `engines/{core,eaudit,paudit,evaluation}`, `eval/`, `frontend/`, `protocols/`, `docs/`; no `api/`, `web/`, `admin/`, `infra/` (dropped by filter). No CI/build/test expectation.
2. `git log --oneline` shows PRs #1-#33 history for kept paths.
3. `/root/projects/onolys/onolys` is the Onolys/onolys repo; `git worktree list` there resolves all worktrees; `/root/projects/onolys/iaudit` is the new repo clone.
4. `/root/projects/README.md` and `/root/projects/onolys/README.md` rows updated for both folders; owner-provided URL recorded.
