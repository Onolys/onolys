---
status: draft
summary: 11 tasks to rebuild the eval backend on the prod pipeline (shared sessions, RunDoc per cell, tick scheduler with provider cap/backoff/breaker, cancel, delete, view adapter, web Delete, CI)
date: 2026-11-25
---
# Tasks: SP05 Eval backend on the prod pipeline
Source of truth: docs/agent_files/session-report-ux-20261124-1738/05-eval-backend-on-prod-pipeline/PRD.md. All PRD open items are RESOLVED. Offline tests only (fake repo, blob store, queue, LLM, in-memory eval store); no deploy, no live LLM/STT. SP03 and SP04 land first. Each task: tests first, then code, one commit.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Prod-side additive hooks | - | todo |
| 2 | Eval config, services, auth wiring | 1 | todo |
| 3 | Session import and gold copy | 1, 2 | todo |
| 4 | Grouping doc and create/rerun | 2, 3 | todo |
| 5 | Tick scheduler core | 1, 4 | todo |
| 6 | Overload backoff, isolation, breaker | 5 | todo |
| 7 | Cancel rework | 5, 6 | todo |
| 8 | Delete flow | 4, 5 | todo |
| 9 | View adapter and read endpoints | 4, 5 | todo |
| 10 | Remove old eval engine | 5, 7, 8, 9 | todo |
| 11 | Web Delete and CI/image wiring | 8, 9, 10 | todo |

## Task 1 — Prod-side additive hooks
What it is / what it means: Small additive changes in the api package that eval needs, without changing prod behaviour (Decisions 1, 3, 6; R3, R8).
What changes at a high level: SessionDoc gets an optional `eval` block; repo (base, Firestore, fake) gets `get_runs` and `delete_run_data`; the transcript write in `routes/transcript.py` is extracted into one shared helper (pack + build + transition), the route keeps `maybe_start_first_run`.
Done when: api tests prove `get_runs` returns only requested ids and `delete_run_data` removes run + report + pointer on fake and Firestore-emulator repos; the extracted helper gives byte-identical TranscriptDocs to before; `eval` never appears in public session views or OpenAPI; existing api tests pass unchanged; no edit under `jobs/`.

## Task 2 — Eval config, services, auth wiring
What it is / what it means: Eval backend composes the api's own settings, blobs, repo and Cloud Tasks queue, and reuses prod login plus the allowlist (R1, R2, Decisions 2, 10, 16).
What changes at a high level: `EvalConfig` adds `DATASETS_BUCKET`, `EVAL_OWNER_UID`, `EVAL_MAX_PER_PROVIDER`=2, `EVAL_PROVIDER_FAIL_LIMIT`=5, `EVAL_OVERLOAD_MAX_WAIT_S`=300, `EVAL_INTERNAL_RETRIES`=1; drops `EVAL_BUCKET`. `EvalServices` builds api settings/blobs/repo/queue; startup refuses unless `eval_mode`; owner uid ensured. `pyproject.toml` and Dockerfile depend on `onolys-api`. `app.py`/`config.py` use the reused auth dependency (SP03 removed `eval/auth`).
Done when: tests cover config defaults/overrides, refusal when not eval mode, ensure_user once, allowlist accept/reject through the reused auth; `uv` workspace resolves.

## Task 3 — Session import and gold copy
What it is / what it means: A dataset session or ready upload becomes one shared prod session, created once (R3, Decision 1, 8).
What changes at a high level: new `eval_sessions.py` with `canonical_sha256`, `ensure_session(source) -> sid` (fingerprint[:32], `ConflictError` = reuse), creation of SessionDoc (`n_runs=1`, eval block) and TranscriptDoc via the Task 1 helper, validation as today, gold copied to `gold/<sha256>.json`.
Done when: tests show same inputs give same sid and one doc; changed goal/span/transcript gives a new sid; hash bytes equal the old `_hash` and `transcript_sha256`; gold copied once and validated; upload prefix is not used for gold; race (double create) is a no-op.

## Task 4 — Grouping doc and create/rerun
What it is / what it means: `eval_runs/{id}` becomes the single rollup record; create makes no RunDocs (R4, R5, R9 rerun, Decision 4).
What changes at a high level: new in-memory + Firestore eval-runs store with the PRD doc shape (refs embedded, no units subcollection); `POST /v1/runs` validates selection, resolves combos, ensures sessions, writes the doc, enqueues tick 1; rerun reuses pinned sids after checking transcript sha and the `resolved_combos` drift rule; Human counted complete at creation.
Done when: tests cover create/rerun response shape unchanged, human auto-add, rerun with missing/changed session refused, and a worst-case serialized doc (499 units x 8 attempts) under 1 MiB.

## Task 5 — Tick scheduler core
What it is / what it means: Server-driven scheduling so eval completes with the browser closed (R6, Decisions 3, 9, 11, 12).
What changes at a high level: new `eval_scheduler.py` and `POST /internal/tasks/tick`: enqueue next tick first, fold terminal RunDocs, fill free sessions in order (one active run per session), transactional `eval_slots/{provider}` claim with cap, deterministic run ids, drift check, `create_run(is_eval=True)`, `internal_error` single retry, other codes stay failed, rollup and stop; stale-tick re-enqueue from `GET`; slot crash recovery.
Done when: fake-queue/LLM tests: 3 sessions x 2 combos x 2 repeats never two active per session, all 12 cells terminal; two concurrent eval runs on two providers never exceed the cap and a changed cap changes behaviour; crash between create and record leaves no duplicate or leaked slot; `internal_error` gets exactly one new attempt; `code_version`/`deadline_exceeded` failures not retried; no GET needed to finish; `not_ready` retried next tick.

## Task 6 — Overload backoff, isolation, breaker
What it is / what it means: Provider-level resilience on top of the scheduler (R6a-R6d, Decisions 5, 13, 14, 15).
What changes at a high level: `upstream_unavailable`/`rate_limited` cells go `waiting`, retried after 15 s doubling with jitter within the 300 s budget via a per-provider cooldown on the slots doc; per-cell try/except with `scheduler_error` after 3 handler errors; per-eval-run consecutive-failure breaker that marks remaining cells `skipped` (`provider_unavailable`) and yields `partial`. No change under `engines/` or `jobs/`.
Done when: fake-clock tests show cooldown blocks only that provider, success clears it, exhausted budget becomes failed and counts; one raising cell leaves others progressing and the run terminal; breaker (limit 2 in test) skips only that provider, success resets, cancelled cells neither count nor reset, in-flight runs kept, other eval runs unaffected; diff gate confirms no edits under `engines/` or `jobs/`.

## Task 7 — Cancel rework
What it is / what it means: Cancel stops new runs only, keeps completed work, no prod worker edit (R7, Decision 6).
What changes at a high level: `POST /v1/runs/{id}/cancel` sets `cancel_requested` and `cancelled_at`, marks unstarted and `waiting` cells `cancelled`, leaves in-flight runs to finish, stays `running` until they end, then `partial` (some done) or `cancelled`; idempotent; terminal and unknown ids handled.
Done when: tests prove no new run after request, in-flight kept, final status rules, second cancel and cancel-on-terminal are 200 no-ops, unknown id 404, slots free as runs end, delete refused until terminal, skipped cells stay skipped.

## Task 8 — Delete flow
What it is / what it means: Remove exactly one eval run's data, resumably (R8, Decision 7).
What changes at a high level: new `eval_delete.py`; `POST /v1/runs/{id}/delete {confirm_run_id}` refused 409 `run_active` unless terminal, sets `deleting`, 202, enqueues `delete` task; handler deletes outputs, reports and blob pointers, RunDocs, then the group doc last; failure keeps `deleting` + `delete_error`; releases slots; audit log line with email hash.
Done when: tests prove refusal while active, mismatched confirm id rejected, full removal of runs/reports/blobs/`runs/<id>/` files and group doc, a second eval run on the same sessions untouched, sessions/transcripts/gold remain, kill-mid-way then retry completes, History shows `deleting`.

## Task 9 — View adapter and read endpoints
What it is / what it means: Existing eval screens keep working on the new data (R10, R11, Decision 9).
What changes at a high level: new `eval_view.py` builds legacy-shaped units from RunDocs/ReportDocs/gold, computes legacy compare scores on read, exposes `list_cells`, `load_report`, `load_gold` for SP06; `read_runs.py` serves list/detail/output with new fields (`cancelled_at`, `skipped_units`, `provider_skips`, `provider_cooldowns`, `waiting`/`skipped` statuses, `run_id`, `attempt`).
Done when: rewritten read tests show response shapes, output fetched from ReportDoc or gold, legacy `build_compare` output unchanged for a fixture, final-attempt selection with earlier failures listed, live then final status visible with no earlier GET.

## Task 10 — Remove old eval engine
What it is / what it means: Delete the duplicated eval-only pipeline (R9, Problem table).
What changes at a high level: remove `_inputs`, `_validate_sources`, `_hash`, `execute_unit`/`finish_unit`/`unit_task`, lease and retry constants, unit repository methods, `store_output`/`load_output`, per-run input copies, `services.engine`, queue kind `unit` and the `unit` task route. Keep uploads, `transcribe`, `Bucket`, `_git_sha`, drift helpers.
Done when: grep gate shows no remaining importers of removed names; `eval/core` CLI `_inputs` untouched; old unit tests rewritten or removed; kept suites (matrix, catalog, uploads, signed upload, app) pass; prod api tests pass.

## Task 11 — Web Delete and CI/image wiring
What it is / what it means: Minimal UI for delete, and CI that covers the changed packages (R12, R13).
What changes at a high level: `eval/web` `api.ts` `deleteRun` and `deleting` status; `Runs.tsx` Delete item (terminal only) with count-stating confirm dialog; existing Cancel button works. CI: eval-backend job now depends on `api`, so `scripts/ci/changes.sh` deps and `test_changes*` need `api` for eval-backend; `test_eval_image.sh` must stop asserting `onolys_api` absent and `onolys_admin_auth`, and the image build copies `api/src`.
Done when: vitest covers Delete enablement, confirm text and `deleting` label, other `NewRun`/`Runs` tests unchanged; `eval-backend`, `eval-web` and `api` CI jobs trigger on the relevant paths (changes-script tests updated and passing); typecheck and lint pass.

## Owner steps (not tasks)
- Terraform plan/apply and deploy (SP03); first live eval (one small run end to end) in the `eval` environment.
- Set spend limits in Anthropic Console and Google Cloud console.
- Review copied allowlist emails (SP03); confirm SP03 env: `DATASETS_BUCKET`, `EVAL_MAX_PER_PROVIDER`, `EVAL_OWNER_UID`, api platform env, Speech agent read grant on `eval-uploads/`.
