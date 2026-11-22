---
status: draft
summary: SP06 new iaudit repo - filter-repo extract from tag iaudit-archive and push, local clone at iaudit-legacy, README rows, optional archive note
date: 2026-11-22
---
# Tasks: SP06 New iaudit repo from archive (Phase 4)

Source of truth: /root/projects/onolys/iaudit/.worktrees/feat/miti-lean-engine/docs/agent_files/feat-miti-lean-engine-20261122-1642/06-iaudit-repo/PRD.md. Runs after SP05 (tag `iaudit-archive` pushed). Code-only archive: the PRD (D3, Non-Goals) excludes CI, build, lock, lint and test passing for the new repo, so there is deliberately no CI-wiring task. The tests for this work are the concrete verification checks in each Done-when (ls-tree, ls-remote, git log, grep of README rows). Repo URL is https://github.com/Onolys/iaudit.git (public, empty, push access confirmed). One commit per task where a repo is touched.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Extract history with filter-repo and push | - | done |
| 2 | Local clone at `iaudit-legacy` | 1 | done |
| 3 | Local README rows | 2 | done |
| 4 | Archive note in new repo README (optional) | 2 | done |

## Task 1 — Extract history with filter-repo and push
What it is / what it means: Build the new repo's content: the iaudit code and its path-relevant history, taken from the immutable tag, then pushed to the owner's empty repo. (D1, D2, D3, D4, R1)
What changes at a high level: Check `git-filter-repo` is installed (pip install if not). In a throwaway clone under the scratchpad, never in the Onolys worktree, clone Onolys/onolys with `--no-local`, check out `iaudit-archive`, and run filter-repo with the R1 keep-list (core, eaudit, paudit, evaluation engines, eval, frontend, protocols, docs, scripts, root config files, `.claude`). Add the new URL as origin and push `main`; tags are not needed. Nothing is changed in Onolys/onolys. No CI, build or pruning work.
Done when: Verification checks pass. `git ls-remote https://github.com/Onolys/iaudit.git refs/heads/main` returns a SHA. `git ls-tree -r --name-only origin/main` lists paths under `engines/core`, `engines/eaudit`, `engines/paudit`, `engines/evaluation`, `eval`, `frontend`, `protocols` and `docs`, and none under `api/`, `web/`, `admin/` or `infra/`. `git log --oneline origin/main` in the throwaway clone shows the PR #1-#33 history for kept paths. If push is refused, record BLOCKED.

## Task 2 — Local clone at `iaudit-legacy`
What it is / what it means: Give the new repo a local home beside the existing one, with no rename of the Onolys checkout. (D5, R2)
What changes at a high level: Clone the new repo to `/root/projects/onolys/iaudit-legacy`. Leave `/root/projects/onolys/iaudit` and its worktrees completely untouched.
Done when: `git -C /root/projects/onolys/iaudit-legacy remote get-url origin` equals the new URL and its `git log --oneline` matches the pushed history. `git -C /root/projects/onolys/iaudit remote get-url origin` still points at Onolys/onolys and the folder name is unchanged.

## Task 3 — Local README rows
What it is / what it means: Record the new repo in the two local project indexes so the next agent finds it. (R3, Acceptance 4)
What changes at a high level: In `/root/projects/README.md` and `/root/projects/onolys/README.md`, add a row `onolys/iaudit-legacy` with the new URL and the description "Interview evidence audit code archive: eaudit/paudit engines, evaluation harness, review UI. Extracted from Onolys/onolys@iaudit-archive". Reconcile the existing `onolys/iaudit` row wording with what SP05 wrote, keeping its folder name.
Done when: `grep -n "iaudit-legacy" ` on both files shows exactly one new row each, containing `https://github.com/Onolys/iaudit.git` and `iaudit-archive`. The `onolys/iaudit` row still exists in both files and is not duplicated.

## Task 4 — Archive note in new repo README (optional)
What it is / what it means: A one-line pointer so anyone opening the new repo knows it is an unbuilt archive. (R4)
What changes at a high level: In the `iaudit-legacy` clone, add the line "Extracted from Onolys/onolys@iaudit-archive; code archive, not built or tested." to the README as one normal commit on top of the filtered history (no history rewrite), then push `main`. Skippable; if skipped, mark in the table and note why.
Done when: `git show origin/main:README.md | grep "code archive, not built or tested"` matches after push, and `git log --oneline origin/main` shows the note commit as the single new commit above the filtered history.
