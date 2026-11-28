---
status: draft
summary: Replace engines/core + miti + oneshot with one `engine/` package (`onolys_engine`): YAML pipelines over a step + scoring library, typed state, one public surface, reshaped LLM layer; STT/voice/rating/scenarios move to api; same outputs proven by provider-payload and golden-report equivalence.
date: 2026-11-28
---
# PRD: 04 Engine package

Repo/branch: Onolys/onolys / `refactor/revamp` · Depends on: 01-legacy-purge (hard); 03-eval-split (hard: lands first and creates tag `engine-v0`, see D13) · Owns: `engine/` (new), `engines/` (deleted), root `pyproject.toml` + `uv.lock`, `api/Dockerfile` + `api/pyproject.toml` (deps/COPY lines), engine jobs and path lists in `.github/workflows/{ci,pr-preview}.yml`, `scripts/gen_miti_schema.py` (moves to `engine/tools/`), `web/package.json` (`gen:api` schema path, one token), one-line engine links in `README.md` + `AGENTS.md`, `config/*/routes.yaml` (route-name entries only), api import lines and the physical move of STT/voice/rating/scenarios/log setup into `api/`. Does not own: behaviour changes (05), api folder design (06), `infra/`/`config/` relocation (09), `docs/`.

## TL;DR
Three packages (`core`, `miti`, `oneshot`; 18.7k lines incl. tests) become one: `engine/`, import `onolys_engine`. A pipeline YAML per evaluation folder lists named steps; a runner loops them over one typed `State`. The API imports `Engine` plus one public types/errors surface (today 89 names from three packages). Product code that lives in the engine by accident (STT, voice, rating, scenarios, upload parsers, log setup) is moved into `api/` by `git mv`. This is a structural refactor: the bytes sent to the model and the reports built from the same replies stay identical, proven by a harness captured on the old code first. Behaviour changes are 05's.

## Problem
| Gap | Evidence |
|---|---|
| Four `Engine` entry points and a registry for a one-engine product | [verified: core `engine.py`+`registry.py`, `miti/engine.py`, `oneshot/engine.py`, `api/engines.py`] |
| API reaches inside: 45 names from core, 42 from miti (28 STT/voice), 2 from oneshot; imports private `_duration_ms` | [verified: AST count of `api/src`; `api/coded_span.py:7`. Brainstorm said 50/39/22: close, not exact] |
| Same facts in several places: 25 min in `pack.yaml`, `spans.py:71`, api `coded_span.py`; prompts and MITI definitions hand-copied into one-shot `instructions.md` | [verified: grep; `instructions.md` "adapted from code_system.md"] |
| Prompt-specific route names `miti_code`/`miti_globals`/`tips`/`oneshot`, one system+user message only, two route files that drift (16000 vs 64000 tokens) | [verified: `llm/types.py`, `routes.default.yaml` vs `config/prod/routes.yaml`] |
| Report built across 7 files; run loop, aggregate and stage emit tangled in `run.py` (454 lines) | [verified: file list; `run.py`] |
| Dead extension points: `validate_codes`/`compute_summary` hooks, `variants()`, `accepts_feedback` on a registry | [verified: `score.py:_apply_hook`, `score_run` passes none] |

## Goals / Non-Goals
**Goals:** one package, one `Engine`; steps + scoring as a library, YAML decides the run; one public boundary with a CI guard; LLM base `send` + wrappers; one `constants.py`; same outputs; tests mirror source.
**Non-goals:** any behaviour change (in-order context, numbered units, reflection volley break, one-shot redesign, `oneshot-split`: 05); api folder design, data layer, fakes (06); `config/` to `infra/<env>/` (09); eval code (03, 10); `docs/` edits (docs/architecture.md, reference pages stay stale until the docs freeze lifts); report schema changes.

## Requirements
**R1 Package.** `engine/` at repo root, dist `onolys-engine`, import `onolys_engine`, src layout. Root workspace `members = ["engine", "api", ...]`; `engines/` removed. Deps: pydantic, pyyaml, litellm, jsonschema, rapidfuzz. No STT/voice extras (move to api deps). One CI job `engine` replaces `core`/`oneshot`/`miti`; Dockerfile COPY lines collapse; `uv.lock` regenerated.
**R2 Layout** (the brainstorm tree, plus two additions marked +):
```
engine/src/onolys_engine/
  __init__.py  engine.py  runner.py  state.py+  public.py  constants.py
  steps/ scoring/ llm/ transcript/ logging/
  models/+   result + report pydantic models (split past 300 lines)
  protocols/miti-4.2.1/{protocol.yaml, definitions/*.md}
  evaluations/{miti,oneshot-single}/{pipeline.yaml, prompts/, fewshot/, report.yaml+, schemas/+, fixtures/}
engine/tools/   audit_report.py, regen_goldens.py, live_check.py (was check.py), probe_llm.py, gen_schemas.py (was gen_miti_schema.py)
engine/tests/   mirrors src; tests/golden/ (recorded replies + expected reports); tests/helpers/
```
**R3 Runner and steps.** `@step("name", reads=..., writes=...)` on `fn(state, **with) -> state`. Load time checks (minimal; [RESOLVED 2026-11-28: owner rule 17], no static slot-graph analysis): unknown step; unknown/missing `with` keys (signature binding, `inspect.signature`/pydantic `validate_call`); missing prompt/fewshot/protocol-id references; any `model` key (models never come from the step). `reads`/`writes` are only what `parallel` needs to merge branch results; no checker for read-before-write, disjointness or run scope (authoring errors show up in the toy-pipeline and golden tests). Control forms: `parallel:` and `repeat: n_runs` only. An entry may carry `stage: <name>`; the runner emits `started/done/failed` progress per stage (a step may mark its stage failed without raising, for degraded tips).
**R4 State.** One typed dataclass (see Architecture). `parallel` runs branches on shallow copies and merges only each branch's declared `writes` (deterministic branch order; `warnings` is append-only). `repeat: n_runs` runs the body per run on a fresh run-scope, appends a `RunResult` to `runs`, excludes a run that raises `StepFailed`/`LLMError` with a `run_failed` warning, raises `AllRunsFailed` if none survive, and starts runs 1..n after run 0's cache warm-up (today's `warmed` event).
**R5 Catalogue.** Every function maps as below; nothing is dropped except dead code.
| Today | Step / library | Reads | Writes |
|---|---|---|---|
| `prepare.mark_roles` | `prepare.mark_roles` | request, transcript | turns, warnings |
| `prepare.select_turns`, `span.py`, core `spans.apply_coded_span` | `prepare.select_span` | turns, request | turns, span, warnings |
| `run_input_checks` (5 kinds) + core `validate_portion_limits` | `checks.duration_max`, `duration_min`, `param_required`, `min_turns`, `portion_words` | turns, span, request | warnings or `InputError`/`SessionTooLong` |
| `rules.check_input` hook; `run._code` language warning | `checks.client_speaks_first`, `checks.language` | turns / transcript | warnings |
| `build_volleys` + context | `segment.volleys` | turns | volleys |
| `code_pass.py` (+ `locate`, `normalize`, `coverage`) | `llm.code_batches` (batch, warm-up, halve on bad output, locate, drop-rate retry) | volleys, request | instances, coverage [run] |
| `globals_pass.py` | `llm.rate_globals`; cap split out as `globals.cap` | turns, request / scores | scores [run] |
| `score.apply_rules`, `rules` | `rules.apply` (kinds `one_code_per_utterance`, `max_per_unit`, `exclusive_group` from protocol) | instances | instances [run] |
| `score.count_instances`; `compute_summaries` + `formula.py` | `score.count`; `score.formulas` | instances; counts, scores | counts; summaries [run] |
| `run.py` loop, `guarded`, `_one_run` | runner `repeat: n_runs` | | runs |
| `run.aggregate`, `representative_run` | `aggregate.runs` | runs | aggregate |
| `tips.py` + `tone.py` | `llm.tips` | aggregate, turns | tips, warnings |
| `build`, `report`, `result`, `compare`, `run_info`, `hashes`, `coverage` | `report.build` + `scoring/{counts,formulas,coverage,aggregate,compare,provenance}.py` + `models/` | all | report |
| core `engine`, `registry`, `validated_run`, `context`, `presets` | `Engine`, `Engine.evaluations()`; output validation + retry inside `Engine.run` | | |
| oneshot `engine`, `render`, `config` | `llm.oneshot`, `tips.limit`; the three config files become the evaluation folder | | |
Deleted: the two score hooks, `EngineRegistry`, `EngineInfo`, `variants()`, `accepts_feedback`, `CodePassFailed`/`GlobalsPassFailed` (one `StepFailed`, same `run_failed` code), `Turn` aliases (`Transcript`/`TranscriptTurn` only).
**R6 Protocol and prompts (rule 11).** `protocol.yaml` holds what the manual says: `id/version/source`, `speaker_roles`, `items[]` (id, kind, label, scale, evidence_min, `caps`), `rules[]` (the manual's counting rules, as today's `pack.yaml`), `summaries[]` (formulas, format, reference levels). `definitions/<id>.md` holds each item's definition + examples. Everything about running stays in the evaluation folder: `pipeline.yaml` (thresholds such as 25 min, batch 25, drop rate 0.20 live here only), `prompts/`, `fewshot/`, `report.yaml` (layout, tone list, compare flags). Prompts use placeholders (`{{codes}}`, `{{globals}}`, `{{counting_rules}}`) rendered from the protocol with Jinja2 (`StrictUndefined`, `keep_trailing_newline=True`; no hand-written renderer; rule 17 [RESOLVED 2026-11-28: owner rule 17]), so any evaluation gets definitions from one source. Rendering stays byte-identical to today's `_render_definitions`. One-shot's hand-written prose stays literal in 04 (replacing it changes behaviour and fixes issues 1-3: 05). The one-shot `schema.json` becomes a generated output of `tools/gen_schemas.py`. `rating.schema.json` is NOT generated and is deleted: 06 builds the rating schema from `Engine.protocol()` at startup (R8).
**R7 Public surface.** `onolys_engine/__init__.py` re-exports exactly `public.py` plus `Engine`; the API and tests import only `from onolys_engine import ...`. Boundary enforced by the linter already in use, not a custom AST test (rule 17 [RESOLVED 2026-11-28: owner rule 17]): ruff `lint.flake8-tidy-imports.banned-api` (TID251, [docs](https://docs.astral.sh/ruff/rules/banned-api/); module-level bans confirmed, the per-file-ignore for `engine/**` is to be verified in T2) bans `onolys_engine.<submodule>`; `import-linter` `forbidden` contract is the fallback if ruff cannot express it. 01's `test_miti_import_boundary.py` is deleted with it.
**R8 Move out of the engine** (`git mv` + import rewrite, no logic change, tests move with them; own file names kept so 06 can merge):
| From | To |
|---|---|
| `miti/stt/*`, `stt_providers.default.yaml` | `api/.../transcription/` |
| `miti/voice/*`, `voice_providers.default.yaml`, `data/scenarios/` | `api/.../voice/` |
| `miti/rating.py` | `api/.../rating/` (with today's `api/rating.py`); `rating.schema.json` is deleted once `ProtocolInfo` exists (T4); until then it stays beside `rating.py`, so tests stay green |
| core `transcript_txt.py`, `transcript_input.py` | `api/.../transcription/` |
| core `json_logging`, `log_context`, allowlist enforcement of `safe_log` | `api/.../logs.py` |
The engine keeps `log_event` and a static `LOG_FIELDS` (public); the API formatter allowlists `LOG_FIELDS` plus its own. Instead of moving the custom JSON formatter (`json_logging.py` 178, `log_context.py` 57, api `logs.py` 95), api logging uses `google-cloud-logging` `StructuredLogHandler` ([docs](https://cloud.google.com/python/docs/reference/logging/latest/handlers-structured-log)); the PHI allowlist (`safe_log.py`) stays as a `logging.Filter`; fields alerts rely on (`jsonPayload.status`, `request_id`) must be unchanged, checked against the alert filters in `infra/modules/environment/alerts.tf` (audit #7) [RESOLVED 2026-11-28: owner] adopt `StructuredLogHandler` (no `python-json-logger` fallback planned); a test asserts `jsonPayload.status` and `request_id` are emitted unchanged and the PHI `logging.Filter` still redacts. Rating needs item ids: it reads `Engine.protocol()` (public `ProtocolInfo`); 06 builds the rating schema from it at startup, so no schema file is kept.
**R9 LLM layer.** `send(messages, model, params)` with multi-turn `Message(role, content, cache=False)`; `send_json(...)` (schema or pydantic model); `send_cached(...)` (marks breakpoints, runs warm-up before fan-out). The client protocol is the single lowest seam; two implementations only: `FixtureClient` (replay; records when `LLM_RECORD` is set; can be told to raise a given error, replacing `FailingClient`/`RecordingClient`) and `StubClient` (api `ADAPTERS=stub`) (rule 9). The ~6 hand-written fake clients / fake `acompletion` shims in `engines/core/tests` (`test_llm*`, `test_retry`, `test_is_transient`), `engines/miti/tests` (`FakeClient`) and `engines/oneshot` (`FakeLLM`) are deleted and their tests re-pointed to this seam; `LiteLLMClient` payload tests use LiteLLM `mock_response` ([docs](https://docs.litellm.ai/docs/completion/mock_requests); error mocking not confirmed on that page, check in T3) instead of patching `acompletion` (audit #2) [RESOLVED 2026-11-28: owner rule 17]. Retries: replace `retry.py` + custom 429/529 backoff and `retry-after` parsing with LiteLLM `num_retries`/`retry_policy` ([docs](https://docs.litellm.ai/docs/routing), confirmed) or tenacity; keep deadline-awareness and the output-schema retry (product logic); `retry.py`/`test_retry.py` (263 lines) go (audit #6) [RESOLVED 2026-11-28: owner] adopt LiteLLM built-in retries (`num_retries`/retry policy, honours `Retry-After`): delete `retry.py`, `test_retry.py` and the custom 429/529 backoff and `retry-after` loop in `litellm_client.py`; keep only product logic (deadline-awareness, only if it is genuinely product behaviour, and the output-schema retry). A short T3 check shows a 429 with `Retry-After` is retried by LiteLLM; if LiteLLM cannot, T3 reports that and no custom fallback is planned. Routes become model specs per generic tier (`cheap|mid|strong`) plus presets; `miti_code`, `miti_globals`, `tips`, `oneshot` entries are deleted from both `config/*/routes.yaml`. Steps never name a model; a run resolves one spec from the request's preset/override, falling back to `constants.DEFAULT_*`. `routes.default.yaml` is deleted: its values become constants, and `ROUTES_FILE` only overrides what differs. Env: keep `LLM_PROVIDER/MODEL/EFFORT`, `ROUTES_FILE`, `MODELS_FILE`; rename `MITI_LLM_RESPONSE_FORMAT` to `LLM_RESPONSE_FORMAT` and `MITI_LLM_RECORD` to `LLM_RECORD` (`ci.yml:124,187`). Keep litellm providers, concurrency, cache warm-up (retries: see above).
**R10 Constants.** `constants.py` holds roles, stage names, text limits, locate thresholds, hash length, schema versions, env-var names, default model spec, `LOG_FIELDS`, error codes. Per-evaluation tunables live in `pipeline.yaml` only (one source). The API's early span check calls `Engine.check_input(transcript, coded_span)`, which runs the pipeline's role-free `checks.*`; the 25 min is no longer known to the API.
**R11 Equivalence.** See Architecture "Proof".

## Architecture
```yaml
# evaluations/miti/pipeline.yaml  (faithful port: today's thresholds, today's behaviour)
protocol: miti-4.2.1
steps:
  - {use: prepare.mark_roles, stage: code}
  - use: prepare.select_span
  - use: checks.duration_max      {with: {minutes: 25, severity: error}}
  - use: checks.min_turns         {with: {role: other, n: 3, severity: error}}   # + duration_min, param_required, subject turns
  - use: segment.volleys          {with: {min_other_words: 3, min_other_chars: 6, break_on: [question]}}
  - repeat: n_runs
    steps:
      - parallel:
          - use: llm.code_batches {with: {prompt: prompts/code.md, fewshot: fewshot/code.json, batch: 25, max_drop_rate: 0.20}}
          - use: llm.rate_globals {with: {prompt: prompts/globals.md, fewshot: fewshot/globals.json}}
      - use: globals.cap
      - use: rules.apply
      - use: score.count
      - use: score.formulas
  - use: aggregate.runs
  - {use: llm.tips, stage: tips, with: {prompt: prompts/tips.md, keep: 5}}
  - {use: report.build, stage: assemble, with: {layout: report.yaml}}
```
```yaml
# evaluations/oneshot-single/pipeline.yaml  (today's single call, same output shape)
output_retry: 1          # today's schema-feedback retry (accepts_feedback)
steps:
  - use: prepare.select_span
  - use: checks.duration_max {with: {minutes: 25, severity: error}}
  - use: checks.portion_words {with: {max: 6000}}
  - use: llm.oneshot {with: {instructions: prompts/instructions.md, schema: schemas/schema.json, max_tokens: 64000}}
  - use: tips.limit
```
Deviations from the brainstorm's illustrative sample, all to keep behaviour: no separate `verify.map_units` (drop-rate retry re-calls the model, so locate stays inside `llm.code_batches`; 05 may split it); `rules.apply` replaces four per-rule steps and `globals.cap` has no `with` (rules and caps are manual content, so the numbers live in `protocol.yaml`, not duplicated per evaluation); `break_on: [question]` only (reflection break is 05).
```python
@dataclass
class State:                      # slots; [run] = reset per repeat
    request: RunRequest; transcript: Transcript; ctx: RunCtx   # ctx: llm client, protocol, folder, metrics, deadline
    turns: list[RoleTurn]; span: SpanChoice; volleys: list[Volley]
    instances: list[Instance]; scores: dict[str, GlobalScore]; counts: dict; summaries: dict   # [run]
    runs: list[RunResult]; aggregate: Aggregate; tips: TipsArtifact; report: dict
    warnings: list[ResultWarning]  # append-only
@step("rules.apply", reads={"instances"}, writes={"instances"})
def apply(state: State) -> State: ...
```
```python
# public surface (names final; bodies are the T3/T4 work)
class Engine:
    @classmethod
    def load(cls, evaluation: str | Path) -> "Engine"        # name -> folder under evaluations/, or any folder
    @staticmethod
    def evaluations() -> list[str]                           # the whole "registry"
    def output_schema(self) -> dict;  def protocol(self) -> ProtocolInfo
    def check_input(self, transcript, coded_span) -> None    # early span/limits check for the API
    async def run(self, request: RunRequest, options: RunOptions | None = None) -> EngineResult
```
`public.py`: `RunRequest` (typed replacement for today's `params` dict: transcript, speaker_map, change_goal, language, coded_span, n_runs, seed, preset, model override), `RunOptions` (llm client, progress, deadline, request_id, feedback), `EngineResult` (`output`, `artifacts`, `run_info`: names unchanged to keep api churn small), `Transcript`, `CodedSpan`, `Tip`, `ProtocolInfo`, `PresetInfo` + `list_presets`, `ProgressCb/Stage/StageStatus`, `LLMClient` + `make_client`, `LOG_FIELDS`, and errors: `EngineError` (was `OnolysError`), `InputError`, `ConfigError`, `InvalidCodedSpan`, `SessionTooLong`, `OutputInvalid`, `RunAborted`, `AllRunsFailed`, `StepFailed`, `LLMError` family, `is_transient`.

**Proof (R11).** T0 runs before any source change, on the old code, and commits the harness into the old packages' tests: (1) *provider payload*: patch `litellm.acompletion`, run each fixture, store the normalized call list (sorted by call tag: messages, response format/schema, params); (2) *golden reports*: replay recorded replies through the full run and store the masked report (mask `created_at`, `request_id`, `run_info`, volatile header keys: today's `test_golden.py` rule). Fixtures (cut from six, [RESOLVED 2026-11-28: owner rule 17]; a refactor proof, not a permanent matrix): `good_practice` (already recorded; also run with `n_runs=3` for aggregate/representative run), `poor_practice` (cap path), `batch_edge` (27 volleys, batch boundary, warm-up); `short_session` and `sparse_evidence` stay only as their existing unit tests; replies come from `expected.yaml` via `regen_goldens --responses`. One-shot: the two recorded replies. After each later task the same suite must pass unchanged: payloads equal after flattening `(system, prefixes, user)` to messages; reports equal after masking. `run_info` provenance (pack/prompt hashes, version, engine id) changes by design and is checked only for shape: new reports validate against the unchanged `report.schema.json` and the api's `report.local.schema.json`. Recorded fixture hash keys change once (tier/call-tag removed) and are re-keyed with `regen_goldens` reusing response bytes.

**Migration (strangler; green at every commit; no shims survive).** The old packages shrink as modules move; callers are rewritten in the same commit.
| Task | Work | Gate |
|---|---|---|
| T0 | Baseline harness on old code (above) | old suites + new harness green |
| T1 | R8 moves out to `api/`; log split; api logging on `StructuredLogHandler` + PHI `logging.Filter`, with a test that `jsonPayload.status`/`request_id` are unchanged | api + remaining engine tests |
| T2 | Scaffold `engine/`, workspace, CI job, Dockerfile; `git mv` core leaf modules (transcript, errors, llm as-is, logging, text limits) into it; delete `engines/core`; rewrite miti/oneshot/api imports | all suites, import-boundary test |
| T3 | `state.py`, `runner.py`, registry, loader checks, `Engine`, `public.py`; toy-pipeline tests; short check that LiteLLM retries a 429 with `Retry-After` (R9) | engine unit tests |
| T4 | Port MITI: protocol + definitions, evaluation folder, steps/scoring/models, LLM reshape (R9), route entries removed, `retry.py`/`test_retry.py` and the custom 429/529 loop deleted (LiteLLM retries, R9), api to `Engine.run`/`check_input`/`protocol()`; delete `engines/miti` and `rating.schema.json` | T0 harness byte/report equal |
| T5 | Port one-shot (`oneshot-single`); `gen_schemas.py` (one-shot schema only); delete `engines/oneshot` | one-shot goldens, schema regen diff clean |
| T6 | `constants.py` sweep; env renames; README/AGENTS/web path; tests-mirror audit; boundary guard final | `git grep` criteria |
| T7 | Full gate (dev-ship) | all suites, api coverage gate |
Tests move with their code (73 test files: core 32, miti 38, oneshot 3); tests of deleted things (route names, hooks, registry, retry, JSON formatter) and the hand fakes (audit #2) are deleted; dev tools with no documented caller (check `probe_llm.py`, `audit_report.py`) are deleted in T6; names describe behaviour (rule 14).

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | Location/name | `engine/`, `onolys-engine`/`onolys_engine`, src layout | `engines/engine/`; keep `onolys_miti` name | Brainstorm tree and eval's git-pin example use `subdirectory = "engine"`; "miti" is one evaluation, not the engine |
| D2 | Boundary shape | `__init__` re-exports `public.py` + `Engine`; AST guard | API imports `onolys_engine.public`; trust review | One import path; matches 00's `from onolys_engine import Engine` example; guard replaces today's two boundary tests |
| D3 | Product code in engine | Move to api in T1, final brainstorm folders, no merging | Leave in `onolys_miti` until 06; temporary `api/staged/` | Engine must be clean now; one move, not two; 06 only consolidates. If 06 lands first, T1 skips what it moved |
| D4 | Logging split | api owns handler/context/allowlist enforcement; engine owns `log_event` + `LOG_FIELDS` | Export 14 logging names publicly; duplicate | Keeps the public surface small, no duplicate logic |
| D5 | Rules/caps location | In `protocol.yaml`, applied by `rules.apply` and `globals.cap` | One pipeline step per rule (brainstorm sample) | Manual facts would be copied into every evaluation (rule 11) |
| D6 | Verify step | Inside `llm.code_batches` | Separate `verify.map_units` | Drop-rate retry calls the model: separating changes behaviour |
| D7 | Slots + signature | Typed slot dataclass; reads/writes in `@step`; `with` keys checked by signature binding | Untyped dict state; per-step pydantic `With` models | Order and name errors fail at load with no extra declarations |
| D8 | Models | One model spec per run from tiers/preset/override; tier named only in config | Model per step in YAML | Prod and eval already apply one model to all calls; brainstorm says never from the step |
| D9 | Default routes | Constants + optional `ROUTES_FILE` override; delete `routes.default.yaml` | Keep two full files | The two files already drifted |
| D10 | Typed request | `RunRequest` replaces `params` dict | Keep dict | Removes `speaker_map.pop`, `engine`, `route_override` side channels |
| D11 | Equivalence oracle | Provider payload + masked golden report, captured on old code first | Hash-keyed fixtures only | Hash keys change when tier names go; payload equality is the stronger claim |
| D12 | `oneshot-split` | 05 creates its folder | 04 adds a stub | Needs new behaviour (parallel calls, third tips call) |
| D13 | Eval | 03 lands first, creates `engine-v0`; eval pins it (not in the workspace); `engine-v1` is cut after 04-06 for 10 | 04 edits eval imports | Eval is the only other caller of core/miti internals (44 names); editing it is 03's job |
| D14 | `engine/README.md` | Keep, rewritten (layout, tests, public surface) | Delete | It lives under the engine folder, so it is code-adjacent; `docs/` stays frozen |
| D15 | Evaluation identity | `run_info.engine` = evaluation name (`miti`, `oneshot-single`); `config` field dropped | Keep `oneshot` + `config: miti` | One name, no variants concept |

## Risks / Open Questions
- [RESOLVED 2026-11-28: owner] LiteLLM retries replace `retry.py` (audit #6): YES, use LiteLLM's built-in retries (`num_retries`/retry policy, honours `Retry-After`). Delete `retry.py`, `test_retry.py` and the custom 429/529 backoff/`retry-after` loop in `litellm_client.py`. Keep only product logic (deadline-awareness if genuinely product behaviour; output-schema retry). T3 keeps a short check that a 429 with `Retry-After` is retried by LiteLLM (owner accepted the default condition); if LiteLLM cannot, T3 reports it and no custom fallback is planned. Trade-off accepted: backoff timing may differ from today.
- [RESOLVED 2026-11-28: owner] Structured logging via google-cloud-logging `StructuredLogHandler` (audit #7): YES. PHI allowlist (`safe_log.py`) kept as a `logging.Filter`; alert fields (`jsonPayload.status`, `request_id`) must stay identical, proven by a test against the filters in `infra/modules/environment/alerts.tf`.
- Rules cited for this SP: 1, 3, 5, 7, 9, 10, 11, 14, 16, 17.
- Risk: payload equality fails on harmless ordering; mitigation: sort by call tag, compare messages not hashes.
- Risk: `parallel` merge differs from today's gather (warning order); mitigation: branch order fixed, covered by `batch_edge` golden.
- Risk: web/type-gen and CI path filters still name old paths; mitigation: AC grep.
- Docs under `docs/` keep stale `engines/...` paths until the freeze lifts [DEFERRED].
- [RESOLVED: 03 first] O1: 03 lands first (T2 needs eval out of the workspace) and creates `engine-v0`.
- [RESOLVED: pass through] O2: engine passes unknown preset keys (e.g. `stt:`) through as `PresetInfo.extra`; 06/09 decide whether STT choice moves to its own file.
- [RESOLVED: ship in wheel] O3: evaluation folders ship fixtures in the wheel (as today's `data/fixtures`), used by api tests; goldens stay in `engine/tests/golden/`.
- [RESOLVED: rename, drop old runs] O4: rename `oneshot:miti` to `oneshot-single` (D15); old stored runs dropped, no mapping.
- [RESOLVED: accepted] O5: provenance hashes (`run_info.pack.hash`, prompt hash keys) change value and keys; shape and schema unchanged.
- [RESOLVED: drop] O6: `oneshot-raw` (model-counted baseline) dropped, not kept as an evaluation.
- [RESOLVED: approved] Pipeline deviation from the brainstorm sample (no `verify.map_units` step; counting rules/caps in `protocol.yaml`).
- [RESOLVED: D13/AGENTS] 04 edits the engine link line in `AGENTS.md` and `README.md` only.
- [RESOLVED: locked] One pipeline YAML per evaluation; no re-export shims; `constants.py` per package; STT/voice/rating/scenarios leave the engine (moved to api as-is in T1, consolidated in 06; accepted).
- [DEFERRED] Verify/locate as its own step, reflection break, in-order context, numbered units: 05. Api folder consolidation, fakes: 06. `config/` to `infra/<env>/`: 09.

## Acceptance Criteria
- `engines/` does not exist; `git grep -nE "onolys_(engine_core|miti|oneshot)|engines/(core|miti|oneshot)"` outside `docs/` returns 0 (incl. `web/package.json`, workflows, Dockerfile, root `pyproject.toml`).
- `onolys_engine` exposes only R7 names; the boundary test fails on a planted `from onolys_engine.steps import x` in `api/`; `api/` has no import of `onolys_miti`-era private names.
- `engine/` contains no STT, voice, rating-card, scenario or upload-parser code; `api/` holds them at the R8 locations.
- `miti` and `oneshot-single` each run from one `pipeline.yaml`; `Engine.load("nope")`, an unknown step and a bad `with` key each fail at load with a named error (one test each).
- No route named `miti_code|miti_globals|tips|oneshot` in code or either `config/*/routes.yaml`; `git grep "complete_json\|LLMRequest(tier"` returns 0.
- Equivalence suite (R11) green: provider payloads and masked reports equal the T0 baselines for all listed fixtures, one-shot goldens pass, reports validate against the unchanged schemas.
- Every literal in R10's list appears once, in `constants.py` or a `pipeline.yaml`; no `25 * 60`, `0.20`, or `300`-style magic in steps.
- Tests mirror source under `engine/tests/`; no test name contains a task id; ruff clean; api coverage gate (94) and full suites pass in dev-ship.
