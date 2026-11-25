---
status: draft
summary: Rebuild the eval backend on the prod pipeline: dataset/upload sessions become shared prod sessions (deterministic id, created once), each combo x repeat is a prod RunDoc started by a small tick scheduler (one active run per session), an `eval_runs` grouping doc rolls up status, delete removes only an eval run's runs/reports/outputs, and the eval-only run engine (units, leases, queue, per-run copies) is deleted. Existing eval web screens keep working.
date: 2026-11-25
---
# PRD: SP05 Eval backend on the prod pipeline

Repo/branch: Onolys/iaudit / `session-report-ux` · Depends on: SP04 (`is_eval` run path), SP03 (env, deploy config) · Owns: `eval/backend/src/onolys_eval_backend/{app,config,services,runs,read_runs,repository,storage,queue,catalog,uploads}.py` + new `eval_sessions.py`, `eval_scheduler.py`, `eval_delete.py`, `eval_view.py`; `eval/backend/{pyproject.toml,Dockerfile,tests}`; `eval/web/src/{api.ts,Runs.tsx,Root.tsx}` (history delete only); additive `api/src/onolys_api/repo/{models,base,firestore,fake}.py` (SessionDoc `eval` block, `get_runs`, `delete_run_data`) and a `routes/transcript.py` helper extraction · SP06 reads this SP's listing; SP07 owns compare screens.

## TL;DR
Eval stops being a second pipeline. A dataset session or upload is imported once as a prod `SessionDoc` + `TranscriptDoc` (id derived from a content fingerprint, so re-import is a no-op). Each combo x repeat is one prod `RunDoc` (via SP04's `create_run(is_eval=True)`) run by the one prod worker. A `tick` task per eval run creates the next run per session when the previous one finishes (never two active on a session), caps sessions in flight, retries failed runs as new RunDocs, and rolls status up on an `eval_runs` doc. Deleting an eval run deletes exactly its RunDocs, ReportDocs, report blobs and run output files; sessions, transcripts, datasets and gold stay. The eval web keeps working through a view adapter; only a Delete action is added.

## Problem
| Gap | Evidence |
|---|---|
| Input validation/snapshot re-implemented | `_inputs`/`_validate_sources` [verified: `runs.py:191-246`] vs prod [verified: `routes/transcript.py:_persist`, `models.py:278 TranscriptDoc.build`] |
| Second hash of the same canonical JSON | [verified: `runs.py:137 _hash`; `models.py:267 transcript_sha256`] |
| Own claim/lease/retry/execution, calls `run_validated` itself | [verified: `runs.py:622-790 execute_unit`, `MAX_ATTEMPTS`, `LEASE_S`] |
| Second run store and output store | [verified: `repository.py` `eval_runs/{id}/units`; `storage.py store_output`, `runs/<run>/<unit>.json`, `runs.py:340-348` per-run input copies] |
| Own queue + dispatch to itself | [verified: `queue.py` kinds `unit|transcribe`; `services.py:queue`] |
| Eval holds no delete at all; data is kept forever | [verified: no delete route in `runs.py`/`read_runs.py`; `Bucket.delete` used only for upload candidates] |
| A shared session cannot use prod cancel: it is terminal | [verified: `firestore.py:1065` sets `state=cancelled`; `start_run` refuses non-`allowed_states`] |

## Goals / Non-Goals
**Goals:** one session per (dataset, session, inputs) shared by all eval runs; one RunDoc per cell; decision-9 scheduling; decision-8 deletion; remove duplication items 1-7; existing eval features keep working; offline tests.
**Non-goals:** compare maths (SP06), compare screens (SP07), `is_eval` itself (SP04), Terraform (SP03), prod behaviour change, migration (data already deleted), per-user data separation, session garbage collection, replacing eval's own audio-upload STT flow.

## Requirements
**R1 Config and composition.** `EvalServices` builds the api's own `Settings.from_env`, `build_blobs` (`AUDIO_BUCKET` = `onolys-audio-eval`), `build_repo` (db from `FIRESTORE_DATABASE`), and api `CloudTasksQueue` (run tasks go to `WORKER_URL/tasks/run`) [verified: `factory.py`, `jobs/queue.py`]. `EvalConfig` keeps allowlist auth and adds `DATASETS_BUCKET` (read-only), `EVAL_OWNER_UID` (default `eval`), `EVAL_MAX_SESSIONS_IN_FLIGHT` (default 20). `EVAL_BUCKET` is removed. `eval/backend` depends on `onolys-api` (workspace); Dockerfile copies `api/src`. Startup refuses unless `settings.eval_mode`.
**R2 Owner uid.** Every allowlisted user acts as ONE eval owner uid (`EVAL_OWNER_UID`), ensured with `repo.ensure_user`. Real identity stays in `eval_runs.created_by` (email, as today [verified: `runs.py:create_run created_by`]).
**R3 Session import (`eval_sessions.py`).** `ensure_session(source) -> sid`. Source = dataset session (read from datasets bucket, validated by `validate_transcript_input` as today) or a ready upload. `fingerprint = sha256(canonical json {dataset_id|null, dataset_session_id|upload_id, transcript_sha256, change_goal, language, coded_span, clinician_speaker})`; `sid = fingerprint[:32]` (matches `ResourceId` shape). Idempotent: `repo.create_session` raising `ConflictError` means reuse [verified: `firestore.py:223-237`]. A changed dataset (new transcript/goal/span) yields a new session; old runs keep pointing at the old one. Created doc: `state=awaiting_input`, `transcript_ready=speaker_confirmed=True`, `clinician_speaker`, `change_goal`, `language`, `coded_span`, `preset` = eval `DEFAULT_PRESET`, `n_runs=1`, `title`, plus `eval: EvalSessionInfo {dataset_id|None, dataset_session_id, source, gold: {sha256, path}|None}`. The transcript is written through ONE helper extracted from `routes/transcript.py:_persist` (`large.pack` + `TranscriptDoc.build` + `transition_session`), shared with the public route; the route keeps `maybe_start_first_run` (a no-op in eval mode per SP04 R6). `TranscriptDoc` gets no eval fields. Gold is copied once to `gold/<sha256>.json` in the eval bucket (content-addressed, never under `uploads/`: that prefix auto-deletes after 1 day [verified: `modules/environment/main.tf` `lifecycle_rule`]); existing gold validation (`validate_gold`) runs at import.
**R4 Grouping doc.** `eval_runs/{eval_run_id}` (Firestore, eval db): `name`, `description`, `input`, `created_by`, `created_at`, `status` (`queued|running|done|partial|failed|cancelled|deleting`), `cancel_requested`, `engines`, `selection`, `combos`, `repeats`, `base_preset`, `saved_config {base_preset, resolved_combos}`, `engine_versions`, `engine_git_sha`, `human` (bool), counters under their current names (`total_units`, `completed_units`, `done_units`, `failed_units`, `cancelled_units`, `usage`, `cost_usd_est`, `unpriced_units`, human units counted complete at creation, as today), `tick_seq`, `last_tick_at`, and `sessions: {sid: {dataset_session_id, order, cursor, active_run_id, state, runs: [{run_id, combo_key, repeat, attempt, status}]}}`. Bounded by `MAX_UNITS=499` x (1+retries) refs, well under the 1 MiB doc limit [verified: `matrix.py:MAX_UNITS`]. No `units` subcollection. Per-session plan order = `plan_units` order (combo-major, repeat-minor), same for every session.
**R5 Create.** `POST /v1/runs` (same request/response) validates selection (`validate_selection`, `plan_units`, unchanged), resolves `resolved_combos`, ensures sessions (R3), writes the group doc, enqueues `tick`. No RunDoc is created at this point. Human is auto-added for datasets whose sessions all have gold (kept) and is never a run: it is gold by sha.
**R6 Scheduler (`eval_scheduler.py`, `POST /internal/tasks/tick`).** Cloud Task `{eval_run_id}-tick-{n}`; handler is a no-op unless `n == tick_seq`. Each tick, in this order: (1) enqueue tick `n+1` (delay ~10 s) BEFORE any work, as prod's transcribe poll does, so a crash cannot end the chain [verified: `jobs/transcribe.py` docstring]; (2) for every session with `active_run_id`, `repo.get_runs` and fold terminal RunDocs into the doc (`status`, usage, cost via `PriceBook` on `run_info.usage`); (3) failed RunDoc with a retryable `kind_for_code(error)` OR `run.code_version != settings.git_sha` (deploy drift) and attempts left (default 2 retries) -> new run for the same cell after backoff (5 s / 20 s); else cell `failed`; (4) fill free slots: sessions without an active run, in `order`, up to `EVAL_MAX_SESSIONS_IN_FLIGHT`, take the next cell, recompute `resolved_route` and compare with `saved_config.resolved_combos[combo_key]` (mismatch -> cell `failed: execution_config_changed`, today's drift rule), then `create_run(is_eval=True, eval_spec, run_id=<deterministic>)`; (5) all cells terminal -> roll up status and stop re-enqueueing. Deterministic `run_id = sha256(eval_run_id|sid|combo_key|repeat|attempt)[:32]`, so a crash between creation and recording is recovered (`ConflictError` = already created). `create_run` returning `not_ready` (session busy, e.g. another eval run is using the same session) = skip this tick, retry next; SP04's allowed states make the repo itself refuse a second active run on a session (defence in depth for decision 9) [verified: `firestore.py:1202`]. `GET /v1/runs/{id}` re-enqueues a tick (`-r<epoch>` name) when `last_tick_at` is stale while active, as uploads do for transcribe [verified: `uploads.py:468-479`].
**R7 Cancel.** `POST /v1/runs/{id}/cancel`: set `cancel_requested`; tick stops creating runs and marks not-yet-started cells `cancelled`; in-flight RunDocs finish normally (no provider cancel, same as today [verified: `runs.py:cancel_run` comment]); status rolls up when they end. Prod session cancel is never used (terminal, would block shared sessions).
**R8 Delete.** `POST /v1/runs/{id}/delete {confirm_run_id}` (POST keeps CORS methods unchanged [verified: `app.py` `allow_methods`]); `confirm_run_id` must equal the path id. Allowlisted user only (existing middleware). Refused 409 `run_active` unless status is terminal (`done|partial|failed|cancelled`): cancel first, wait, then delete. Accepted: set `status=deleting` (hidden from tick, shown in History as `deleting`), return 202, enqueue `delete` task `{id}-delete-{n}`. Handler is idempotent and resumable; for every ref in the group doc (all attempts): (1) delete outputs under `{uid}/{sid}/runs/{run_id}/`, (2) delete ReportDoc and its blob pointer, (3) delete RunDoc (`repo.delete_run_data`), and last (4) delete the group doc, so a retry always still has the refs. Failure at any step leaves `deleting` + `delete_error` code, task retries with a new name; the same POST again is a safe retry. Never deleted: sessions, TranscriptDocs, transcript blobs, datasets, `gold/*`, other eval runs' RunDocs (refs list only this run's ids; shared-session test below). No session field is repaired: report versions are `max+1` over existing reports so gaps are harmless [verified: `firestore.py:333-336,376`], eval reads reports by run id, and all runs of the deleted group are terminal so no session is left `running`. History shows `deleting` until the group doc is gone, then the row disappears; detail returns 404.
**R9 Removals (each grep-backed).** Delete: `_inputs`, `_validate_sources` (callers: `create_run`, rerun only [verified: grep `runs.py`]); `_hash` (5 refs, all `runs.py`); `execute_unit`, `finish_unit`, `unit_task`, `_ExecutionConfigChanged`, `is_retryable` loops, lease constants (callers: `runs.py`, `test_runs.py`, `test_persistence.py`); `FirestoreEvalRepository/InMemoryEvalRepository` unit methods `create_run(units)`, `get_unit`, `list_units`, `update_unit`, `transact_unit` (callers: `runs.py`, `read_runs.py` and tests only); `storage.store_output/load_output`, `runs/<run>/` paths; per-run `inputs/<session>/` copies; `services.engine/_bound_engines` (moved to api `engines.py` by SP04); `queue.py` kind `unit` and the `unit` Cloud Task. Keep: `queue.py` for `tick`, `delete`, `transcribe`; `eval_uploads` collection and uploads routes; `Bucket` adapter; `_git_sha`; `_routes_for/_combo_snapshot` (drift rule, R6). `eval/core/src/onolys_eval/run.py` has its own `_inputs` (CLI runner) and is untouched [verified: grep]. Rerun keeps `saved_config.base_preset` and the `resolved_combos` equality rule (live `models.yaml` can drift; no session pins it) and drops input snapshot-equality: rerun reuses the pinned prod `sid`s from the group doc (immutable, so bytes are preserved for free) after checking each still exists with the same `transcript_sha256`.
**R10 Read endpoints (shape).** See table. `eval_view.py` builds legacy-shaped unit dicts from RunDocs/ReportDocs/gold so `build_compare` and the web keep working until SP06 replaces it; scores for the legacy compare are computed on read (`miti_lean_scores`/`oneshot_scores`/`gold_scores`) instead of being stored.
**R11 Listing for SP06.** `eval_view.list_cells(eval_run_id) -> list[Cell]`, `Cell = {sid, dataset_session_id, combo_key, repeat, attempt, run_id, status, started, ended, error, run_info(usage, cost_usd_est), gold_ref}`, ordered session -> plan -> attempt, plus `load_report(cell)` and `load_gold(sid)`. Final attempt per (sid, combo_key, repeat) is the highest `attempt`; earlier failed attempts stay listed (time footnote).
**R12 Web (minimal).** `api.ts`: `deleteRun(id)`, `RunStatus` adds `deleting`. `Runs.tsx`: "Delete" item in `RunActions` (disabled unless terminal) + confirm dialog stating counts ("N runs, N reports, N output files; datasets, gold and sessions stay"), `deleting` label. Compare views untouched.
**R13 Tests (offline).** Fake repo (`FakeRepo`), `FakeBlobStore`, `InMemoryQueue`, fake LLM factory, in-memory eval-runs store; no keys, no live runs. Existing `test_runs/test_persistence/test_read_runs/test_run_configuration` are rewritten against the new store; `test_matrix/test_catalog/test_uploads*/test_signed_upload/test_app` stay (paths and config only).

## Architecture
```
eval web --(allowlist)--> eval-backend: POST /v1/runs
   ensure_session x N --> SessionDoc+TranscriptDoc (sid=fingerprint), gold/<sha>.json
   eval_runs/{id} (grouping) ; enqueue tick
tick (self re-enqueue ~10s) --> create_run(is_eval=True, run_id=det) --> start_run txn --> Cloud Task run
                                  one active run per session, <= N sessions in flight
prod worker (same image/handler) --> RunDoc + ReportDoc + {uid}/{sid}/runs/{run_id}/*
eval-backend read --> group doc (progress) ; RunDocs/ReportDocs/gold (detail, compare)
```
Endpoint shapes:
| Endpoint | Shape change |
|---|---|
| `POST /v1/runs`, `/cancel`, `/rerun` | none (body and reply same); rerun now reuses pinned sids |
| `GET /v1/runs` | same fields from group doc; `status` may be `deleting` |
| `GET /v1/runs/{id}` | `units[]`: `unit_id` = run id (human: `human-<sid>`), `session_id` still the dataset session id, new `run_id`, `prod_session_id`, `attempt`; `output` never inline (web already fetches when absent [verified: `Runs.tsx` `UnitOutput`]); `compare` same shape via legacy builder until SP06 |
| `GET /v1/runs/{id}/units/{unit}/output` | same; source is ReportDoc (or gold) |
| `/v1/options`, `/v1/datasets*`, `/v1/uploads*`, `/v1/me`, `/healthz` | none (uploads move from `uploads/` to `eval-uploads/` prefix) |
| `POST /v1/runs/{id}/delete` | new |
| `/internal/tasks/unit` | removed; `tick`, `delete` added; `transcribe` kept |

Worked example: 12 sessions x 6 combos x 3 repeats = 216 RunDocs; 12 sessions in flight (<= 20), each runs its 18 runs in order; a thirteenth session would start as one finishes.

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| 1 | Session identity | `sid = fingerprint[:32]`, create-or-reuse | Firestore query by `(dataset_id, session_id)` | No index, race-free via exclusive create, pins transcript+goal+span so changed data never reuses a stale session |
| 2 | Owner uid | One shared eval uid | Uid per allowlisted email | Sessions are shared across users and runs; history is already global |
| 3 | Scheduler | Self-re-enqueued `tick` Cloud Task in eval-backend | Hook in prod worker; Cloud Scheduler sweep | No prod worker change; same pattern as eval's transcribe poll; no new infra |
| 4 | Refs location | Embedded in group doc | `units` subcollection | Item 4 removal; size bounded |
| 5 | Retry | New RunDoc per attempt, <=2 retries, transient or drift only | Eval-side in-unit loop | Prod worker already retries delivery; SP04 asks SP05 to re-create failed runs |
| 6 | Cancel | Stop creating, let in-flight finish | Prod session cancel | Prod cancel is terminal on the shared session |
| 7 | Delete | Refuse while active, ordered idempotent steps, group doc last | Auto-cancel then delete; delete session too | Late worker writes would orphan blobs; sessions are shared |
| 8 | Gold | Copy to `gold/<sha256>.json` at import | Read datasets bucket at compare time | Decision 7; immune to dataset edits; one read path |
| 9 | Compare bridge | View adapter feeds legacy `build_compare` | Drop compare until SP06 | Existing screens keep working |
| 10 | Image | Separate eval-backend image that imports `onolys_api` | Add an eval `SERVICE_MODE` to the api image | Keeps public app free of eval routes; resolves SP03's open point |

## Manual steps
- Owner: after deploy, verify one small run end to end in staging eval, then approve SP03 R9 Step B (legacy removal).
- Owner: seed/confirm `admin-allowed-emails-eval`; no data migration (already deleted 2026-11-24).
- SP03 must add env `DATASETS_BUCKET`, `EVAL_MAX_SESSIONS_IN_FLIGHT`, `EVAL_OWNER_UID`, the api platform env for eval-backend, and read grant for the Speech service agent on `eval-uploads/` of `onolys-audio-eval`.

## Risks / Open Questions
- [OPEN] `create_run` takes `app` and mints its own `run_id` (SP04 R2). Need: optional `run_id` param and a deps object eval can build. Default: SP05 makes that one additive edit to `routes/runs.py` and passes a `SimpleNamespace(state=...)`; fallback without it: tick recovers orphans by scanning `list_runs(uid,sid)` for `eval.eval_run_id/combo_key/repeat`.
- [OPEN] Who may delete an eval run. Default: any allowlisted user (the allowlist is the trust boundary), typed confirmation in the UI, audit log line with email hash. Alternative: creator only.
- [OPEN] Tick shares queue `steps-eval` with run tasks, so ticks can wait behind 20 long runs. Default: share; revisit if lag is seen. Alternative: a small separate queue (SP03).
- [OPEN] Two eval runs on the same dataset session at once interleave (slower, correct). Default: allow. Alternative: 409 at create.
- [OPEN] Retry budget. Default: 2 retries, backoff 5 s/20 s, only transient kinds or `code_version` drift.
- [OPEN] Replace eval's own audio-upload STT (`transcribe` task, ~600 lines) with the prod validate/transcribe steps. Default: no, keep as is for this SP.
- [OPEN] `EVAL_MAX_SESSIONS_IN_FLIGHT` default. Default: 20, matching SP03's `2 x 10` dispatches.
- [RESOLVED: SP05] No eval fields on `TranscriptDoc` (SP04 mentioned both); the session carries them.
- [DEFERRED] Garbage collection of sessions no run references; a "delete dataset session" tool.
- [DEFERRED] Compare computed server side from RunDocs (SP06); screens (SP07).
- Risk: `repo.get_runs`/`delete_run_data` and the SessionDoc block touch files SP04 also edits (additive, different classes). Land SP04 first.
- Risk: drift guard fails in-flight runs on every deploy; tick re-creates them as new attempts (R6.3).

## Acceptance Criteria
- Import: same inputs -> same `sid`, one SessionDoc/TranscriptDoc, gold copied once; changed goal/span/transcript -> new `sid`; no `eval` field leaks into public session views or OpenAPI.
- Scheduler (fake queue/LLM): 3 sessions x 2 combos x 2 repeats never has two active RunDocs on a session; sessions in flight <= cap; all 12 cells reach terminal; a crash between create and record yields no duplicate; failed-transient and drifted runs get a new attempt, others stay failed; cancel leaves in-flight to finish and cancels the rest.
- Delete: refused while active; after delete, that eval run's RunDocs, ReportDocs, report blobs and `runs/<id>/` files are gone and the group doc is gone; a second eval run on the same sessions keeps everything, and the sessions/transcripts/gold remain; killing the handler mid-way then retrying completes; History shows `deleting` then no row.
- Existing: name/description, saved_config rerun prefill, history search/filter/sort, config modal, unit progress, cost estimate, uploads, datasets catalog and once-per-session Human all pass their (rewritten) tests; `NewRun`/`Runs` vitest unchanged except Delete.
- Removed names (R9) have no remaining importers (grep gate); prod `api` tests untouched and passing.
- All tests offline.
