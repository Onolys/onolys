---
status: draft
summary: 5 tasks to switch api to onolys_miti (one atomic import swap), narrow stages, rename paudit/iaudit names, slim the image, clean old env vars.
date: 2026-11-22
---
# Tasks: SP02 api switches to engines/miti
Source of truth: 02-api-switch/PRD.md. Depends on SP01 (`onolys_miti` interface and fixtures, read from its README). Order keeps every commit green: Task 1 is the atomic swap, later tasks build on it. Rating routes, storage and the first-run gate are untouched throughout.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Atomic import swap and engine seam | SP01 | done |
| 2 | Stages, fake adapter, artifacts, parity | 1 | done |
| 3 | Rename old names and report contract | 2 | done |
| 4 | Packaging and slim image | 3 | done |
| 5 | Old env var cleanup on infra and Cloud Run | 4 | done (no changes needed) |

## Task 1 — Atomic import swap and engine seam
What it is / what it means: Every api import of the old core, paudit and evaluation packages becomes `onolys_miti` in one pass, src and tests together, never mixed (PRD R1, D2). The engine is now called without a pack or rating.
What changes at a high level: Real adapter calls `run_miti`; `pack` and `rating` leave the `Evaluation.run` seam (D1, D2). The run stops loading the rating card and stops passing a coded span; it passes `seed` = session id (D10). Rating validation, rating schema and scenarios come from `onolys_miti` accessors, no pack loader or protocols env var (D8). Error mapping drops the pack and eaudit branches; public codes stay. Report schema path and test fixtures come from `onolys_miti`, never old engines. Accessor and fixture names are checked in SP01's README at coding time.
Done when: Import-guard test (no old-package imports in `api/src`, `api/tests`) is written first, fails, then passes. `test_span_not_passed` (params carry `seed`, never `coded_span`) and `test_rating_ignored` (same report with or without a submitted card, engine never sees a rating) pass. Mechanically swapped and rewritten test files pass with `-m "not live"`; rating PUT/GET tests unchanged and green.

## Task 2 — Stages, fake adapter, artifacts, parity
What it is / what it means: The pipeline vocabulary becomes what the engine really does: code, tips, assemble (D3, D4, D5, D7).
What changes at a high level: `Stage` narrows to three names and weights become 40/8/3 so progress stays under the 99 cap. Fake adapter emits the new stages, builds the no-rating report shape with the engine-style `run_info`, uses the whole session as span, and drops the eaudit logic. Failure markers become `[fail:code]` and `[fail:tips]`; `[fail:eaudit]` goes. Run artifacts written are `code.json` and `tips.json` only.
Done when: Tests first: run and machine tests assert steps `code, tips, assemble`, monotonic progress to 99 then 100, artifacts `code,tips`, code failure fails run and session as `internal_error`, tips failure gives a report with a warning. A parity test runs fake and real (fixture LLM) and asserts same top-level keys, stage sequence and schema validity.

## Task 3 — Rename old names and report contract
What it is / what it means: Nothing paudit, iaudit or eaudit survives in api or config; breaking, no migration (D6, D11).
What changes at a high level: LLM routes become `miti_code` and `miti_globals` in prod and staging routes config, staging presets and tests. Env vars set by api tests move to the `MITI_*` names. Error and log strings, artifact names carry no old name. Report key `run_info.paudit` becomes `run_info.miti`, `run_info.eaudit` goes, `run_info.miti.span` is added in the local report schema (src and tests copy). Public contract files (`openapi.json`, `docs/contracts/public/*`) are regenerated if they embed those keys. `schema_version` unchanged.
Done when: Name-guard test (no old names in `api/src`, `api/tests`, `config`) written first, then green. Staging presets test asserts `miti_*` routes. Real-flow report validates against both the engine schema and the updated local schema. `python -m onolys_api.contracts --check` green.

## Task 4 — Packaging and slim image
What it is / what it means: The api depends on `onolys-miti` only, and the container ships no old engines, protocols or eaudit contracts (R5, D9).
What changes at a high level: `api/pyproject.toml` deps and workspace source point at `onolys-miti` with the stt-google and voice-gemini extras; mutmut copy list drops protocols; `uv.lock` refreshed. Dockerfile installs and copies only miti and api source, keeps old members' manifests only so uv can resolve the workspace until SP05, and drops the protocols, contracts copies and their two env vars. Old packages stay workspace members.
Done when: `uv sync --frozen --package onolys-api` resolves and the api suite passes. Image builds; importing paudit, onolys_core, eaudit or onolys_evaluation fails inside it; `/app/protocols` absent; app boots with `SERVICE_MODE=combined` for `ADAPTERS=stub` and `real` (fixture providers). Image size recorded.

## Task 5 — Old env var cleanup on infra and Cloud Run
What it is / what it means: No leftover `PAUDIT_*`, `IAUDIT_*` or `EAUDIT_*` variable remains anywhere (R5, OPEN-5 resolved).
What changes at a high level: Grep `infra/` and remove any such variable (expected none, they came from the image ENV removed in Task 4). Apply terraform and confirm the live service carries none. Owner allows apply; nobody uses prod. If cloud credentials are missing, record a blocked note and finish the rest.
Done when: Grep of Dockerfile and `infra/` for the three prefixes is empty. After apply, `gcloud run services describe` shows no such variable, or the blocked note names the missing access.
