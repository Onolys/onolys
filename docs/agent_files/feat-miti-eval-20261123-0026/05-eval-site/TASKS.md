---
status: draft
summary: SP5 eval site - eval/backend service (options, uploads, run units via Cloud Tasks, compare), eval/web SPA, infra + terraform apply, CI, deploy-eval workflow, docs
date: 2026-11-23
---
# Tasks: SP5 Eval site (eval.onolys.com)

Source of truth: /root/projects/onolys/iaudit/.worktrees/feat/miti-eval/docs/agent_files/feat-miti-eval-20261123-0026/05-eval-site/PRD.md. Runs last, after SP1-SP4 have landed. Staging only. One commit per task. Tests are written first in every task. DNS for eval.onolys.com is an owner task and does not block anything here.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Backend skeleton, auth, config, workspace member | - | done |
| 2 | Storage layer: bucket, Firestore, prices | 1 | done |
| 3 | Options and datasets endpoints | 2 | done |
| 4 | Uploads, speaker pick, transcribe poll-chain | 2 | done |
| 5 | Run creation, unit execution, finalisation | 3, 4 | done |
| 6 | Compare, history, rerun, tokens and $ | 5 | done |
| 7 | Infra: Terraform for eval and staging apply | 1 | done |
| 8 | Web app: shell, auth, New run | 1 | done |
| 9 | Web app: progress, compare, history | 6, 8 | done |
| 10 | CI jobs for eval backend and web | 6, 9 | in-progress |
| 11 | Deploy workflow and image guard | 7, 10 | todo |
| 12 | Live smoke, docs, reference page | 11 | todo |

## Task 1 — Backend skeleton, auth, config, workspace member
What it is / what it means: The empty but secure shell of the eval service: a new uv workspace member that only allowlisted founders can call. (R3, R9, D2)
What changes at a high level: Create `eval/backend` as a uv member, with an app factory mirroring the admin backend (CORS outermost, then `AdminAuthMiddleware`, `/v1/me`, health). Config from env: bucket, queue, service URL, prod engine, default preset, routes file. `ADMIN_AUTH` fixed on; empty allowlist fails startup. Internal task routes are exempt from allowlist auth and checked by Cloud Tasks OIDC instead. Lock regenerated once.
Done when: Tests first: anonymous `/v1/me` = 401, non-allowlisted = 403, allowlisted = 200, empty allowlist fails startup, internal route rejects a missing or wrong OIDC token, a test asserts eval imports nothing from the API limits module (AC6).

## Task 2 — Storage layer: bucket, Firestore, prices
What it is / what it means: One place that talks to the bucket and Firestore, so the rest of the code works against fakes in tests. (R7, R8, D4)
What changes at a high level: Bucket access for datasets, uploads and run outputs (SP2 layout). Firestore access for `eval_uploads`, `eval_runs` and `units` with the fields in R7, inline output up to 500 KB else a bucket ref. Add the `eval_runs(created_at desc)` index entry and a comment-only note in `firestore.rules`. Add the hand-kept `prices.yaml` and the cost helper (use `cost_usd` when set, else tokens x price, labelled estimate).
Done when: Fake-backed tests: round-trip of runs and units, large output spills to bucket, cost helper picks `cost_usd` first and falls back to prices, rules file still denies client access.

## Task 3 — Options and datasets endpoints
What it is / what it means: What the New run screen's dropdowns and dataset picker read. (R2, R3, D4)
What changes at a high level: `GET /v1/options` builds the engine list (Human, MITI lean, registry variants, including one-shot registered in eval/backend only) and presets (`list_presets` minus `test-*`), with "(prod)" flags from `PROD_ENGINE` and `DEFAULT_PRESET` config, never hardcoded, plus per-mode defaults. `GET /datasets` and `/datasets/{id}` read manifests from the bucket.
Done when: Tests first: prod flags follow config, `test-*` presets hidden, Human is a pseudo-engine (D7) and listed for uploads only when a gold file is attached, defaults per mode, dataset list and detail from a fake bucket.

## Task 4 — Uploads, speaker pick, transcribe poll-chain
What it is / what it means: Get a single transcript or audio file into a runnable state, keeping it for reruns. (R4, D5)
What changes at a high level: `POST /uploads` validates size and type, parses `.json` and `.txt` with SP1 parsers and gold against `gold.v1`, stores under `uploads/<id>/` and records it. Audio: a transcribe task starts STT with the prod parameters, re-enqueues 15 s poll tasks, and saves the result as `transcript.v1`. When roles are unknown, state becomes `awaiting_speakers` and `POST /uploads/{id}/speakers` applies the clinician pick via the core speaker helper.
Done when: Tests first with fakes: oversize, wrong type and bad gold rejected; `.json`/`.txt` accepted; audio chain start, poll until done, writes transcript; unknown roles hold in `awaiting_speakers` until picked.

## Task 5 — Run creation, unit execution, finalisation
What it is / what it means: The core of the site: turn a request into units and execute them in the background so runs survive a closed tab. (R5, D3, D8)
What changes at a high level: `POST /runs` expands session x engine x preset x repeat (Human = one unit per session), writes run and units, enqueues one Cloud Task per unit. The unit handler builds `RunContext`, resolves the engine from the registry and the preset through core routes, passes variant config, calls `run_validated`, adapts to `Scores` via `onolys_eval.adapters`, stores result and usage. State changes are idempotent; the last unit finishes the run (`done`, `partial` or `failed`) via a counter transaction; cancel makes pending units no-op. Run input is resolved to the coded span (dataset manifest, upload override, gold-span warning for Human).
Done when: Tests first: unit counts (including Human single, 2x2x3), redelivered task exits 200 without rerun, cancel, last-unit finalisation with failed units, lean-MITI invalid output fails the unit directly while one-shot retries (D2), tasks enqueued with the expected OIDC target.

## Task 6 — Compare, history, rerun, tokens and $
What it is / what it means: Read-side of runs: the compare payload, history list and rerun. (R3, R6, R8, D9)
What changes at a high level: `GET /runs`, `GET /runs/{id}` return status, units and a compare block computed on read with `onolys_eval.metrics.compare/aggregate` on the common subset (counts, globals, summaries recomputed from counts). Repeats give mean and min-max; failed units are shown and excluded from MAE with n; no Human means no error columns. Run totals carry tokens and "~$". `POST /runs/{id}/rerun` creates a new run on the saved input with different engines and presets.
Done when: Tests first: compare output equals `onolys_eval.metrics` on the same fixture data (AC2), with and without Human, repeats range, failed-unit exclusion, history stores engine versions, git sha and resolved preset-to-model map (AC5), rerun reuses saved input.

## Task 7 — Infra: Terraform for eval and staging apply
What it is / what it means: All cloud resources for the site, staging only, behind an `eval_enabled` flag. (R10)
What changes at a high level: Hosting site and custom domain for `eval.onolys.com`, authorized domains in Identity Platform, Cloud Run `onolys-eval-backend-staging` with its own service account, sizing and env/secrets per R10, Cloud Tasks queue (4 concurrent, 2 retries, 900 s deadline) with enqueuer and invoker roles, bucket IAM on the SP2 bucket including the conditional STT-agent read on `uploads/`, Firestore and Speech roles, CORS origins, deployer SA entries. Reuse the `admin_staging` web app config. Agent runs `terraform apply` for staging with ADC creds; if credentials or a gcloud binary are missing, record BLOCKED.
Done when: `terraform validate` and `plan` clean after apply, or BLOCKED recorded. Speech and Vertex roles verified against the worker SA at apply; the bucket denies anonymous reads (AC7).

## Task 8 — Web app: shell, auth, New run
What it is / what it means: The browser app and its first screen, where a founder picks what to run. (R1, R2, D1, D6)
What changes at a high level: Create `eval/web` (Vite + React + TS like `web/`). Copy the Firebase sign-in, AuthGate and `authFetch` modules from the admin frontend. New run screen: dataset and upload modes, engine and preset multi-selects with "(prod)" labels and per-mode defaults, runs per cell 1 or 3, change goal and language, optional gold and span override, speaker-pick step, planned unit count before Start.
Done when: Tests first: auth gate (anonymous, "Not allowed", allowed), dropdown defaults per mode, Human only with gold, planned-count math, speaker-pick step shown for unknown roles.

## Task 9 — Web app: progress, compare, history
What it is / what it means: The rest of the screens: watch a run, read results, revisit old runs. (R1, R6)
What changes at a high level: Progress grid polling every 3 s with Cancel. Compare table with Human first, per-cell mean and range with expandable detail, per-session diffs, MAE column, failed units flagged, tokens and ~$, per-unit output JSON view. History table with open and "Rerun with different engines/presets" that prefills New run.
Done when: Tests first: compare table with and without Human (error columns absent without), failed-unit display, polling stops on finished run, rerun prefill.

## Task 10 — CI jobs for eval backend and web
What it is / what it means: Tests run on every push and PR for the new code. (R12, CI default)
What changes at a high level: Add eval backend (pytest, lint, types as other members) and eval web (install, test, build) jobs to `ci.yml`; extend `changes.sh` flags and the dependency rules so engine, core, auth or eval changes rerun them; update `test_changes*` scripts first.
Done when: `test_changes*` cover the new flags, actionlint passes, both jobs green locally via their commands and in `ci.yml` structure checks.

## Task 11 — Deploy workflow and image guard
What it is / what it means: One workflow ships backend and site to staging. (R11)
What changes at a high level: `deploy-eval.yml` copied from `deploy-admin.yml`: build the eval image (backend, eval core, admin auth, engines, config, protocols pack), deploy Cloud Run, set CORS, build the SPA with the eval API URL and existing admin staging Firebase vars, deploy Hosting, smoke anonymous `/v1/me` = 401. A script test asserts no dataset files in the image.
Done when: `test_deploy_eval.sh` written first and passing, actionlint passes, image build succeeds without dataset files.

## Task 12 — Live smoke, docs, reference page
What it is / what it means: Prove it works on staging and document it. (AC1-AC7)
What changes at a high level: Run the deploy once, then manual smoke per acceptance criteria 1-5 (401 check, dataset defaults on `casaa-miti421-video2013`, 2x2x3 unit count and tab-close survival, `.txt` with and without gold, audio upload with speaker pick, history and rerun). Write `docs/reference/eval-site.md` (usage, API, data layout, prod labels, cost caveats).
Done when: Smoke results recorded per AC, with BLOCKED noted where an owner step is pending; reference page exists and links resolve.

## Closing note — manual (owner) steps
- Create DNS record(s) for `eval.onolys.com` from the Hosting custom-domain output, then wait for the cert (not blocking).
- Confirm repo variables `ADMIN_STAGING_VITE_FIREBASE_*` are set.
- Raise LLM provider quota if 96-unit runs hit rate limits.
- Needs SP1-SP4 landed and SP2 bucket created before tasks 3-7 can fully run.
