---
stage: design
status: draft
summary: Index of the 5 sub-project PRDs for the MITI eval site (transcript.v1 + upload, CASAA dataset + CLI, engines/core, oneshot + validation, eval.onolys.com), with dependency graph, locked decisions, cross-SP seams, open items, owner tasks, PRD mismatches
date: 2026-11-23
---
# MITI eval site: design index

Branch `feat/miti-eval` (Onolys/onolys). Brainstorm: `brainstorm.md`. PRDs are drafts; this file does not replace them.

## Sub-projects
| # | Name | Phase | Depends on | Owns | One-line scope |
|---|---|---|---|---|---|
| SP1 | `01-transcript-format-upload` | 1 | none | `engines/miti` transcript/span/prepare/run/result/run_info + schemas; `api` routes/transcript.py, sessions, runs, speakers, jobs; `web/features/upload`; `docs/contracts/public`; `docs/reference/transcript-format.md` | `transcript.v1` (= Turn shape) + JSON schema, `.json`/`.txt` upload (PUT /transcript) in API + web, `coded_span` (ms or turn range, default full) |
| SP2 | `02-casaa-dataset-cli` | 1 (parallel with SP1/SP3) | SP1 schema (stub with Turn shape until then) | `eval/core/**` (`onolys_eval`), `eval/datasets/**`, root workspace `eval/*`, staging bucket TF | Fetch 8 CASAA 2013 sessions, PDF to `transcript.v1` + `gold.v1`, metrics module, private bucket, CLI `run` of lean engine on 1 session vs gold |
| SP3 | `03-engines-core` | 2 | SP1 | `engines/core/**` (`onolys_engine_core`), moves out of `onolys_miti`, `api` presets/logs/adapters/repo/config/engines.py, Dockerfile, CI core job | Extract engine-agnostic basics, `Engine` ABC + `EngineRegistry` + `list_presets` (prod flags), `RunContext.feedback`, `validate_output`; MITI becomes `MitiEngine` |
| SP4 | `04-oneshot-engine-validation` | 3 | SP3, SP1 | `engines/oneshot/**` (`onolys_oneshot`), `api/jobs/validated_run.py`, edits to run.py/real.py/error_map.py/engines.py, core llm `response_schema` + cost | Generic one-shot engine + `miti` config; API-layer validate + retry-once for all engines; tokens/cost |
| SP5 | `05-eval-site` | 4 | SP1, SP2, SP3, SP4 | `eval/backend/**`, `eval/web/**`, deploy-eval.yml, eval CI, eval infra (Hosting, Cloud Run, Tasks, IAM), `docs/reference/eval-site.md` | eval.onolys.com: dataset/upload modes, engine x preset multi-select, Cloud Tasks units, Firestore history, compare table vs human, tokens/$ |

## Dependency graph
```
SP1 -> SP3 -> SP4 -> SP5
SP1 -> SP2 -------> SP5
SP2 runs in parallel with SP1 and SP3 (needs only the Turn shape; SP1 schema swapped in later)
```
Suggested order: {SP1, SP2} then SP3, SP4, SP5. SP2 CLI spike gates SP5 (go/no-go on lean accuracy).

## Locked decisions (brainstorm)
- Same repo; site at eval.onolys.com; staging only; auth = `onolys_admin_auth` + `admin_allowed_emails`.
- First dataset = CASAA 2013 video series, 8 sessions, MITI 4.2.1. MI-TAGS later.
- Datasets in private staging GCS bucket; repo is PUBLIC, holds only scripts/manifests/spec, never data.
- Code the full transcript by default; dataset may specify a window. `coded_span` = `{start_ms,end_ms}` or `{start_turn,end_turn}`; absent = full.
- `transcript.v1` = engine `Turn` shape. STT writes it. No migration, breaking changes OK (no users).
- Upload `.json` / `.txt` (`T:`/`C:` or `Name:`) in main app + API; counts as 1 session; speaker gate if roles missing.
- Gold: session-level codes + optional per-utterance; compare session-level. Metrics: counts, 4 globals, R:Q, %CR, per-session diff, MAE.
- Run history (dataset, engine, git sha, preset/model, results) in staging Firestore. Uploads saved to private staging bucket, kept for reruns.
- Two modes: dataset (has gold) or single upload (audio or transcript, optional gold file).
- Two multi-selects: Engine (Human, MITI lean, One-shot) and Preset; "(prod)" labels; defaults pre-tick Human(dataset)/MITI lean (prod)/prod preset. Runs = engine x preset; Human ignores preset.
- 1 run per cell, option 3. Eval skips usage limits. No cost cap; show tokens + rough $.
- CLI spike first, then site.
- `engines/core` engine-agnostic only; `Engine` base class with overridable `run(ctx, transcript, params)` + declared output schema; registry by name.
- `oneshot` generic (instructions + schema -> 1 call); MITI config versioned in repo, same MITI report schema as lean, by name, not UI-editable; one-shot is eval-site only.
- Validation in API layer for all engines; retry once with errors, then fail. Lean internal checks stay.
- Eval backend = own Cloud Run `eval/backend`, background runs, site polls.
- `coded_span` support is an intended engine change in SP1; "no behavior change" applies to core extraction only.

## Cross-SP interface seams (owner -> consumers)
| Contract / file | Owner | Consumers | Notes |
|---|---|---|---|
| `TranscriptV1` model, `transcript.v1.schema.json`, `.txt` parser | SP1 defines (in miti) -> SP3 relocates to core | SP2, SP4, SP5, API, STT | Self-contained pydantic module (SP1 R2) |
| `coded_span` grammar (half-open, 0-based turns; ms) + report/`run_info.span.mode` | SP1 | SP2 (`gold.coded_span`), SP4 (`apply_coded_span` in core), SP5 | Explicit bad span = 422 `invalid_coded_span` |
| `RunContext` (+ `feedback`), `OnolysError/InputError`, LLM client, route presets, `safe_log` | SP3 (core) | SP4, SP5, MITI | Package `onolys_engine_core` (not `onolys_core`: banned by guard tests) |
| `Engine` ABC, `EngineResult{output, artifacts, run_info}`, `EngineRegistry`, `EngineInfo` | SP3 | SP4 (OneshotEngine, adds `variants`), SP5 | API builds registry in `api/.../engines.py`, explicit imports |
| `list_presets` + `prod` flags; `PROD_ENGINE`, `DEFAULT_PRESET` | SP3 | SP5 (options endpoint) | Prod = env settings |
| `validate_output`, `build_feedback`, value-free issues | SP3 | SP4 wrapper | PHI-safe |
| `run_validated` (validate + retry once, `output_invalid`) | SP4 (`api/jobs/validated_run.py`) | API run job; SP5 expects to call it | See mismatch M1 |
| `LLMRequest.response_schema`, `to_provider_schema`, `cost_usd` | SP4 (edits core llm; shared with SP3) | oneshot | |
| `run_info.usage` `{calls,input_tokens,output_tokens,cache_*,cost_usd}` | SP4 (R10) / MITI `RunInfo` | SP5 tokens + $ | See mismatch M3 |
| `gold.v1` schema, manifest format, bucket layout `datasets/<id>/<sid>/{transcript,gold}.json` | SP2 | SP5 | Bucket `onolys-eval-data-staging`; `uploads/`, `runs/` reserved for SP5 |
| `onolys_eval.metrics` (`Scores`, `compare`, `aggregate`, `compare.v1`), `scores_from_report` | SP2 | SP5, SP4 (projection) | R:Q, %CR recomputed from counts via pack formula on both sides |
| Shared files | root `pyproject.toml` (SP2 `eval/*`, SP3, SP4), `ci.yml` (SP3, SP4, SP5), `api/Dockerfile` (SP3, SP4), `infra/` (SP2 bucket, SP5 rest), core llm files (SP3 moves, SP4 edits) | | Sequence edits; no parallel edits to same file |

## Open items by SP ([OPEN] only)
**SP1**
- Mission says whole session if <=20 min else reproducible 20-min window; locked says absent = full. Recommend: engine full; API applies `default_window` for main app. Needs owner OK + `docs/mission.md` edit.
- `duration_max` 25 min is an error; raise for eval? Tune 6,000-word cap vs CASAA lengths.
- `.txt` `Name:` label false positives ("Note: ..."); is 8-speaker cap + gate enough?
- Transcript language when file omits it (default `en`, or ask in UI).
- `test_golden.py`/`test_span.py` impact (`good_practice.json` <=20 min or untimed); random-window tests move to `default_window`.
- Rating card `coded_span` (`from_s/to_s`) vs new report form: comparison code change?

**SP2**
- Staging creds: no `gcloud`/SA key on this machine; upload needs ADC (spike does not).
- Are CASAA transcripts excerpts of longer videos (assume transcript = span, `coded_span: null`).
- Coded vs uncoded PDF text match per utterance (coded = source of truth).
- Per-PDF parser accuracy / how many overrides (try `rounder`, `confirmed-smoker` first).
- Gold is one consensus coder; MAE ceiling-limited. Accept.
- Engine volley rules vs CASAA row coding may cause rule-mismatch, not model error.
- Exact `Report` field path for counts/globals; token/$ price source.

**SP3**
- `routes.default.yaml` MITI aliases (`miti_code`, `miti_globals`, `tips`) stay in core YAML; renaming changes fixture keys.
- `MITI_MODEL_*` / `MITI_LLM_*` env names in core: keep or add `LLM_*` aliases.
- `span.py` is MITI-coupled; core `apply_coded_span` (SP4 decides, see SP4 R3).
- Logger rename `"miti"` -> `"onolys"` affects Cloud Logging filters; keep `miti` until checked.
- `stt/` stays in miti; move when a second engine needs audio.
- Where eval gets "prod engine": `PROD_ENGINE` setting vs hard-coded `miti`.

**SP4**
- 1. "Same report schema" (locked) vs Decision 4 (model-authorable subset). Owner OK needed; fallback = full schema + deterministic provenance fill. Test: full schema in `json_schema` mode on Gemini + Claude.
- 2. Lean ignores `feedback`; retry reruns full pipeline (up to 8 min, 2x cost). Recommend `Engine.accepts_feedback` and skip retry when false; locked text says retry all.
- 3. Provider schema subsets (Gemini/Claude/OpenAI strict) may need per-provider rules.
- 4. Long transcripts: no chunking; >~6,000 words may hit output cap; route `max_output_tokens`.
- 5. `cost_usd` null for unpriced models; tokens only?
- 6. Quote/offset accuracy: recompute offsets via `locate` (needs core copy) or score counts only.

**SP5**
- Unit duration for lean (900 s deadline); 100+ unit runs at concurrency 4 may take >1 h.
- "(prod)" = staging `DEFAULT_PRESET`/`PROD_ENGINE` vs prod env's; default pass prod value via Terraform var.
- Speaker-gate logic location after SP1/SP3 (see M5).
- Per-engine `Scores` adapter location (see M2).
- STT cost + Vertex/Gemini quota roles for eval SA.
- Price table source when litellm cost absent (default `prices.yaml`).
- Shared auth package for `frontend/` + `eval/web` (default copy).
- Gold-file span vs chosen span differ (default use gold's span, warn).
- Uploaded real recordings retention/deletion undefined (PHI-like).
- Firebase custom-domain verification quirks for non-prod site.

## Owner tasks (not agent-doable)
- Confirm CASAA reuse terms (internal-only until confirmed).
- Staging GCP access/credentials on this machine (no `gcloud`, no SA key) and apply the bucket Terraform (SP2), later the eval Terraform (SP5).
- DNS record(s) for `eval.onolys.com` from Hosting custom-domain output; wait for cert.
- Confirm which preset is "prod" if it differs from staging `DEFAULT_PRESET`.
- Review curated `change_goal` per CASAA session (SP2).
- Confirm repo vars `ADMIN_STAGING_VITE_FIREBASE_*` set; LLM provider quota for large runs.
- Decide SP1 [OPEN] on mission default window (full vs 20-min) and SP4 [OPEN] 1-2.
- Later: submit MI-TAGS access form; confirm transcript-option product copy (SP1).

## Cross-PRD mismatches
- **M1 run_validated location.** SP5 R5 assumes it lives in `onolys_engine_core` or `onolys_api` and eval calls it. SP4 R8 puts it in `api/src/onolys_api/jobs/validated_run.py`. Eval backend must not import `onolys_api` (SP5 AC6 forbids API limits import; SP5 R11 image excludes `api/`). Fix: SP4 puts `run_validated` + `OutputInvalid` in `onolys_engine_core` (API imports it).
- **M2 Scores adapter ownership, 3 versions.** SP2 R6: `scores_from_report` in `onolys_eval.metrics`, "SP3/SP4 engines supply their own adapter". SP4 R7: one shared projection `scores(report)` for lean + oneshot. SP5 default: `onolys_eval.adapters` registry by engine name. Also SP2's mapper reads the lean report; oneshot emits a report subset. Pick one: `onolys_eval.adapters` keyed by engine, both engines' outputs share counts/globals field paths.
- **M3 usage/tokens naming.** SP4 R10: `run_info.usage{input_tokens,output_tokens,cache_*,cost_usd,calls}`. SP5 assumption: `run_info{tokens, cost_usd?}`. SP3 `EngineResult.run_info` is an untyped dict and says nothing about usage; MITI `RunInfo` shape vs `usage` dict not reconciled (who maps for lean). Fix: SP3 types `run_info["usage"]`; SP5 reads that.
- **M4 oneshot variants not in SP5.** SP4 R1/R7: engine needs `params["config"]` and registry `variants`; SP5 options/units only list "One-shot" with no config param; SP5 R5 does not pass `config`. Also SP4 needs a `oneshot` route in routes YAML for staging; SP5 env mentions `ROUTES_FILE` only.
- **M5 speaker-gate helper has no owner.** SP5 default assumes SP1 puts a pure helper in core. SP1 R5 implements the gate in API (`first_run`, `routes/speakers.py`); SP3 inventory does not move it to core.
- **M6 `accepts_feedback`.** SP4 [OPEN] 2 proposes an SP3 flag; SP3 `Engine` ABC lacks it, and SP4 R1 also edits SP3's registry (`variants`) without SP3 listing it. Locked "retry for all" vs recommendation unresolved.
- **M7 SP3 migration misses `eval/core`.** SP2 `run` imports `RunContext`/Turn from `onolys_miti`; SP3 moves those to core but its Owns list excludes `eval/core`. SP3 (or SP2 follow-up) must update SP2 imports; also SP3's `onolys_miti` re-exports nothing.
- **M8 oneshot in main app registry.** SP4 edits `api/.../engines.py` (the main API registry) to add oneshot, but locked decision is one-shot eval-site only; SP5 builds its own registry state. Ensure the main API does not expose it (separate registry builder or gating).
- **M9 core llm file ownership overlap.** SP3 moves `llm/*` to core; SP4 lists the same files as owned (raw-schema + cost). Sequential (SP4 after SP3) is fine but both claim them; also root `pyproject.toml`, `api/Dockerfile`, `ci.yml` edited by SP2/SP3/SP4/SP5.
- **M10 SP5 stale text.** SP5 header says "SP4 PRD not yet written, interface assumed"; SP4 exists now. Interface assumptions block should be replaced by M1-M3 resolutions.
- **M11 SP4 schema vs locked.** SP4 Decision 4 (report subset) contradicts the locked "same MITI report schema as lean"; comparable scoring relies on M2 projection. (Also listed as SP4 [OPEN] 1.)
- **M12 SP1 mission default vs locked** (SP1 [OPEN]): `docs/mission.md` says 20-min window; also SP2 relies on whole-session coding for CASAA (fine today: untimed).
