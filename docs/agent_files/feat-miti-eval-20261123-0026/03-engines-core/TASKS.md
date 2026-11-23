---
status: draft
summary: SP3 engines/core - new onolys_engine_core package, move engine-agnostic modules out of onolys_miti, Engine ABC + registry + presets + validate_output, MitiEngine, API migration, Docker/CI/docs
date: 2026-11-23
---
# Tasks: engines/core, engine interface, registry (SP3)

Source of truth: /root/projects/onolys/iaudit/.worktrees/feat/miti-eval/docs/agent_files/feat-miti-eval-20261123-0026/03-engines-core/PRD.md. Runs after SP1 (TranscriptV1, coded_span). Moves are behaviour-neutral: golden tests pass unchanged, no fixture re-record (R9). Breaking imports are fine, no shims (D7). One commit per task. Root shared files (`pyproject.toml`, `uv.lock`, `ci.yml`, Dockerfile) are touched only here in SP order.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Core package scaffold + basics move + import boundary test | - | done |
| 2 | Move LLM client and routes to core | 1 | done |
| 3 | Move transcript, txt parser, schema, speaker-gate helper; update eval imports | 1 | done |
| 4 | Engine ABC, result types, feedback hook, validate_output | 1 | in-progress |
| 5 | EngineRegistry and list_presets | 2, 4 | todo |
| 6 | MitiEngine adoption | 2, 3, 4, 5 | todo |
| 7 | API migration: engines.py, PROD_ENGINE, registry in RealEvaluation | 3, 5, 6 | todo |
| 8 | Dockerfile, CI core job, docs | 7 | todo |

## Task 1 — Core package scaffold + basics move + import boundary test
What it is / what it means: Create the new `engines/core` workspace package (`onolys-engine_core`, module `onolys_engine_core`) and move the pieces with no MITI coupling: run context, errors, retry, safe logging. (R1, R2, D1, D7)
What changes at a high level: Add package metadata with the four deps; `onolys-miti` depends on it. Move `RunContext`, `OnolysError/InputError/ConfigError`, `retry`, `safe_log` (logger name stays `miti`, `register_fields` kept). Update every import in miti and api to the core path, no re-exports. Add the AST-scanning boundary test (core imports nothing from `onolys_miti`) and make sure the name passes the existing `onolys_core` guard tests. Lock regenerated once.
Done when: Boundary test written first and failing, then passing. Moved modules' unit tests relocated and green. Existing miti tests (including `test_golden.py`) and the two naming guard tests pass; `uv sync --frozen` works.

## Task 2 — Move LLM client and routes to core
What it is / what it means: The LLM client, types, fixture/stub/recording clients, errors, routes and warm-up become engine-agnostic core code. SP4 later extends them. (R1, R9, M9)
What changes at a high level: Move `llm/*` and the `locate_config_file` helper it borrows from `stt.select`. Keep `routes.default.yaml` MITI aliases, route names (`miti_code`, `miti_globals`, `tips`), prompts and response-model class names, and the `MITI_MODEL_*`, `MITI_LLM_RESPONSE_FORMAT`, `MITI_LLM_RECORD` env names. Fixtures stay under miti data. Update importers.
Done when: A test asserts `FixtureClient.key_for` yields the same keys as before for the existing golden fixtures (file names unchanged). Moved llm tests green; golden tests pass with no re-record.

## Task 3 — Move transcript, txt parser, schema, speaker-gate helper; update eval imports
What it is / what it means: SP1's `TranscriptV1`, `.txt` parser, JSON schema and the role-inference helper live in core so every engine and the API share them. The API keeps the gate UI and state. (R1, M5, M7, D6)
What changes at a high level: Relocate those SP1 files and `transcript.v1.schema.json` to core; `Span` and `span.py` stay in MITI. `stt/` stays in miti and imports `Turn` from core. Update API, miti and `eval/core/**` imports (`Turn`, `RunContext` now from core). Resolve any schema path references. No content changes (SP1 owns content).
Done when: SP1's transcript, parser and schema tests run unchanged against core paths. Targeted API upload/speaker tests, eval/core tests and miti tests pass. Boundary test still green.

## Task 4 — Engine ABC, result types, feedback hook, validate_output
What it is / what it means: The shared engine contract and the PHI-safe validation helpers that SP4's validate-and-retry loop will use. (R3, R4, M3, M6, D3, D4)
What changes at a high level: Add `Engine` (name, version, `accepts_feedback` default False, async `run`, `output_schema`, `variants`), `EngineResult`, `RunInfo` (extra allowed), `RunUsage`, `EngineVariant`, `ProgressCb`. Add `RunContext.feedback` (default None). Add `validate_output` returning capped, value-free `ValidationIssue`s (path, message) and `build_feedback`. `run_validated` is not built here (SP4).
Done when: Unit tests first: ABC cannot be instantiated without abstract methods; defaults hold; `validate_output` caps count and length and never contains instance values; `build_feedback` includes the fixed conformance instruction; `ctx.feedback` reaches a stub engine's `run`.

## Task 5 — EngineRegistry and list_presets
What it is / what it means: A name-keyed engine registry and a preset lister that flags the prod ones, for the API and the eval options endpoint. (R5, R6, D5)
What changes at a high level: `register`, `get` (unknown raises `InputError`), `engines()` returning `EngineInfo` with prod flag, schema id, `accepts_feedback` and variants. `list_presets(registry, prod_name)` returns name, prod, and route-to-model map with no keys. Prod is computed at list time, not stored in YAML. Route data comes from core routes.
Done when: Tests: unknown engine raises; `engines()` marks only the configured prod engine; variants appear; `list_presets` returns `default`/`claude`, flags the prod preset (falls back to `default`), exposes no key material.

## Task 6 — MitiEngine adoption
What it is / what it means: MITI becomes `MitiEngine(Engine)` without changing its behaviour or output. (R7, R9)
What changes at a high level: Add `MitiEngine` wrapping `run_miti` (signature unchanged), reading `speaker_map` from params, mapping `MetricsCollector` into `RunInfo.usage`, `output_schema()` returning the report schema. Lean internal checks and prompts untouched. `onolys_miti` exports only `run_miti` and `MitiEngine`.
Done when: Test shows `MitiEngine.run` output equals `run_miti` on a golden fixture; `output_schema()` validates the golden report through `validate_output`; registry returns it as `miti`. All existing miti tests incl. `test_golden.py` pass unchanged.

## Task 7 — API migration: engines.py, PROD_ENGINE, registry in RealEvaluation
What it is / what it means: The API stops importing engine internals by name and runs engines through the registry, and exposes prod flags from settings. (R5, R6, R8, D2)
What changes at a high level: New `engines.py` builds the registry by explicit import (MITI only; one-shot is eval-only, M8). Add `PROD_ENGINE` setting (default `miti`). `RealEvaluation` resolves the engine via `registry.get`. `PresetResolver` keeps its allowlist (`ENABLED_EXTRA_PRESETS`, `test-*`) and calls `list_presets`. Update `presets.py`, `logs.py`, adapters (real and fake), repo and config imports to `onolys_engine_core`, leaving `onolys_miti` only for MITI/stt/voice.
Done when: API tests written first: registry built, `PROD_ENGINE` default and override, unknown engine error mapping, `test-*` still excluded, real and fake adapters unchanged in behaviour. Targeted API tests pass; a grep test shows API imports `onolys_miti` only for allowed areas.

## Task 8 — Dockerfile, CI core job, docs
What it is / what it means: Make the build and CI know about the new package. (R8, M9, acceptance criteria)
What changes at a high level: `api/Dockerfile` copies `engines/core`. Add a `core` job to `ci.yml` (tests plus boundary test), and register core in the `changes.sh` flags and DEPS map so core changes also rerun miti and api, keeping `test_changes.sh` and `test_changes_deps.py` honest. Update `docs/architecture.md` and `engines/miti/README.md` for the core/engine split. Lock regenerated once.
Done when: Updated `test_changes.sh` and `test_changes_deps.py`, actionlint and `uv lock --check` pass; the core job runs the core tests locally. The API image builds and `import onolys_engine_core, onolys_miti` succeeds inside it. Docs link check passes.

## Closing note
No manual steps (PRD: none). Prod `DEFAULT_PRESET` is untouched. Deferred per PRD: engine-declared aliases, `LLM_*` env aliases, logger rename, moving `stt/`, entry-point discovery, per-engine preset compatibility. `apply_coded_span` and `run_validated` belong to SP4.
