---
status: draft
summary: Code-only archive: create the new iaudit repo from tag iaudit-archive via git filter-repo (path-filtered history), push to owner-given URL, clone new repo at /root/projects/onolys/iaudit-legacy (no rename of existing iaudit folder), update README rows. No CI/build. BLOCKED on owner's new repo URL.
date: 2026-11-22
---
# PRD: SP06 New iaudit repo from archive (Phase 4)

Repo/branch: new GitHub repo (URL [OPEN-1], owner-provided) · local clone `/root/projects/onolys/iaudit-legacy` (existing `/root/projects/onolys/iaudit` stays as is, no rename) · Depends on: SP05 (tag `iaudit-archive` pushed) + owner's repo URL · Blocks: nothing
Owns: the new repo's pushed content; the local clone; edits to `/root/projects/README.md` and `/root/projects/onolys/README.md`. Not owned: Onolys/onolys (read-only; SP05 already deleted the code there).

## TL;DR
The new repo only HOLDS THE CODE for later. Clone Onolys/onolys at tag `iaudit-archive` (1cc7321), `git filter-repo` keeping the iaudit paths, push to the owner's empty repo. No CI, no workflow fixes, no build/test passing, no nightly/secrets, no pruning of dangling api/admin refs. Also clone the new repo locally at `/root/projects/onolys/iaudit-legacy`; the existing local folder is not renamed. Cannot start until owner gives URL + push access.

## Problem
- Evidence-audit work (eaudit, paudit, evaluation, core, eval harness, review/eval UI, ADRs 0001-0016) is deleted from Onolys/onolys by SP05; it must be preserved in its own repo for later.
- The tag alone is not a standalone home; a path-filtered repo with history is.

## Goals / Non-Goals
**Goals:** new repo containing iaudit code + path-relevant history, pushed; local layout: `onolys/iaudit` = Onolys repo (unchanged), `onolys/iaudit-legacy` = new repo clone; local README rows updated.
**Non-Goals:** CI/workflows (`ci.yml`, `nightly.yml`, `changes.sh`) edits; making it build, lock, lint or pass tests; secrets; pruning MITI/api/admin leftovers or dangling refs beyond what filter-repo drops; deploying; new features; rewriting history/PR numbers; renaming the GitHub repo Onolys/onolys; renaming the existing local folder (owner 2026-11-22: no rename).

## Requirements
**R1 History.** `git clone --no-local <Onolys/onolys> work && cd work && git checkout iaudit-archive && git filter-repo --path engines/core --path engines/eaudit --path engines/paudit --path engines/evaluation --path eval --path frontend --path protocols --path docs --path pyproject.toml --path uv.lock --path scripts --path AGENTS.md --path README.md --path .gitignore --path .claude`. Run in a throwaway clone under the scratchpad, never in the Onolys worktree. Then `git remote add origin <url>` and push `main` (tags not needed). `filter-repo` must be pre-installed (`pip install git-filter-repo`). Path list is a keep-list for the archive; contents copied as-is (no CI files required).
**R2 Local clone (no rename).** The existing `/root/projects/onolys/iaudit` (holds Onolys/onolys) is left untouched: no rename, no worktree repair. Clone the new repo to `/root/projects/onolys/iaudit-legacy`.
**R3 Local README.** Update `/root/projects/README.md` and `/root/projects/onolys/README.md`: add a new row `onolys/iaudit-legacy` (new repo URL, "Interview evidence audit code archive: eaudit/paudit engines, evaluation harness, review UI. Extracted from Onolys/onolys@iaudit-archive") in both files. The existing `onolys/iaudit` row (Onolys/onolys) keeps its folder name; reconcile its wording with what SP05 wrote.
**R4 Archive note.** Optionally add a one-line "extracted from Onolys/onolys@iaudit-archive; code archive, not built or tested" to the new repo README as a normal commit on top.

## Architecture
```
Onolys/onolys @ iaudit-archive (1cc7321)
   | git filter-repo (keep: engines/{core,eaudit,paudit,evaluation}, eval, frontend, protocols, docs, scripts, root config)
   v
new iaudit repo (code + history only)  --> cloned at /root/projects/onolys/iaudit-legacy
local: /root/projects/onolys/iaudit (Onolys) unchanged; new clone at /root/projects/onolys/iaudit-legacy
```
History evidence (`git log origin/main`, 41 commits): #1-#33 are all iaudit; after #33, path-touching commits are few (eaudit #35/#47, paudit #35, evaluation #35/#47, core #35/#45/#47, eval #35, frontend #35, protocols #35/#45). #36-#49 are mostly MITI platform/api/web/infra and are dropped by the filter except where they touched kept paths.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | History | filter-repo on iaudit-archive, kept paths, full history | truncate at #32/#33; plain snapshot | Keeps blame/PR trail, drops MITI noise automatically |
| D2 | Tip state | Tag state (1cc7321) of kept paths | Reset to #32 | Post-32 code is what works |
| D3 | Scope | Code-only archive: no CI, build, secrets, pruning | Standalone buildable repo | Owner 2026-11-22: only holding code for later |
| D4 | Source repo | Onolys/onolys unchanged (tag is the only link) | Move/fork | SP05 deletes; tag immutable |
| D5 | Local layout | Keep existing `onolys/iaudit` as is; new clone at `onolys/iaudit-legacy`, no rename | Rename existing to `onolys/onolys` | Owner 2026-11-22 (supersedes earlier rename decision): avoids breaking worktrees/sessions |

## Manual steps (owner)
1. Create empty GitHub repo (no README/license), choose name and visibility.
2. Give URL; grant Claude/this machine push access (gh auth or deploy key).

## Risks / Open Questions
- [OPEN-1] New repo URL/name and push access (BLOCKED on owner; whole SP waits).
- [RESOLVED: /root/projects/onolys/iaudit-legacy, no rename, owner 2026-11-22] (OPEN-2 local folder; existing `/root/projects/onolys/iaudit` untouched; new row `onolys/iaudit-legacy` in `/root/projects/README.md` + `/root/projects/onolys/README.md`)
- [RESOLVED: not needed — code-only archive, owner 2026-11-22] (OPEN-3 `changes.sh`, OPEN-4 core pruning, OPEN-5 nightly secrets)
- [RESOLVED: history option a, D1]
- [DEFERRED] Making the repo buildable/CI'd; renaming packages `onolys-*` to `iaudit-*`; publishing; deleting the tag from Onolys/onolys.
- Risk: filter drops a path someone later needs. Mitigation: tag `iaudit-archive` stays in Onolys/onolys; re-run filter with more paths.

## Acceptance Criteria
1. New repo `main` pushed to owner URL; contains `engines/{core,eaudit,paudit,evaluation}`, `eval/`, `frontend/`, `protocols/`, `docs/`; no `api/`, `web/`, `admin/`, `infra/` (dropped by filter). No CI/build/test expectation.
2. `git log --oneline` shows PRs #1-#33 history for kept paths.
3. `/root/projects/onolys/iaudit-legacy` is the new repo clone; `/root/projects/onolys/iaudit` (Onolys/onolys) is unchanged, not renamed.
4. `/root/projects/README.md` and `/root/projects/onolys/README.md` each have a new row for `onolys/iaudit-legacy`; owner-provided URL recorded.
