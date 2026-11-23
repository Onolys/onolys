---
stage: code
status: in-progress
summary: All five sub-projects implemented and individually reviewed PASS; full branch review in progress before PR/CI
date: 2026-11-23
---
# MITI eval site: design index

Branch `feat/miti-eval` (Onolys/onolys). Brainstorm: `brainstorm.md`. Governing decisions and PRD contracts below remain unchanged.

## Current implementation and review status

- All five sub-projects implemented; every planned task is done, including SP5 Task 12 at `d11ca6c`.
- SP1–SP5 individually reviewed PASS. SP5 fixes ea9afe5 and 789d4ff resolved all three initial findings after two rounds; final Bug Hunter, Security and Architect all PASS.
- Full branch three-persona review now in progress: `cf3a2a2207fc3846a39b435b8ac01c28ac24e558..789d4ff`. Next: resolve any full-review findings, then `dev-ship` PR/CI. Never merge automatically. Review fixes are not deployed; staging remains source 4808722/revision00005-hfh.
- Live Firebase staging app works at https://onolys-eval-staging.web.app. Task 12 evidence qualifies Gemini HTTP 402/default-provider acceptance, owner DNS/certificate, unregistered deploy workflow, and unverified actual in-flight tab-close proof. Implementation completion does not claim these acceptance conditions passed.
- Private CASAA data and sensitive evidence remain outside the public repository. See SP5 code/review artifacts and `code-2026-11-23-task12.md` for exact evidence.

## Sub-projects
| # | Name | Phase | Depends on | Owns | One-line scope |
|---|---|---|---|---|---|
| SP1 | `01-transcript-format-upload` | 1 | none | `engines/miti` transcript/span/prepare/run/result/run_info + schemas; `api` routes/transcript.py, sessions, runs, speakers, jobs; `web/features/upload`; `docs/contracts/public`; `docs/reference/transcript-format.md`; `docs/mission.md` full-session wording | `transcript.v1` (= Turn shape) + JSON schema, `.json`/`.txt` upload (PUT /transcript) in API + web, `coded_span` (ms or turn range, default full) |
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
- Code the full transcript by default everywhere (main app too, D3); sessions over the engine's 25-min `duration_max` get a clear error asking for a `coded_span`; dataset may specify a window. `coded_span` = `{start_ms,end_ms}` or `{start_turn,end_turn}`; absent = full.
- `transcript.v1` = engine `Turn` shape. STT writes it. No migration, breaking changes OK (no users).
- Upload `.json` / `.txt` (`T:`/`C:` or `Name:`) in main app + API; counts as 1 session; speaker gate if roles missing.
- Gold: session-level codes + optional per-utterance; compare session-level. Metrics: counts, 4 globals, R:Q, %CR, per-session diff, MAE.
- Run history (dataset, engine, git sha, preset/model, results) in staging Firestore. Uploads saved to private staging bucket, kept for reruns.
- Two modes: dataset (has gold) or single upload (audio or transcript, optional gold file).
- Two multi-selects: Engine (Human, MITI lean, One-shot) and Preset; "(prod)" labels; defaults pre-tick Human(dataset)/MITI lean (prod)/prod preset. Runs = engine x preset; Human ignores preset.
- 1 run per cell, option 3. Eval skips usage limits. No cost cap; show tokens + rough $.
- CLI spike first, then site.
- `engines/core` engine-agnostic only; `Engine` base class with overridable `run(ctx, transcript, params)` + declared output schema; registry by name.
- `oneshot` generic (instructions + schema -> 1 call); MITI config versioned in repo, by name, not UI-editable; outputs only the scoring subset (behavior counts, 4 globals, tips) and comparison uses that subset for every engine (lean projected to it) (D1, supersedes "same report schema"); one-shot is eval-site only (registered only in eval/backend, M8).
- Validation via `run_validated` (in `onolys_engine_core`, called by api and eval/backend) for all engines; retry once with errors only for engines with `accepts_feedback=True` (one-shot); lean MITI fails directly (D2). Lean internal checks stay.
- Prod = preset named by the prod env `DEFAULT_PRESET` (infra var `default_preset`, currently `default`: Gemini hydrogen cheap / neon mid+strong, reasoning_effort low) + engine MITI lean; eval reads these from config, not hardcoded (D4).
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
| `run_validated` (validate + retry once if `accepts_feedback`, `output_invalid`) | SP4, in `onolys_engine_core` | API run job; eval/backend | M1 |
| `LLMRequest.response_schema`, `to_provider_schema`, `cost_usd` | SP4 (edits core llm; shared with SP3) | oneshot | |
| `RunUsage{input_tokens,output_tokens,cost_usd?,calls}` in `EngineResult.run_info.usage` | SP3 defines, SP4 fills cost | SP5 tokens + $ | M3 |
| `gold.v1` schema, manifest format, bucket layout `datasets/<id>/<sid>/{transcript,gold}.json` | SP2 | SP5 | Bucket `onolys-eval-data-staging`; `uploads/`, `runs/` reserved for SP5 |
| `onolys_eval.metrics` (`Scores`, `compare`, `aggregate`, `compare.v1`), `onolys_eval.adapters` (lean: SP2; oneshot: SP4) | SP2 | SP5, SP4 | R:Q, %CR recomputed from counts via pack formula on both sides |
| Shared files | root `pyproject.toml` (SP2 `eval/*`, SP3, SP4), `ci.yml` (SP3, SP4, SP5), `api/Dockerfile` (SP3, SP4), `infra/` (SP2 bucket, SP5 rest), core llm files (SP3 moves, SP4 edits) | | Sequence edits; no parallel edits to same file |

## Open items
None. All former [OPEN] items are resolved or [DEFERRED] in the PRDs (see each PRD's Risks section). Owner-level choices applied: D1 scoring-subset output, D2 retry only for `accepts_feedback`, D3 full session everywhere (`docs/mission.md` wording update is in SP1 scope), D4 prod = `default` preset + MITI lean read from config, D5 CASAA terms OK and GCP access available.

## Owner tasks (not agent-doable)
- Review curated `change_goal` per CASAA session (SP2).
- Confirm repo vars `ADMIN_STAGING_VITE_FIREBASE_*` set; raise LLM provider quota if large runs hit limits.
- Later (not blocking build): DNS record(s) for `eval.onolys.com` from the Hosting custom-domain output, wait for cert; submit MI-TAGS access form; confirm transcript-option product copy (SP1).
- Not owner tasks anymore: CASAA terms (confirmed OK); GCP access (ADC via `~/.config/gcloud` on this machine, terraform at `/root/.local/bin/terraform`, `gcloud` CLI binary not installed: install or use ADC). Applying the bucket (SP2) and eval (SP5) Terraform are implementation steps.

## Cross-PRD mismatches: Resolved
Applied to the PRDs on 2026-11-23.
- **M1 `run_validated` location.** Lives in `onolys_engine_core` (SP4 owns it there); api and eval/backend both call it.
- **M2 Scores extraction.** Single home `onolys_eval.adapters`: SP2 creates the module + MITI lean adapter, SP4 adds the oneshot adapter; all produce `Scores` for metrics.
- **M3 Usage naming.** Typed `RunUsage{input_tokens, output_tokens, cost_usd?, calls}` in core, defined by SP3 in `EngineResult.run_info`, cost filled by SP4; SP5 uses those names.
- **M4 Variants.** Registry exposes engine variants; eval Engine dropdown lists "One-shot · MITI" etc.; SP5 passes `params["config"]`.
- **M5 Speaker gate helper.** Txt parsing + role inference lives in core (SP3 relocates it from SP1's module); api keeps the gate UI/state.
- **M6 `accepts_feedback`.** Added to SP3's Engine ABC; `variants` listed in SP3 registry.
- **M7 eval imports.** SP2 imports `Turn`/`RunContext` from `onolys_miti` initially; SP3 Owns includes updating eval/core imports to core.
- **M8 One-shot registry.** NOT registered in the main api registry; only in eval/backend.
- **M9 Ownership.** SP3 owns core `llm/*` creation; SP4 extends (`response_schema`, cost). Shared root files (`pyproject.toml`, `uv.lock`, `ci.yml`, Dockerfiles) edited sequentially in SP order.
- **M10 SP5 stale text.** Replaced with the real SP4 interfaces (M1-M3).
- **M11 SP4 schema vs locked.** Resolved by D1 (scoring subset for every engine).
- **M12 Mission default vs locked.** Resolved by D3 (full session everywhere; mission.md wording update added to SP1 scope).
