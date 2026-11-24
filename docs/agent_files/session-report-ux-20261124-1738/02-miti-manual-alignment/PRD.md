---
status: draft
summary: Align the MITI engine with the 4.2.1 manual where it deviates (volley breaks, one persuasion slot, no forced global reset), add bounded client context and a residual-coverage metric, and prove manual alignment plus non-regression with stepwise n_runs=3 measurements; no accuracy claim.
date: 2026-11-24
---
# PRD: SP02 MITI coding manual alignment

Repo/branch: Onolys/iaudit / `session-report-ux` · Depends on: none (SP01 commits first; engine call signature from `jobs/run.py` unchanged) · Owns: `engines/miti/**` (`prepare.py`, `code_pass.py`, `globals_pass.py`, `check.py`, `data/pack.yaml`, `data/prompts/*`, `data/fixtures/**`, `tests/**`, `README.md`)

Evidence tags: [manual p.N] = MITI 4.2.1 (casaa.unm.edu/assets/docs/miti4_21.pdf; printed page = PDF page, read in full for pp.3-7, 13-21, 26-28, 32-33, 37-38). [verified: file:line] = read in this worktree. [eng] = engineering choice, not in the manual. Source: `eval-miti-coding.md` (re-checked; page corrections in D8).

## TL;DR
Code counts, 4 globals and summary formulas already match the manual [eval; spot-rechecked p.32-33]. Three real deviations remain: any client turn, even "mm-hm", breaks a volley [verified: `pack.yaml:268-271`, `prepare.py:113-135`]; a volley can score both Persuade and Persuade with Permission [verified: `score.py:44`, `pack.yaml:256`]; globals are overwritten with 3 when fewer than 2 quotes locate [verified: `globals_pass.py:180-196`]. Fix those, add bounded client context and a coverage metric, and measure each step against a baseline. Claim: manual alignment and non-regression, not accuracy.

## Problem
- Over-parsing: facilitative speech ends volleys, so once-per-volley codes (Q, GI, SR/CR, AF...) are counted more often than the manual allows [manual p.13, p.15-16].
- Persuade and Persuade with Permission are one slot; today both can count in one volley, inflating Total MINA [manual p.13; p.33].
- The reset pulls good and poor sessions to 3, contrary to "start at 3 and move up or down" [manual p.4], and to "high SST with no sustain talk" [manual p.7, p.38 FAQ 6] and "do not penalize when no change talk" [manual p.5].
- Permission "may last several minutes" and can come before, during or after persuasion [manual p.18-19]; the coder sees one prior client turn [verified: `code_pass.py:~158`, `prepare.py:29`].
- Uncovered clinician speech is not measured; silent drops are invisible.

## Goals / Non-Goals
**Goals:** manual-faithful volley parsing, persuasion slot and globals; bounded context; coverage visibility; a repeatable baseline-vs-new measurement; two new fixtures; re-recorded goldens.
**Non-goals:** accuracy claims without human-coded data; report schema change or null globals (the manual has no "no score": every review has four globals, p.3); quote-validation rework (`locate` already validates [verified: `code_pass.py:177`, `globals_pass.py:140`]); compact anchors (transcript is not repeated per batch); tips context (`tips.py:100`); any API/web change; new protocols (mission).

## Requirements
**R1 Volley breaks.** A client turn does not break a volley when it is facilitative, unless it answers a direct clinician question. Implement in `build_volleys`: client turn with fewer than `min_other_words` words is facilitative and is skipped (not codable); it still breaks when the previous clinician turn, trimmed, ends with `?`. Pack: `min_other_words: 5`. The clinician turns on both sides then form one volley.
**R2 One persuasion slot.** Pack rule `exclusive_group`, unit volley, `codes: [persuade_permission, persuade]`, `precedence: [persuade_permission, persuade]`; the loser is down-counted `superseded_by_persuade_permission` [existing mechanism, `score.py:57`]. Prompt/pack text states the same-utterance rule [manual p.20].
**R3 Globals.** Delete the reset branch in `_rate`; the model's score stands, cap-on-poor-practice unchanged. Keep `insufficient_evidence` as an `info` diagnostic with no "reset" wording. Stop emitting `source: "default"`. Prompt states: start at 3 and move with evidence [p.4]; absence of sustain talk is not penalized [p.7, p.38]; no penalty when client offers no change talk [p.5]; low scores need evidence of the clinician behavior, not of its absence.
**R4 Bounded context + guard.** Per volley, `context_before`: the last up to 4 client turns before the volley, at most 150 words in total (drop oldest whole turns; if the newest alone exceeds 150, keep its last 150 words), text only, no turn ids, replaces `previous_other_turn`. It sits in the user message only [verified: `_render_batch`]. Guard: a located quote must fall in a batch-owned clinician turn; a quote that matches only context text is dropped with warning `context_quote`; each instance's turn id must belong to its batch; batches stay disjoint.
**R5 Coverage metric.** After location, compute clinician words not covered by any located utterance, per volley and per run. Emit info warning `coverage_gap` when a volley with at least 40 clinician words returns no utterance. Retry the batch once (reusing the existing retry at `code_pass.py:~268`) only when more than 50% of such volleys in a batch are empty. Thresholds are [eng]; ship them from the baseline distribution before enabling the retry.
**R6 Measurement.** Extend `check.py`: `--n-runs` (default 3), `--report-out` JSON per fixture and run: count MAE, globals-within-1, bad-output rate, tokens, p50/p95 latency, plus diagnostics (volleys, persuasion double counts, coverage residual %, `insufficient_evidence` count, dropped). Gates in `thresholds.yaml` stay as they are; no hard ship gate.
**R7 Fixtures.** (a) `long_session`: about 6,000 words, over 25 volleys so the 25-volley batch edge falls inside a permission-then-persuade pattern, with facilitative "yeah"s and a question-answer "yeah". (b) `sparse_evidence`: short, little change talk, no sustain talk (expect SST 4-5, p.38). Hand-set expected counts and global ranges in `expected.yaml`, with the rule/page behind each count. Audit existing `expected.yaml` against R1 and change an expected count only where the manual requires it. Re-record `golden/good_practice` (keyed by request hash) after R4's prompt edit.

## Architecture
Order and commits (each is a measurement point; SP02 commits after SP01): 0 baseline on current HEAD, 1 volley break, 2 persuasion slot, 3 globals, 4 context + guard, 5 coverage. One commit per step with its tests and `measurements/stepN.json`; goldens re-recorded once, at step 4 end, then re-checked at step 5. The cache prefix (`cache_prefixes`, `code_pass.py:~131`) must stay byte-identical across batches of a run; the R4 prompt edit changes it once versus baseline, which is expected. Volley ids change when R1 merges volleys; goldens and `expected.yaml` follow.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | Facilitative rule | Skip client turn under 5 words; break if prior clinician turn ends `?` [eng threshold] | Word count only; lexicon ("yeah, right, good"); LLM judge | Manual gives a semantic rule, no number [p.13, p.15-16]. Its own example "Okay, all right. Good." is 4 words [p.32]. Lexicon is language-bound; LLM adds a call. Question exception is the manual's [p.15-16]; fewer parses is the default [p.14, p.16] |
| D2 | Ack of a clinician reflection | Not special-cased | Detect reflections before parsing | Manual allows parsing here [p.15-16] but needs a code to decide, and says prefer fewer parses [p.14]. [DEFERRED] below |
| D3 | Persuasion precedence | PwP wins at volley level | Persuade wins; keep both | Manual fixes it only within one utterance [p.20]; slot is one per volley [p.13]. Extension is [eng], matches "high bar for Persuade" [p.17, p.19] |
| D4 | Global default | Remove reset; model score stands | Keep reset; null score | Start at 3, move by evidence [p.4]; absence of sustain/change talk not penalized [p.5, p.7, p.38]. No null: four globals per review [p.3] |
| D5 | `insufficient_evidence` | Keep as info diagnostic | Delete | Cheap signal to audit thin evidence; no score effect |
| D6 | Context | 4 client turns, 150 words, text only [eng sizes] | Single turn; both speakers; full history | Permission lasts minutes, may precede or follow [p.18-19]; the answer ("Sure") is a client turn [p.19-20]. Bounded cost, in user message so cache holds |
| D7 | Coverage | Residual metric + warning; retry only on extreme gaps [eng thresholds] | Force explicit uncoded entries | Not every utterance is coded [p.14, p.32 F]; explicit tiling costs output tokens for no score gain |
| D8 | Manual page corrections | Not-coded list and length caution are p.32 (F, G), not p.14/15; duration advice p.3, p.37 FAQ 1; `duration_max` 25 min is an engine cap [p.32 G allows longer with caution] | n/a | Cite correct pages in prompts and docs |
| D9 | Measurement, not gate | n_runs=3, baseline vs each step | Hard gate | Owner: audit + plan. Gate numbers stay as the existing smoke limits |

## Manual steps
- Live runs need `GEMINI_API_KEY` on the machine (owner-provided credential); measurement steps run only where it exists.
- [DEFERRED, owner, optional] A certified-coder human-coded set (3-5 sessions) is the only real accuracy evidence; not required to merge.

## Risks / Open Questions
| Item | Status |
|---|---|
| Volley-break threshold 5 may merge a real short answer ("I don't know why", no `?` before it) | [OPEN] tune with the two new fixtures; report effect on counts. Mitigation: `?` exception |
| Reflection-acknowledgement parsing (D2) may undercount reflections slightly | [DEFERRED] revisit if baseline shows R:Q drift |
| Persuasion precedence across utterances (D3) is an extension of p.20 | [RESOLVED: owner default, PwP wins] |
| Globals after reset removal may swing on thin evidence (empty `evidence` lists in the report) | [OPEN] confirm `report.schema.json`/web accept empty evidence (defaults already stored `[]`); check with `insufficient_evidence` counts |
| Coverage retry thresholds (40 words, 50%) | [OPEN] set from baseline before enabling retry |
| Context lets the model code context speech | Mitigated by the R4 guard; test required |
| ~5 synthetic fixtures are a smoke test; expected counts are hand-set by us, not independent | Accepted; no accuracy claim; limits stated in the measurement summary |
| Token/latency growth from context | Tracked; accept within +25% of baseline (eval) |
| Quality claim | [RESOLVED: owner] claim manual alignment and non-regression only |
| Schema narrowing (`source` enum `default`) | [RESOLVED: stop emitting; leave the enum value to avoid schema churn; no back-compat needed] |

## Acceptance Criteria
1. **Volley tests** (tiny hand transcripts in `test_prepare.py`): clinician / "yeah" / clinician = 1 volley; clinician ending "?" / "yeah" / clinician = 2; client turn of 5+ words breaks; facilitative turn is not codable but is available as context.
2. **Persuasion test** (`test_score.py`): volley holding persuade and persuade_permission counts one (permission), the other `superseded_by_persuade_permission`; Total MINA excludes the loser; no counted volley exceeds 8 codes [p.13]; `test_miti_pack.py` asserts the rule.
3. **Globals test** (`test_globals_pass.py`): a rating with 1 located quote keeps its model score (not 3); the `info` warning remains; no `source: "default"` in output; SST 5 with zero evidence is kept.
4. **Context/guard tests** (`test_code_pass.py`): rendered `context_before` has at most 4 turns, at most 150 words, no turn ids; a quote located only in context is dropped with `context_quote`; `cache_prefixes` are equal across all batches of a run; batches are disjoint.
5. **Coverage tests**: residual computed on a hand transcript; `coverage_gap` fires at the threshold; the batch retries once only above 50% empty volleys (fake client).
6. **Fixtures**: `long_session` (about 6,000 words, at least 2 batches, pattern across the batch edge) and `sparse_evidence` exist with hand-set `expected.yaml`; `test_data.py` passes; `test_golden.py` passes after re-record.
7. **Measurement artifacts committed**: `02-miti-manual-alignment/measurements/{baseline,step1..step5}.json` (from `check.py --n-runs 3 --report-out`) and `summary.md` with a baseline-vs-step table of count MAE, globals-within-1, bad-output rate, tokens, p50/p95 latency, persuasion double counts (target 0 after step 2), coverage residual. Reading rule (no hard gate): counts not farther from hand-set expected, globals-within-1 not worse than baseline, p95 and tokens within +25%.
8. **Audit committed**: `audit.md` maps each rule (volley, 8-code slots, persuasion, globals, not-coded list, formulas) to manual page and file:line, marked match / fixed here.
9. Impacted tests under `engines/miti/tests` pass; the full suite runs only at ship. Engine call signature unchanged.
