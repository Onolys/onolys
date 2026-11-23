---
status: draft
summary: generic engines/oneshot (instructions + schema -> one structured model call), versioned MITI config, and one API-layer validate-and-retry wrapper for every engine; token/cost fields for SP5
date: 2026-11-23
---
# PRD: oneshot engine + API-layer output validation (SP4)

**Repo/branch:** Onolys/onolys · `feat/miti-eval` · **Depends on:** SP3 (Engine ABC, registry, `validate_output`, `RunContext.feedback`), SP1 (`TranscriptV1`, `coded_span`) · **Owns:** `engines/oneshot/**` (new, import `onolys_oneshot`), `engines/core/src/onolys_engine_core/validated_run.py` (new: `run_validated` + `OutputInvalid`, M1), edits to `api/src/onolys_api/{jobs/run.py,adapters/real.py,adapters/error_map.py}` (call `run_validated`, map `output_invalid`; `engines.py` is NOT edited: one-shot is not in the main api registry, M8), the oneshot adapter added to `onolys_eval.adapters` (module created by SP2, M2), `engines/core/src/onolys_engine_core/llm/{types,litellm_client,fixture_client}.py` (extends files SP3 creates: `response_schema` + cost, M9), root `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml` (edited after SP3, sequentially; the api Dockerfile is untouched, the eval backend image from SP5 includes `engines/oneshot`)

## TL;DR
`oneshot` is a generic engine: a named config (instructions + output JSON schema + small metadata) plus transcript and params go into ONE model call that must return JSON matching the schema. A second piece, `run_validated` in `onolys_engine_core` (called by the API and by eval/backend), validates every engine's output against `engine.output_schema()`; engines with `accepts_feedback=True` (one-shot) get one retry with the errors fed back, others fail directly. First config: `miti`, which outputs only the scoring subset (counts, 4 globals, tips).

## Problem
- No second engine exists, so lean MITI cannot be compared with a plain "ask the model once" baseline.
- The core LLM client only takes a pydantic `response_model` (`LLMRequest.response_model`, `model_validate`, `model_json_schema()` [verified: `llm/types.py`, `litellm_client.py:150,297`]); a config-driven schema has no model class.
- Output validation today is `report_validator()` in `jobs/run.py:62`, report-only, one shot [verified]; a bad report fails with no retry.
- `cost_usd` exists in `RunUsage` but is never computed (only the fake adapter sets it) [verified: grep `cost_usd`]. SP5 needs tokens + $.

## Goals / Non-Goals
| Goals | Non-Goals |
|---|---|
| Generic engine, configs picked by name from repo | UI-editable prompts; configs outside the repo |
| `miti` config scored on the same subset (counts, globals, tips) as lean, via the same `Scores` | Multi-call, tool use, chunking long transcripts |
| One validation+retry path for all engines | Fixing lean prompts or schema |
| Tokens/$ per run for SP5 | One-shot in the main app (eval site only) |

## Requirements
**R1 Package.** `engines/oneshot` (`onolys-oneshot`, module `onolys_oneshot`); depends on `onolys-engine-core` only, never `onolys_miti` (AST test, as SP3). `OneshotEngine(Engine)`, `name="oneshot"`; `params["config"]` selects the config (required; unknown name → `InputError`). The registry `variants` field is defined and listed by SP3 (M6); `OneshotEngine.variants()` just returns the config names (label "One-shot · MITI"), and the eval Engine dropdown lists them. SP5 passes `params["config"]` (M4). One-shot is registered only in eval/backend's registry, never in the main api registry (M8).
**R2 Config layout.** `engines/oneshot/src/onolys_oneshot/configs/<name>/{config.yaml, instructions.md, schema.json}` (package data, versioned in git; hash of all three in run_info).
`config.yaml`: `name`, `version`, `route` (route alias, default `oneshot`), `max_output_tokens`, `inputs: [transcript, params]` (which to render), `params_schema` (optional; validates `params` before the call), `schema_hint` (bool, see R5).
**R3 Prompt rendering.** System = `instructions.md` + a fixed core footer ("Return only JSON matching the schema; never invent quotes, speakers or timestamps"). User = rendered inputs, in order of `inputs`: `transcript` as plain lines `[<turn id>] <speaker/role>: <text>` (ids so output can cite turns; timestamps only if present), then `params` as a small JSON block (whitelisted keys, e.g. `change_goal`). Transcript is cut to `coded_span` first. Core `apply_coded_span` (decided here, per SP3): add `apply_coded_span(transcript, span) -> TranscriptV1` to core (pure turn/ms slicing, half-open per SP1 R7); MITI's `span.py` keeps its own `Span` offsets and may call it. Output echoes the span applied (`run_info`, not in the model schema).
**R4 Engine run.** Render, one `ctx.llm.complete` call, `temperature 0`, no engine-side retry on schema failure (the API wrapper owns it). If `ctx.feedback` is set, append it to the user message after the inputs. Return `EngineResult{output=<parsed dict>, run_info{engine, config, config_hash, span, usage, model, route, structured_output_mode}}`. `output_schema()` returns the config's schema.
**R5 Structured output.** Core `LLMRequest` gains `response_schema: dict | None` (mutually exclusive with `response_model`; parsed value is a plain `dict`, no pydantic). Mode follows the route (`MITI_LLM_RESPONSE_FORMAT`, `structured_output_mode`): `json_schema` sends the schema through a core `to_provider_schema()` (strip `$schema`, `title`, `default`, `minimum`; inline `$ref`; keep `required`/`additionalProperties`); `json_object` sends no schema, so `schema_hint: true` embeds the schema text in the system prompt. Default routes are `json_object` [verified: `llm-client.md`], so the hint is on for `miti`. Fixture key hashes the schema text instead of a model `__name__`. Truncation (`finish_reason=length`) stays a non-retried `LLMBadOutput`.
**R6 MITI config content.** `configs/miti/` is a copy, not an import: `instructions.md` is authored for one call from `prompts/{code,globals}_system.md` and the item definitions in `data/pack.yaml`; a test reads those files by path (data, not code) and fails if any pack item id (`gi persuade … confront`, `cct sst partnership empathy`) is missing from the instructions. Why copy: SP3 rule "core and oneshot never import MITI"; the lean prompts are shaped for volley-by-volley calls plus few-shots and can't be reused verbatim.
**R7 MITI schema.** Per Decision 4 and owner decision D1: `schema.json` = only the model-authorable scoring subset: behavior counts (the 10 pack item ids), the 4 globals, and `tips`. No instances/quotes/offsets, and fields software derives (`header`, `run_info`, `method`, `scorecard`, `layout`, `aggregates`, `reasons_audit`, summaries) are not asked of the model. `onolys_eval.adapters` (M2) has one adapter per engine, all producing `Scores`: SP2's lean adapter projects the lean report to the same subset, SP4 adds the one-shot adapter; R:Q and %CR are recomputed from counts by SP2's formula for gold, lean and oneshot, so engines are scored identically. Generated by `scripts/gen_miti_schema.py` from `report.schema.json`; a drift test (path-read) keeps it in sync.
**R8 Validation wrapper.** `onolys_engine_core.validated_run.run_validated(engine, ctx, transcript, params, progress_cb) -> EngineResult` (in core so both api and eval/backend call it, M1): (1) `engine.run`; (2) `issues = validate_output(result.output, engine.output_schema())`; (3) none → return; (4) else, only if `engine.accepts_feedback` (D2; otherwise raise `OutputInvalid` at once, `attempts=1`), once: `ctx.feedback = build_feedback(issues)` (errors + "Your last answer did not match the schema. Return the complete JSON object; every required field present, no extra fields, exact enum values"), re-run; (5) still issues → raise `OutputInvalid`. Called for every engine; The API's `RealEvaluation` and eval/backend call it instead of `run_miti`/`engine.run` directly; `report_validator()` in `run.py` is removed (the report schema now comes from `MitiEngine.output_schema()`). Lean's internal checks run first; the API check is additional. Issues are value-free (SP3 R4) so logs and Firestore carry no PHI.
**R9 Errors.** New public code `output_invalid` (retryable false) via `error_map.to_public`, message "The engine returned an answer that did not match its schema." Detail on the run: `validation{attempts, first_issues[path,message] (max 10)}`. Engine-raised `LLMBadOutput` keeps its existing mapping (the wrapper does not retry exceptions; the task queue's attempt limit does).
**R10 Usage/cost.** Each `EngineResult.run_info.usage` is the core typed `RunUsage{input_tokens, output_tokens, cost_usd?, calls}` defined by SP3 (M3; existing cache_* counters stay as optional extras); SP4 fills `cost_usd`. Core client computes `cost_usd` per call via `litellm.completion_cost`, `None` if the model is unpriced; wrapper sums both attempts (`validation.attempts` shows the retry; `usage` is the total). SP5 displays these and totals per row.
**R11 Tests.** Oneshot: golden fixtures (recorded replies via `FixtureClient`, `MITI_LLM_RECORD=1` to re-record) for `miti` on `good_practice.json` and one short session; offline unit tests for rendering, `coded_span`, config loading, hint/mode switching, schema validation of the recorded reply. Wrapper: stub engine with bad-then-good output (retry, `feedback` set, usage summed), bad-twice (`output_invalid`, no PHI in issues), good-first (no retry), lean `MitiEngine` golden report passes. Live check stays manual.

## Architecture
```
api task ─▶ registry.get(name) ─▶ run_validated ─▶ engine.run(ctx, transcript, params)
                                     │  issues? ─▶ ctx.feedback=… ─▶ run once more ─▶ still bad ─▶ output_invalid
OneshotEngine: config(name) ─▶ render(transcript[coded_span], params) ─▶ 1 LLM call (response_schema) ─▶ dict
core adds: LLMRequest.response_schema, to_provider_schema, cost_usd, apply_coded_span
```

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| 1 | MITI source | Copy into config + presence test | Import `onolys_miti` data | Keeps oneshot generic; drift caught by test |
| 2 | Dynamic schema | `response_schema` dict in core client | Build pydantic models from JSON | No codegen; validation is the core validator |
| 3 | `apply_coded_span` | New in core | Reuse MITI `span.py` | `span.py` imports `result.CodedSpan` (MITI) |
| 4 | MITI schema | Model-authorable scoring subset (counts, 4 globals, tips); lean projected to it for comparison (owner D1) | Full report schema | Model cannot author provenance/offsets; 35 KB, 45 nullable `anyOf`s, 29 defaults risk provider limits [verified: `report.schema.json`] |
| 5 | Where validation lives | `run_validated` in core, called by api and eval | Inside each engine | One path |
| 6 | Retry transport | `ctx.feedback`, one retry, only if `accepts_feedback` (owner D2) | Loop inside engine; retry all | SP3 R4; lean ignores feedback |
| 7 | Config selection | `params["config"]` + `variants` (SP3 registry) | One engine per config | Generic engine, one registry entry |
| 8 | Cost | litellm `completion_cost` at call time | Price table in repo | Already a dependency |

## Manual steps
- Record golden fixtures with live keys (`set -a; . ~/.config/onolys/keys.env`), once per prompt change.
- Terraform/env: add an `oneshot` route to the routes YAML for staging eval (code, not infra).

## Risks / Open Questions
- [RESOLVED: model-authorable subset (owner D1)] One-shot outputs only behavior counts, the 4 globals and tips; no instances/quotes/offsets, no provenance. Comparison and scoring use this same subset for every engine (the lean output is projected to it by its adapter). Supersedes "same MITI report schema" in the brainstorm. Cheapest check stays: send the subset schema in `json_schema` mode to Gemini and Claude presets.
- [RESOLVED: retry only when `Engine.accepts_feedback` is True (owner D2)] One-shot retries once with feedback; lean MITI (accepts_feedback False) fails directly with `output_invalid` on invalid output. Supersedes "retry once" for all engines in the brainstorm.
- [RESOLVED: simple `to_provider_schema` first] Strip unsupported keywords, inline `$ref`; add per-provider rules only if the Gemini/Claude measurement in tests fails. Per-provider strict-mode rules for OpenAI [DEFERRED].
- [RESOLVED: no chunking; set `max_output_tokens` in the `oneshot` route] The counts+globals+tips subset is small. `finish_reason=length` stays a non-retried `LLMBadOutput`; over-cap sessions already fail `session_too_long` (SP1).
- [RESOLVED: show tokens always; `cost_usd` null when unpriced] SP5 then shows a rough $ from its `prices.yaml` estimate, labelled as estimate.
- [RESOLVED: score counts only] No instances/quotes/offsets in the one-shot output, so no `locate` copy in core.
- [DEFERRED] Per-config few-shots; non-JSON-schema validation (rules); multi-input configs (e.g. ADHD) beyond transcript+params.

## Acceptance Criteria
- `onolys_oneshot` imports nothing from `onolys_miti` (AST test); package has CI job; Docker image builds.
- `OneshotEngine` with `config=miti` on a recorded fixture returns output that validates against its schema; unknown config → `InputError`; `coded_span` restricts rendered turns.
- `LLMRequest.response_schema` works in both modes; fixture key stable per schema text.
- `run_validated`: bad-then-good succeeds with `feedback` set and summed usage; bad-twice fails `output_invalid` with value-free issues; lean golden report passes unchanged; no engine bypasses it.
- `run_info.usage` carries tokens and `cost_usd` (null when unpriced) for lean and oneshot.
- Instructions-vs-pack test and schema drift test pass; `test_golden.py` for MITI unchanged.
