---
status: draft
summary: extract engine-agnostic basics to engines/core (onolys_engine_core), add Engine base class + registry with prod-marked engines/presets; MITI behaviour and golden keys unchanged
date: 2026-11-23
---
# PRD: engines/core, engine interface, registry (SP3)

**Repo/branch:** Onolys/onolys · `feat/miti-eval` · **Depends on:** SP1 (TranscriptV1, coded_span) · **Owns:** `engines/core/**` (new), moves out of `engines/miti/src/onolys_miti/{context,errors,retry,safe_log,transcript_v1,transcript_txt,llm/*}`, `engines/miti/src/onolys_miti/data/transcript.v1.schema.json`, import edits in `engines/miti/**`, `api/src/onolys_api/{presets.py,logs.py,adapters/real.py,adapters/fake.py,repo/*,config.py,engines.py (new)}`, `api/Dockerfile`, `pyproject.toml` (workspace), `.github/workflows/ci.yml` (core job), `docs/architecture.md`, `engines/miti/README.md`

## TL;DR
New workspace package `engines/core` (import `onolys_engine_core`) holds what any engine needs: transcript types, LLM client + route presets, run context, PHI-safe logging, JSON-schema validator. It also defines an `Engine` base class and a name-keyed registry that lists engines and presets with a "prod" flag. MITI becomes `MitiEngine(Engine)`; its output and golden fixtures do not change.

## Problem
- Everything lives in `onolys_miti`, and the API imports it directly: 14 API modules import `onolys_miti.*` (e.g. `adapters/real.py`, `presets.py`, `logs.py`) [verified: grep `from onolys_miti api/src`]. A second engine (`oneshot`, SP4) would have to depend on the MITI package for `RunContext`, the LLM client or `Turn`.
- The only entry is `run_miti(ctx, transcript, speaker_map, params, progress_cb)` [verified: `run.py:420`], called by name from `RealEvaluation` [verified: `adapters/real.py:132`]. No registry, no declared output schema.
- Presets are only reachable via `PresetResolver` in the API; "prod" is implicit (see R6).

## Goals / Non-Goals
| Goals | Non-Goals |
|---|---|
| `engines/core` with zero MITI imports (CI-enforced) | Moving `stt/`, `voice/` (not engine-agnostic yet; see [OPEN]) |
| `Engine` base class + `EngineRegistry`; MITI adopts it | The oneshot engine, the validation/retry loop (SP4) |
| Registry lists engines and presets with `prod` flags (for SP5) | Eval site, datasets, metrics |
| Golden tests pass unchanged; fixture keys unchanged | Changing prompts, routes, report shape |

## Requirements
**R1 Inventory.** Core vs MITI, by import evidence:
| Module | Class | Evidence |
|---|---|---|
| `context.py` (RunContext) | core | 12 lines, no imports; `Any`-typed llm/metrics |
| `errors.py` | core | `OnolysError/InputError/ConfigError`, no imports |
| `retry.py` | core | stdlib only; sole user `llm/litellm_client.py:17` |
| `safe_log.py` | core | has `register_fields()` for engine-specific names; logger name `"miti"` becomes `"onolys"`; MITI registers its fields via `rating.py`/`run.py` already |
| `llm/*` (client, types, fixture/stub/recording clients, errors, routes, warm) | core | imports only `errors` and `stt.select.locate_config_file` (`routes.py:17`); that helper moves to core |
| `transcript.py` Turn/Transcript | core as `TranscriptV1` (SP1 supersedes) | SP1 R2; drops the `stt.SttRun` import |
| `transcript_txt.py` parser, `transcript.v1.schema.json` | core | SP1 files, moved |
| JSON-schema validator | core, new | `jsonschema` already a dependency; only `rating.py:6` uses it today |
| `transcript.Span` (code-point offsets) | MITI | used by `locate.py`, tips quotes |
| `span.py`, `prepare.py`, `locate.py`, `normalize.py`, `code_pass.py`, `globals_pass.py`, `tips.py`, `tone.py`, `score.py`, `formula.py`, `rules.py`, `compare.py`, `rating.py`, `report.py`, `result.py`, `build.py`, `run_info.py`, `hashes.py`, `miti.py`, `check.py`, `data/` | MITI | import `miti`, `result`, `report` |
| `stt/`, `voice/` | stay in `onolys_miti` for now | `stt/base.py` imports `safe_log`, `transcript`; not needed by oneshot |
**R2 Package.** `engines/core/pyproject.toml` name `onolys-engine-core`, module `onolys_engine_core`, deps `pydantic, pyyaml, litellm, jsonschema`; `onolys-miti` depends on it; workspace glob `engines/*` already picks it up [verified: root `pyproject.toml` members]. The name avoids the banned `onolys_core` in `test_no_old_imports.py` / `test_naming_guard.py` [verified: both grep for it].
**R3 Engine interface** (see Architecture). Async `run(ctx, transcript, params, progress_cb) -> EngineResult`; declared `output_schema()` (JSON Schema dict); `speaker_map` travels in `params["speaker_map"]`, a plain dict, engines read what they need (oneshot may ignore).
**R4 Retry hook.** `RunContext.feedback: str | None` (default None). The API validation loop (SP4) re-calls `run` with `feedback` set to validation errors plus a fixed schema-conformance instruction; engines that make a final output call append it to their prompt, others ignore it. Core ships `validate_output(output, schema) -> list[ValidationIssue]` (path, message; capped count and length, no instance values, so no PHI) and `build_feedback(issues) -> str`.
**R5 Registry.** `EngineRegistry.register(engine)`, `get(name)` (unknown → `InputError`), `engines() -> [EngineInfo{name, version, prod, output_schema_id}]`. The API builds one in `api/src/onolys_api/engines.py` by explicit import (no entry-point magic) and passes the prod engine name from settings (new `PROD_ENGINE`, default `miti`).
**R6 Presets + prod flag.** Today a preset is a named route-override bundle in the routes YAML [verified: `routes.default.yaml` `presets:` default, claude]; the "prod" one is the env's `DEFAULT_PRESET` (Terraform `var.default_preset` → env var [verified: `infra/modules/environment/services.tf:10`]), falling back to `default`, else `config/<env>/routes.yaml` via `ROUTES_FILE`. Core adds `list_presets(registry, prod_name) -> [PresetInfo{name, prod, models}]` where `models` = route→`litellm_id` (no keys). `PresetResolver` (API) keeps the allowlist (`ENABLED_EXTRA_PRESETS`, `test-*`) and calls it; eval (SP5) lists all but `test-*`.
**R7 MITI adoption.** `MitiEngine.run` adapts to existing `run_miti`; `run_miti` stays as the function it wraps, signature unchanged. `output_schema()` = `report.schema.json` (`report.schema_path()`). Lean engine's internal checks stay.
**R8 Migration.** API and MITI import core types from `onolys_engine_core`; `onolys_miti` re-exports nothing (no users; breaking OK) except `run_miti`/`MitiEngine`. `RealEvaluation` resolves the engine through the registry. Dockerfile copies `engines/core`; CI gets a core job and an import-boundary test.
**R9 Fixture keys.** Moves must not alter `FixtureClient.key_for`.

## Architecture
```
api ──registry.get(name)──▶ Engine.run(ctx, transcript, params, progress_cb) ─▶ EngineResult
  │                              ├─ MitiEngine (onolys_miti)  ─ uses core llm/ctx/log
  │                              └─ OneshotEngine (SP4)
  └─ validate_output(result.output, engine.output_schema())  [SP4 loop; retry sets ctx.feedback]
core: transcript · llm · context · safe_log · validate · registry · presets
```
```python
class Engine(ABC):
    name: ClassVar[str]; version: ClassVar[str]
    @abstractmethod
    async def run(self, ctx: RunContext, transcript: TranscriptV1,
                  params: dict, progress_cb: ProgressCb | None = None) -> EngineResult: ...
    @abstractmethod
    def output_schema(self) -> dict: ...          # JSON Schema
class EngineResult(BaseModel): output: dict; artifacts: Any = None; run_info: dict
ProgressCb = Callable[[str, str], None]           # (stage, status); MITI narrows to Stage literals
```
Fixture-key safety: the key hashes tier, call_tag, system, user, cache_prefix and the response model's `__name__`, not module paths [verified: `fixture_client.py:25-37`]. Moving files is safe if route names (`miti_code`, `miti_globals`, `tips`), prompts and response-model class names stay put. Fixtures stay in `engines/miti/.../data/fixtures/golden`.

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| 1 | Package name | `onolys_engine_core` | `onolys_core` | banned by existing guard tests |
| 2 | Registry wiring | Explicit in API | Entry points | 2-3 engines; greppable |
| 3 | Feedback transport | `RunContext.feedback` | New `run` arg; params key | Signature stable; params stay user input |
| 4 | Result type | `output: dict` + artifacts | Generic over pydantic model | Uniform validation and Firestore storage |
| 5 | Prod flags | Computed at list time from settings | Flag in YAML | Prod already = env `DEFAULT_PRESET` |
| 6 | STT/voice | Stay in miti | Move to core | Not needed by SP4; avoids churn |
| 7 | Backwards re-exports | None | Shim | No users |

## Manual steps
- None. (Docker/CI edits are code. Prod's `DEFAULT_PRESET` unchanged.)

## Risks / Open Questions
- [OPEN] `routes.default.yaml` holds MITI route aliases (`miti_code`, `miti_globals`, `tips`) [verified]. Keep in core YAML for now (prod `config/<env>/routes.yaml` may reference them); later let engines declare aliases. Renaming changes fixture keys.
- [OPEN] Env vars `MITI_MODEL_*`, `MITI_LLM_RESPONSE_FORMAT`, `MITI_LLM_RECORD` live in core `llm/`. Keep names (no rename churn) or add `LLM_*` aliases?
- [OPEN] `span.py` coded-span resolution is MITI-coupled (imports `result.CodedSpan`). If oneshot needs the same turn/ms slicing, add a core `apply_coded_span` in SP4; SP1 final shape decides.
- [OPEN] `safe_log` logger rename `"miti"`→`"onolys"` affects Cloud Logging filters; keep `miti` until checked.
- [OPEN] `stt/` imports `transcript.Turn`; after SP1 it imports from core. Move STT to core once a second engine needs audio.
- [OPEN] Where eval (SP5) gets "prod engine": API setting `PROD_ENGINE` vs hard-coded `miti`.
- [RESOLVED: SP1 owns TranscriptV1 content] SP3 only relocates it.
- [DEFERRED] Entry-point plugin discovery; per-engine preset compatibility.

## Acceptance Criteria
- `engines/core` imports nothing from `onolys_miti` (test scans AST) and has its own CI job; `uv sync --frozen` works.
- `engines/miti/tests/test_golden.py` and all other miti tests pass; golden fixture file names are unchanged (no re-record).
- `MitiEngine` returns the same report as `run_miti`; its `output_schema()` validates the golden report via `validate_output`.
- `EngineRegistry.get("miti")` works; unknown name → `InputError`; `engines()` marks the configured prod engine.
- `list_presets` returns `default`/`claude` with `prod: true` on `DEFAULT_PRESET` (or `default`), no API keys, `test-*` excluded by the API layer.
- `validate_output` returns capped, value-free issues; `ctx.feedback` reaches the engine in a unit test.
- API passes its tests importing only `onolys_engine_core` (+ `onolys_miti` for MITI/stt/voice); API image builds and `import onolys_engine_core, onolys_miti` succeeds.
