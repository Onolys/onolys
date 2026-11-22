---
status: approved
summary: New lean `engines/miti` (dist `onolys-miti`, import `onolys_miti`): MITI-hardcoded coding + tips + no-rating report, plus the STT/voice/LLM infra api needs; side by side with old packages.
date: 2026-11-22
---
# PRD: SP01 engines/miti lean MITI engine

Repo/branch: Onolys/onolys (local `iaudit`) / `feat/miti-lean-engine` · Depends on: none (Phase 1) · Blocks: SP02 (api switch), SP04 (admin, indirectly), SP05 (cleanup)
Owns: `engines/miti/**` (src, tests, data, schemas, pyproject), root `pyproject.toml`/`uv.lock` only if the glob needs it (it does not: `engines/*`). Not owned: `api/`, `web/`, `admin/`, old `engines/{core,paudit,evaluation,eaudit}` (untouched), CI files (SP05).

## TL;DR
One package, `onolys_miti`, copied (not moved) from paudit + core + evaluation with MITI hardcoded. `run_miti(ctx, transcript, speaker_map, params, progress_cb) -> MitiOutput(report, artifacts)` does span selection + code pass + globals pass (n_runs averaged) + basic tips + report assembly, producing the no-rating report. No user-entered span: `run_miti` picks it from the transcript duration (whole session if <= 20 min, else a random 20-min window seeded by session id) and records it. Everything named paudit/iaudit/eaudit is renamed to miti (routes, env vars, run_info key, artifacts). STT Chirp, Gemini Live voice, LLM client/routes, transcript, errors, safe_log etc. come along so api never imports `onolys_core`. Old packages stay until SP05.

## Problem
- Three engines deep (core, paudit, evaluation) + eaudit for a product that now only does MITI coding. Pack loader, schemas, hooks, compare/reasons, eaudit turn helpers are dead weight. [verified: api imports `onolys_core.*`, `paudit.{pack,engine,code_pass,globals_pass,result}`, `onolys_evaluation.{api,report,rating}`; `to_eaudit_turns` used only by `onolys_evaluation/reasons.py`]
- Packaging/CI/test surface is 3 packages (core 44 py, paudit 28, evaluation 25) to ship one report.

## Goals / Non-Goals
**Goals**
- Self-contained `engines/miti`: no import of `onolys_core`, `paudit`, `onolys_evaluation`, `eaudit` (grep test).
- Same coding behaviour as paudit (prompts, rules, formulas, thresholds untouched) so coding parity is provable.
- No-rating report with the same content as today; the only shape changes are the renames in R6 (breaking changes are fine: nobody uses prod, no backward compat, old data may be wiped).
- Coded span chosen by the engine, never by the user (R7).
- Basic tips kept.
- Testable offline (fixture LLM) with its own CI-ready test command.

**Non-Goals**
- Deleting old packages, CI jobs, docs (SP05); editing api/web/admin (SP02-04).
- Protocol-agnostic pack layer; clinician-rating comparison, reasons audit, eaudit.
- Prompt or MITI-logic changes; official MITI claims.
- Backward compatibility with old reports, old stage names or old route/env names (owner 2026-11-22).
- Richer tips (wait for user feedback).

## Requirements
**R1. Layout** (`engines/miti/src/onolys_miti/`; source -> dest; copy then edit)

| Module | From | Notes |
|---|---|---|
| `code_pass.py`, `globals_pass.py`, `prepare.py`, `score.py`, `formula.py`, `result.py` | paudit same names | `Pack` arg replaced by module constant `MITI` (frozen, loaded once from data); `pack.pack_hash`/`facts()` kept as `MITI.hash` |
| `span.py` (new, ~30 lines) | none | `select_coded_span(transcript, seed) -> SpanChoice` (R7) |
| `run.py` | paudit `engine.py` (run loop, aggregate, n_runs, `AllRunsFailed`, prompt_hashes) + evaluation `api.py` (stage/progress/usage wiring, sans eaudit) | public `run_miti` |
| `tips.py`, `tone.py` (banned-word lint only) | evaluation | tips route + prompt from data |
| `report.py` (models + schema), `build.py` | evaluation `report.py`, `build_report` + the no-rating subset of `compare.py` (`compare_item`->`not_rated`, `explain`, `compare_summaries` Onolys-only, `representative_instances`) | see R3 |
| `rating.py` | evaluation `rating.py` (`validate_rating`, `is_no_rating`) | api's rating endpoints stay (SP02); ~136 lines; only reason to ship `rating.schema.json` |
| `rules.py` | `protocols/miti-4.2.1/rules.py` | plain import; hooks.py dynamic loading dropped |
| `stt/`, `voice/`, `llm/` (+ `routes.default.yaml`, `stt_providers.default.yaml`, `voice_providers.default.yaml`) | core same | `llm/smoke.py`, `stt/check.py` kept only if a test uses them |
| `transcript.py`, `errors.py`, `safe_log.py`, `locate.py`, `normalize.py`, `retry.py`, `run_info.py`, `context.py` (`RunContext` only) | core | `to_eaudit_turns`/`from_eaudit_turns`, `Engine` protocol, `PackRef`, `EngineResult` dropped |
| `data/` | `protocols/miti-4.2.1/{pack.yaml,rules?,prompts/*,report.yaml,rating.schema.json,fixtures,scenarios}` | byte-identical copies (see D3) |

Dropped, with evidence: `pack.py` loader/schema validation (one pack, loaded at import); `hooks.py` (dynamic rules import); `stub.py` and `cli.py` (admin-only, SP04 removes `paudit_routes`) [verified: only `admin/backend` imports `paudit.stub`]; `check.py` x2 (live harnesses) re-created as one small `python -m onolys_miti.check` (R4); `compare.py` rating diff, `reasons.py`, eaudit stage; `onolys_core.engine.Engine/PackRef` (api's `PackRef` use goes with SP02). Re-grep before dropping each module during coding.

**R2. Public API**
```python
async def run_miti(ctx: RunContext, transcript: Transcript, speaker_map: dict[str,str],
                   params: dict, progress_cb: ProgressCb | None = None) -> MitiOutput
class MitiOutput: report: Report; artifacts: Artifacts(code: MitiResult, tips: TipsArtifact|None)
Stage = Literal["code", "tips", "assemble"]   # + StageStatus unchanged
```
- Params: `change_goal`, `language`, `n_runs` (default 1), `preset`, `code_version`, `seed` (str, the session id; default: `ctx` request id); `speaker_map` merged in as today. **`coded_span` is no longer a param**: callers cannot pass one; `run_miti` computes it (R7). STT params, LLM routes/presets stay parameters (`resolve_preset`, `LiteLLMClient`, `SttParams`, `GoogleChirp3` re-exported from `onolys_miti.{llm,stt}`).
- Errors (all `OnolysError`): `InputError`, `ConfigError`, `AllRunsFailed`, `CodePassFailed`, `GlobalsPassFailed`, `LLMError` family, `SttProviderError`; same `code` strings so `error_map.py` needs only import changes. `PackError` is not ported unless `error_map.py` needs it [RESOLVED: implementer verifies at coding time, default: not ported; api drops its branch].
- Progress: stages `code` (code+globals passes together; paudit never reported them separately), `tips`, `assemble`. SP02 narrows api `Stage`; SP03 updates web labels to the new names only (no legacy names kept).
- Deadline: `ctx.deadline` honoured as today (api owns RUN_DEADLINE_S).
- Not exported: eaudit/compare anything.

**R3. Report (no-rating)**
- `Report` model + generated `schemas/report.schema.json` copied, then edited only for the R6 renames (`run_info.paudit` -> `run_info.miti`, `run_info.eaudit` dropped, engine name). Rated/partial variants may stay in the model (trimming is a later cleanup, not for compat). `schema_version` stays `"0.0.1"`; old stored reports need not validate (wipe or ignore).
- `build_report_no_rating(...)` produces the same JSON as `evaluation.build_report(rating=None)`: scorecard rows with `diff.status:"not_rated"`, `globals`/`behaviours` explanations ("Onolys scored N."), summaries with `clinician:null`, `reasons_audit:{status:"skipped",items:[]}`, `aggregates` nulls, `header.has_clinician_rating:false`, `rating_coverage{0,14}`, `layout`/`method` from `report.yaml`.
- Intentional deltas, all in `run_info`: `run_info.evaluation.engine` becomes `"miti"`; the code-pass info key `run_info.paudit` is renamed `run_info.miti`; `run_info.eaudit` removed (schema + model); the chosen span is recorded (R7). `pack_hash` equal to today's (D3). Volatile fields: `created_at`, `request_id`, `code_version`, usage.
- Tips: same single-call design (`tips` route, `tips_system.md`, validate-by-locate, tone lint, 3-5 tips, retry <3, `fewer_tips`/`tips_failed` warnings). A tips failure degrades to a warning; a coding failure raises.

**R4. Tests (ported, offline by default)**
- Port: paudit `test_{code_pass,globals_pass,engine,formula,prepare,result,score,miti_pack}` (+ `test_agnostic` replaced by "no import of old packages" test); core `test_{llm*,routes,locate,retry,run_info*,safe_log,stt,google_chirp,voice*,types}`; evaluation `test_{build_report,tips,tone,report_schema,validate_rating,run_evaluation}` (reduced to no-rating). Drop `test_transcript_eaudit`, `test_compare`, `test_reasons`, `test_layering`.
- LLM: copy `fixture_client`/`FixtureClient` + recorded replay; fixtures + `expected.yaml`, `thresholds.yaml` in `data/fixtures`.
- **Parity proof (golden):** a test runs `run_miti` with the FixtureClient on `good_practice` and compares to `data/fixtures/evaluation/report_no_rating.json` after masking volatile keys (`created_at`, `request_id`, `code_version`, `run_info.*`). A one-off script, run once during SP01 and not committed to CI, runs old `run_evaluation(rating=None)` and new `run_miti` on the same FixtureClient and diffs the full JSON; expected diff = only the R6/R7 `run_info` renames/additions. Result recorded in the PR. The golden `report_no_rating.json` copy under `data/fixtures` is updated for the same renames.
- Live check: `python -m onolys_miti.check --preset <p>` (marker `live`, excluded by default) = old paudit check + tips checks merged.
- Schema test: output validates against the new `report.schema.json`; `report.local.schema.json` in api is updated in SP02 to the renamed keys. Span tests (R7): <= 20 min -> whole session; > 20 min -> 20-min window inside the session; same seed -> same window; different seeds vary; no timestamps -> whole + `span_ignored`.

**R5. Workspace/CI**
- `engines/miti/pyproject.toml`: dist `onolys-miti`, `packages=["src/onolys_miti"]` + package data; deps = union of core+paudit+evaluation used deps (pydantic, pyyaml, litellm, rapidfuzz, extras `stt-google`, `voice-gemini`, jsonschema if used); dev group same as core. Auto-joins the workspace via `engines/*`; `uv lock` updated.
- Testable by `uv run --package onolys-miti pytest engines/miti -m "not live"`. CI job + `changes.sh` flag + `test_changes.sh` cases for `engines/miti` are added in SP05; SP01 only documents the command. Unit tests are still written in SP01 (test-first); only the CI wiring waits. [RESOLVED: CI job added later in SP05, owner 2026-11-22]

**R6. Naming (owner 2026-11-22: nothing paudit/iaudit/eaudit survives in `engines/miti`)**
- LLM routes `paudit_code`/`paudit_globals` -> `miti_code`/`miti_globals` in code, `routes.default.yaml` and fixtures (`tips` unchanged). api/`config/*/routes.yaml` and staging presets follow in SP02. No migration; prod config edited directly.
- Env vars `IAUDIT_MODEL_CHEAP|MID|STRONG`, `IAUDIT_LLM_RESPONSE_FORMAT`, `IAUDIT_LLM_RECORD` (in core `llm/routes.py`, `llm/__init__.py`, `fixture_client.py`) -> `MITI_*`. `PAUDIT_PROTOCOLS_DIR` and `IAUDIT_CONTRACTS_DIR` do not exist in `onolys_miti` (data is in the package).
- `run_info.engine` / `run_info.evaluation.engine` = `"miti"`; `run_info.paudit` -> `run_info.miti`; `run_info.eaudit` removed; `PauditResult` -> `MitiResult`; error/warning strings, log fields, artifact names (`code`, `tips`) and docstrings carry no old name.
- Test-enforced: `git grep -iE "paudit|iaudit|eaudit|onolys_core|onolys_evaluation" engines/miti` empty (src, tests, data).

**R7. Coded span: automatic (owner 2026-11-22)**
- No user input. Lives in `onolys_miti/span.py`, called at the top of `run_miti` (after speaker mapping, before `prepare`), so every caller (api, fake, check) gets identical behaviour. Duration = max over turns of `end_ms` (fallback `start_ms`); no timestamps at all -> whole session, `span_ignored` warning (existing behaviour).
- Rule: duration <= `MAX_CODED_S` (1200 s, a constant in `span.py`) -> code the whole session (`coded_span = None` for `select_turns`). Longer -> random 20-min window: `rng = random.Random(sha256(seed))`, `from_s = floor(rng.uniform(0, duration_s - 1200))`, `to_s = from_s + 1200`. Reproducible: same session id + same transcript -> same window (re-runs and n_runs all use the one window; chosen once per `run_miti`, not per run). Turns overlapping the window are kept whole (existing `select_turns`).
- Recorded: `MitiResult.coded_span` (ints, `null` when whole), `run_info.miti.span = {mode: "whole"|"random_window", duration_s, seed}` and, for the window case, a `coded_window` info warning ("coded 12:40-32:40 of a 41:10 session"). Appears in `code.json` and the report `run_info`.
- Context (verified): today the upload cap is 20 min (`config/*/stt_providers.yaml` `max_audio_s: 1200`; `api/.../audio.py` `DEFAULT_MAX_DURATION_S = 20 * 60`), so the window path is dormant until the cap is lifted; it is still implemented and tested now.

## Architecture
```
api RealEvaluation -> run_miti(ctx, transcript, speaker_map, params, cb)
  span (whole | seeded 20-min window) -> prepare(select, volleys) -> [code_pass x batches (warm then fan-out)] || [globals_pass] -> locate -> rules -> counts/summaries
  x n_runs -> aggregate(mean/min/max) -> tips (1 call, Onolys-only view) -> build_report_no_rating -> MitiOutput
infra (same package): stt/ voice/ llm/ transcript errors safe_log locate normalize retry run_info
data/: pack.yaml, prompts/, report.yaml, rating.schema.json, fixtures/, scenarios/
```
MITI is data in `data/` + `rules.py`, read through the `MITI` constant; no loader, no pack params.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | Import / dist name | `onolys_miti` / `onolys-miti` | `miti` | Matches `onolys_core`/`onolys_evaluation`; a bare `miti` may clash on PyPI [RESOLVED: implementer verifies at coding time, default `onolys_miti`] and is a generic top-level name |
| D2 | Copy vs move | Copy; old packages untouched until SP05 | git mv | api, admin, eaudit tests keep working; distinct import names (`onolys_miti` vs `onolys_core`/`paudit`) so no clash in one venv. Cost: two `safe_log`/`RunContext`/`Transcript` classes exist transiently; SP02 must switch every import in one change, never mix |
| D3 | Where MITI data lives | Inside package `data/`, byte-identical copies of pack files; `protocols/` left for SP05 | Read `protocols/` in place | Self-contained wheel/image (api Docker only needs `engines/miti`). Identical bytes + same file-order hash keep `pack_hash` unchanged. Two copies until SP05 deletes `protocols/` |
| D4 | Pack abstraction | `MITI` constant from `data/pack.yaml` loaded at import, validated by a unit test not a runtime schema | Python dataclasses for all items | Smallest edit to paudit code and prompt rendering; data stays reviewable |
| D5 | Report model | Keep full `Report` (rated variants included), build only no-rating, apply R6 renames | Trim to no-rating model | Smallest edit; trimming is a later cleanup. Not for old-data compat (dropped) |
| D6 | Stages | `code`, `tips`, `assemble` | Keep old 5 names | Honest names; eaudit/compare no longer exist. api/web change in SP02/03 |
| D7 | Rating validation | Port `validate_rating` + `rating.schema.json` | Drop; api stubs it | Rating endpoints stay in api; removing is SP02's call |
| D8 | Live harnesses | Merge into one `check` module | Port both | Fewer files; thresholds reused |
| D10 | Coded span | Engine picks it (whole <= 20 min, else seeded random 20-min window), recorded in result + run_info | User-entered span; api picks it | One place for every caller; reproducible via session-id seed; no UI/validation surface (owner 2026-11-22) |
| D11 | Names | Everything renamed to miti, breaking | Keep old route/env names | Nobody uses prod; no migration or compat code (owner 2026-11-22) |
| D9 | Core infra | Copy everything api imports directly (see R1), nothing else | Copy all of core | Verified by grep; `Engine`, `PackRef`, eaudit helpers are unused after the switch |

## Risks / Open Questions
- [RESOLVED: implementer verifies at coding time, default `onolys_miti`, owner 2026-11-22] (OPEN-1) PyPI name check; no `miti` dir/dist in repo [verified: grep of pyproject files].
- [RESOLVED: CI job added later in SP05, owner 2026-11-22] CI job for `engines/miti` is added in SP05 (after SP02); the package is not CI-gated between SP01 and SP05. Unit tests are still written in SP01 per test-first policy; only the CI wiring waits.
- [RESOLVED: implementer verifies at coding time, default `PackError` not ported, SP02 removes api uses, owner 2026-11-22] (OPEN-3) `PackError`/`PackRef`.
- [RESOLVED: implementer verifies at coding time, default: admin keeps importing the old packages until SP04, SP05 waits for both, owner 2026-11-22] (OPEN-4)
- [RESOLVED: identical `report_no_rating` except the R6/R7 `run_info` renames/additions; pack_hash unchanged via identical files] Parity claim, proven by the golden test.
- [RESOLVED: user-entered span removed; engine picks whole session or seeded random 20-min window, owner 2026-11-22] (R7)
- [RESOLVED: rename everything to miti, no migration, owner 2026-11-22] (R6)
- [RESOLVED: not bumping schema_version, nobody uses prod] renames are breaking but unversioned.
- [DEFERRED] Tips quality/expansion; trimming `Report` to no-rating; deleting `rating.py`.
- Risk: renamed routes break recorded fixtures keyed by route name; re-record/rename them with the code (offline replay test catches it).
- Risk: `safe_log` field registry is per-package; api's `logs.py` registers fields via old module. Mitigation: SP02 imports `onolys_miti.safe_log` everywhere in one pass.
- Risk: copied fixtures drift from `protocols/` until SP05; low, since both are frozen in this initiative.

## Acceptance Criteria
- `uv sync --frozen --package onolys-miti` and `pytest engines/miti -m "not live"` pass; ruff clean.
- `git grep -iE "onolys_core|paudit|iaudit|onolys_evaluation|eaudit" engines/miti` returns nothing (src, tests, data; test-enforced).
- `run_miti` on fixture transcript + FixtureClient yields a report that validates against `schemas/report.schema.json` and `api/src/onolys_api/schemas/report.local.schema.json` and matches `report_no_rating.json` after volatile masking.
- Old-vs-new diff script shows only the R6/R7 `run_info` deltas; output attached to the PR.
- Span: transcript <= 20 min -> whole session, `coded_span` null; > 20 min -> 20-min window, reproducible for a given seed, recorded in `MitiResult.coded_span`, `run_info.miti.span` and a `coded_window` warning; `params` containing `coded_span` is ignored/rejected.
- Routes `miti_code`/`miti_globals` and `MITI_*` env vars used; no old names anywhere in `engines/miti`.
- Progress callback emits `code`, `tips`, `assemble` (started/done/failed); coding failure raises `AllRunsFailed`/`CodePassFailed`/`GlobalsPassFailed`; tips failure yields a warning and a report.
- n_runs=3 with FixtureClient averages counts/globals and excludes a failed run with `run_failed`.
- No file outside `engines/miti/**` (and `uv.lock`) is modified.
