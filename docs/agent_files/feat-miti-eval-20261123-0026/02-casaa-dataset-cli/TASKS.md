---
status: draft
summary: SP2 tasks - eval/core package skeleton + repo guard, gold/manifest schemas, metrics, MITI lean adapter, fetch, PDF convert (+overrides), bucket + upload, run CLI, CI job, live acceptance
date: 2026-11-23
---
# Tasks: SP2 CASAA dataset + gold format + CLI eval spike

Source of truth: /root/projects/onolys/iaudit/.worktrees/feat/miti-eval/docs/agent_files/feat-miti-eval-20261123-0026/02-casaa-dataset-cli/PRD.md. Tests first, one commit per task. No dataset content in git (public repo); unit fixtures are synthetic. SP1 not required: use the engine `Turn` shape until the transcript schema lands.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Package skeleton, workspace line, repo guard | - | done |
| 2 | Manifest and `gold.v1` schemas | 1 | done |
| 3 | Metrics module | 2 | done |
| 4 | MITI lean adapter | 3 | done |
| 5 | Fetch command | 2 | done |
| 6 | PDF convert with overrides | 2, 5 | done |
| 7 | Convert the 8 sessions (rounder first) | 6 | done |
| 8 | Staging bucket (Terraform) and upload | 2, 7 | done |
| 9 | `run` CLI spike | 4, 7 | done |
| 10 | CI job for `eval/core` | 1 | done |
| 11 | Live acceptance pass | 8, 9, 10 | done |

## Task 1 — Package skeleton, workspace line, repo guard
What it is / what it means: The empty, installable `onolys-eval` package plus the safety net that keeps CASAA data out of the public repo. (R1, R9)
What changes at a high level: Add `eval/core` as a uv member (workspace `members` gains `eval/*`; lock regenerated), depending on `onolys_miti` and `pyyaml`, with `pdfplumber` in an optional `convert` extra. Add the `onolys-eval` entry point (subcommands stubbed) and `python -m onolys_eval`. Add `.gitignore` entries for `eval/**/raw/` and `eval/**/*.cache`. Delete the stale untracked `eval/__pycache__` locally.
Done when: Guard test written first: it fails if `git ls-files eval/` holds any pdf, mp3, `transcript.json`, `gold.json` or a file over 200 KB, and passes on the skeleton. `uv sync` and `uv lock --check` pass; the CLI prints help.

## Task 2 — Manifest and `gold.v1` schemas
What it is / what it means: The shared data contracts SP5 will reuse. (R2, R5)
What changes at a high level: Define the manifest format (dataset fields and per-session fields incl. `clinician_labels`, `code_header`, `change_goal` with source, nullable `coded_span`, optional audio) with a loader and validator. Ship `gold.v1.schema.json` with a typed model: counts and globals keyed by the engine item ids, computed summaries, optional per-utterance codes, parse method and warnings. Write the committed `casaa-miti421-video2013` manifest with the 8 sessions (URLs, titles, change goals from `Focus:` or curated, `license_note`).
Done when: Tests first: a valid manifest and gold load; bad ids, out-of-range globals and unknown keys are rejected; a summary-only gold (no utterance codes) validates; the committed manifest validates and lists 8 sessions.

## Task 3 — Metrics module
What it is / what it means: Pure, engine-agnostic scoring that SP5 reuses unchanged. (R6, D1)
What changes at a high level: Add `Scores`, `compare`, `aggregate` and the JSON-serialisable `compare.v1` output. Per key: gold, ours, signed and absolute diff. Aggregate gives MAE per count, global and summary, mean bias, globals within 1 point, and n. R:Q and %CR are recomputed from counts on both sides with the pack formula (`onolys_miti.formula`); null results are skipped in MAE and reported in n. No I/O, no LLM. Include the one-consensus-coder and rule-mismatch caveats in the compare output notes.
Done when: Tests first with synthetic scores: MAE, bias, within-1, null-skip, and R:Q / %CR equal `onolys_miti.formula` output; `compare.v1` round-trips through JSON.

## Task 4 — MITI lean adapter
What it is / what it means: The single home for turning an engine report into `Scores`. (R6, M2)
What changes at a high level: Create `onolys_eval.adapters` with the lean adapter: full lean report to `Scores`, projected to the scoring subset (behavior counts, 4 globals, tips). Confirm the exact field paths against the engine's report module while writing it and fix them in the adapter only. SP4 adds the one-shot adapter later.
Done when: Unit test on a synthetic golden lean report asserts the field mapping and the projection; a report with a missing field fails loudly, not silently.

## Task 5 — Fetch command
What it is / what it means: Reproducible download of the raw PDFs into a cache outside git. (R3)
What changes at a high level: `onolys-eval fetch <dataset>` downloads coded and uncoded PDFs (and audio when listed) into the per-session raw folder, skips existing files, and records sha256 and retrieved_at. Default cache `~/.cache/onolys-eval`; refuse any cache path inside a git work tree.
Done when: Tests first using a local HTTP server or mocked transport: files land in the right layout, a second run skips, `fetch.json` has hashes, and a cache path inside a git tree is refused.

## Task 6 — PDF convert with overrides
What it is / what it means: Parser from coded PDF to `transcript.json` and `gold.json`, with a manual fallback. (R4, R5)
What changes at a high level: `onolys-eval convert <dataset> [--session id] [--dump] [--allow-warnings]` using pdfplumber word positions: rows by utterance number, columns by header x-positions, headers/footers dropped, wrapped lines and wrapped code labels joined, then a label map to engine ids (incl. two-code rows and not-coded). Per-PDF quirks come from manifest settings. Roles come from the speaker label. Derive counts from utterance codes, read globals, compute summaries via the pack formula. Emit the listed warning checks; apply `overrides/<session>.yaml` (ids, codes, globals only, never text); exit non-zero on unresolved warnings.
Done when: Tests first on synthetic PDFs or word-position fixtures (no CASAA text): label map covers wrapped `Persuade with`, `Emphasize Persuade with`, `AF Q` and not-coded; each warning type fires; an override resolves a warning and marks the method `auto+override`; non-zero exit and `--allow-warnings` behave as specified.

## Task 7 — Convert the 8 sessions
What it is / what it means: The one-time data job producing real transcripts and gold in the cache. (R4, Risks)
What changes at a high level: Run fetch, then convert `rounder` and `confirmed-smoker` first, then the remaining six. Fix parser settings per PDF in the manifest; write committed override files (codes only) for the 2-3 PDFs that need them, and reassess if more are needed. Output validates against the transcript schema (Turn shape for now) and `gold.v1`. Data stays in the cache.
Done when: All 8 sessions have `transcript.json` and `gold.json` with zero unresolved warnings. Rounder derived counts equal its printed totals and globals are 4/3/5/5. `git ls-files eval/` still passes the guard test.

## Task 8 — Staging bucket (Terraform) and upload
What it is / what it means: A private bucket SP5 can read, and the command that fills it. (R7)
What changes at a high level: Add `onolys-eval-data-staging` in `infra/` (staging only, uniform access, public access prevention enforced, no versioning); agent runs plan and apply with the local Terraform and ADC, recording BLOCKED if auth fails. Add `onolys-eval upload <dataset>` using `google-cloud-storage` via ADC: renders manifest.json from yaml, copies per-session transcript, gold and raw files under `datasets/<id>/`; refuses unresolved warnings.
Done when: Tests first with a fake storage client: object layout matches R7, upload refuses unresolved warnings. Terraform plan is clean after apply. All 8 sessions are in the bucket and an anonymous read is denied (or BLOCKED recorded).

## Task 9 — `run` CLI spike
What it is / what it means: The command that answers how far off lean MITI is on one session. (R8)
What changes at a high level: `onolys-eval run <dataset> <session_id> [--preset] [--runs N] [--source cache|bucket] [--json-out]`. Load transcript and gold, build a `RunContext` like `onolys_miti.check`, call `run_miti` with the prebuilt speaker map and `{change_goal, language, n_runs, preset}`, map via the lean adapter, compare, and print the header line (preset, engine, git sha, tokens, rough cost), the code/gold/ours/diff table and the summary line. Tokens and cost from `MetricsCollector` for now. `--json-out` writes `compare.v1` plus run metadata and errors if the path is inside the repo. Exit 0 on a completed comparison.
Done when: Tests first with a fake engine run: table layout, `--json-out` content, in-repo path refused, bucket source reads via a fake client. Output matches the R8 sample shape.

## Task 10 — CI job for `eval/core`
What it is / what it means: CI today runs no eval tests; add them so the public-repo guard and metrics tests run on every PR. (CI default)
What changes at a high level: Add an `eval-core` job to `ci.yml` running the package's unit tests, and an eval change flag in `changes.sh` (eval paths plus the shared paths, with eval re-running when miti changes since it imports it). Keep it to unit tests: no network, no live keys.
Done when: `test_changes.sh` and `test_changes_deps.py` updated first for the new flag and pass; actionlint passes; `uv lock --check` passes.

## Task 11 — Live acceptance pass
What it is / what it means: Prove the spike end to end against the real model. (Acceptance criteria)
What changes at a high level: Load keys with `set -a; . ~/.config/onolys/keys.env; set +a` and run `onolys-eval run casaa-miti421-video2013 rounder`. Save `compare.v1` JSON outside the repo. Walk the acceptance list and record results; make no engine changes.
Done when: The table prints and JSON is written outside the repo. Every acceptance bullet is checked and noted, with BLOCKED entries for anything needing access that was missing.

## Owner / manual steps
- Review the curated `change_goal` per CASAA session (manifest, Task 2/7).
- CASAA terms confirmed OK (D5). GCP via ADC in `~/.config/gcloud`; `gcloud` CLI is not installed (use ADC from Python, Terraform at `/root/.local/bin/terraform`). Applying bucket Terraform is agent work, not an owner task.
- Deferred, not tasked: role-play audio dataset, utterance-level alignment, `--runs 3` median vs mean.
