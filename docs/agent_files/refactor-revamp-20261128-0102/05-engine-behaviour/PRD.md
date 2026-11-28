---
status: draft
summary: On top of 04's engine package, change what the engine does - in-order uncapped context, numbered clinician units instead of quotes, volleys split after a coded reflection, one shared instruction source, and one-shot rebuilt on the MITI input and shared scoring steps (oneshot-single, new oneshot-split); re-baselined fixture goldens plus owner-run live and eval checks stand in for in-repo eval.
date: 2026-11-28
---
# PRD: 05 Engine behaviour

Repo/branch: Onolys/onolys / `refactor/revamp` · Depends on: 04-engine-package (hard: steps, `State`, `protocol.yaml`, golden harness), 00-rules-file (rules 3, 4, 9, 11), 03-eval-split (eval stays pinned to an old tag; it bumps to the tag cut after 05) · Owns: `engine/` behaviour inside 04's layout: `steps/{segment,code,globals,tips}`, `protocols/miti-4.2.1/{protocol.yaml (groups), instructions/, fewshot/}`, `evaluations/{miti,oneshot-single,oneshot-split}/`, `models/` response shapes, `tools/{volley_stats,regen_goldens}.py`, `engine/tests/golden/` re-baselines. Does not own: api folders (06), eval repo (03/09), report schema, STT, `docs/`.

## TL;DR
04 moved code without changing output. 05 changes it, one reviewed re-baseline per change: (1) the code pass gets the conversation in order (last 6 turns of both speakers as read-only context, then ~25 volleys with client turns), no word caps; (2) clinician turns are over-split into numbered units `u14` and the model returns `{units, code, rationale}` instead of quotes; (3) a volley splits after a client answer to a coded reflection (post-code step, no extra model call); (4) prompt and rule text live once in the protocol folder and are rendered into every evaluation; (5) one-shot uses the same input, raw shape and scoring steps as MITI, the model never counts: `oneshot-single` (1 call) and `oneshot-split` (2 parallel calls + tips call). Closes brainstorm issues 1-5.

## Problem
| # | Issue | Evidence | Effect |
|---|---|---|---|
| 1 | One-shot: "any client turn ends a volley" | `engines/oneshot/.../configs/miti/instructions.md:15-16` vs MITI keeping short facilitative input inside (`prepare.py:202-205`; manual E.1/E.3) | more volleys, more codes |
| 2 | One-shot: "Emphasizing Autonomy trumps Seeking Collaboration, which trumps Affirm" and no lower-code rule | `instructions.md:18`; MITI says lower when unsure `code_system.md:27-29` (grep: "lower of" appears only there) | inflated MI-adherent codes |
| 3 | Model counts, "Do not return evidence instances, quotes, offsets" | `instructions.md:9-11`, `schema.json` counts block | no line metrics, not comparable |
| 4 | Client answer to a reflection never breaks a volley | `prepare.py:135-145` `_asks_question`, only use `:203-205`; audit.md:17 "no special detector" | volleys too long, slot caps undercount |
| 5 | Context out of order and capped | `prepare.py:153-170` (`[-4:]`, 150/300 words), `:197` previous volley cut to 100 words, `code_pass.py:161-174` repeats `context_before` in every volley with client turns first, previous clinician volley second | order lost, text repeated |
| + | One-shot tips differ: max 3, no quote/turn | `instructions.md:33-35` vs `tips.py:45`, `tips_system.md` | tips not comparable |
Root cause of 1-3 and +: one-shot's prose is a hand copy of MITI prompts ("adapted from code_system.md", `instructions.md:13,25,41`).

## Goals / Non-Goals
**Goals:** the five fixes plus tips parity; one instruction source; same report shape for all evaluations; quality evidence without eval in-repo.
**Non-goals:** Jev, per-volley / per-global calls, per-slot metrics; non-English; report schema; api (06); eval code; a model-counting one-shot; question-break via coded questions; unit ids for globals evidence (stays quotes).

## Requirements
**R1 Context and batches.** `llm.code_batches` user message = `context` (last `context_turns` turns, default 6, before the batch's first turn, both speakers, selected span only, plain text, no ids to code) then the batch's turns in real order: clinician turns carry `volley_id` and their units, client turns text only. Same renderer for every call that codes. Drop `context_before`, the 150/100-word limits, `_client_context`, `previous_clinician_volley`. Batch size stays 25.
**R2 Units.** New step `segment.units` writes `units` (`u1..uN` over selected clinician turns, session-global). Split after `.` `?` `!` (followed by space or end, closing quotes kept), at `;` `—` and `:` (space follows), never inside `3.5`/`10:30`; a short abbreviation list lives in `constants.py`. Units tile each turn (every non-space char in exactly one unit). Over-splitting is intended. Response shape: `{volleys:[{volley_id, utterances:[{units:["u14","u15"], code, rationale}]}]}`; the `units` items are schema-restricted to `u<digits>`.
**R3 Verification (unit mapping).** Inside the call step (04 D6 stands; shared helper `map_units`). An utterance is valid when all ids exist, belong to this volley (not context, not another volley), are contiguous, lie in one turn, and are unused. Span = first unit start to last unit end; `quote` is sliced by code, never from the model. Invalid -> dropped with a warning (`unit_not_found`, `units_not_contiguous`, `units_span_turns`, `overlap`). Max drop rate 20% (`constants.py`), one retry, then `StepFailed`: unchanged. `context_quote` handling disappears. Instance fields and report schema unchanged. `locate.py` stays for globals and tips quotes only.
**R4 Reflection split.** New step `segment.split_on_reflection` (after coding, before `rules.apply`): within a pre-split volley, at each client gap between two clinician turns, split when the final utterance of the preceding clinician turn is coded in group `reflection`. Instances after the gap move to a new volley `v7.2`; `volleys` and `coverage` recompute. `protocol.yaml` gains `groups: {reflection: [sr, cr]}`, shared with the sr/cr `exclusive_group` rule. `segment.volleys` keeps `break_on: [question]`.
**R5 One instruction source (rule 11).** Fragments in `protocols/miti-4.2.1/instructions/`: `coding_rules.md` (units, split-less, lower-code rules, not-coded list, reflection-vs-structuring), `globals_rules.md`, `tips_rules.md`; few-shot examples in `protocols/miti-4.2.1/fewshot/`. Evaluation prompts keep only framing and use placeholders `{{coding_rules}} {{globals_rules}} {{tips_rules}} {{codes}} {{globals}} {{counting_rules}} {{fewshot_*}} {{output_format}}`; `output_format` is generated from the response models. Deleted: one-shot prose, copied definitions, `instructions.md`, hand-written `schema.json`.
**R6 One-shot on shared steps.** Same prepare, volleys, units, renderer, response sub-shapes (`volleys`, `globals` incl. `poor_practice_cited`, `tips` incl. quote/turn) and post-steps (`segment.split_on_reflection`, `globals.cap`, `rules.apply`, `score.*`, `aggregate.runs`, `tips.validate`, `report.build`). `Engine.output_schema()` = the report schema for every evaluation. `tips.validate` is split out of `llm.tips` (pure; shared). Output property order is `volleys` then `globals` then `tips`.
**R7 Variants.** See Architecture. Truncated or invalid single call fails (`on_bad_output: fail`), no halving; MITI keeps halving.
**R8 Measurement.** `tools/volley_stats.py` (no LLM): per transcript.v1 file prints volleys, units, clinician words, projected calls at batch 25, and old-vs-new payload words. Run on the repo fixtures now (synthetic: 5-27 volleys, `fixtures/README.md`) and on real eval sessions where converted (none cached on this machine: `~/.cache/onolys-eval` absent, verified). Results go in `05-engine-behaviour/measurements.md`; batch size is revisited from them.
**R9 Validation without eval.** Fixture goldens re-baselined per change (R10 table); `expected.yaml` hand counts stay the oracle; owner steps below.
**R10 New fixtures.** `reflection_answer` (two simple reflections split by client "yeah": 2 sr; a statement + "yeah" stays one volley); `batch_edge` expectations updated for context; one-shot goldens for both variants.

## Architecture
**Reflection tension.** Volleys must exist before the call (batching, context), but "reflection" is a code the model assigns during it. Per-utterance codes do not depend on where volleys end; boundaries only decide slot counting, which is software after the call. So the split can follow coding.
| Option | How | Verdict |
|---|---|---|
| A. Post-code split | model codes merged volleys; step re-segments by coded reflection; rules run on final volleys | **Recommended**: deterministic given the codes, no extra call, fits 04's step model |
| B. Heuristic at build time | clinician turn ends in a statement + short client reply = reflection | rejected: statements, information and advice also match; over-splits, inflates counts |
| C. Two-pass LLM | code, re-segment, recode | rejected: 2x cost, codes would not change |
| D. Model returns break flags | extra schema field | rejected: model-defined segmentation, differs per variant |
Residual risk: a wrongly coded reflection adds a slot; bounded because only the same code across the gap gains a count.

```yaml
# evaluations/miti/pipeline.yaml (changes vs 04)
  - use: segment.volleys   {with: {min_other_words: 3, min_other_chars: 6, break_on: [question]}}
  - use: segment.units
  - repeat: n_runs
    steps:
      - parallel:
          - use: llm.code_batches {with: {prompt: prompts/code.md, batch: 25, context_turns: 6}}
          - use: llm.rate_globals {with: {prompt: prompts/globals.md}}
      - use: segment.split_on_reflection {with: {group: reflection}}
      - {use: globals.cap}
      - ...rules.apply, score.count, score.formulas
# oneshot-single: repeat body = llm.oneshot {prompt: prompts/oneshot.md, max_tokens: 64000, on_bad_output: fail}
#   then split_on_reflection, globals.cap, rules.apply, score.*; after: aggregate.runs, tips.validate, report.build
# oneshot-split: parallel: llm.code_batches {batch: all, on_bad_output: fail} + llm.rate_globals;
#   then split_on_reflection ... aggregate.runs, llm.tips (third call), report.build
```
| Variant | Calls | Tips |
|---|---|---|
| miti | ~V/25 code + 1 globals (parallel) | separate call on scored reading |
| oneshot-single | 1: volleys, globals, tips in order | same call, validated by `tips.validate` |
| oneshot-split | 2 parallel (all volleys; globals) | third call, same `llm.tips` |
Both oneshot pipelines keep 04's `checks.portion_words` (6000) and `duration_max`. Model ids still come from constants/env only.

**Validation plan.** (a) Code-level: unit tiling invariants; `map_units` cases (each invalid class, 20% boundary); split cases; loader rejects unresolved placeholders. (b) Prompt-source test: every shared fragment appears byte-identically in each prompt that uses it, and no fragment sentence appears literally in an evaluation prompt. (c) Re-baselines in separate commits, each with a diff summary:
| Step | Changes | Must stay equal |
|---|---|---|
| T1 extract fragments | nothing | MITI payloads byte-equal to 04 baseline |
| T2 context + no caps | code payloads | counts, reports on all fixtures |
| T3 units | payloads, replies re-derived from `expected.yaml` by `regen_goldens` (no LLM) | counts, instance spans |
| T4 reflection split | `reflection_answer`, maybe `batch_edge` | other fixtures |
| T5-T6 one-shot | new goldens | MITI goldens |

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | Reflection break | Post-code split step (option A) | B heuristic, C two-pass, D flags | Only option that sees real codes without a second call |
| D2 | Where context lives | One renderer, last N turns before batch | Per-volley snapshots | No repeated text; order kept |
| D3 | Unit-id fallback | Units only at runtime; quote path kept only until the go/no-go gate (O1) passes, then deleted | Runtime dual mode | Rule 16; two paths double test load |
| D4 | Cross-turn utterance | Not allowed (as today) | Allow across client "yeah" | Manual "when unsure split less"; evidence stays in one turn |
| D5 | oneshot-raw | Not kept | Keep as baseline | Needs its own prose (breaks rule 11) and no shared steps; eval's pin of the old tag still gives the baseline |
| D6 | Tips in one-shot | Same shape as MITI, shared validator | Keep 3 simple tips | Comparable, one code path |
| D7 | Shared text | Fragments + placeholders in protocol folder | Generate one-shot prompt by copying | 04 already rendered definitions this way; extends it |
| D8 | Drop-rate constant | `constants.py` default, not repeated per pipeline | Per pipeline | One source |
| D9 | Re-baseline | One commit per behaviour change | One big regen | Reviewable diffs |
| D10 | Eval id | `oneshot-split` new id; old `oneshot:miti` runs not comparable | Map old runs | Eval pins old tag anyway |

## Manual steps (owner)
1. Convert real eval sessions (eval's converters; needs the private cache) and run `volley_stats`; paste into `measurements.md`.
2. `live_check` on the synthetic fixtures with the real model, per variant (needs keys): bad-output rate, drop rate, count MAE, globals within 1 against `thresholds.yaml`.
3. After the engine tag is cut, bump eval's pin and run the engine comparison on `casaa-miti421-video2013` (old tag vs new miti vs oneshot-single vs oneshot-split): `globals_within_1`, `line_accuracy`, count MAE.
4. Certified-coder wording review of `instructions/` (prompts still say DRAFT).

## Risks
- Model mis-groups or invents unit ids: dropped, 20% rule, gate O1.
- Whole-session single call hits output limits on long sessions: fails by design; `duration_max` 25 and `portion_words` bound it. Estimate ~60-120 volleys x ~3 utterances is under 64k tokens, unmeasured.
- Fewer repeated words but more structure: payload size may move either way; `volley_stats` reports it.
- Re-baselining can hide a regression: counts oracle in `expected.yaml` stays hand-written.

## Open Questions
- [OPEN] O1 Go/no-go for units vs quotes. Default: pass when `live_check` bad-output <= 10% and unit drop <= today's quote drop; else keep quotes with in-order context.
- [OPEN] O2 Reflection split reads only the preceding turn's last utterance. Default: yes.
- [OPEN] O3 One-shot with `n_runs>1`: tips taken from the representative run. Default: honour `n_runs`.
- [OPEN] O4 Batch size after measurement. Default 25.
- [OPEN] O5 Comparison gate. Default: new miti no worse than old tag by more than 0.1 on `globals_within_1` or 10% relative count MAE; one-shot variants reported, not gated.
- [RESOLVED: D5] `oneshot-raw` not kept (answers 04 O6).
- [DEFERRED] Coded-question break, unit ids for globals evidence, Jev, per-volley/per-global calls, non-English.

## Acceptance Criteria
- Each fix has a test: #1/#3 no one-shot prose or schema left (`git grep "any client turn"` and `instructions.md` absent); #2 lower-code rule appears in every coding prompt render; #4 `reflection_answer` yields 2 sr, statement+"yeah" stays one volley; #5 payload has context in order, no `context_before`, no 150/100 limits.
- Unit tiling property test and `map_units` tests pass; instances keep turn/start/end/quote; report validates against the unchanged schema for all three evaluations.
- All three pipelines load (`Engine.load`), share steps, and name no model; oneshot output validates against the report schema.
- Prompt-source test green; T1 shows MITI payloads byte-equal before T2.
- Goldens re-baselined per R10 with one commit per change; `expected.yaml` counts unchanged except the new fixture and justified `batch_edge` edits.
- `volley_stats` runs on fixtures; `measurements.md` has numbers; real-session numbers are an owner step.
- No LLM call made during build; ruff clean; dev-ship full gate.
