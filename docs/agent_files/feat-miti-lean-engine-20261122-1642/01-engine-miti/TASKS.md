---
status: draft
summary: Build engines/miti (onolys_miti) in 7 commits - scaffold+data, infra copy, coding passes, auto span, report/tips, run_miti, parity+live check.
date: 2026-11-22
---
# Tasks: SP01 engines/miti lean MITI engine
Source of truth: docs/agent_files/feat-miti-lean-engine-20261122-1642/01-engine-miti/PRD.md. Copy (not move) from paudit, core and evaluation into one self-contained package with MITI hardcoded and everything renamed to miti. Only `engines/miti/**` and `uv.lock` change; CI wiring is SP05. Every task writes its tests first and runs only those tests.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Scaffold package, MITI data, naming guard | none | done |
| 2 | Copy infra (llm, stt, voice, transcript, errors, utils) | 1 | done |
| 3 | Port coding passes and MITI constant | 1, 2 | done |
| 4 | Automatic coded span | 3 | done |
| 5 | Report model, builder, tips, rating validation | 2, 3 | done |
| 6 | `run_miti` entry point, stages, n_runs | 4, 5 | done |
| 7 | Golden parity proof, live check, acceptance | 6 | done |

## Task 1 — Scaffold package, MITI data, naming guard
What it is / what it means: The empty shell of `onolys-miti` plus the MITI protocol data, so later tasks have a place to land. Covers R1 (data), R5, R6 and D1, D3, D4.
What changes at a high level: New workspace member with its own dependency list (union of what core, paudit and evaluation use, with the stt-google and voice-gemini extras) and a dev group; lock file refreshed. MITI pack files, prompts, report config, rating schema, fixtures and scenarios copied byte-identical into the package data. First verify no `miti` name clash (D1, default `onolys_miti`). A guard test fails if the old names (paudit, iaudit, eaudit, onolys_core, onolys_evaluation) appear anywhere in the package; copied data gets the renames applied (route names, engine name) with the pack hash kept equal to today's.
Done when: `uv sync --frozen --package onolys-miti` works; the guard test and a data test (pack loads, pack hash equals the known old hash) pass; ruff clean.

## Task 2 — Copy infra (llm, stt, voice, transcript, errors, utils)
What it is / what it means: Everything api imports from core today, so api never needs `onolys_core` again. Covers R1 infra rows, R6 env and route renames, D9.
What changes at a high level: Copy the LLM client and routes, fixture client and replay, STT (Chirp) and voice (Gemini Live) providers with their default yaml, transcript, errors, safe_log, locate, normalize, retry, run_info and `RunContext`. Drop eaudit turn helpers, the Engine protocol, PackRef and EngineResult. Rename routes to `miti_code` and `miti_globals` and env vars to `MITI_*`; verify at coding time whether `PackError` is needed (default: not ported). Re-grep before dropping each module.
Done when: Ported core tests (llm, routes, locate, retry, run_info, safe_log, stt, google_chirp, voice, types) pass offline under the new names; the guard test still passes.

## Task 3 — Port coding passes and MITI constant
What it is / what it means: The MITI coding logic, unchanged in behaviour, so coding parity is provable. Covers R1 coding rows, D4.
What changes at a high level: Copy prepare, code pass, globals pass, score, formula, result and the MITI rules module. The `Pack` argument becomes a frozen `MITI` constant loaded once from the data; the dynamic rules loading goes away. `PauditResult` becomes `MitiResult`. Prompts, rules, formulas and thresholds are not touched.
Done when: Ported paudit tests (code_pass, globals_pass, formula, prepare, result, score, miti_pack) pass with the fixture client; a test proves `onolys_miti` imports no old package.

## Task 4 — Automatic coded span
What it is / what it means: The engine, not the user, decides which part of a long session is coded. Covers R7 and D10.
What changes at a high level: A small span module that computes session duration from turn end times, codes the whole session when it is 20 minutes or less, otherwise picks a 20-minute window using a random generator seeded from the session id. The choice is recorded on the result (`coded_span`, span mode, duration, seed) and as a `coded_window` info warning; no timestamps gives whole session plus the existing `span_ignored` warning. Any caller-supplied `coded_span` param is ignored or rejected.
Done when: Span tests pass: at most 20 min gives whole with null span; over 20 min gives a window inside the session; same seed gives same window; different seeds vary; no timestamps gives whole plus warning; a passed `coded_span` has no effect.

## Task 5 — Report model, builder, tips, rating validation
What it is / what it means: The no-rating report and the tips that go into it. Covers R3, D5, D7, D8 partly.
What changes at a high level: Copy the report model and generate `report.schema.json` with only the R6 renames (`run_info.miti`, no `run_info.eaudit`, engine name miti). Build the no-rating subset of the compare logic (not_rated rows, Onolys-only explanations and summaries, representative instances) and `build_report_no_rating`. Port tips (single call, locate validation, tone lint, 3-5 tips, retry, warnings) and rating validation with its schema. Reasons audit, rating diff and eaudit are not ported.
Done when: Ported tests (build_report reduced to no-rating, tips, tone, report_schema, validate_rating) pass; a built report validates against the new schema; a tips failure yields a warning, not an error.

## Task 6 — `run_miti` entry point, stages, n_runs
What it is / what it means: The one public function api will call. Covers R2 and D6.
What changes at a high level: A run module that applies speaker mapping, picks the span once, runs the code and globals passes, repeats n_runs times and averages (min/max kept), runs tips, builds the report and returns `MitiOutput` with artifacts. Progress reports `code`, `tips`, `assemble`. Failed runs are excluded with `run_failed`; all failing raises `AllRunsFailed`; coding failure raises, tips failure degrades. Deadline honoured; error codes unchanged; public re-exports for llm and stt types.
Done when: Ported engine and run_evaluation tests pass on the fixture client, covering stage events, n_runs=3 averaging with one failed run, deadline, and coding-failure versus tips-failure behaviour.

## Task 7 — Golden parity proof, live check, acceptance
What it is / what it means: Evidence that the new engine matches the old one and the package is ready for SP02 and SP05. Covers R4, D8 and the acceptance criteria.
What changes at a high level: A golden test runs `run_miti` on `good_practice` with the fixture client and compares to the updated `report_no_rating.json` after masking volatile keys. A one-off, uncommitted script diffs old `run_evaluation(rating=None)` against new output; expected diff is only the run_info renames and span additions, recorded for the PR. One merged live check module (marker `live`, off by default) covers the old paudit and tips checks. The test command is documented.
Done when: Golden and schema tests pass (also against the api local report schema); the old-vs-new diff shows only the expected deltas; `pytest engines/miti -m "not live"` and ruff are green; the guard grep is empty; `git status` shows nothing outside `engines/miti/**` and `uv.lock`.
