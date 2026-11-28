---
status: draft
summary: Legacy purge in six PRD batches (12 tasks) - delete guard tests, compat code, spec ids, CI guard scripts, dead staging fallbacks, one dead infra script; no .tf or cloud-state change.
date: 2026-11-28
---
# Tasks: 01 Legacy purge

Source of truth: /root/projects/onolys/onolys/.worktrees/refactor/revamp/docs/agent_files/refactor-revamp-20261128-0102/01-legacy-purge/PRD.md. Pure deletion and rewording, one commit per task, lint and impacted tests green after each. Never edit `infra/scripts/identity-config.py`, any `.tf`, `.firebaserc`, `firebase.json`, or `docs/` (except regenerated `docs/contracts/public`). CI exists (`.github/workflows/ci.yml`); this SP changes it, adds none. Full suite runs only in dev-ship.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Delete guard/migration tests + legacy CSS test (R1, R6) | none | done |
| 2 | T2 pre-check: count old-shape docs in staging + prod | none | done |
| 3 | Delete compat code and eval pre-matrix readers (R2) | 1, 2 | done |
| 4 | Spec ids to plain words: api (R3) | 3 | done |
| 5 | Spec ids to plain words: engines (R3) | 3 | done |
| 6 | Spec ids to plain words: eval (R3) | 3 | done |
| 7 | Spec ids to plain words: web (R3) | 3 | done |
| 8 | Regenerate contracts (R7 tail) | 4, 5, 6, 7 | done |
| 9 | Prune `scripts/ci/`; `changes` job on paths-filter (R4, D3) | 3 | done |
| 10 | Remove dead staging fallbacks in workflows + `release_target.py` (R7) | 9 | done |
| 11 | Infra: delete `check-staging.py` and removal-guard tests (R5) | 1 | done |
| 12 | Final acceptance sweep + post-merge cloud checks | 8, 10, 11 | done |

## Task 1 — Delete guard/migration tests + legacy CSS test
What it is / what it means: Tests that only assert "the old thing is gone" protect nothing after launch (rule 16). PRD R1, R6, D5.
What changes at a high level: Delete the listed whole-file guards (name/naming guards, old-import and transcript-migration tests in api and miti, `test_old_engine_removed`, three infra removal guards, `styles.test.ts`). In mixed files delete only the "is gone" functions, keeping boundary tests (miti-import boundary, the two core "imports without miti" tests). Keep the files PRD names as kept (fake/real parity, repo guard, LiteLLM compatibility, `test_llm_migration.py`). Fix `web/README.md:8`.
Done when: no file or test name contains `migration`, `naming_guard`, `no_old_imports`, `old_engine_removed` (except the kept `test_llm_migration.py`); pytest for api, core, miti, eval backend, infra/scripts and vitest for web pass; `ruff` clean.

## Task 2 — T2 pre-check: old-shape docs
What it is / what it means: "Prelaunch, no old docs" is unverified (prod tags exist). Deleting readers for old-shape docs is only safe if none exist. PRD R2 T2, AC8.
What changes at a high level: Nothing in the repo. Agent runs a one-off read-only count query in staging and prod Firestore for run docs lacking the new fields (`kind`, `interviews`, new failure fields). Record both counts in the task log.
Done when: both counts recorded. If either is above 0, report counts to the owner, mark Task 3's old-doc item blocked (rest of Task 3 proceeds), and do not delete those readers.

## Task 3 — Delete compat code and eval pre-matrix readers
What it is / what it means: Code kept only "for compatibility" (PRD R2, O2 resolved: delete).
What changes at a high level: Remove legacy `daily_cap` read and field; old-doc derivations (`_derive_old_failure`, `kind` fill-on-read, `interviews` default, `free_run_void`) only if Task 2 counts are 0; the `jobs/machine.py` re-export shim, re-pointing `first_run.py` and `run.py` to `onolys_api.progress`; `MITI_MODEL_CHEAP/MID/STRONG` (keep `LLM_PROVIDER/MODEL/EFFORT` and `MITI_LLM_RESPONSE_FORMAT`); stale text in `errors.py` and `scripts/README.md:8`; old-name entries in the `ci.yml` image-import loop (keep `onolys_eval`); eval `is_legacy`, scheduler legacy `tick_seq` docs, `legacy_selection`. Delete their tests too.
Done when: impacted api (unit + emulator marker), core, eval backend and eval web tests pass; `api-coverage --fail-under=94` passes locally; `git grep -nE 'paudit|iaudit|eaudit|onolys_core|onolys_evaluation'` outside `docs/` is 0.

## Task 4 — Spec ids to plain words: api
What it is / what it means: Rule 12: no PRD/SP/FX/AC/R/D/ADR ids or task-slug refs in code. PRD R3. Tasks 4-7 touch separate packages, so two may run in parallel.
What changes at a high level: Rewrite each id-bearing comment, docstring and test name in `api/` (about 163 src and 122 test lines) to plain words; never blind-delete a sentence. Reword test names, do not rename files.
Done when: the R3 regex returns 0 in `api/` (exceptions listed in the task log); ruff and api tests pass; `api-coverage` still at least 94.

## Task 5 — Spec ids to plain words: engines
What it is / what it means: Same as Task 4, for `engines/` (about 48 src, 24 test lines), including `$comment`s in `pack.yaml`, `miti-result.schema.json`, `rating.schema.json`.
What changes at a high level: Reword comments, docstrings, test names and data-file comments. If the miti schema text changes, regenerate it in Task 8.
Done when: R3 regex returns 0 in `engines/` (exceptions logged); ruff, core, miti, oneshot impacted tests pass.

## Task 6 — Spec ids to plain words: eval
What it is / what it means: Same as Task 4, for `eval/` (about 39 src, 19 test lines) and `eval/web`. `infra/` stays excluded.
What changes at a high level: Reword in place; eval-only scripts and `REMOVED_ENV` are left for 03.
Done when: R3 regex returns 0 in `eval/` (exceptions logged); eval backend pytest and eval web vitest pass; lint clean.

## Task 7 — Spec ids to plain words: web
What it is / what it means: Same as Task 4, for `web/` (about 98 src, 65 test lines); `web/src/mocks` is excluded (08 deletes it), as are generated and fixture files.
What changes at a high level: Reword comments and `describe("…FX17")`-style test names; no file renames (07 owns moves).
Done when: R3 regex returns 0 in `web/` outside excluded paths (exceptions logged); `eslint`/typecheck and web vitest pass.

## Task 8 — Regenerate contracts
What it is / what it means: Ids also live in generated files (PRD R7 last paragraph).
What changes at a high level: Run `python -m onolys_api.openapi && python -m onolys_api.contracts` (updates `api/openapi.json` and 2 files in `docs/contracts/public`), `npm run gen:api` in `web`, and the miti schema generator if Task 5 edited it. Commit only regenerated output.
Done when: regenerated files contain no ids; a second regeneration yields an empty diff; api contract tests and web typecheck pass; `docs/` diff is only `docs/contracts/public`.

## Task 9 — Prune `scripts/ci/`; `changes` job on paths-filter
What it is / what it means: Remove CI scripts that are not release-protecting and their tests, and replace hand-rolled path routing (PRD R4, D3, O1 approved).
What changes at a high level: Delete `check_docs_scope.sh`, `check_links.py`, the listed tests-of-tests and `key_guard_fixtures/`, plus `changes.sh`, `test_changes.sh`, `test_changes_deps.py`. In `ci.yml`, replace the `changes` job with a pinned `dorny/paths-filter` step emitting the same output names so `required_gate.py` is unchanged. Shrink `guards` to key guard (no planted-fixture step), direct `bash scripts/ci/check_config.sh`, actionlint. Keep the 9 release-protecting scripts and the 6 eval-only files.
Done when: `actionlint` passes; the `changes` outputs match old `changes.sh` on 5 sample diffs (dry-read); `scripts/ci/` holds 9 kept plus 6 eval-only files; callers in deploy and pr-preview workflows still resolve.

## Task 10 — Dead staging fallbacks in workflows
What it is / what it means: `STAGING_GCP_PROJECT` is set, so the fallbacks are dead (PRD R7).
What changes at a high level: Remove the `|| vars.GCP_PROJECT || 'onolys'`, `|| vars.WIF_PROVIDER/DEPLOYER_STAGING_SA`, `'onolys-app-staging'` and `!vars.STAGING_GCP_PROJECT && vars.STAGING_VITE_*` branches in `deploy-staging.yml`, `pr-preview.yml`, `pr-preview-cleanup.yml`, and the `resolve` `PROJECT` in `deploy-prod.yml` (keep its WIF/SA auth). In `release_target.py` require the isolated vars and drop the legacy-target path and `LEGACY_SITES`; adjust its tests.
Done when: `actionlint` passes; `release_target.py staging` and `preview` run with the real variable set and give the expected target; release_target tests pass; no `|| vars.WIF_PROVIDER` or `'onolys-app-staging'` remains in the four workflows.

## Task 11 — Infra: dead script and guard tests
What it is / what it means: PRD R5, D6. Only tests and one script go; Terraform is untouched.
What changes at a high level: Delete `infra/scripts/check-staging.py` and `test_check_staging.py`; confirm the R1 infra guards (Task 1) are gone. `identity-config.py` and all `.tf` stay as is. `removed {}` blocks, retired domains, `deployer_staging`, Firebase layout are handed to 09.
Done when: `pytest infra/scripts` passes; `terraform fmt -check` and `validate` unaffected; `identity-config.py` byte-identical to `main`; no `.tf` in the diff.

## Task 12 — Final acceptance sweep and post-merge cloud checks
What it is / what it means: Prove PRD acceptance criteria 1-9 before review.
What changes at a high level: No new edits unless a check fails. Run the criteria greps and `git diff --stat` against the base. After merge, the agent deletes stale `STAGING_VITE_FIREBASE_*` and `STAGING_VITE_CONTACT_EMAIL` repo variables if unused (keeping `WIF_PROVIDER`, `DEPLOYER_STAGING_SA`, `DEPLOYER_PROD_SA`), and confirms via `terraform state list` (prod root) that `google_secret_manager_secret.provider` and `google_billing_budget.monthly` are absent, as input for 09. Old staging resources in project `onolys` and retired auth domains are retired via 09's plan/apply.
Done when: AC1-9 hold (ids regex 0, `scripts/ci/` file count, zero `.tf`/`docs/` changes except contracts, T2 counts recorded, `api-coverage` at least 94); the state-list result is recorded for 09.

Owner-only: act on the Task 2 report if either count is above 0; delete the GitHub variables only if `gh` lacks rights.
