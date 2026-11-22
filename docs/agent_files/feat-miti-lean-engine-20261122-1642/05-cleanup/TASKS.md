---
status: draft
summary: SP05 cleanup - tag iaudit-archive, repoint and delete non-MITI code, rewire CI/scripts/lock, infra and naming sweep, docs rewrite, link check
date: 2026-11-22
---
# Tasks: SP05 Cleanup + docs (Phase 3)

Source of truth: /root/projects/onolys/iaudit/.worktrees/feat/miti-lean-engine/docs/agent_files/feat-miti-lean-engine-20261122-1642/05-cleanup/PRD.md. Runs last, after SP01-04 have landed. Tag first, delete second, one commit per task (the tag step has no commit). Breaking changes are fine; prod is unused.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Archive tag `iaudit-archive` | - | done |
| 2 | Repoint leftovers and delete old packages | 1 | in-progress |
| 3 | CI, scripts, workspace and lock | 2 | todo |
| 4 | Infra cleanup and apply | 2 | todo |
| 5 | Naming sweep | 3, 4 | todo |
| 6 | Docs rewrite and prune | 2, 5 | todo |
| 7 | Link check and external READMEs | 6 | todo |

## Task 1 — Archive tag `iaudit-archive`
What it is / what it means: A permanent, pushed marker on the last commit that still holds the evidence-audit code, so SP06 can build the iaudit repo from it later. (D1, D2, R1)
What changes at a high level: Create an annotated tag on `1cc7321` (not on the branch head), push it to origin. Never move it. If the push is refused or the tag already points elsewhere, record BLOCKED and continue.
Done when: Check written first: `git ls-remote --tags origin iaudit-archive` resolves to `1cc7321`, and the tag's tree lists `engines/eaudit`, `eval/` and `frontend/src/eval`. Both checks pass, or BLOCKED is logged.

## Task 2 — Repoint leftovers and delete old packages
What it is / what it means: Remove everything that is not MITI: four old engine packages, `protocols/`, `eval/`, the empty `backend/`, and the old eaudit contract files. Keep `docs/contracts/public/`. (R2, D7)
What changes at a high level: First fix remaining kept-side references that SP02/03/04 did not catch (web schema path and fixtures, Dockerfile COPY and ENV lines that dangle, `.dockerignore` entries). Then delete, in that order. Check SP01-04 have landed before starting.
Done when: The R2 reference grep is run before deleting and returns nothing for kept code. After deletion, the same grep hits only allowed historical places. `api` and `web` targeted tests and the api image build still pass.

## Task 3 — CI, scripts, workspace and lock
What it is / what it means: Make automation describe a MITI-only repo and add the `miti` CI job that SP01 deliberately left to this task. (R3, R4, D5, D8)
What changes at a high level: Drop the four old CI jobs and their `needs:` references, add the `miti` job, trim nightly to `api-real-mode`, rework `changes.sh` flags and dependencies, update `check_config.sh`, `dev.sh` and its README, fix the workspace header comment, regenerate the lock once.
Done when: Tests rewritten first: `test_changes.sh` expects the new flags and still covers shared-path, force-all and api-reruns-on-miti cases. Then `test_changes.sh`, `test_changes_deps.py`, `test_check_config.sh`, actionlint and `uv lock --check` pass. The lock has no old package names. `ci.yml` has `miti` and none of the removed jobs.

## Task 4 — Infra cleanup and apply
What it is / what it means: Clear any old naming or path references from Terraform, then apply it. Prod is unused, so renames that replace resources are fine. GCP projects and state buckets are not renamed. (R4b)
What changes at a high level: Grep `infra/` for old package, path, env and name references, fix what is found (admin bits stay with SP04). The agent runs apply for staging and prod. If credentials are missing, record BLOCKED and move on.
Done when: Grep over `infra/` is clean. `terraform plan` is clean for staging and prod after apply, or BLOCKED is recorded. No `PAUDIT_*` or `IAUDIT_*` env remains in Dockerfiles.

## Task 5 — Naming sweep
What it is / what it means: Remove `paudit`/`iaudit`/`eaudit` and "Interview Evidence" wording from every kept file, so the repo reads as Onolys MITI. (R4c)
What changes at a high level: Update `dev.sh` env names, scripts README, CI comments, config comments (route names stay SP02's, SP05 checks they match), package metadata and `.dockerignore`. Historical text stays only under `docs/agent_files/**`, superseded ADR banners and ADR 0025.
Done when: `rg -ni "iaudit|paudit|eaudit|interview evidence"` excluding `docs/agent_files/**` and `uv.lock` hits only the allowed places. Rerun CI-script tests from Task 3.

## Task 6 — Docs rewrite and prune
What it is / what it means: Docs describe only MITI coding. Old evidence-audit docs go, mixed docs are trimmed. (R5, D3, D4, D7)
What changes at a high level: Rewrite mission, AGENTS, README and architecture. Delete the eaudit-only concept, implementation, reference, testing and example docs and ADRs 0001-0016. Trim the mixed reference and testing docs. Add superseded banners to ADRs 0017, 0018, 0019, 0023 and write ADR 0025 recording the tag and the SP06 recipe. Rewrite the contracts README as a pointer to `public/`. Regenerate the docs indexes. `docs/agent_files/**` is untouched.
Done when: Checks written first: grep gate on the four root docs for `eaudit|paudit|caudit|Interview Evidence` returns nothing, and each docs README lists only existing files. Both pass after the rewrite.

## Task 7 — Link check and external READMEs
What it is / what it means: Prove no kept doc points at a deleted one, and update the two project-index READMEs outside the repo. (R5, Acceptance 8)
What changes at a high level: Run `check_links.py` before and after the doc changes and fix inbound links. Update the `onolys/iaudit` row in `/root/projects/README.md` and the `iaudit` row in `/root/projects/onolys/README.md` to the new Onolys description, noting the archive tag and that the local folder keeps its name.
Done when: `python3 scripts/ci/check_links.py` passes. Both external rows contain the new description and the `iaudit-archive` mention.
