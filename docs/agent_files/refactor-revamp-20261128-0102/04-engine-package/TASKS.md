---
status: draft
summary: Engine package in 8 tasks (PRD T0-T7) - capture equivalence baseline on old code, move product code to api, scaffold engine/, runner + Engine, port MITI, port one-shot, constants sweep, full gate.
date: 2026-11-28
---
# Tasks: 04 Engine package

Source of truth: /root/projects/onolys/onolys/.worktrees/refactor/revamp/docs/agent_files/refactor-revamp-20261128-0102/04-engine-package/PRD.md. Strangler migration: old packages shrink as modules move, callers are rewritten in the same commit, every commit green, no shims survive. Structural only; behaviour changes are 05's. Task N here is PRD T(N-1). Needs 01 done and 03 landed (eval out of the workspace, tag `engine-v0` exists). CI exists (`ci.yml`); this SP changes its jobs, adds none. Full suite runs only in dev-ship (Task 8). Do not edit `docs/`.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Equivalence baseline on old code (PRD T0, R11) | none | todo |
| 2 | Move product code out of the engine into api (T1, R8) | 1 | todo |
| 3 | Scaffold `engine/`, workspace, CI, Docker; move core leaf modules (T2, R1, R2) | 2 | todo |
| 4 | State, runner, loader checks, `Engine`, public surface (T3, R3, R4, R7) | 3 | todo |
| 5 | Port MITI: protocol, steps, scoring, LLM reshape, api rewire (T4, R5, R6, R9) | 4 | todo |
| 6 | Port one-shot as `oneshot-single`; `gen_schemas.py` (T5) | 5 | todo |
| 7 | Constants sweep, env renames, link lines, boundary guard final (T6, R10) | 6 | todo |
| 8 | Full gate and acceptance sweep (T7) | 7 | todo |

## Task 1 — Equivalence baseline on old code
What it is / what it means: The proof that later tasks change structure only. It must be captured before any source change, so it is the oracle for Tasks 2-7. PRD T0, R11, D11.
What changes at a high level: Add a harness to the old packages' tests: (1) provider-payload capture (patch `litellm.acompletion`, store normalized call list sorted by call tag); (2) masked golden reports (today's `test_golden.py` mask rule). Add fixtures `poor_practice`, `short_session`, `sparse_evidence`, `batch_edge` (27 volleys), and `good_practice` with `n_runs=3`, replies generated from `expected.yaml` via `regen_goldens --responses`. Keep the two recorded one-shot replies. No source change.
Done when: harness and all baselines are committed; the new harness tests plus the existing core, miti and oneshot suites pass on unchanged source; a second capture yields an identical diff.

## Task 2 — Move product code out of the engine into api
What it is / what it means: STT, voice, rating, scenarios, upload parsers and log setup are product code living in the engine by accident. Moving them first keeps the new engine clean. PRD T1, R8, D3, D4.
What changes at a high level: `git mv` (own file names kept, tests move with them) to the R8 locations in `api/`; move their deps and extras into api; rewrite imports; split logging so api owns handler, context and allowlist enforcement while the engine keeps `log_event` and a static `LOG_FIELDS`. `rating.schema.json` stays beside `rating.py`. If 06 already moved a piece, skip it. No logic change.
Done when: api suites and remaining core/miti/oneshot suites pass; Task 1 baselines unchanged; `git grep` shows no STT/voice/rating/scenario/upload-parser code left under `engines/`; the log allowlist test passes in api.

## Task 3 — Scaffold `engine/`, move core leaf modules
What it is / what it means: Creates the single package and kills `engines/core`. PRD T2, R1, R2, D1, D2.
What changes at a high level: Create `engine/` (dist `onolys-engine`, import `onolys_engine`, src layout, deps per R1), update root workspace members and regenerate `uv.lock`. Replace the `core`/`oneshot`/`miti` CI jobs and path lists in `ci.yml` and `pr-preview.yml` with one `engine` job; collapse Dockerfile and api `pyproject.toml` lines. `git mv` core leaf modules (transcript, errors, llm as-is, logging, text limits) into it, delete `engines/core`, and rewrite miti, oneshot and api imports. Add the AST boundary test (no `onolys_engine.<submodule>` or `_private` import from outside).
Done when: all suites pass under the new workspace; Task 1 baselines unchanged; the `engine` CI job runs locally via its commands; boundary test passes and fails on a planted submodule import.

## Task 4 — State, runner, loader checks, `Engine`, public surface
What it is / what it means: The mechanism the YAML pipelines run on, built and tested on toy pipelines before any real port. PRD T3, R3, R4, R7, D7.
What changes at a high level: Add `state.py` (typed slot dataclass), `runner.py` (`@step` with reads/writes, `parallel`, `repeat: n_runs` with run-scope reset, `run_failed` exclusion, `AllRunsFailed`, warm-up after run 0, stage progress), the loader and its load-time checks, `Engine` (`load`, `evaluations`, `output_schema`, `protocol`, `check_input`, `run`), and `public.py` with `__init__` re-exporting exactly it plus `Engine`.
Done when: toy-pipeline tests cover each load error (unknown evaluation, unknown step, bad `with` key, mis-ordered read, overlapping parallel writes, run-scope slot outside `repeat`, missing prompt reference, `model` key) one test each; parallel merge order and repeat exclusion tests pass; boundary test still green.

## Task 5 — Port MITI
What it is / what it means: The main port: today's miti behaviour becomes protocol data, a pipeline YAML and a step/scoring library, with the LLM layer reshaped. PRD T4, R5, R6, R9, D5, D6, D8, D9.
What changes at a high level: Add `protocols/miti-4.2.1` (protocol.yaml with items, rules, caps, summaries; definitions) and `evaluations/miti` (pipeline, prompts with placeholders rendered byte-identically, fewshot, report.yaml, fixtures shipped in wheel). Implement the R5 catalogue as steps and `scoring/` and `models/` modules; drop dead hooks, registry, aliases, one `StepFailed`. Reshape LLM: multi-turn `Message`, `send`/`send_json`/`send_cached`, tiers and presets, unknown preset keys passed through as `PresetInfo.extra`, constants for `routes.default.yaml` (deleted), remove the four prompt-named route entries from both `config/*/routes.yaml`, rename the two `LLM_*` env vars (`ci.yml`). Rewire api to `Engine.run`/`check_input`/`protocol()`; delete `rating.schema.json`; delete `engines/miti`; delete tests of removed things.
Done when: Task 1 payload and masked-report equivalence passes on all fixtures; reports validate against unchanged `report.schema.json` and `report.local.schema.json`; api suites pass at coverage 94; `git grep "complete_json\|LLMRequest(tier"` returns 0.

## Task 6 — Port one-shot as `oneshot-single`
What it is / what it means: The second evaluation, same single call and output shape; renamed, `oneshot-raw` dropped, old stored runs not mapped. PRD T5, D12, D15, O4, O6.
What changes at a high level: Add `evaluations/oneshot-single` (pipeline with `output_retry: 1`, `llm.oneshot`, `tips.limit`, prompts kept literal, schema) and `engine/tools/gen_schemas.py` (generates only the one-shot schema); `run_info.engine` carries the evaluation name, `config` field dropped. Move `scripts/gen_miti_schema.py` to tools and fix the `web/package.json` `gen:api` path. Delete `engines/oneshot` and `engines/`.
Done when: both recorded one-shot replies reproduce their goldens; `gen_schemas.py` regeneration gives an empty diff; api tests for the renamed engine pass; `engines/` does not exist.

## Task 7 — Constants sweep, env renames, link lines, guard final
What it is / what it means: Leaves one source for every literal and removes remaining old names. PRD T6, R10, D14.
What changes at a high level: Sweep `constants.py` (roles, stages, limits, locate thresholds, hash length, schema versions, env names, default model spec, `LOG_FIELDS`, error codes); thresholds only in `pipeline.yaml`; no magic numbers in steps. Rewrite `engine/README.md`; update the one-line engine links in `README.md` and `AGENTS.md`. Audit that tests mirror source and no test name carries a task id. Finalise the boundary guard.
Done when: `git grep` for old package/path names outside `docs/` returns 0 (incl. workflows, Dockerfile, `web/package.json`, root `pyproject.toml`); grep finds no `25 * 60` or `0.20` in steps; mirror audit and boundary tests pass; ruff clean.

## Task 8 — Full gate and acceptance sweep
What it is / what it means: Proves every PRD acceptance criterion before review. PRD T7.
What changes at a high level: No new edits unless a check fails. Run all suites through dev-ship, including the Task 1 equivalence suite, api coverage gate, and every acceptance grep.
Done when: all suites green, api coverage at least 94, acceptance criteria hold, CI green on the branch.

Owner-only: none beyond 03 landing first and tag `engine-v0` existing; `engine-v1` is cut after 04-06 for 10.
