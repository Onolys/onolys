---
status: draft
summary: Engine package in 8 tasks (PRD T0-T7) - capture equivalence baseline on old code, move product code to api, scaffold engine/, runner + Engine, port MITI, port one-shot, constants sweep, full gate. Refreshed for rule 17 (library over custom code).
date: 2026-11-28
---
# Tasks: 04 Engine package

Source of truth: /root/projects/onolys/onolys/.worktrees/refactor/revamp/docs/agent_files/refactor-revamp-20261128-0102/04-engine-package/PRD.md. Strangler migration: old packages shrink as modules move, callers are rewritten in the same commit, every commit green, no shims survive. Structural only; behaviour changes are 05's. Task N here is PRD T(N-1). Needs 01 done and 03 landed (eval out of the workspace, tag `engine-v0` exists). CI exists (`ci.yml`); this SP changes its jobs, adds none. Full suite runs only in dev-ship (Task 8). Do not edit `docs/`. Rule 17 applies throughout: use the library, do not rebuild it (LiteLLM retries and `mock_response`, `StructuredLogHandler`, Jinja2 `StrictUndefined`, ruff `banned-api`, one stub client).

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Equivalence baseline on old code (PRD T0, R11) | none | todo |
| 2 | Move product code out of the engine into api; api logging on `StructuredLogHandler` (T1, R8) | 1 | todo |
| 3 | Scaffold `engine/`, workspace, CI, Docker; move core leaf modules; ruff boundary ban (T2, R1, R2, R7) | 2 | todo |
| 4 | State, runner, minimal loader checks, `Engine`, public surface; LiteLLM 429 check (T3, R3, R4, R7) | 3 | todo |
| 5 | Port MITI: protocol, steps, scoring, LLM reshape, api rewire (T4, R5, R6, R9) | 4 | todo |
| 6 | Port one-shot as `oneshot-single`; `gen_schemas.py` (T5) | 5 | todo |
| 7 | Constants sweep, env renames, link lines, boundary guard final (T6, R10) | 6 | todo |
| 8 | Full gate and acceptance sweep (T7) | 7 | todo |

## Task 1 — Equivalence baseline on old code
What it is / what it means: The proof that later tasks change structure only. It must be captured before any source change, so it is the oracle for Tasks 2-7. PRD T0, R11, D11. A refactor proof, not a permanent test matrix.
What changes at a high level: Add a harness to the old packages' tests: (1) provider-payload capture (patch `litellm.acompletion`, store normalized call list sorted by call tag); (2) masked golden reports (today's `test_golden.py` mask rule). Three fixtures only: `good_practice` (already recorded; also run with `n_runs=3` for aggregate and representative run), `poor_practice` (cap path), `batch_edge` (27 volleys, batch boundary, warm-up). Replies come from `expected.yaml` via `regen_goldens --responses`. `short_session` and `sparse_evidence` stay as their existing unit tests. Keep the two recorded one-shot replies. No source change.
Done when: harness and all baselines are committed; the new harness tests plus the existing core, miti and oneshot suites pass on unchanged source; a second capture yields an identical diff.

## Task 2 — Move product code out of the engine into api
What it is / what it means: STT, voice, rating, scenarios, upload parsers and log setup are product code living in the engine by accident. Moving them first keeps the new engine clean. PRD T1, R8, D3, D4, rule 17.
What changes at a high level: `git mv` (own file names kept, tests move with them) to the R8 locations in `api/`; move their deps and extras into api; rewrite imports. Split logging: the engine keeps `log_event` and a static `LOG_FIELDS`; api drops the custom JSON formatter and log-context code and uses google-cloud-logging `StructuredLogHandler`, with the PHI allowlist (`safe_log.py`) kept as a `logging.Filter`. `rating.schema.json` stays beside `rating.py` until Task 5. If 06 already moved a piece, skip it. No other logic change.
Done when: api suites and remaining core/miti/oneshot suites pass; Task 1 baselines unchanged; `git grep` shows no STT/voice/rating/scenario/upload-parser code left under `engines/`; a test asserts `jsonPayload.status` and `request_id` are emitted unchanged (field names checked once by hand against `infra/modules/environment/alerts.tf`; no test reads the `.tf`) and the PHI `logging.Filter` still redacts; the custom JSON formatter and its tests are gone.

## Task 3 — Scaffold `engine/`, move core leaf modules
What it is / what it means: Creates the single package and kills `engines/core`. PRD T2, R1, R2, R7, D1, D2, rule 17.
What changes at a high level: Create `engine/` (dist `onolys-engine`, import `onolys_engine`, src layout, deps per R1), update root workspace members and regenerate `uv.lock`. Replace the `core`/`oneshot`/`miti` CI jobs and path lists in `ci.yml` and `pr-preview.yml` with one `engine` job; collapse Dockerfile and api `pyproject.toml` lines. `git mv` core leaf modules (transcript, errors, llm as-is, logging, text limits) into it, delete `engines/core`, and rewrite miti, oneshot and api imports. Enforce the boundary with ruff `banned-api` (TID251) banning `onolys_engine.<submodule>` outside the engine; verify the per-file ignore for `engine/**` works, else use an `import-linter` `forbidden` contract. If ruff cannot express it, report to the owner (no auto-fallback). No custom AST test: delete `api/tests/test_miti_import_boundary.py`, `engines/core/tests/test_import_boundary.py` and `engines/core/tests/test_transcript_imports.py`. The new `engine` CI job finishes within 5 minutes.
Done when: all suites pass under the new workspace; Task 1 baselines unchanged; the `engine` CI job runs locally via its commands; ruff passes and flags a planted `from onolys_engine.steps import x` in `api/`.

## Task 4 — State, runner, loader checks, `Engine`, public surface
What it is / what it means: The mechanism the YAML pipelines run on, built and tested on toy pipelines before any real port. PRD T3, R3, R4, R7, D7. Load checks stay minimal (rule 17).
What changes at a high level: Add `state.py` (typed slot dataclass), `runner.py` (`@step` with reads/writes used only for `parallel` merging, `parallel`, `repeat: n_runs` with run-scope reset, `run_failed` exclusion, `AllRunsFailed`, warm-up after run 0, stage progress), the loader with only these checks (unknown step; unknown or missing `with` keys via signature binding; nothing else, missing files fail on open), `Engine` (`load`, `evaluations`, `output_schema`, `protocol`, `check_input`, `run`), and `public.py` with `__init__` re-exporting exactly it plus `Engine`. Run a short check that LiteLLM retries a 429 with `Retry-After`; report if it cannot (no custom fallback).
Done when: toy-pipeline tests cover each load error (unknown evaluation, unknown step, bad `with` key) one test each; parallel merge order and repeat exclusion tests pass; no read-before-write, disjoint-writes or run-scope checker exists; the 429 check result is recorded; ruff boundary ban still green.

## Task 5 — Port MITI
What it is / what it means: The main port: today's miti behaviour becomes protocol data, a pipeline YAML and a step/scoring library, with the LLM layer reshaped on library features. PRD T4, R5, R6, R9, D5, D6, D8, D9, rule 17.
What changes at a high level: Add `protocols/miti-4.2.1` (items, rules, caps, summaries; definitions) and `evaluations/miti` (pipeline, prompts with `{{...}}` placeholders rendered by Jinja2 `StrictUndefined` with `keep_trailing_newline=True` and byte-identical to today, no hand-written renderer; fewshot, report.yaml, fixtures shipped in wheel). Implement the R5 catalogue as steps and `scoring/` and `models/` modules; drop dead hooks, registry, aliases, one `StepFailed`. Reshape LLM: multi-turn `Message`, `send`/`send_json`/`send_cached`, tiers and presets, unknown preset keys as `PresetInfo.extra`, `routes.default.yaml` to constants (deleted), remove the four prompt-named route entries from both `config/*/routes.yaml`, rename the two env vars (`ci.yml`). Retries via LiteLLM `num_retries`/retry policy: delete `retry.py`, `test_retry.py` and the custom 429/529 loop; keep only the output-schema retry and deadline-awareness if genuinely product. Clients: only `FixtureClient` (replay, record via `LLM_RECORD`, raise a given error) and `StubClient`; delete the ~6 hand-written fakes and re-point their tests; payload tests use LiteLLM `mock_response`. Rewire api to `Engine.run`/`check_input`/`protocol()`; delete `rating.schema.json`; delete `engines/miti`; delete tests of removed things.
Done when: Task 1 payload and masked-report equivalence passes on all three fixtures; reports validate against unchanged `report.schema.json` and `report.local.schema.json`; api suites pass at coverage 94; `git grep "complete_json\|LLMRequest(tier"` returns 0; no hand-written fake client or `retry.py` remains.

## Task 6 — Port one-shot as `oneshot-single`
What it is / what it means: The second evaluation, same single call and output shape; renamed, `oneshot-raw` dropped, old stored runs not mapped. PRD T5, D12, D15, O4, O6.
What changes at a high level: Add `evaluations/oneshot-single` (pipeline with `output_retry: 1`, `llm.oneshot`, `tips.limit`, prompts kept literal, schema) and `engine/tools/gen_schemas.py` (generates only the one-shot schema); `run_info.engine` carries the evaluation name, `config` field dropped. Move `scripts/gen_miti_schema.py` to tools and fix the `web/package.json` `gen:api` path. Delete `engines/oneshot` and `engines/`.
Done when: both recorded one-shot replies reproduce their goldens; `gen_schemas.py` regeneration gives an empty diff; api tests for the renamed engine pass; `engines/` does not exist.

## Task 7 — Constants sweep, env renames, link lines, guard final
What it is / what it means: Leaves one source for every literal and removes remaining old names. PRD T6, R10, D14.
What changes at a high level: Sweep `constants.py` (roles, stages, limits, locate thresholds, hash length, schema versions, env names, default model spec, `LOG_FIELDS`, error codes); thresholds only in `pipeline.yaml`; no magic numbers in steps. Apply the owner's answer on the dev-tools [OPEN] (default: delete `audit_report.py`, `probe_llm.py` and their tests; keep `regen_goldens.py`, `gen_schemas.py`, `live_check.py`). Rewrite `engine/README.md`; update the one-line engine links in `README.md` and `AGENTS.md`. Audit that tests mirror source and no test name carries a task id. Finalise the ruff boundary ban.
Done when: `git grep` for old package/path names outside `docs/` returns 0 (incl. workflows, Dockerfile, `web/package.json`, root `pyproject.toml`); grep finds no `25 * 60` or `0.20` in steps; mirror audit passes; ruff clean including the boundary ban.

## Task 8 — Full gate and acceptance sweep
What it is / what it means: Proves every PRD acceptance criterion before review. PRD T7.
What changes at a high level: No new edits unless a check fails. Run all suites through dev-ship, including the Task 1 equivalence suite, api coverage gate, and every acceptance grep.
Done when: all suites green, api coverage at least 94, acceptance criteria hold (with the ruff-ban and minimal-load-check reading above), CI green on the branch.

Owner-only: none beyond 03 landing first and tag `engine-v0` existing; `engine-v1` is cut after 04-06 for 10.
