---
status: draft
summary: Eval repo in four phases (17 tasks) - P1 converter base class, P2 metrics registry, P3 chart registry + report YAML, P4 cut-over to engine-v1, own sessions/cells, api leaf features, (default) DB and rule 17 library pass.
date: 2026-11-28
---
# Tasks: 10 Eval libraries

Source of truth: /root/projects/onolys/onolys/.worktrees/refactor/revamp/docs/agent_files/refactor-revamp-20261128-0102/10-eval-libraries/PRD.md. All work is in the new public repo Onolys/onolys-eval (branch `refactor/libraries`, created by 03), using the flattened paths (`core/`, `backend/`, `web/`, `datasets/`, `fixtures/`). Registries are plain dicts with a unique-id check only: no accepts/dims cross-validation, no per-metric option models, no `charts.yaml` manifest. Follow `docs/rules/coding-rules.md` (rule 17: use the library). P1-P3 stay on pin `engine-v0` and change no numbers; P4 needs tag `engine-v1` from 06. Eval CI exists from 03; tasks extend it. One commit per task. Full suite only in dev-ship.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | P1: delete non-English converters; capture converter characterization set | 03 | todo |
| 2 | P1: `Converter` base class, `mapping.yaml`, `CONVERTERS` dict | 1 | todo |
| 3 | P1: port English converters + `PdfConverter` to subclasses | 2 | todo |
| 4 | P1: `tools/new_dataset.py`; delete `publicsets.py`, HEADER/`build_manifest` | 3 | todo |
| 5 | P2: capture snapshot goldens on the 14 compare fixtures | 4 | todo |
| 6 | P2: metrics registry, `CompareData` loader, formulas seam | 5 | todo |
| 7 | P2: move all metric code into `metrics/`; delete old summary files | 6 | todo |
| 8 | P3: report YAML loader, reports endpoints | 7 | todo |
| 9 | P3: web chart registry, `ChartCard`, 7 chart ids, `ReportView` | 8 | todo |
| 10 | P3: delete old tab endpoints/types/charts; adopt `@onolys/common`; deploy | 9 | todo |
| 11 | P4: pin to `engine-v1`; confirm api leaf lint; emulator tests in CI | 10, 04/05/06 merged, tag `engine-v1` | todo |
| 12 | P4: `eval_sessions`, `eval_cells`, `/tasks/cell` calling `Engine.run` | 11 | todo |
| 13 | P4: scheduler on cells; new evaluation ids; one `parse_report` | 12 | todo |
| 14 | P4: replace eval copies with api leaf features | 12 | todo |
| 15 | P4: rule pass (constants, scheduler split, `reports_routes`, tests mirror) | 13, 14, 17 | todo |
| 16 | P4: Terraform worker service, `(default)` DB switch, drop old runs, deploy, acceptance sweep | 15 | todo |
| 17 | P4: rule 17 pass (pydantic-settings, TTLCache, LiteLLM Router, delete breaker) | 13, 14 | todo |

## Task 1 — P1: delete non-English converters; capture characterization set
What it is / what it means: Before refactoring converters, freeze today's English output so the new classes can be proven byte-identical, and remove what is being dropped. PRD P1, D9, O5, risk "converter output drifts".
What changes at a high level: Delete `midas-es`, `phac-fr` and every non-English converter with their datasets, manifests, fixtures and tests; keep `phac-en` (English-only). Run the remaining old converters on each test sample and commit the outputs (transcript, gold, counts, warnings) as a characterization set, with a test that re-runs the old code against it.
Done when: no non-English converter or dataset remains (`git grep` for the deleted ids is 0); characterization test passes on the old code for every remaining dataset; existing converter tests and CI green.

## Task 2 — P1: `Converter` base class, `mapping.yaml`, `CONVERTERS` dict
What it is / what it means: The one place that owns everything common to datasets: provenance, spans, gold, counts, writing, status. PRD P1 bullet 1, D8.
What changes at a high level: Add the `Converter` base (about 250 lines) in `core/src/onolys_eval/convert/` with class vars `dataset_id` and `source_format`, a `mapping.yaml` loader (roles, label-to-code maps, labeled ids, source urls, label scheme), overridable `read`, `session_specs`, `turns`, optional `counts/globals/quality` with defaults, and `convert(manifest, cache, session_id)`. CSV/zip/JSON/HTML helpers are base methods; one level of inheritance only. A `CONVERTERS` dict keyed by `source_format` replaces the literal dispatch.
Done when: unit tests of the base using a tiny test subclass cover defaults, partial counts, spans, warnings and mapping loading; a duplicate `source_format` is rejected; ruff and impacted tests pass.

## Task 3 — P1: port English converters + `PdfConverter`
What it is / what it means: Each dataset becomes a small subclass plus a `mapping.yaml` beside its manifest. PRD P1, D8.
What changes at a high level: Port every remaining converter (annomi, phac-en and the other English ones) to subclasses with their `mapping.yaml`; the CASAA PDF parser becomes `PdfConverter(Converter)` keeping its parser. The dispatch table points to the new classes. Old converter modules and the `_SESSION_DERIVERS` map go.
Done when: new classes reproduce the Task 1 characterization set byte-for-byte; each subclass is at most about 100 lines (PDF excepted); old dispatch removed; converter tests pass.

## Task 4 — P1: `tools/new_dataset.py`; delete `publicsets.py` and header code
What it is / what it means: Dataset headers live once, in `manifest.yaml`; scaffolding derives from the subclass. PRD P1 bullet 3, AC P1.
What changes at a high level: `tools/new_dataset.py` writes a manifest from `session_specs`. Delete `publicsets.py`, every `HEADER` dict and `build_manifest`, and any leftover per-dataset `convert_X_dataset` wrappers. No new converter mapping tooling (deferred).
Done when: `git grep` finds no `HEADER =`, `build_manifest` or `publicsets`; a test runs `new_dataset` on a sample and validates the manifest; the characterization set still passes; CI green.

## Task 5 — P2: capture snapshot goldens on the 14 compare fixtures
What it is / what it means: Numbers must not move. Today's payloads are the reference. PRD risk "silently shifts a number", D11.
What changes at a high level: Run the current `overview`, `deep-dive`, `analysis` and `lines` payload builders on all 14 `fixtures/compare` scenarios and store them as snapshots with a snapshot library (e.g. `syrupy`), not a hand-built golden harness, with a test comparing live output to them. Use stable ordering and fixed rounding.
Done when: golden test passes on unchanged code for all 14 scenarios and all four payloads.

## Task 6 — P2: metrics registry, `CompareData`, formulas seam
What it is / what it means: The uniform contract every metric and chart will share. PRD P2 contract, D5.
What changes at a high level: Add `metrics/registry.py` with the `@metric(id, better, needs)` decorator (plain dict, unique-id check), `MetricResult`/`Row` types, and best-marking derived from `better` (replacing the three copies). Add one `CompareData` loader (today's `View`). Add `formulas.py` as the single seam to the engine summary formulas (`pack.yaml` for now). An unmet `needs` returns rows with `na.reason`, never an error.
Done when: unit tests cover registration, duplicate-id rejection, best marking (higher/lower/ties), n/a reason rows and the loader; goldens still pass; ruff green.

## Task 7 — P2: move all metric code into `metrics/`; delete old files
What it is / what it means: One implementation of every metric. PRD P2, AC P2.
What changes at a high level: Move agreement, line, operations and reliability metrics into `agreement.py`, `lines.py`, `operations.py`, `reliability.py`; move the metric code inline in `compare_routes.py` (`_leaderboard_quality`, `_operational_best`, bias %) in. Endpoints keep their payloads and now call the registry. Delete `core/_formulas.py` and `core/summary/{session_metrics,line_metrics,analysis,operations}`.
Done when: goldens match exactly on all 14 fixtures; `git grep` finds no metric arithmetic outside `metrics/`; deleted files gone; per-module metric tests added under `tests/metrics/`; CI green. Deployable.

## Task 8 — P3: report YAML loader, reports endpoints
What it is / what it means: A new comparison view becomes one YAML file. PRD P3, D4, D7.
What changes at a high level: Add `reports/{overview,deep-dive,analysis}.yaml` reproducing today's tabs. Add the loader `reports.py`, fail-fast at startup: unknown metric id and duplicate ids are load errors (chart ids are checked by the web test in Task 9, not here). Add `GET /v1/eval-runs/{id}/reports` and `/reports/{report_id}?combos=` returning `{title, sections:[{id,title,caption,chart,rows,cohort,notes}]}`. Old endpoints stay until Task 10.
Done when: tests show the three reports match goldens value-for-value; a test report added as one YAML with no code loads and evaluates; load rejects unknown metric and duplicate ids; endpoint tests pass.

## Task 9 — P3: web chart registry, `ChartCard`, chart ids, `ReportView`
What it is / what it means: The web side of the same idea: one card, one CSS, a registry of 7 chart ids. PRD P3 web, D6.
What changes at a high level: Add `ChartProps`, `registerChart({id, Component, columns})`, shared `ChartCard` (extends `ChartFrame`; title, caption, legend, n/a reasons, cohort line, auto "Show data" table from `columns`), one `charts.css` on `@onolys/common` tokens, and `ReportView` looping sections. Port the 15 chart components into `table.ranked`, `heatmap.grid`, `bars.grouped`, `dots.per_item`, `scatter.xy`, `stat.tiles`, `text.clauses`. ComboSelector, ReasoningRollup and `line/*` stay bespoke. Tabs switch to `ReportView`.
Done when: vitest tests per chart id (render, table twin, n/a); ONE web test loads the shipped `reports/*.yaml` and asserts every `chart.use` is registered (no manifest, no manifest-equals-registry test); Overview/Deep-dive/Analysis render through reports; web lint and typecheck pass.

## Task 10 — P3: delete old tab code; adopt `@onolys/common`; deploy
What it is / what it means: Remove the three-places-per-view code and finish 02's deferred adoption. PRD P3, rule 16, AC P3.
What changes at a high level: Delete the three tab endpoints and their TS types, the old per-tab components, per-chart and per-tab CSS. Replace eval-local `Chip`, `Note`, `ErrorPage` and `theme-init.js` with `@onolys/common` equivalents; keep `DataTable`, `Disclosure`, `StatTile` in eval. Deploy eval (still `engine-v0`) and click through the three reports.
Done when: old endpoints/types/components gone (`git grep` 0); chart components at most 7 plus bespoke views; backend and web tests pass; eval deployed and a click-through recorded.

## Task 11 — P4: pin to `engine-v1`; confirm api leaf lint; emulator tests
What it is / what it means: Start of the cut-over. Needs 04/05/06 merged and tag `engine-v1`. PRD P4, D1, D2, O1, O2. If 06 landed before this work began, P4 may run first.
What changes at a high level: First confirm tag `engine-v1` exists (`git ls-remote`, agent step) and that 06's ruff `banned-api` leaf rules are in it, so `onolys_api.{data,auth,tasks,transcription}` import nothing from routes/sessions/pipeline (no separate import-graph test); if not, report to 06 and stop (never copy code). Then move the pins for `onolys-engine` and `onolys-api` to `engine-v1` (no `snapshot/` worker build). Switch `formulas.py` to `protocol.yaml`. Add the Firestore emulator and Auth emulator to eval CI. Add a ruff `banned-api` config allowing only `onolys_api.{data,auth,tasks,transcription}` (no custom guard test).
Done when: tag and leaf-rule check recorded; image builds on the new pins; goldens still match (or differences explained by engine changes and re-recorded by the agent with a note); ruff banned-api passes on the tree (confirm once by hand that a banned import is flagged; no committed test); CI runs emulator tests and each eval CI job stays under 5 minutes.

## Task 12 — P4: `eval_sessions`, `eval_cells`, `/tasks/cell`
What it is / what it means: Eval's own run path, with no api worker. PRD P4 step 1.
What changes at a high level: Add `eval_sessions/{sid}` (content-addressed pinned transcript, goal, span, language, clinician speaker, gold ref) and `eval_cells/{id}` (replaces `RunDoc`: status, attempt, usage, timing, error, report, engine id, route snapshot, git sha). Add the `/tasks/cell` handler that calls `Engine.run` with the route override and validates against `Engine.output_schema()`. `eval_sessions.py` stops importing `onolys_api.repo`. Eval's `config/` copy (with overlay) follows 04's route format.
Done when: emulator-backed tests cover creating sessions, a cell run to done and to failure, schema validation failure, retry/attempt; the engine is stubbed only through its own public `FixtureClient` (`make_client`), no custom fake; no `onolys_api.repo` import remains.

## Task 13 — P4: scheduler on cells; new evaluation ids; one `parse_report`
What it is / what it means: Scheduling stops creating api runs. PRD P4 step 1, O3, 03 O1.
What changes at a high level: The scheduler creates cells, not api runs; the drift guard goes (one image, one sha). Evaluation ids become `miti`, `oneshot-single`, `oneshot-split` with no mapping from `oneshot:miti`. One `parse_report`; delete `_parse_oneshot`, `oneshot_scores` and `_OneshotOutput`. No old-run rendering.
Done when: scheduler tests (emulator) cover all three evaluation ids end to end with a stubbed engine; `git grep` for the deleted names and for drift-guard code is 0; the compare payloads for the new ids pass.

## Task 14 — P4: replace eval copies with api leaf features
What it is / what it means: One implementation of data, auth, queue and STT (decision D2). PRD P4 step 2.
What changes at a high level: Import `onolys_api.{data,auth,tasks,transcription}` through their public surface only. Make the eval repository thin wrappers over `get_unowned_doc`, `set_unowned_doc`, `update_unowned_doc`, `query_unowned` plus `in_transaction`; slot/tick claims become `in_transaction` functions. Delete `InMemoryEvalRepository` and its Protocol, `InMemoryTaskQueue` (use 06's `InProcessQueue`), `InMemoryBucket` (use 06's `LocalBlobStore`), eval `CloudTasksQueue`, token-verify code in `auth.py` (keep `allowlist.py`; token verification becomes Firebase Admin `verify_id_token`, decision D-A, no custom verifier or cert cache, `email_verified` as one claim check if required), the `uploads.py` STT poll chain (keep upload bookkeeping and gold/span validation, target about 250 lines), and `fixtures/compare/fakes.py`. Tests move to the Firestore emulator.
Done when: no in-memory repo/queue/bucket class remains (`git grep` 0); ruff banned-api passes; a test signs in via the Auth emulator and rejects a bad token; upload, auth allowlist and repository tests pass on the emulator.

## Task 15 — P4: rule pass
What it is / what it means: Final shape of the backend. PRD P4 step 4 (constants, scheduler split, `reports_routes`, tests mirror).
What changes at a high level: One `constants.py` (collections, paths, limits, states, engine ids, providers); split `eval_scheduler.py` by feature into `scheduler/` past about 300 lines; `compare_routes.py` becomes thin `reports_routes.py`; tests mirror source (`tests/metrics/`, `tests/convert/`). No spec ids in docstrings.
Done when: no source file over about 300 lines without a named exception; `git grep` for duplicated literals is 0; spec-id grep is 0; relocated tests pass.

## Task 16 — P4: Terraform worker service, drop old runs, deploy, acceptance sweep
What it is / what it means: Put the cut-over live and prove the whole PRD. PRD P4, Manual steps 1-2, O3, O4.
What changes at a high level: The agent runs Terraform plan, then apply, to make the worker a second Cloud Run service from the same eval image (env var renames). Deploy. Database switch (decision D-B, Manual step 2): Terraform copy creates `(default)` and deletes the named `eval` database outright; `firebase.json` becomes one firestore entry (deny-all rules + `firestore.indexes.json`), deploy uses `--project`; remove `FIRESTORE_DATABASE`/`firestore_database` from `backend/` config, Terraform env, workflows and tests (`test_app.py`, `test_config.py`). No export, backup or migration; old run docs go with the database. Run the acceptance greps (no `onolys_api.repo/.routes/.jobs/.engines/.adapters` import, backend and worker on one sha, no in-memory classes, one `parse_report`, no old-id mapping).
Done when: plan reviewed and applied cleanly; Terraform creates `(default)` and deletes the named `eval` database; backend and worker revisions share one sha; old runs gone; `git grep` for `FIRESTORE_DATABASE`/`firestore_database` is 0; eval CI green; acceptance greps recorded.

## Task 17 — P4: rule 17 pass (libraries instead of hand-rolled code)
What it is / what it means: Replace hand-rolled config, cache and provider-breaker code with libraries. PRD P4 step 4, audit #1, #9, #11, owner resolution on LiteLLM Router, rule 17.
What changes at a high level: `config.py` becomes pydantic-settings `BaseSettings`. `compare_cache.py` hand LRU+TTL becomes `cachetools.TTLCache`. The worker builds one LiteLLM `Router` from the route specs (`allowed_fails`, `cooldown_time`, `num_retries`) and hands the engine a client sending through it via `RunOptions(llm=...)`; if 04's `LiteLLMClient` cannot take a Router, add that one optional parameter, not a second client class. Delete the custom per-provider breaker/cooldown/`overload_streak` code in `eval_scheduler.py`, the `cooldown_until`/`overload_streak` fields of `eval_slots/{provider}`, `eval_view.provider_cooldowns` and its consumers (`read_runs.py`, web `api.ts`, `AlertsStrip.tsx`, `RunStatus.test.tsx`), and their tests (`test_eval_resilience.py`, `test_eval_cancel.py` breaker cases). A cell whose Router retries are exhausted fails normally. Drop the uvicorn `--proxy-headers --forwarded-allow-ips` flags from `backend/Dockerfile`. Remove legacy `preset:`/`resolved_presets` handling in `comboFields.ts` if still present.
Done when: config tests run through pydantic-settings (defaults, one required var, one bad value); the existing compare-cache tests pass on `TTLCache` (no new test of the library's TTL); one test using LiteLLM's `mock_response` failure shows a cell whose Router retries are exhausted fails as a normal failure; `git grep` for `overload_streak`, `cooldown_until`, `provider_cooldowns`, `OVERLOAD_`, `proxy-headers` is 0; no hand-rolled env parsing or LRU remains; backend and web tests pass.

Owner-only: none by default. After deploy, one small eval run for each of miti, oneshot-single and oneshot-split (live LLM/STT) is an agent step through the eval API; the owner does it only if sign-in or keys need a human (PRD Manual step 3 [OPEN]).
