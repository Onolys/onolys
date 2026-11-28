---
status: draft
summary: API by feature in 11 tasks (T0-T10 from the PRD) - baseline, eval-mode deletion, fakes out, one data layer, then one folder per feature, routes/dev.sh/CI, final cleanup and engine-v1 tag.
date: 2026-11-28
---
# Tasks: 06 API by feature

Source of truth: /root/projects/onolys/onolys/.worktrees/refactor/revamp/docs/agent_files/refactor-revamp-20261128-0102/06-api-by-feature/PRD.md. Strangler migration: one commit per task, green suite at every commit, no shim survives Task 10. Task numbers match the PRD's T0-T10. `api/openapi.json`, `docs/contracts/public/**` and `web/src/api/schema.d.ts` are never edited (R9). Tests move with their feature commit and run only the impacted ones; the full suite runs in dev-ship. CI exists (`.github/workflows/ci.yml`); Tasks 2 and 9 update the `api-*` jobs, none is added.

| # | Task | Depends on | Status |
|---|---|---|---|
| 0 | Baseline: job timings, project-id isolation check, contract blob ids | none | todo |
| 1 | Delete eval-mode code (R5) | 0 | todo |
| 2 | Fakes out: all tests on the emulator, stubs per R4 | 1 | todo |
| 3 | `constants.py` and the `data/` layer (R2, R3) | 2 | todo |
| 4 | `usage/`, `auth/`, `email/` | 3 | todo |
| 5 | `audio/` and `transcription/` | 3 | todo |
| 6 | `sessions/` | 4, 5 | todo |
| 7 | `pipeline/`, `tasks/`, `app.py` mode table | 6 | todo |
| 8 | `voice/` and `rating/` | 7 | todo |
| 9 | Slim `routes/`, `http.py`, `gen_contracts.py`, `dev.sh`, CI (R6, R8) | 8 | todo |
| 10 | Delete shims and old folders; regroup tests; engine-v1 tag | 9 | todo |

## Task 0 — Baseline
What it is / what it means: Record numbers and fixed points that later tasks are judged against. The phase-0 spikes 2 (Admin SDK with Auth-emulator tokens) and 5 (api CI job merge) already ran and the owner decided; this task consumes those decisions, it does not re-run them. PRD T0, O1, O3, D3.
What changes at a high level: Nothing in product code. Time the `api-unit` and `api-emulator` jobs (and the local runtimes). Confirm the job-merge share still holds on the new layout, as a note for the owner. Check per-test Firestore-emulator project-id isolation works (two projects, same doc path, no cross-visibility). Note the git blob ids of `api/openapi.json`, `docs/contracts/public/**`, `web/src/api/schema.d.ts` and the T0 sha. Record which token verifier the owner chose for `AUTH_MODE=emulator`.
Done when: findings are in the task log and reported to the owner; a throw-away isolation probe test (kept inside `api/tests/`, deleted afterwards) passes; the contract blob ids are recorded.

## Task 1 — Delete eval-mode code
What it is / what it means: Eval left this repo in 03, so its prod-path hooks go first (smallest code, lowest risk). PRD R5, T1.
What changes at a high level: Remove `eval_mode`/`EVAL_MODE`, `RunDoc.eval`, `EvalRunInfo`, `EvalGold/EvalSessionInfo`, `reject_eval_write`, `eval_session_input_sha256`, the `create_run(is_eval, eval_spec)` arguments, `EvalDisabled`, `engines.eval_snapshot/resolve_engine`, the drift guard in `jobs/run.py`, the first-run skip, and the route override in the run adapter. Delete their tests (`test_eval_*`, `test_start_run_eval`, `test_engine_registry`). Prod `params` stay equal to today's.
Done when: the AC2 grep (`EVAL_MODE|eval_mode|is_eval|EvalRunInfo|EvalDisabled|eval_snapshot`) returns 0 in `api`; impacted run, first-run and start-run tests pass; the contract diff against the T0 sha is empty.

## Task 2 — Fakes out
What it is / what it means: Swap the test backend before touching the data code, so "test on the emulator" and "rewrite the transactions" are separate steps. PRD R4, D2, D3, D7, O2, O4.
What changes at a high level: `tests/conftest` and a new `tests/helpers/` run every data-touching test through the existing `FirestoreRepo` on the emulator, with a fresh project id per test and a clear "Needs emulator" message. Delete `FakeRepo`, the parity test, `[fake]` twin params and `FAKE_*` fixtures, `MemoryRateStore`, and the adapter fakes. Replace them with the R4 stubs: `LocalBlobStore` (slimmed `storage/fake.py` plus signed-URL routes), `InProcessQueue`, `RecordingSender`, fixture STT, fixture voice, and the engine `FixtureClient` from public `make_client` (stub mode runs the real engine). `[fail:*]` titles become one `stub_hint`, honoured only when `ADAPTERS=stub`. Move `StubTokenVerifier` (`test:<uid>`) into `tests/helpers/` and inject it via `create_app(token_verifier=)`. Delete `test_acceptance_checklist.py`. Add a test that boots the app with the PR-preview settings and runs a session to `report_ready`. Update the CI emulator job to start Firestore and Auth emulators.
Done when: AC1 fake-class grep returns 0 except names still to be removed in Task 3; the whole api suite passes on the emulator locally and in the `api-emulator` job; the PR-preview-settings test passes; the contract diff is empty.

## Task 3 — Constants and the data layer
What it is / what it means: Write the data logic once. `Db` plus five base functions with the owner check inside, one-line wrappers, and one place for names and paths. PRD R2, R2b, R3, D1, D8, T3.
What changes at a high level: Add `constants.py` (collection names, blob key templates, 300 MB / 1 s / 500 KB, 20 min fallback, state names, task kinds, retry/lease numbers, header names). Add `data/{store,paths,docs,models,blobs}.py`: `get_doc/set_doc/update_doc/create_doc/query/scan/in_transaction`, `paths.py` as the only path composer, the 42 single-doc wrappers in `docs.py`, the 500 KB inline-or-blob rule in `blobs.py`. Add the separately named ownerless functions (`get_unowned_doc`, `set_unowned_doc`, `update_unowned_doc`, `query_unowned`) for eval only. `uid` stays required in the owned functions. `FirestoreRepo` methods now delegate to the new layer so no caller changes. `test_repo_contract` and `test_firestore_cross_instance` run before this task and stay as the oracle; the former becomes emulator-only `tests/data/` tests.
Done when: `tests/data/` passes, including a foreign-uid `NotFoundError` test per collection, a `create_doc` conflict test, an `in_transaction` retry test, and a unit test that the ownerless functions skip the owner check; no caller changed; contract diff empty.

## Task 4 — `usage/`, `auth/`, `email/`
What it is / what it means: The three small features with few callers go first. PRD R1, R4, D5, T4.
What changes at a high level: `usage/{limits,charge}.py` (from `repo/limits.py`, `jobs/caps.py`, `jobs/charging.py`, usage txns). `auth/{verify,deps}.py`: `AUTH_MODE=emulator` replaces `fake`, using the verifier the owner chose in the phase-0 spike; `deps` holds `current_user`, API-key parse and the rotate txn. `email/{service,rate}.py` (service, rate limit, reset email, `RecordingSender`). `auth/` and `email/` take explicit settings and clients and do not import `routes/`, `sessions/` or `pipeline/`. Tests move to mirrored folders `tests/{usage,auth,email}/`; real emulator tokens are exercised in `tests/auth/`.
Done when: usage, auth and email tests pass at their new paths, with the auth tests using real emulator tokens; `auth/` and `email/` have at most 2 files each; contract diff empty.

## Task 5 — `audio/` and `transcription/`
What it is / what it means: Audio rules and the speech-to-text path, merged with the STT files 04 moved into `api/`. PRD R1, R2b, T5.
What changes at a high level: `audio/{rules,ffmpeg,validate}.py` (from `audio.py`, `audio_child.py`, `jobs/validate.py`, upload-limit rules). `transcription/{transcribe,providers,transcript}.py` (providers = Chirp, fixture, registry, select; transcript store and parsers; languages). `transcription/` is a leaf module: explicit settings and clients, no imports from `routes/`, `sessions/`, `pipeline/`. Byte literals now come from `constants.py`. Tests move to `tests/{audio,transcription}/`.
Done when: audio, validate, STT-provider and transcribe tests pass at new paths; the literals grep (300 MB, 500 KB, `uploads/`) no longer hits these folders; contract diff empty.

## Task 6 — `sessions/`
What it is / what it means: The audio-to-report session lifecycle gets one folder, with its transactions written once on top of `in_transaction`. PRD R1, R2, T6.
What changes at a high level: `sessions/{state,lifecycle,sweep}.py` from `jobs/machine.py`, `progress.py`, `stale.py`, `sweep.py`, `alive.py`, `delete.py` and the session txns (`cancel`, `fail_stale`, `transition`, `confirm_speaker`, `publish_report`, `discard_failed_upload`). The `FirestoreRepo` versions are the source of truth; business logic in `routes/sessions.py` (613 lines) moves here. Cross-user reads use `scan` only in sweeps. Session state names are defined once. Tests move to `tests/sessions/`.
Done when: session, cancel, delete, stale and sweep tests pass at new paths on the emulator; no src file in `sessions/` is over about 300 lines; contract diff empty.

## Task 7 — `pipeline/`, `tasks/`, app mode table
What it is / what it means: Evaluation runs and the task queue, plus the hand-registered 7 task kinds replaced by one table. PRD R1, R2b, D6, T7, hand-off 05.
What changes at a high level: `pipeline/{run,start,presets}.py` calling `Engine.load/run/check_input/protocol` only (the `start_run`/`start_first_run`/`retry_step` txns move here; `adapters/validated.py`, `coded_span.py`, `engines.py` are deleted). `tasks/{queue,runner,handlers,errors}.py` plus `tasks/routes.py`, with `handlers.py` as the task-kind to handler table and `InProcessQueue` shipped here; `claim_step`/`claim_run` in the runner. `app.py` becomes the factory with one mode table (mode to routers and handlers). Re-check `schemas/report.local.schema.json` against `Engine.output_schema()` and drop the copy if redundant. `tasks/` is a leaf module. Tests move to `tests/{pipeline,tasks}/`.
Done when: run, retry, first-run, claim and worker tests pass at new paths; an `InProcessQueue` test passes; stub-mode run uses the real engine with the fixture client; app mode-table tests pass; contract diff empty.

## Task 8 — `voice/` and `rating/`
What it is / what it means: Interviews and rating validation. PRD R1, O6, D10, T8.
What changes at a high level: `voice/{relay,providers,interviews}.py` (3 files; interview lifecycle and its sweep live in `interviews.py`, with 04's moved voice and scenarios). `rating/validate.py` builds its schema from `Engine.protocol()` at startup; no committed `rating.schema.json` is left in `api/`. Tests move to `tests/{voice,rating}/`.
Done when: voice, interview and rating tests pass at new paths; a test shows the rating schema comes from `Engine.protocol()`; `git ls-files api | grep rating.schema.json` is empty; `voice/` has at most 3 files; contract diff empty.

## Task 9 — Routes, `http.py`, `gen_contracts.py`, `dev.sh`, CI
What it is / what it means: Finish the HTTP layer and the local and CI tooling. PRD R1, R6, R8, R9, D9, D11, T9, hand-off 08.
What changes at a high level: `routes/<resource>.py` hold HTTP only; route path, method, `operation_id` and model names are explicit in decorators. `http.py` takes middleware, request id, body limit, client info and error handlers. `contracts.py`/`openapi.py` move to `api/tools/gen_contracts.py`, with the CI and README commands updated. `api/scripts/dev.sh` starts both emulators from one `FIREBASE_CONFIG` path variable and runs combined mode with `ADAPTERS=stub AUTH_MODE=emulator`; `--check` and `--quickstart` are kept, and `--quickstart` mints a token through the Auth emulator and runs the upload-to-`report_ready` flow. Config-file paths go through one `CONFIG_ROOT`. In `ci.yml`, the emulator job starts `--only firestore,auth`, the regeneration step uses the new tool, and the unit/emulator merge follows the owner's decision. Other `api-*` jobs stay; the coverage gate stays at 94.
Done when: `dev.sh --quickstart` passes with both emulators; `test_combined_integration` and the PR-preview-settings test pass; the CI regeneration diff is empty and `api/openapi.json` and `docs/contracts/public` are untouched against the T0 sha; `actionlint` passes on `ci.yml`.

## Task 10 — Final cleanup, regroup, engine-v1 tag
What it is / what it means: Remove everything transitional, prove the acceptance criteria, then hand off to eval (10). PRD T10, AC, R2b, hand-off 10.
What changes at a high level: Delete the empty `repo/ adapters/ storage/ jobs/` and every delegating shim. Final test regroup: `tests/` mirrors src, no `test_t*`, no task or spec ids in names, the root holds only app-level files and `conftest.py`. Add the import-graph test: `data/ auth/ tasks/ transcription/` import nothing from `routes/ sessions/ pipeline/`, and `routes/` and feature folders never import or call the ownerless functions. Update `api/README.md` (emulator prerequisites, `dev.sh`). Run the full gate in dev-ship and record before/after job times for the PR description. After 06 merges, re-run phase-0 spike 3 (uv resolves git-subdirectory deps with `workspace=true`) against the post-06 layout and report the result to the owner (no automatic fallback). Then create and push git tag `engine-v1` on the merge commit.
Done when: AC1-AC4 greps return 0 or hit only the named files; the import-graph and 04 boundary-guard tests pass; ruff clean; coverage at least 94; all `api-*` jobs green; the contract files are unchanged against the T0 sha; the spike 3 result is reported and tag `engine-v1` exists.

Owner-only: act on the Task 0 report (job-merge, verifier choice); read the Task 10 spike 3 result and decide any fallback. Install `firebase-tools` on dev machines to run the emulator tests locally.
