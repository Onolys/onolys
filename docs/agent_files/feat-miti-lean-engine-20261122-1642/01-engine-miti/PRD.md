---
status: draft
summary: New lean `engines/miti` (dist `onolys-miti`, import `onolys_miti`): MITI-hardcoded coding + tips + no-rating report, plus the STT/voice/LLM infra api needs; side by side with old packages.
date: 2026-11-22
---
# PRD: SP01 engines/miti lean MITI engine

Repo/branch: Onolys/onolys (local `iaudit`) / `feat/miti-lean-engine` · Depends on: none (Phase 1) · Blocks: SP02 (api switch), SP04 (admin, indirectly), SP05 (cleanup)
Owns: `engines/miti/**` (src, tests, data, schemas, pyproject), root `pyproject.toml`/`uv.lock` only if the glob needs it (it does not: `engines/*`). Not owned: `api/`, `web/`, `admin/`, old `engines/{core,paudit,evaluation,eaudit}` (untouched), CI files (SP05).

## TL;DR
One package, `onolys_miti`, copied (not moved) from paudit + core + evaluation with MITI hardcoded. `run_miti(ctx, transcript, speaker_map, params, progress_cb) -> MitiOutput(report, artifacts)` does code pass + globals pass (n_runs averaged) + basic tips + report assembly, with the no-rating report shape unchanged. STT Chirp, Gemini Live voice, LLM client/routes, transcript, errors, safe_log etc. come along so api never imports `onolys_core`. Old packages stay until SP05.

## Problem
- Three engines deep (core, paudit, evaluation) + eaudit for a product that now only does MITI coding. Pack loader, schemas, hooks, compare/reasons, eaudit turn helpers are dead weight. [verified: api imports `onolys_core.*`, `paudit.{pack,engine,code_pass,globals_pass,result}`, `onolys_evaluation.{api,report,rating}`; `to_eaudit_turns` used only by `onolys_evaluation/reasons.py`]
- Packaging/CI/test surface is 3 packages (core 44 py, paudit 28, evaluation 25) to ship one report.

## Goals / Non-Goals
**Goals**
- Self-contained `engines/miti`: no import of `onolys_core`, `paudit`, `onolys_evaluation`, `eaudit` (grep test).
- Same coding behaviour as paudit (prompts, rules, formulas, thresholds untouched) so output parity is provable.
- Same no-rating report JSON as today, so api/web/Firestore stay compatible.
- Basic tips kept.
- Testable offline (fixture LLM) with its own CI-ready test command.

**Non-Goals**
- Deleting old packages, CI jobs, docs (SP05); editing api/web/admin (SP02-04).
- Protocol-agnostic pack layer; clinician-rating comparison, reasons audit, eaudit.
- Prompt or MITI-logic changes; official MITI claims.
- Richer tips (wait for user feedback).

## Requirements
**R1. Layout** (`engines/miti/src/onolys_miti/`; source -> dest; copy then edit)

| Module | From | Notes |
|---|---|---|
| `code_pass.py`, `globals_pass.py`, `prepare.py`, `score.py`, `formula.py`, `result.py` | paudit same names | `Pack` arg replaced by module constant `MITI` (frozen, loaded once from data); `pack.pack_hash`/`facts()` kept as `MITI.hash` |
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
- Params unchanged: `change_goal`, `coded_span`, `language`, `n_runs` (default 1), `preset`, `code_version`; `speaker_map` merged in as today. STT params, LLM routes/presets stay parameters (`resolve_preset`, `LiteLLMClient`, `SttParams`, `GoogleChirp3` re-exported from `onolys_miti.{llm,stt}`).
- Errors (all `OnolysError`): `InputError`, `ConfigError`, `AllRunsFailed`, `CodePassFailed`, `GlobalsPassFailed`, `LLMError` family, `SttProviderError`; same `code` strings so `error_map.py` needs only import changes. `PackError` kept as alias-free removal candidate [OPEN-3].
- Progress: stages `code` (code+globals passes together; paudit never reported them separately), `tips`, `assemble`. SP02 narrows api `Stage`; web progress labels keyed on old names must be checked by SP03 [verified: no `web/src` hit for stage strings in this grep; fake adapter emits old four].
- Deadline: `ctx.deadline` honoured as today (api owns RUN_DEADLINE_S).
- Not exported: eaudit/compare anything.

**R3. Report (no-rating) and compatibility**
- `Report` model + generated `schemas/report.schema.json` copied unchanged (full/partial/rated variants stay valid so already-stored sessions still validate). `schema_version` stays `"0.0.1"`; no bump (shape unchanged).
- `build_report_no_rating(...)` produces the same JSON as `evaluation.build_report(rating=None)`: scorecard rows with `diff.status:"not_rated"`, `globals`/`behaviours` explanations ("Onolys scored N."), summaries with `clinician:null`, `reasons_audit:{status:"skipped",items:[]}`, `aggregates` nulls, `header.has_clinician_rating:false`, `rating_coverage{0,14}`, `layout`/`method` from `report.yaml`.
- Intentional deltas, all in `run_info`/`header`: `run_info.evaluation.engine` becomes `"miti"`; `run_info.eaudit` null (as today with no rating); `run_info.paudit` key kept (holds the code-pass info) so schema and web need no change. `pack_hash` equal to today's (D3). Volatile fields: `created_at`, `request_id`, `code_version`, usage.
- Tips: same single-call design (`tips` route, `tips_system.md`, validate-by-locate, tone lint, 3-5 tips, retry <3, `fewer_tips`/`tips_failed` warnings). A tips failure degrades to a warning; a coding failure raises.

**R4. Tests (ported, offline by default)**
- Port: paudit `test_{code_pass,globals_pass,engine,formula,prepare,result,score,miti_pack}` (+ `test_agnostic` replaced by "no import of old packages" test); core `test_{llm*,routes,locate,retry,run_info*,safe_log,stt,google_chirp,voice*,types}`; evaluation `test_{build_report,tips,tone,report_schema,validate_rating,run_evaluation}` (reduced to no-rating). Drop `test_transcript_eaudit`, `test_compare`, `test_reasons`, `test_layering`.
- LLM: copy `fixture_client`/`FixtureClient` + recorded replay; fixtures + `expected.yaml`, `thresholds.yaml` in `data/fixtures`.
- **Parity proof (golden):** a test runs `run_miti` with the FixtureClient on `good_practice` and compares to `data/fixtures/evaluation/report_no_rating.json` after masking volatile keys (`created_at`, `request_id`, `code_version`, `run_info.*`). A one-off script, run once during SP01 and not committed to CI, runs old `run_evaluation(rating=None)` and new `run_miti` on the same FixtureClient and diffs the full JSON; expected diff = only `run_info.evaluation.engine`. Result recorded in the PR.
- Live check: `python -m onolys_miti.check --preset <p>` (marker `live`, excluded by default) = old paudit check + tips checks merged.
- Schema test: new `report.schema.json` equals the old one byte for byte (until SP05), and `report.local.schema.json` in api still validates output.

**R5. Workspace/CI**
- `engines/miti/pyproject.toml`: dist `onolys-miti`, `packages=["src/onolys_miti"]` + package data; deps = union of core+paudit+evaluation used deps (pydantic, pyyaml, litellm, rapidfuzz, extras `stt-google`, `voice-gemini`, jsonschema if used); dev group same as core. Auto-joins the workspace via `engines/*`; `uv lock` updated.
- Testable by `uv run --package onolys-miti pytest engines/miti -m "not live"`. CI job + `changes.sh` flag + `test_changes.sh` cases for `engines/miti` are added in SP05; SP01 only documents the command. [OPEN-2]

## Architecture
```
api RealEvaluation -> run_miti(ctx, transcript, speaker_map, params, cb)
  prepare(select, volleys) -> [code_pass x batches (warm then fan-out)] || [globals_pass] -> locate -> rules -> counts/summaries
  x n_runs -> aggregate(mean/min/max) -> tips (1 call, Onolys-only view) -> build_report_no_rating -> MitiOutput
infra (same package): stt/ voice/ llm/ transcript errors safe_log locate normalize retry run_info
data/: pack.yaml, prompts/, report.yaml, rating.schema.json, fixtures/, scenarios/
```
MITI is data in `data/` + `rules.py`, read through the `MITI` constant; no loader, no pack params.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | Import / dist name | `onolys_miti` / `onolys-miti` | `miti` | Matches `onolys_core`/`onolys_evaluation`; a bare `miti` may clash on PyPI [OPEN-1 verify] and is a generic top-level name |
| D2 | Copy vs move | Copy; old packages untouched until SP05 | git mv | api, admin, eaudit tests keep working; distinct import names (`onolys_miti` vs `onolys_core`/`paudit`) so no clash in one venv. Cost: two `safe_log`/`RunContext`/`Transcript` classes exist transiently; SP02 must switch every import in one change, never mix |
| D3 | Where MITI data lives | Inside package `data/`, byte-identical copies of pack files; `protocols/` left for SP05 | Read `protocols/` in place | Self-contained wheel/image (api Docker only needs `engines/miti`). Identical bytes + same file-order hash keep `pack_hash` unchanged. Two copies until SP05 deletes `protocols/` |
| D4 | Pack abstraction | `MITI` constant from `data/pack.yaml` loaded at import, validated by a unit test not a runtime schema | Python dataclasses for all items | Smallest edit to paudit code and prompt rendering; data stays reviewable |
| D5 | Report model | Keep full `Report` (rated variants included), build only no-rating | Trim to no-rating model | Old stored sessions and `report.local.schema.json` still validate; web types unchanged; trimming is a later cleanup |
| D6 | Stages | `code`, `tips`, `assemble` | Keep old 5 names | Honest names; eaudit/compare no longer exist. api/web change in SP02/03 |
| D7 | Rating validation | Port `validate_rating` + `rating.schema.json` | Drop; api stubs it | Rating endpoints stay in api; removing is SP02's call |
| D8 | Live harnesses | Merge into one `check` module | Port both | Fewer files; thresholds reused |
| D9 | Core infra | Copy everything api imports directly (see R1), nothing else | Copy all of core | Verified by grep; `Engine`, `PackRef`, eaudit helpers are unused after the switch |

## Risks / Open Questions
- [OPEN-1] Name check: no `miti` dir/dist in repo [verified: grep of pyproject files]; PyPI clash not checked (offline). `onolys_miti` avoids it either way.
- [OPEN-2] CI job for `engines/miti` is in SP05 (after SP02) so the package is not CI-gated between SP01 and SP05. Alternative: add the job in SP01 (small `ci.yml`/`changes.sh` edit). Default: add a minimal job in SP01 if reviewers agree; SP05 then only removes old jobs.
- [OPEN-3] `PackError` and `PackRef` in api: SP02 removes uses; SP01 keeps `PackError` out unless `error_map.py` needs it.
- [OPEN-4] `admin/backend` still imports old `onolys_core`/`paudit` until SP04; fine, but SP05 must wait for both.
- [RESOLVED: byte-identical `report_no_rating` except `run_info.evaluation.engine`; pack_hash unchanged via identical files] Parity claim, proven by the golden test.
- [RESOLVED: not bumping schema_version] shape unchanged.
- [DEFERRED] Tips quality/expansion; trimming `Report` to no-rating; deleting `rating.py`.
- Risk: `safe_log` field registry is per-package; api's `logs.py` registers fields via old module. Mitigation: SP02 imports `onolys_miti.safe_log` everywhere in one pass.
- Risk: copied fixtures drift from `protocols/` until SP05; low, since both are frozen in this initiative.

## Acceptance Criteria
- `uv sync --frozen --package onolys-miti` and `pytest engines/miti -m "not live"` pass; ruff clean.
- `git grep -E "onolys_core|paudit|onolys_evaluation|eaudit" engines/miti/src` returns nothing (test-enforced).
- `run_miti` on fixture transcript + FixtureClient yields a report that validates against `schemas/report.schema.json` and `api/src/onolys_api/schemas/report.local.schema.json` and matches `report_no_rating.json` after volatile masking.
- Old-vs-new diff script shows only the `run_info.evaluation.engine` delta; output attached to the PR.
- Progress callback emits `code`, `tips`, `assemble` (started/done/failed); coding failure raises `AllRunsFailed`/`CodePassFailed`/`GlobalsPassFailed`; tips failure yields a warning and a report.
- n_runs=3 with FixtureClient averages counts/globals and excludes a failed run with `run_failed`.
- No file outside `engines/miti/**` (and `uv.lock`) is modified.
