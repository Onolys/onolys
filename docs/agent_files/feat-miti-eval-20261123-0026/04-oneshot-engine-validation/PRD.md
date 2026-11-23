---
status: draft
summary: generic engines/oneshot (instructions + schema -> one structured model call), versioned MITI config, and one API-layer validate-and-retry wrapper for every engine; token/cost fields for SP5
date: 2026-11-23
---
# PRD: oneshot engine + API-layer output validation (SP4)

**Repo/branch:** Onolys/onolys · `feat/miti-eval` · **Depends on:** SP3 (Engine ABC, registry, `validate_output`, `RunContext.feedback`), SP1 (`TranscriptV1`, `coded_span`) · **Owns:** `engines/oneshot/**` (new, import `onolys_oneshot`), `api/src/onolys_api/jobs/validated_run.py` (new), edits to `api/src/onolys_api/{jobs/run.py,adapters/real.py,adapters/error_map.py,engines.py}`, `engines/core/src/onolys_engine_core/llm/{types,litellm_client,fixture_client}.py` (raw-schema + cost additions, shared with SP3), root `pyproject.toml`, `api/Dockerfile`, `.github/workflows/ci.yml`

## TL;DR
`oneshot` is a generic engine: a named config (instructions + output JSON schema + small metadata) plus transcript and params go into ONE model call that must return JSON matching the schema. A second piece, in the API, validates every engine's output against `engine.output_schema()`, retries once with the errors fed back, then fails the run. First config: `miti`.

## Problem
- No second engine exists, so lean MITI cannot be compared with a plain "ask the model once" baseline.
- The core LLM client only takes a pydantic `response_model` (`LLMRequest.response_model`, `model_validate`, `model_json_schema()` [verified: `llm/types.py`, `litellm_client.py:150,297`]); a config-driven schema has no model class.
- Output validation today is `report_validator()` in `jobs/run.py:62`, report-only, one shot [verified]; a bad report fails with no retry.
- `cost_usd` exists in `RunUsage` but is never computed (only the fake adapter sets it) [verified: grep `cost_usd`]. SP5 needs tokens + $.

## Goals / Non-Goals
| Goals | Non-Goals |
|---|---|
| Generic engine, configs picked by name from repo | UI-editable prompts; configs outside the repo |
| `miti` config scored on the same contract as lean | Multi-call, tool use, chunking long transcripts |
| One validation+retry path for all engines | Fixing lean prompts or schema |
| Tokens/$ per run for SP5 | One-shot in the main app (eval site only) |

## Requirements
**R1 Package.** `engines/oneshot` (`onolys-oneshot`, module `onolys_oneshot`); depends on `onolys-engine-core` only, never `onolys_miti` (AST test, as SP3). `OneshotEngine(Engine)`, `name="oneshot"`; `params["config"]` selects the config (required; unknown name → `InputError`). Registry exposes the available config names so SP5 can list them (`engines()` entry gains `variants: [config names]`; small SP3 edit).
**R2 Config layout.** `engines/oneshot/src/onolys_oneshot/configs/<name>/{config.yaml, instructions.md, schema.json}` (package data, versioned in git; hash of all three in run_info).
`config.yaml`: `name`, `version`, `route` (route alias, default `oneshot`), `max_output_tokens`, `inputs: [transcript, params]` (which to render), `params_schema` (optional; validates `params` before the call), `schema_hint` (bool, see R5).
**R3 Prompt rendering.** System = `instructions.md` + a fixed core footer ("Return only JSON matching the schema; never invent quotes, speakers or timestamps"). User = rendered inputs, in order of `inputs`: `transcript` as plain lines `[<turn id>] <speaker/role>: <text>` (ids so output can cite turns; timestamps only if present), then `params` as a small JSON block (whitelisted keys, e.g. `change_goal`). Transcript is cut to `coded_span` first. Same core `apply_coded_span` that SP3 flagged [OPEN]: decide here: add `apply_coded_span(transcript, span) -> TranscriptV1` to core (pure turn/ms slicing, half-open per SP1 R7); MITI's `span.py` keeps its own `Span` offsets and may call it. Output echoes the span applied (`run_info`, not in the model schema).
**R4 Engine run.** Render, one `ctx.llm.complete` call, `temperature 0`, no engine-side retry on schema failure (the API wrapper owns it). If `ctx.feedback` is set, append it to the user message after the inputs. Return `EngineResult{output=<parsed dict>, run_info{engine, config, config_hash, span, usage, model, route, structured_output_mode}}`. `output_schema()` returns the config's schema.
**R5 Structured output.** Core `LLMRequest` gains `response_schema: dict | None` (mutually exclusive with `response_model`; parsed value is a plain `dict`, no pydantic). Mode follows the route (`MITI_LLM_RESPONSE_FORMAT`, `structured_output_mode`): `json_schema` sends the schema through a core `to_provider_schema()` (strip `$schema`, `title`, `default`, `minimum`; inline `$ref`; keep `required`/`additionalProperties`); `json_object` sends no schema, so `schema_hint: true` embeds the schema text in the system prompt. Default routes are `json_object` [verified: `llm-client.md`], so the hint is on for `miti`. Fixture key hashes the schema text instead of a model `__name__`. Truncation (`finish_reason=length`) stays a non-retried `LLMBadOutput`.
**R6 MITI config content.** `configs/miti/` is a copy, not an import: `instructions.md` is authored for one call from `prompts/{code,globals}_system.md` and the item definitions in `data/pack.yaml`; a test reads those files by path (data, not code) and fails if any pack item id (`gi persuade … confront`, `cct sst partnership empathy`) is missing from the instructions. Why copy: SP3 rule "core and oneshot never import MITI"; the lean prompts are shaped for volley-by-volley calls plus few-shots and can't be reused verbatim.
**R7 MITI schema.** See Decision 4 and [OPEN] 1. Default: `schema.json` = the lean report's model-authorable part (`globals`, `behaviours` counts + `instances{turn_id,start,end,quote,rationale}`, `tips`); fields that software derives (`header`, `run_info`, `method`, `scorecard`, `layout`, `aggregates`, `reasons_audit`, summaries) are not asked of the model. SP2's metrics read one shared projection `scores(report)` (counts, globals; R:Q and %CR recomputed from counts by SP2's formula for gold, lean and oneshot), so both engines are scored identically. Generated by `scripts/gen_miti_schema.py` from `report.schema.json`; a drift test (path-read) keeps it in sync.
**R8 API validation wrapper.** `jobs/validated_run.py::run_validated(engine, ctx, transcript, params, progress_cb) -> EngineResult`: (1) `engine.run`; (2) `issues = validate_output(result.output, engine.output_schema())`; (3) none → return; (4) else once: `ctx.feedback = build_feedback(issues)` (errors + "Your last answer did not match the schema. Return the complete JSON object; every required field present, no extra fields, exact enum values"), re-run; (5) still issues → raise `OutputInvalid`. Called for every engine; `RealEvaluation` calls it instead of `run_miti` directly; `report_validator()` in `run.py` is removed (the report schema now comes from `MitiEngine.output_schema()`). Lean's internal checks run first; the API check is additional. Issues are value-free (SP3 R4) so logs and Firestore carry no PHI.
**R9 Errors.** New public code `output_invalid` (retryable false) via `error_map.to_public`, message "The engine returned an answer that did not match its schema." Detail on the run: `validation{attempts, first_issues[path,message] (max 10)}`. Engine-raised `LLMBadOutput` keeps its existing mapping (the wrapper does not retry exceptions; the task queue's attempt limit does).
**R10 Usage/cost.** Each `EngineResult.run_info.usage` = `{calls, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd}` (same shape as `RunUsage`). Core client computes `cost_usd` per call via `litellm.completion_cost`, `None` if the model is unpriced; wrapper sums both attempts (`validation.attempts` shows the retry; `usage` is the total). SP5 displays these and totals per row.
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
| 4 | MITI schema | Model-authorable subset of report | Full report schema | Model cannot author provenance/offsets; 35 KB, 45 nullable `anyOf`s, 29 defaults risk provider limits [verified: `report.schema.json`] |
| 5 | Where validation lives | API wrapper | Inside each engine | One path; locked |
| 6 | Retry transport | `ctx.feedback`, one retry | Loop inside engine | SP3 R4 |
| 7 | Config selection | `params["config"]` + `variants` in registry | One engine per config | Generic engine, one registry entry |
| 8 | Cost | litellm `completion_cost` at call time | Price table in repo | Already a dependency |

## Manual steps
- Record golden fixtures with live keys (`set -a; . ~/.config/onolys/keys.env`), once per prompt change.
- Terraform/env: add an `oneshot` route to the routes YAML for staging eval (code, not infra).

## Risks / Open Questions
- [OPEN] 1. "Same report schema" (locked) vs Decision 4 subset. Needs owner OK. Fallback: config schema = full report schema, API validates it, and a deterministic post-step fills provenance. Cheapest test: send the full schema in `json_schema` mode to the Gemini and Claude presets and read the errors.
- [OPEN] 2. Lean ignores `feedback`; a retry reruns the whole pipeline (up to 8 min, double cost) with no new information. Recommend `Engine.accepts_feedback` (SP3 flag) and skip the retry when false; locked text says retry for all.
- [OPEN] 3. Provider schema subsets (Gemini vs Claude vs OpenAI strict) may need per-provider rules in `to_provider_schema`; measure.
- [OPEN] 4. Long transcripts: no chunking; a one-shot over ~6,000 words (SP1 cap) may exceed output tokens (`finish_reason=length`). Route `max_output_tokens`?
- [OPEN] 5. `cost_usd` for unpriced/preview models stays null; show tokens only?
- [OPEN] 6. Quote/offset accuracy: oneshot can't guarantee `start/end`; do we recompute offsets by locating `quote` in the turn text (reuse of MITI `locate`, would need a core copy) or score counts only?
- [DEFERRED] Per-config few-shots; non-JSON-schema validation (rules); multi-input configs (e.g. ADHD) beyond transcript+params.

## Acceptance Criteria
- `onolys_oneshot` imports nothing from `onolys_miti` (AST test); package has CI job; Docker image builds.
- `OneshotEngine` with `config=miti` on a recorded fixture returns output that validates against its schema; unknown config → `InputError`; `coded_span` restricts rendered turns.
- `LLMRequest.response_schema` works in both modes; fixture key stable per schema text.
- `run_validated`: bad-then-good succeeds with `feedback` set and summed usage; bad-twice fails `output_invalid` with value-free issues; lean golden report passes unchanged; no engine bypasses it.
- `run_info.usage` carries tokens and `cost_usd` (null when unpriced) for lean and oneshot.
- Instructions-vs-pack test and schema drift test pass; `test_golden.py` for MITI unchanged.
