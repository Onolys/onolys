---
status: draft
summary: Engine behaviour in 7 tasks (Jinja2 StrictUndefined and pydantic schema per rule 17, no prompt-source test) - one instruction source, in-order uncapped context, reflection split, shared one-shot-ready steps, oneshot-single, oneshot-split, final sweep; one reviewed golden re-recording per behaviour change.
date: 2026-11-28
---
# Tasks: 05 Engine behaviour

Source of truth: /root/projects/onolys/onolys/.worktrees/refactor/revamp/docs/agent_files/refactor-revamp-20261128-0102/05-engine-behaviour/PRD.md. Builds on 04's `engine/` package (steps, `State`, `protocol.yaml`, golden harness). One commit per task; each golden re-recording is its own commit with a diff summary. No gating, baselines or model-quality measurement. Numbered units are deferred (quotes stay). CI exists (`.github/workflows/ci.yml`); no new job. Full suite runs only in dev-ship. No LLM call during build (stubbed clients, fixtures).

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | One instruction source: fragments + placeholders for MITI (R4, T1) | 04 | todo |
| 2 | In-order uncapped context, batch 25 (R1, R2, T2) | 1 | todo |
| 3 | Reflection split step + `groups` (R3, R8, T3) | 2 | todo |
| 4 | Shared response shapes, `tips.validate`, report-schema output (R5) | 3 | todo |
| 5 | `oneshot-single` rebuilt on shared steps (R4-R6, T4) | 4 | todo |
| 6 | `oneshot-split` + `n_runs` for one-shot (R5, R6, T5) | 5 | todo |
| 7 | Final acceptance sweep (R7, AC) | 6 | todo |

## Task 1 — One instruction source for MITI
What it is / what it means: Prompt and rule text must live once (rule 11). This moves MITI's existing wording into protocol fragments with no change in what the model receives. Rendering uses the library (rule 17), not custom code. PRD R4, D7, T1.
What changes at a high level: Create `instructions/` (`coding_rules.md`, `globals_rules.md`, `tips_rules.md`) and `fewshot/` in `protocols/miti-4.2.1/`. MITI prompts keep only framing plus the `{{...}}` placeholders, rendered by Jinja2 with `StrictUndefined` (04 R6), so an unresolved placeholder is a render error and no separate loader check exists. `output_format` is generated from the response models via pydantic `model_json_schema()`. Wording stays text-for-text, so the lower-code rule is only added if it already exists in MITI text.
Done when: MITI provider payloads are byte-equal to 04's output on all fixtures (no golden change); no prompt-source or render test (byte-identity, literal-sentence or StrictUndefined checks) is added; ruff clean.

## Task 2 — In-order uncapped context, batch 25
What it is / what it means: Today context is out of order, repeated per volley and word-capped. Fix issue 5. PRD R1, R2, D2, D8.
What changes at a high level: One renderer used by every coding call: last `context_turns` (6) turns of both speakers before the batch as read-only text, then the batch's turns in real order (clinician turns with `volley_id`, client turns text only). Remove `context_before`, the 150/100-word limits, `_client_context`, `previous_clinician_volley`. Batch size 25 fixed. Response shape and quote verification unchanged.
Done when: renderer unit tests (order, no ids on context, selected span only, short sessions); `batch_edge` expectation updated and justified; MITI payload baselines and report goldens re-recorded in one commit with a diff summary, counts in `expected.yaml` unchanged except justified edits; api stub-mode run (`FixtureClient`) and web preview/stub tests green in the same commit; no `context_before` or 150/100 limit left.

## Task 3 — Reflection split step
What it is / what it means: A client answer to a coded reflection should end the volley (issue 4). Done after coding because volleys must exist before the call. PRD R3, D1, O2, R8.
What changes at a high level: Add `groups: {reflection: [sr, cr]}` to `protocol.yaml`, shared with the sr/cr `exclusive_group` rule. New step `segment.split_on_reflection` between coding and `rules.apply`: at a client gap, split when the preceding clinician turn's last utterance is in the reflection group; later instances move to `v7.2`; `volleys` and `coverage` recompute. Wire into the MITI pipeline. Add fixture `reflection_answer`.
Done when: step unit tests (two reflections split by "yeah" gives 2 sr; statement plus "yeah" stays one volley; last-utterance-only; multiple gaps; coverage recompute); `reflection_answer` fixture with hand-written `expected.yaml`; goldens re-recorded in one commit (only `reflection_answer`, maybe `batch_edge`, change); api stub run and web stub tests green.

## Task 4 — Shared shapes and post-steps
What it is / what it means: One-shot must reuse MITI's shapes and steps. This prepares them without adding a variant. PRD R5.
What changes at a high level: Define response sub-shapes (`volleys`, `globals` incl. `poor_practice_cited`, `tips` incl. quote/turn) in `models/`, property order volleys, globals, tips. Split pure `tips.validate` out of `llm.tips`. `Engine.output_schema()` returns the report schema for every evaluation.
Done when: MITI goldens unchanged (byte-equal payloads and reports); unit tests for `tips.validate` (valid, bad quote/turn dropped) and shape order; `output_schema()` test against the unchanged report schema; ruff clean.

## Task 5 — oneshot-single
What it is / what it means: Replace the hand-copied one-shot prose with the shared source; fixes issues 1-3 and tips parity. PRD R4-R6, D5, D6, D10.
What changes at a high level: `evaluations/oneshot-single/` with `llm.oneshot` (1 call, `max_tokens` 64000, `on_bad_output: fail`, no halving), then split, `globals.cap`, `rules.apply`, `score.*`, `aggregate.runs`, `tips.validate`, `report.build`; keep `checks.portion_words` and `duration_max`. Delete one-shot prose, copied definitions, `instructions.md`, the generated `schemas/schema.json` and `tools/gen_schemas.py` (nothing generates a schema file now). `oneshot-raw` and the `oneshot:miti` rename were done in 04.
Done when: pipeline loads via `Engine.load`, names no model; the lower-code rule is in `coding_rules.md` and shows in the new payload golden diff; `git grep "any client turn"` empty, `instructions.md`, `schema.json` and `gen_schemas.py` absent; web `gen:api` still uses only the report schema; truncated/invalid reply fails test; report validates against the schema; new one-shot golden recorded in its own commit; MITI goldens unchanged; api stub and web stub tests green.

## Task 6 — oneshot-split and n_runs
What it is / what it means: Second variant (2 parallel calls plus tips call) and one-shot honouring `n_runs`. PRD R5, R6, O3.
What changes at a high level: `evaluations/oneshot-split/`: parallel `llm.code_batches` (batch all, `on_bad_output: fail`) and `llm.rate_globals`, shared post-steps, then third call `llm.tips`. Both one-shot pipelines repeat per `n_runs`; tips come from the representative run.
Done when: loads via `Engine.load`; tests for `n_runs>1` in both variants (representative-run tips, aggregate) and for fail-on-bad-output; new `oneshot-split` golden in its own commit; MITI and single goldens unchanged; api stub and web stub tests green.

## Task 7 — Final acceptance sweep
What it is / what it means: Prove the PRD acceptance list as a whole. PRD Acceptance Criteria, R7.
What changes at a high level: Fix any gaps found; no new scope. Check `tools/regen_goldens.py` covers all three evaluations.
Done when: all three pipelines load, share steps, validate against the report schema; each fix (#1-#5) has its test; `expected.yaml` counts changed only for the new fixture and justified `batch_edge` edits; no LLM call in build; ruff clean; dev-ship full gate and CI pass.

## Owner-only
- Certified-coder wording review of `instructions/` (prompts still say DRAFT).
