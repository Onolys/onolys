---
status: draft
summary: Delete migration/guard tests, compat code, spec ids, dead staging fallbacks and ~20 CI-guard tests before the restructure; no Terraform or cloud-state change.
date: 2026-11-28
---
# PRD: 01 Legacy purge

Repo/branch: Onolys/onolys / `refactor/revamp` · Depends on: 00-rules-file (rule 16 and rule 12 text exist) · Owns: the test files, compat code, spec-id text and CI scripts listed below. Edits only the minimum other lines needed to stay green. Docs untouched (`docs/` incl. ADRs and `docs/agent_files`), except regenerated contract files (R7).

## TL;DR
Rule 16 says delete retired, superseded and "for compatibility" code before launch. This SP does that as pure deletion in six batches, each leaving lint and tests green. It touches no Terraform and no cloud state. Candidate cloud-state deletions (`removed {}` blocks, retired auth domains, old deployer SA) are listed and handed to 09 with owner steps. The legacy CSS layer is already gone from code; only a guard test and one README line remain.

## Problem
Later SPs would move and rewrite code that is already dead. Evidence:
| Area | Finding |
|---|---|
| Guard/migration tests | 11 files (some partly) plus ~10 single tests that only assert "old thing is gone" (R1) |
| Compat code | `daily_cap` read, old-doc derivations, `MITI_MODEL_*` env, re-export shim, staging fallback in 5 workflows (R2) |
| Spec ids | ~580 matching lines in code (R3) |
| `scripts/ci/` | 36 files; 19 are tests, 4 fixtures; `changes.sh` hand-rolls path routing (R4) |
| `infra/scripts/` | 17 `test_*.py`, 4 of them removal guards; one dead operator script (R5) |

## Goals / Non-Goals
**Goals:** everything in R1-R6 removed; CI green after every batch; ids and compat gone from code.
**Non-goals:** any `.tf`, `.firebaserc`, `firebase.json` change (09); folder moves, renames, fakes (04/06/07/08); eval split items (03); `docs/` edits; deleting cloud resources or GitHub variables (Manual steps).

## Requirements
**R1 Guard, migration and parity tests (delete).**
| Test | Evidence |
|---|---|
| `api/tests/test_name_guard.py`, `engines/miti/tests/test_naming_guard.py` | greps for `paudit|iaudit|eaudit|onolys_core` [verified: grep → only these 2 files + `ci.yml:468` + `check_docs_scope.sh` name them] |
| `api/tests/test_no_old_imports.py` (drop `test_no_file_imports_an_old_package`; keep the miti-import boundary test until 04/06 replace it), `engines/miti/tests/test_no_old_imports.py`, `engines/miti/tests/test_transcript_migration.py` | assert absence of old packages/re-exports |
| `engines/core/tests/test_transcript_migration.py`: drop `…aliases…` and `…removed_transcript_modules` tests; keep the two "imports without miti" boundary tests (04 owns them) | lines 17, 45 |
| `eval/backend/tests/test_old_engine_removed.py` | `REMOVED` names list |
| `web/src/hosting/styles.test.ts` | asserts no `legacy` CSS (R6) |
| `infra/scripts/test_{no_admin,budget_removed,nightly_gemini_secret}.py` | removal guards |
| In mixed files delete only the "is gone" functions: `api/tests/test_config.py::test_daily_run_cap_removed_everywhere`, `test_failure_kind.py::…are_gone`, `test_decide_cancel.py::test_reexported_from_charging`, `miti/tests/test_run.py::test_public_reexports`, `test_types.py::test_extracted_llm_has_no_miti_reexports`, `test_report_schema.py::test_schema_has_no_old_run_info_keys`, `infra/scripts/test_legacy_root_prod_only.py::{test_no_staging_or_eval…,test_no_old_staging…,test_no_eval_hosting…}`, `test_isolated_environment.py` legacy-name test | `grep -n "def test.*(removed|gone|reexport|legacy|old_)"` |
Kept on purpose: `api/tests/test_fake_real_parity.py` (06 deletes it with the fakes); `eval/core/tests/test_repo_guard.py` (dataset-leak guard, 03); `engines/core/tests/test_{claude,openai}_compatibility.py` (LiteLLM behaviour tests, not legacy despite the name); `test_llm_migration.py` (live structure test, rename in 04); positive infra tests (09 reviews them).

**R2 Compat code (delete code and its tests).**
| Item | Where | Notes |
|---|---|---|
| Legacy `daily_cap` field | `api/.../repo/limits.py:62-67`, `models.py:91`, `api/tests/test_limits.py` (4 tests) | no deploy or infra sets it [verified: grep infra/.github → 0] |
| Old-doc derivations | `models.py` `_derive_old_failure`, `kind` fill-on-read, `interviews` default; `test_failure_kind.py:164`; `test_charging.py:107` (`free_run_void`) | prelaunch, no old docs to read |
| Re-export shim | `api/.../jobs/machine.py:16-24` (`progress` tables); re-point `first_run.py:24`, `run.py` to `onolys_api.progress` | |
| Back-compat env | `core/llm/routes.py` `MITI_MODEL_CHEAP/MID/STRONG` (+ tests `test_routes.py:142`, `test_llm_override.py`) | set nowhere outside tests [verified: grep → tests + routes.py only]. Keep `LLM_PROVIDER/MODEL/EFFORT` (deploy workflows set them) and `MITI_LLM_RESPONSE_FORMAT` (oneshot golden test; 04 decides) |
| Stale text | `api/.../errors.py:34` "admin pack routes"; `scripts/README.md:8` retired-admin line; `ci.yml:468` old names in the image-import loop (keep `onolys_eval`) | |
| Eval old-run readers | `eval/backend/read_runs.py` `is_legacy`, scheduler `tick_seq` legacy docs, `eval/web` `legacy_selection` paths | [RESOLVED: delete] O2; old eval runs/data dropped, no migration |
Left for others: `adapters/validated.py` "legacy/fake adapter bridge" and `adapters/fake.py` (06); core `Turn = TranscriptTurnV1` aliases (04); eval `REMOVED_ENV` (tied to `test_eval_image.sh`, 03); eval `upload.py` bucket defaults and the ≤25 MiB multipart upload path (03/10).

**R3 Spec/planning ids in code and comments.** Rewrite each to plain words (rule 12), never blind-delete a sentence. Counts [verified: `git grep -nE '\b(PRD|SP[0-9]{1,2}|FX[0-9]+|AC[0-9]+|R[0-9]{1,2}[a-z]?|D[0-9]{1,2}|ADR ?[0-9]+)\b'`, non-md, excluding generated/fixtures; upper bound, a few false hits]:
| Package | src lines/files | tests lines/files |
|---|---|---|
| api | 163/59 | 122/67 |
| engines | 48/35 | 24/18 |
| eval | 39/22 | 19/18 |
| web | 98/64 | 65/28 (`web/src/mocks`: 29 more, 08 deletes it) |
Also task-slug refs ("05-processing-screen R4", "03-failure-policy") and engine data files (`pack.yaml`, `miti-result.schema.json`, `rating.schema.json` `$comment`s). Test names carrying ids (`describe("…FX17")`) are reworded, not renamed files (14 is 06/07).

**R4 `scripts/ci/` (36 files).**
| Action | Files |
|---|---|
| Keep, release-protecting | `check_config.sh`, `check_no_llm_keys_in_pr_workflows.py`, `pr_preview.sh`, `release_target.py`, `staging_ran_image.py`, `validate_staging_llm.py`, `verify_staging_release.cjs`, `smoke_prod_llm_validator.sh`, `required_gate.py` |
| Delete: not release-protecting | `check_docs_scope.sh` (greps legacy terms in docs), `check_links.py` |
| Delete: tests of tests | `test_check_config.sh`, `test_check_links.py`, `test_check_no_llm_keys…py`, `test_ci_gate.py`, `test_deploy_prod.sh`, `test_deploy_prod_llm.py`, `test_deploy_staging.py`, `test_pr_preview.sh`, `test_release_targets.py`, `test_staging_ran_image.py`, `test_workflow_checkout_before_auth.py`, `test_workflow_python_versions.py`, `key_guard_fixtures/` (4 files) |
| Replace | `changes.sh`, `test_changes.sh`, `test_changes_deps.py` with a path filter in the `changes` job (D3) |
| Left for 03 (eval-only) | `set_eval_origin.sh`, `test_deploy_eval.sh`, `test_eval_image.sh`, `test_hosting_targets.sh`, `test_verify_staging_release.cjs`, `test_workflow_run_guard.py` (only `deploy-eval.yml` uses `workflow_run` [verified]) |
`ci.yml` `guards` job shrinks to: key guard (no planted-fixture step), a direct `bash scripts/ci/check_config.sh`, actionlint. Remove the old-name import loop entries (R2). Callers of kept scripts verified: `deploy-prod.yml:84,129-131`, `deploy-staging.yml:69-118`, `pr-preview*.yml`. `gen_miti_schema.py` stays in `scripts/` for 04 (D4).

**R5 `infra/`: tests and one script only.** Delete `infra/scripts/check-staging.py` + `test_check_staging.py` (hard-codes `PROJECT="onolys"` for the retired in-prod-project staging; no caller in workflows/docs [verified: grep]). Delete the guards in R1. No `.tf` file changes, so `terraform plan` is unchanged by this SP. Kept and handed to 09:
| Item | Why not deleted here |
|---|---|
| `removed {}` blocks (`main.tf`, `budget.tf`) | deleting while the resource is still in state makes the next plan destroy it |
| `retired_authorized_domains` + `app_staging_site_id` (`identity.tf`) | changing the list re-triggers a provisioner that patches live Identity Platform config |
| `deployer_staging` SA + WIF (`deployer.tf`) | still used: `deploy-prod.yml:88-89` auths with `vars.WIF_PROVIDER` + `vars.DEPLOYER_STAGING_SA` to read staging |
| `examples/*prod*`, `.firebaserc` `app-staging`/`eval-staging` entries, `firebase.json` `staging`/`eval` DBs | Firebase/infra layout is 09 |

**R6 Legacy CSS layer.** Already removed in code [verified: `web/src/styles/index.css` has `@layer theme, base, components, utilities`, no `legacy-app.css` tracked; `eval/web` has no legacy layer]. Delete `web/src/hosting/styles.test.ts`; fix `web/README.md:8` (names a layer that no longer exists).

**R7 Staging fallback in workflows.** `STAGING_GCP_PROJECT=onolys-staging` is set [verified: `gh variable list`], so the `|| vars.GCP_PROJECT || 'onolys'`, `|| vars.WIF_PROVIDER/DEPLOYER_STAGING_SA`, `'onolys-app-staging'` and `!vars.STAGING_GCP_PROJECT && vars.STAGING_VITE_*` branches are dead in `deploy-staging.yml`, `pr-preview.yml`, `pr-preview-cleanup.yml`, and `deploy-prod.yml` `resolve` `PROJECT` (keep its WIF/SA auth). `release_target.py`: staging/preview require the isolated vars (drop the "clear it to use the legacy target" path and `LEGACY_SITES`). Regenerate generated contracts after R3: `python -m onolys_api.openapi && python -m onolys_api.contracts` (4 ids in `api/openapi.json`, 2 files in `docs/contracts/public`), `npm run gen:api` in `web` (4 in `schema.d.ts`), and the miti schema if edited.

## Architecture
Batches, in order, one commit each, and the checks to run:
| # | Batch | Check |
|---|---|---|
| 1 | R1 tests + R6 | touched packages' pytest/vitest, `ruff` |
| 2 | R2 compat code + tests | api (unit + emulator marker), core, eval; `api-coverage --fail-under=94` still passes |
| 3 | R3 ids per package (api, engines, eval, web: 4 commits; can run 2 parallel) | lint, tests, contract regen diff clean |
| 4 | R4 + `ci.yml` | `actionlint`; dry-read `changes` flags vs old `changes.sh` on 5 sample diffs |
| 5 | R7 workflows + `release_target.py` | `actionlint`, `release_target.py staging|preview` run with the real var set |
| 6 | R5 infra tests/script | `pytest infra/scripts`, `terraform fmt/validate` untouched |

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| D1 | Eval legacy in this SP | Purge in place (spec ids, guards); defer eval-only scripts and `REMOVED_ENV` to 03 | Leave all eval to 03 | 03 would copy dead code into the new repo |
| D2 | Terraform | Zero `.tf` edits | Delete `removed {}` / retired domains now | Each can change real cloud state; needs owner plan/apply |
| D3 | Replace `changes.sh` | One `changes` job using `dorny/paths-filter` (pinned), same output names, so `required_gate.py` is unchanged. Owner-approved (verified: 3.4k stars, release v4.0.3 Aug 2026, maintained, not archived) | Workflow `paths:` only; keep `changes.sh` minus tests | `paths:` selects workflows not jobs, and a skipped workflow can never feed `required`; third-party actions are allowed [verified: `gh api actions/permissions` → all] |
| D4 | `gen_miti_schema.py` | Leave for 04 | Move now | Engine schema layout is 04's; `oneshot` test reads it by path [verified: `test_miti_config.py`] |
| D5 | Mixed test files | Delete only the legacy functions | Delete whole files | Boundary tests protect rule 5 until 04/06 replace them |
| D6 | Dead operator script | Delete `check-staging.py` | Keep | Targets the retired layout; no caller |

## Manual steps
1. After merge, owner deletes stale GitHub repo variables `STAGING_VITE_FIREBASE_*` and `STAGING_VITE_CONTACT_EMAIL` if unused. Keep `WIF_PROVIDER`, `DEPLOYER_STAGING_SA`, `DEPLOYER_PROD_SA`.
2. Owner confirms `terraform state list` (prod root) lacks `google_secret_manager_secret.provider` and `google_billing_budget.monthly` before 09 removes the `removed {}` blocks.
3. Owner retires old staging resources in project `onolys` (Hosting site `onolys-app-staging`, old Cloud Run/DB) and the retired auth domains. Agents never apply or delete cloud resources.

## Risks / Open Questions
- [RESOLVED: approved D3] O1: `dorny/paths-filter` instead of `paths:` filters.
- [RESOLVED: delete] O2: delete eval readers for pre-matrix runs (`is_legacy`, `legacy_selection`, no-`tick_seq` docs); old eval run data is dropped anyway.
- [RESOLVED: yes] O3: edit one line each in `web/README.md:8` and `scripts/README.md:8` (outside `docs/`).
- [RESOLVED: ruleset `main` lists `required_status_checks: []`, so no check name is enforced; changing job structure cannot block merges] [verified: `gh api rulesets/24909559`].
- [RESOLVED: dropping `test_deploy_prod.sh` loses pins on deploy-prod invariants (production environment, sha format); accepted by the brainstorm "drop tests of tests"].
- [DEFERRED: 09] `removed {}`, retired domains, `deployer_staging`, `.firebaserc`, `firebase.json`.
- [DEFERRED: 09] moving `deploy-prod` `resolve` to `STAGING_DEPLOYER_SA` (needs new IAM in the staging project).
- Risk: deleting compat code may drop api coverage below 94 (CI gate); batch 2 runs the combined gate locally first.

## Acceptance Criteria
1. The R1 files and functions are gone; no file name or test name contains `migration`, `naming_guard`, `no_old_imports`, `old_engine_removed`.
2. `git grep -nE 'paudit|iaudit|eaudit|onolys_core|onolys_evaluation'` outside `docs/` returns 0.
3. The R3 regex returns 0 in api, engines, eval, web (excluding `web/src/mocks`, generated and fixture files); the task lists any intentional exceptions.
4. `scripts/ci/` holds the 9 kept files plus the 6 eval-only files for 03; `changes.sh` is gone and `ci.yml` selects jobs identically (5 sample diffs).
5. No `|| vars.WIF_PROVIDER`/`'onolys-app-staging'` fallback in the four workflows; `gh variable` unchanged.
6. `git diff --stat` shows zero `infra/**/*.tf` and zero `docs/` changes other than regenerated `docs/contracts/public`.
7. Each batch commit passes lint and its impacted tests; final `api-coverage` ≥ 94.
