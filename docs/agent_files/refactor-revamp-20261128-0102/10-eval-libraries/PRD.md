---
status: draft
summary: In the new eval repo, replace eval's scattered metrics, 15 chart components and the English dataset converters with three libraries (metrics registry, chart registry, converter base class) driven by report YAML; then cut eval off the api worker and prod sessions by bumping to the new engine (`engine-v1`) and importing the api's leaf data, auth, tasks and transcription features by tag. New repo `Onolys/onolys-eval` is public; all old eval runs and data are dropped.
date: 2026-11-28
---
# PRD: 10 Eval libraries (metrics, charts, report YAML, converters, own run path)

Repo/branch: Onolys/onolys-eval (public; `refactor/libraries`, after 03 created it) · Depends on: 03 (hard); P4 also needs tag `engine-v1`, created by 06 (T10) after it merges (03 created `engine-v0`) · Owns: whole eval repo. Paths below are the new flattened ones; mapping: `eval/core`->`core/`, `eval/backend`->`backend/`, `eval/web`->`web/`, `eval/datasets`->`datasets/`, `eval/fixtures`->`fixtures/`. Does not own: engine (04/05), api features (06), Terraform restructure (09), per-slot metrics, Jev, per-volley experiments (separate PR), docs outside this repo.

## TL;DR
Eval gets three libraries and one cut-over. (1) One **converter** base class; each dataset is a small subclass plus a `mapping.yaml` beside its manifest. (2) One **metrics registry**: named functions returning uniform rows. (3) One **chart registry** plus **report YAML** that says which metrics feed which charts; the backend evaluates a report, the web renders it. Phases P1-P3 run on the `engine-v0` pin, change no numbers, and keep eval deployed. P4 is the cut-over: bump to the new engine, give eval its own sessions and run executor (03 O1), and replace eval's copies of auth, Firestore, queue and STT with the api's leaf features (06 makes them importable), pulled by git tag. Out of scope per the brief: per-slot metrics, Jev, per-volley experiments.

## Problem
| Gap | Evidence |
|---|---|
| Metrics live in 7 core files plus inline in routes; "best", tolerance and mean helpers repeat | [verified: `core/{metrics,_formulas}.py`, `core/summary/{session_metrics,line_metrics,analysis,operations,run_report}.py` ~1.1k lines; `compare_routes.py:189-270` `_leaderboard_quality`, `_operational_best`, bias % inline; `_mark_best` in session_metrics vs best-marking in routes] |
| Each Compare tab is a hard-wired endpoint + payload type + layout; a new view is code in three places | [verified: `/overview /deep-dive /analysis` in `compare_routes.py`; `compareApi.ts` types; `Overview/DeepDive/MoreAnalysis.tsx`] |
| 13 chart components in `compare/charts/` plus Leaderboard and MetricHeatmap, each hand-writing its table twin; 4 chart CSS files plus per-tab CSS | [verified: `web/src/compare/charts/*`; `ui/ChartFrame.tsx` is the only shared base] |
| 8 converters + `publicsets.py` + `convert.py` (PDF) = ~2.1k lines of near-parallel code (non-English ones are deleted, not ported); dataset headers exist twice (HEADER dict in code, manifest.yaml) | [verified: `annomi.py` HEADER vs `datasets/annomi/manifest.yaml`; same shape `build_session`/`convert_X_dataset`/`build_manifest` in each] |
| Eval backend duplicates api features: `EvalRepository` has a Protocol, an in-memory fake and a Firestore class; `InMemoryTaskQueue`; `InMemoryBucket`; `uploads.py` (626 lines) carries its own STT poll chain; `eval_delete.py` | [verified: `repository.py:33,64,214`, `queue.py`, `storage.py:100+`, `uploads.py:86-600`; 67 fake/in-memory refs in backend tests] |
| Eval writes prod `SessionDoc`s and runs on the api worker (`create_run(is_eval)`), which 06 deletes | [verified: `eval_sessions.py:13-22`, `eval_scheduler.py:29-36,357-400`; 03 R9, handoff] |
| Two report parsers (miti, oneshot) and two score projections exist only because one-shot counts in the model | [verified: `run_report.py:106,120`, `adapters.py:28-66`; 05 makes all evaluations share one shape] |

## Goals / Non-Goals
**Goals:** a new comparison view = one YAML file; a new dataset = a subclass + mapping; one implementation of every metric; eval never touches prod session/run docs; numbers unchanged through P1-P3 (proven by goldens); eval usable after every phase.
**Non-goals:** new metrics, per-slot metrics, Jev, new engine behaviour; Line view / reasoning redesign; non-English datasets (deleted); docs outside this repo; Terraform restructure; migrating or mapping old runs.

## Requirements
**P1 Converters** (`core/` -> `core/src/onolys_eval/convert/`).
- `Converter` base (about 250 lines): class vars `dataset_id`, `source_format`; `datasets/<id>/mapping.yaml` loaded by base (roles, label-to-code maps, labeled ids, source urls, label scheme); methods subclasses override: `read(raw) -> source`, `session_specs(source)` (for `sessions_from_source`), `turns(source, session) -> turns with codes`, optional `counts/globals/quality` (defaults tally turn codes, no globals, no quality). Base owns: fetch provenance, span handling, `make_gold`, partial counts, write transcript/gold, warnings/status, `convert(manifest, cache, session_id)`. Replaces `publicsets.py`, `_SESSION_DERIVERS`, the `SourceFormat` literal dispatch (a `CONVERTERS` dict keyed by `source_format`).
- One level of inheritance (rule 7): CSV/zip/JSON/HTML helpers are base methods, no mid-level classes. CASAA PDF parsing (`convert.py` 385 lines) becomes `PdfConverter(Converter)` keeping its parser; not expected to shrink much.
- `build_manifest` and HEADER dicts leave shipped code: `tools/new_dataset.py` writes a manifest from `session_specs`; the header lives only in `manifest.yaml`.
- `midas-es`, `phac-fr` and all non-English converters are deleted; `phac-en` stays (`phac.py` becomes its English-only subclass). Estimate: ~2.1k -> ~1.0k lines (not measured).
**P2 Metrics library** (`core/src/onolys_eval/metrics/`): `registry.py`, `agreement.py` (counts, globals, summaries, bias, within-1), `lines.py` (accuracy, macro F1, P/R/F1, confusion, agreement), `operations.py` (cost, time, failures, coverage, frontier), `reliability.py` (repeat agreement, head-to-head, error-vs-length, grid, baseline), `formulas.py` (single seam to the engine's summary formulas: `pack.yaml` now, `protocol.yaml` after P4). `compare_routes.py` metric code moves in; endpoints keep their payloads until P3.
- Contract:
```python
@metric("globals_within_1", better="higher", needs=("human_globals",))
def globals_within_1(data: CompareData, combos: Sequence[str], **opts) -> MetricResult: ...
# MetricResult(rows: list[Row], cohort: {paired, of} | None, notes: list[str])
# Row: metric, combo, item?, session?, value, n, of, repeats, na: {reason} | None, best: bool, extra: dict
```
`CompareData` = today's `View` (gold projections, parsed runs, cells, prices, group) built by one loader. Registry marks `best` from `better` (replaces three copies). An unmet `needs` yields rows with `na.reason`, never an error (today's "n/a - reason").
**P3 Charts + report YAML**
- `reports/*.yaml` (id = filename).
```yaml
report: overview
title: Overview
requires: [human_labels]
sections:
  - id: leaderboard
    title: Leaderboard
    metrics: [count_error, globals_within_1, line_accuracy, macro_f1, cost_per_run, time_per_run, failures]
    chart: {use: table.ranked, with: {sort: count_error, order: asc}}
  - id: heatmap
    title: Metric heatmap
    metrics: [{use: item_miss, with: {items: [counts, globals, ratios]}}]
    chart: {use: heatmap.grid, with: {rows: item, cols: combo}}
    collapsed: true
```
- Loader (`backend/.../reports.py`, fail-fast at startup): unknown metric id is a load error (registry = plain dict; duplicate ids fail at import). Chart ids are checked by ONE web unit test that loads the shipped `reports/*.yaml` and asserts every `chart.use` is registered; no `charts.yaml` manifest and no manifest-equals-registry test (second copy of the same list; [RESOLVED 2026-11-28: owner rule 17]). Backend evaluates: `GET /v1/eval-runs/{id}/reports` (list) and `/reports/{report_id}?combos=` -> `{title, sections:[{id,title,caption,chart:{use,with},rows,cohort,notes}]}`. The three tab endpoints and their TS types are deleted in the same PR (rule 16). `reasoning`, `lines`, `line-matches` stay, reading numbers from the library.
- Web: `ChartProps<O> = {rows, options, combos, cohort, notes}`; `registerChart({id, Component, columns})`. Shared `ChartCard` (extends `ChartFrame`) renders title, caption, legend, n/a reasons, cohort line, and auto-builds the "Show data" table from `columns`; one `charts.css` on `@onolys/common` tokens; `ui/chart/{Axis,scales,theme}` stay as primitives. `ReportView` loops sections; no per-report code.
| Today | Chart id |
|---|---|
| Leaderboard, PrfTable, ReliabilityTable | `table.ranked` |
| MetricHeatmap, InterviewGrid, ConfusionGrid | `heatmap.grid` |
| CountBars, MissBuckets, HeadToHead | `bars.grouped` (`stack`, `mode` options) |
| GlobalsDotPlot | `dots.per_item` |
| CostAccuracyScatter, ErrorVsLength | `scatter.xy` |
| BaselineCard, verdict block | `stat.tiles`, `text.clauses` |
| ComboSelector, ReasoningRollup, `line/*` | stay bespoke (controls and drill-downs, not charts) |
Shipped reports: `overview`, `deep-dive`, `analysis` reproducing today's tabs. Eval-local `Chip`, `Note`, `ErrorPage`, `theme-init.js` adopt `@onolys/common` (02 deferred item). Eval keeps its own `DataTable`, `Disclosure`, `StatTile` (not promoted).
**P4 Cut-over** (needs tag `engine-v1`, created by 06 after it merges; eval started on `engine-v0`).
1. *Engine + own run path.* Pins become `onolys-engine` and `onolys-api` at `engine-v1` (uv git-subdirectory deps proven in spike 3; re-lock against the tag, no wheels fallback needed) (no `snapshot/` worker build). Eval gets `eval_sessions/{sid}` (pinned transcript blob content-addressed like gold, goal, span, language, clinician speaker, gold ref) and `eval_cells/{id}` (replaces `RunDoc`: status, attempt, usage, timing, error, report, engine id, route snapshot, git sha). A `/tasks/cell` handler in the eval backend calls `Engine.run` with the route override and validates against `Engine.output_schema()`. Scheduler creates cells, not api runs; the drift guard goes (one image, one sha). Worker = same eval image as a second Cloud Run service. `eval_sessions.py` no longer imports `onolys_api.repo`. Eval's own `config/` copy (with overlay) follows 04's route format. Old eval runs and data are dropped; no old-run rendering or id mapping. Evaluation ids are `miti`, `oneshot-single`, `oneshot-split` (no mapping from `oneshot:miti`); one `parse_report`; `_parse_oneshot`, `oneshot_scores`, `_OneshotOutput` deleted.
2. *Shared features (decision D2).* Import `onolys_api.{data,auth,tasks,transcription}` only, through their public surface (06 made them leaf modules; no copies). Delete: `InMemoryEvalRepository` + Protocol, `InMemoryTaskQueue`, `InMemoryBucket`, eval `CloudTasksQueue`, token-verify code in `auth.py` (keep `allowlist.py`; token verification becomes Firebase Admin `verify_id_token`, owner D-A, replacing today's use of api's custom `IdTokenVerifier`, which 06 deletes; no custom verifier or cert cache in eval; `email_verified` is one claim check if required), `uploads.py` STT poll chain (keep upload bookkeeping and gold/span validation; target ~250 lines, estimate). Eval's docs have no owner, so its repository becomes thin wrappers over 06's ownerless functions (`get_unowned_doc`, `set_unowned_doc`, `update_unowned_doc`, `query_unowned`) plus `in_transaction` (06 keeps `uid` required in the owned functions; eval never passes a fake uid); slot/tick claims are `in_transaction` functions. Tests use the Firestore emulator (rule 9); in-memory fixtures and `fixtures/compare/fakes.py` go.
3. *Database `(default)` (owner D-B, 2026-11-28).* The eval project `onolys-eval` has one database, named `eval` (leftover of the old shared project). Eval's Terraform copy (from 03) creates `(default)` and deletes the named `eval` database outright; `firebase.json` becomes ONE firestore entry (object form: deny-all rules + `firestore.indexes.json`), deploy picks the project with `--project`; `FIRESTORE_DATABASE` / `firestore_database` removed from `backend/` config, Terraform env, workflows and tests (`test_app.py`, `test_config.py`). No export, backup or data migration: owner allows deleting any existing staging/eval records. Do this together with the old-run deletion in Manual steps.
4. *Rule pass (rule 17, audit).* `config.py` becomes pydantic-settings `BaseSettings` (replaces hand-rolled env parsing; audit #1); `compare_cache.py` hand LRU+TTL becomes `cachetools.TTLCache` (audit #9; [docs](https://cachetools.readthedocs.io/en/latest/)); eval LLM calls go through a LiteLLM `Router` ([RESOLVED 2026-11-28: owner]): the worker builds one Router from the route specs (`allowed_fails`, `cooldown_time`, `num_retries`; [docs](https://docs.litellm.ai/docs/routing)) and hands the engine a client that sends through it (`Engine.run(..., RunOptions(llm=...))`; if 04's `LiteLLMClient` cannot take a Router, P4 adds that one optional parameter, not a second client class). The custom per-provider breaker/cooldown/`overload_streak` (~150 lines in `eval_scheduler.py`: `_record_outcome`, `_start_cooldown`, the `waiting`-behind-cooldown path and `OVERLOAD_*` backoff; `cooldown_until`/`overload_streak` fields of `eval_slots/{provider}` in `repository.py`; `eval_view.provider_cooldowns`, the `provider_cooldowns` field in `read_runs.py:141` and its consumers `eval/web/src/api.ts`, `run/AlertsStrip.tsx`, `RunStatus.test.tsx`) and their tests (`test_eval_resilience.py`, `test_eval_cancel.py` breaker cases) are DELETED, not kept beside the Router; a cell whose Router retries are exhausted fails as a normal failure (audit #11). The `uvicorn --proxy-headers --forwarded-allow-ips='*'` flags in `backend/Dockerfile` are dropped (06 R10 removed the only `X-Forwarded-For` reader; nothing in `eval/backend/src` reads `request.client` [verified: grep → 0]); eval `preset:`/`resolved_presets` handling in `comboFields.ts` is removed if legacy (01 hand-on). `constants.py` (collections, paths, limits, states, engine ids, providers); `eval_scheduler.py` (754) splits by feature past ~300 lines (`scheduler/`); `compare_routes.py` becomes the thin `reports_routes.py`; tests mirror source (`tests/metrics/…`, `tests/convert/…`).

## Architecture
```
datasets/<id>/{manifest,mapping}.yaml -> Converter subclass -> transcript.v1 + gold.v1 (bucket)
eval run -> scheduler -> eval_cells -> /tasks/cell -> Engine.run (onolys-engine, tag) -> report
reports/*.yaml --load/validate--> backend: CompareData -> metrics registry -> rows
      -> GET /reports/{id} -> web ReportView -> chart registry (reports/charts.yaml checks both ends)
onolys-api (tag): data, auth, tasks, transcription (leaf features)   onolys-engine (tag): Engine.run, output_schema, protocol.yaml formulas
```

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | Phase order | P1 converters, P2 metrics, P3 charts+YAML, P4 cut-over | 03's "own sessions first" | Own sessions cannot be built on the old pin without writing the executor twice (api worker is the only run path until the new `Engine.run`); P1-P3 need nothing from 04-06 and run on `engine-v0`. If 06 has landed when 10 starts, run P4 first |
| D2 | Shared features | Depend on `onolys-api` by tag, import only the four leaf features | Extract a shared package; keep eval's copies restructured | One implementation (rule 9) with no new repo or release process; the api is already a pinned dependency. No copies: if the api is not leaf, fix the api (06) |
| D3 | Engine upgrade | Part of 10 (P4 step 1), same step as own run path | Separate step | Same change: stop using the api worker = call the new engine directly |
| D4 | Who renders a report | Backend computes rows, web draws charts | Web computes from raw data; backend renders HTML | Metrics need Python, gold, prices; payload is already server-side today |
| D5 | Metric contract | Decorated function, uniform `Row`, `better`, `needs` | Class per metric; free-form dict per tab | Uniform rows are what let any chart take any metric; `better` and `needs` replace repeated best/n-a code |
| D6 | Chart contract | `{rows, options}` + id list + auto table twin | Keep 13 components, add YAML only | A shared base removes the per-chart table/CSS; merges 15 components into 7 ids |
| D7 | Report `inputs:` block (brainstorm sketch) | Dropped; dataset and engines come from the eval run, combos chosen at view time | Pin engines in YAML | An eval run already fixes both; YAML stays reusable across runs |
| D8 | Converter variation | Python subclass for parsing, `mapping.yaml` for tables | All YAML; all code | Raw formats (CSV, zip, JSON, HTML, PDF) need code; label maps and roles are data |
| D9 | Non-English | Delete `midas-es`, `phac-fr` and all non-English converters; keep `phac-en` | Port; leave untouched | Owner decision |
| D10 | Old stored runs | All dropped (no mapping, no rendering) | Migration script; dual parsers; baseline export | Owner decision; rule 16 |
| D11 | Tests | Goldens first, Firestore emulator, tests mirror source | Keep in-memory fakes | Rule 9 and 14; goldens prove "no numbers change" |

## Manual steps
1. At P4 deploy: the agent applies (plan first) the Terraform change that points the worker service at the eval image (env var renames).
2. Agent plans and applies the `(default)` database switch (item 3 above): the named `eval` database and all old run docs are deleted with it; no export or backup.
3. Owner runs one small eval run after deploy (live LLM/STT).

## Risks / Open Questions
- [RESOLVED: no copies; 06 provides leaf modules] O1: 06 makes `data`, `auth`, `tasks`, `transcription` leaf (no import of routes/sessions/pipeline), accept explicit settings/clients, expose separately named ownerless functions, and ship an in-process queue stub (06 R2b). P4 starts with an import-graph check; if it fails, fix the api, do not copy.
- [RESOLVED: `engine-v0` then `engine-v1`] O2: eval starts on `engine-v0` (created by 03); `engine-v1` is created by 06 (T10) after it merges, for P4.
- [RESOLVED: yes] O3: delete all old eval run data; no old-run rendering.
- [RESOLVED: second service] O4: worker is a second Cloud Run service from the same eval image.
- [RESOLVED: delete] O5: `midas-es`, `phac-fr` and all non-English converters deleted; `phac-en` kept.
- [RESOLVED: no promotion] O6: eval keeps `DataTable`, `Disclosure`, `StatTile`; adopts only existing `@onolys/common` equivalents.
- [RESOLVED: follow 04] O7: eval's own `config/` copy follows 04's format.
- [RESOLVED: yes, in P4 step 1] 03 O1 "own sessions" handed to 10.
- [RESOLVED 2026-11-28: owner] Eval scheduler breaker (audit #11): eval ALSO goes through LiteLLM (Router). Delete the custom per-provider breaker/cooldown/`overload_streak` and the `eval_slots` cooldown fields; use Router cooldowns/`allowed_fails`/retries. P4 states eval calls go through the Router (P4 step 4). Trade-off accepted: cooldown no longer shows in the eval run view.
- Rules cited: 1, 3, 7, 9, 10, 14, 16, 17.
- [DEFERRED] Per-slot metrics, Jev, per-volley/per-global experiments; trimming staging/prod from eval Terraform; a converters mapping for new datasets.
- Risk: a refactor silently shifts a number. Mitigation: before P2, capture today's `overview/deep-dive/analysis/lines` payloads on all 14 `fixtures/compare` scenarios as snapshots with a snapshot library (e.g. `syrupy`, `--snapshot-update`; https://github.com/syrupy-project/syrupy, not fetched) rather than a hand-built golden harness; P2 must match exactly, P3 must match value-for-value through the new reports.
- Risk: converter output drifts. Mitigation: pre-refactor characterization: run old English converters on each test sample and commit outputs; new classes must be byte-identical.
- Risk: P4 stalls waiting on 04-06. Mitigation: P1-P3 are independent and deployable.
- Risk: api tag drags api dependencies (FastAPI, Firestore, ffmpeg tooling) into the eval image. Mitigation: only leaf imports; ruff `banned-api` bans every other `onolys_api` module (no custom guard test; rule 17).

## Acceptance Criteria
- P1: all remaining (English) converters subclass `Converter`; `midas-es`, `phac-fr` and non-English converters are gone; outputs byte-identical to the pre-refactor characterization set; `publicsets.py` and per-module `HEADER`/`build_manifest` gone; each subclass is small (target <= 100 lines except PDF).
- P2: `git grep` finds no metric arithmetic outside `metrics/`; goldens from 14 fixtures match exactly; `core/_formulas.py`, `core/summary/{session_metrics,line_metrics,analysis,operations}` deleted.
- P3: `overview`, `deep-dive`, `analysis` render from YAML; adding a report = one YAML file with no code (shown by a test report); load rejects an unknown metric id; every shipped report's `chart.use` is registered (one web test); chart components <= 7 plus bespoke views; old endpoints/types gone; eval deployed and clicked through.
- P4: `config.py` is pydantic-settings; `compare_cache` uses `cachetools`; no `onolys_api.repo`, `.routes`, `.jobs`, `.engines`, `.adapters` import; backend/worker revisions share one sha with no drift code; no in-memory repo/queue/bucket class; no scheduler breaker/cooldown/`overload_streak` code (eval LLM calls go through a LiteLLM Router); tests pass against the Firestore emulator; one `parse_report`; one small run completes end to end for miti, oneshot-single, oneshot-split; no old runs or old-id mapping remain.
- Whole: tests mirror source; no spec ids in docstrings; one `constants.py`; CI green in the eval repo.
