---
status: done
summary: Direction sound but 3 of 7 items are mis-aimed. Do b (persuasion slot). Change a, c, d, f, g. The biggest manual deviations, volley breaking and the midpoint reset, are not in the brainstorm. Add them.
date: 2026-11-24
---

# Evaluation: MITI engine improvements vs MITI 4.2.1

Manual source: `casaa.unm.edu/assets/docs/miti4_21.pdf`. Downloaded and extracted; page numbers are the manual's own. Engine paths are under `engines/miti/src/onolys_miti/`. Nothing was run live, so every effect estimate below is reasoned, not measured.

## Verdict table

| # | Item | Today (file:line) | Manual ref | Verdict | Value | Cost |
|---|---|---|---|---|---|---|
| a | Ordered clinician coverage incl. explicit uncoded | `code_pass.py:249-255` checks volley ids only. Empty `utterances` is allowed; no check that quotes tile the turns. | p.14 F: not all utterances are coded; p.16 "fewer parses" | **Change**: coverage becomes a measured warning, not a tiling requirement | Low-Med | Low |
| b | One persuasion-family slot per volley | `pack.yaml:256` `max_per_unit code:any`; `score.py:44` keys on `(volley, code)`, so persuade and persuade_permission each count once in the same volley | p.13: "Persuade (Persuade or Persuade with)", one per volley; p.20 same-utterance rule | **Do** | Med (real overcount) | Very low, a pack rule |
| c | Client acknowledgement/permission context | `code_pass.py:158` sends only the single `previous_other_turn`; `prepare.py:132` | p.18-19: permission lasts several minutes, may come before, during, or after; p.16 facilitative speech | **Change**: bounded text-only context window, client and clinician turns, in the user message | Med-High | Low-Med |
| d | Count only owned turns, validate overlap | Batches are disjoint volley slices (`code_pass.py:317`). Context turns are never clinician-coded. Double count cannot happen today. | n/a | **Change**: becomes a guard that comes with c, not a standalone item | Low | Very low |
| e | Validate quotes, keep exact | Already done. `_locate_volley` (`code_pass.py:177`), `globals_pass.py:140`, `tips.py:196` all use `locate`. The stored quote is `turn.text[start:end]`, so source text, not model text. | n/a | **Drop** as new work; keep the tests. Only tighten fuzzy tier (see Missed) | ~0 | n/a |
| f | Remove midpoint reset; "no score" | `globals_pass.py:180-196` resets to `scale["default"]` when fewer than `evidence_min` quotes (`pack.yaml:39,63,83,100` = 2) | p.4 default 3; FAQ 6 (p.38) | **Change**: delete the reset, not the concept of a default. Null only on explicit abstain. | High | Med (schema/UI/aggregate) |
| g | Same stages, compact anchors | Code pass sends each volley's text once; globals sends the full span once; tips sends clinician turns once. The transcript is not repeated per batch. | n/a | **Drop** (premise is mostly false) | ~0 | n/a |

## Item details

**a. Coverage.**
- The model only has to return each volley id. Silently skipped utterances are possible but not detected.
- The manual says not every utterance is coded, including greetings, structure and facilitative comments (p.15 F). Demanding explicit uncoded entries for all clinician speech roughly doubles output tokens (est. +2-4k per 6,000-word session, +10-25% code-pass latency) for no scoring gain.
- Better: compute residual clinician words not covered by any returned utterance, per volley. Record this as a metric and a `coverage_gap` info warning. Retry once only when the residual is very high (suggest >40% of words plus no code returned in a volley with at least 3 sentences). This reuses the existing drop-rate retry (`code_pass.py:268`).
- Measured first (see plan); decide the threshold from the baseline.

**b. Persuasion slot.**
- The manual lists "Persuade (Persuade or Persuade with)" as one slot per volley (p.13).
- Today a volley can score both `persuade` and `persuade_permission`, which overcounts MINA (Total MINA = Confront + Persuade) and inflates the persuasion count.
- Add an `exclusive_group` over `[persuade_permission, persuade]` with precedence `persuade_permission`. This matches the p.20 same-utterance rule; the manual is silent on cross-utterance precedence, so this extends it.
- It is a pack-only change: `exclusive_group` already exists (`score.py:57`). No prompt change, so no golden re-record.
- Consequence: Persuade with Permission does not feed Total MINA (as the manual defines it); a volley holding both is then scored as the permission code only.

**c. Context.**
- Problem is real. Permission "may last several minutes" (p.18) and can come before, during or after persuasion. A volley whose permission was given 3 turns earlier cannot be judged from one preceding client turn.
- Tips has the same single-turn limit (`tips.py:100`).
- Implement as `context_before`: the last K turns (suggest 4, at most 150 words, either speaker, labelled `context_only`) before each volley's first turn. Do not include context across batch edges as codable.
- Context is in the user message, so the cache prefix at `code_pass.py:144` is unchanged.
- Cost: +15-35% of code-pass input (est. +1-2k tokens at 6,000 words; negligible vs 120k).
- Quality risk: the model may code context speech. Mitigated by d.

**d. Ownership guard.**
- Make only clinician turns inside the batch codable. `_locate_volley` already searches only `volley.turns`.
- Add: reject or drop any quote that locates only in a context turn, and keep the existing volley-id set check. Cheap and test-only.

**e. Quotes.** Already validated three ways. Fuzzy tier (`locate.py`, threshold 90, guarded for numbers and negation) can bridge small model typos; that is acceptable and preserves source text. No new work.

**f. Globals.** Manual evidence against the brainstorm as worded:
- Manual p.4: "The coder assumes a default score of '3' and moves up or down as indicated." A default of 3 is the manual's own method, not a misleading artifact. Removing it entirely is less faithful.
- What is wrong is the reset: `_rate` overwrites the model's score with 3 when fewer than 2 quotes locate. This is wrong because:
  - SST can legitimately be 4-5 with no sustain talk (FAQ 6, p.38: "higher ratings may be given even in the complete absence of sustain talk").
  - CCT low scores (1-2) are about absence of attention, so quotes may not exist.
  - Do not penalize when the client offers no change talk (p.5).
  - The reset therefore pulls both good and poor sessions toward 3 and hurts `globals_within_1`.
- "No score" is not in the manual. Every review has four global scores (p.3 B). A null is justified only when the model abstains, e.g. a very short span (FAQ 1: under 10 min harder; 2-5 min, counts only).
- Recommended: keep `score` as returned; store `evidence_count` and a `low_evidence` flag, not a reset; allow `score: null` only when the model explicitly abstains. Technical/Relational summaries are null if either input is null (the existing `evaluate()` already returns None, `formula.py:50`). The manual does not say how to handle this; null is the honest choice.
- Schema cost: `GlobalScore.score: int` (`result.py:138`), Stat mean across `n_runs` (`run.py:105`), the report schema and UI all need nullable handling. Owner says no back-compat is needed, which keeps this contained.
- The `source: "default"` enum value goes away.

**g. Anchors.** Request count is already one code call per ≤25 volleys plus one globals call plus one tips call. There is no per-batch transcript repeat to remove. Globals needs the whole span (holistic judgment, p.4 D). Compacting it would hurt quality. Keep as is.

## Missed deviations from the manual (evidenced)

1. **Volley breaking (largest).**
   - Manual p.13 E.1 and p.16 E.3: a volley is ended by client speech other than facilitative comments ("yeah, right, good"). It breaks only if the acknowledgement answers a direct question or reflection.
   - Engine: `pack.yaml:271` `min_other_words: 0` makes any client turn, even "mm-hm", break the volley (`prepare.py:133`).
   - Effect: more volleys, so more once-per-volley codes (Q, GI, SR/CR, etc.) and inflated counts. The pack comment calls it an "accepted default".
   - Fix: set `min_other_words` to about 3 and add an exception when the preceding clinician turn ends in a question (a simple, deterministic heuristic). Needs a manual-faithful test on a fixture with "yeah" mid-turn.
   - Highest value-per-effort item, and mostly config.
2. **Evidence-min reset** for SST/CCT (see f). It is a manual violation, not just a UX issue.
3. **No deviation (checked)**: not-coded list matches p.15 F. **Code set**: all 10 count codes plus 4 globals are present, definitions cite correct pages, and the summary formulas and thresholds match H and I (pp. 32-33). R:Q, %CR, MIA and MINA formulas are correct. No missing codes. The brainstorm's concern "missing codes like Seek/Affirm" is unfounded.
4. **Input checks**: `duration_min` is a warning only (p.37 / FAQ 1); `duration_max` 25 min is an engine cap, not a manual rule (manual allows longer segments with caution, p.14 G).

## Measurement plan

Existing: `python -m onolys_miti.check` (live; needs `GEMINI_API_KEY`) runs 3 synthetic fixtures and gates count MAE ≤1.5, globals-within-1 ≥0.75, bad-output ≤10%, p95 ≤90 s, ≤120k tokens.

1. **Baseline first** on the current commit. Run with `n_runs=3` per fixture and record per-metric values, not just pass/fail. Re-record goldens per prompt change (request-hash keyed).
2. **Instrument** (small, outside the gate): per run log `volleys`, `coverage_residual_pct`, `dropped`, `insufficient_evidence` count, `calls`, `tokens`, `wall_s`.
3. **Step the changes** in order b, volley break (new), f, c. Re-run after each so regressions are attributable.
4. **Fixtures needed.** The 3 fixtures are 129-507 words, about 22 turns. They are too small to see batch edges (≥25 volleys) or latency.
   - Add 1 synthetic long fixture near the mission cap of 6,000 words and 25 min (`docs/mission.md:18`), with a permission-then-persuade pattern spanning a batch edge and "yeah" acknowledgements.
   - Add 1 short fixture with sparse change talk and no sustain talk, to test f (expected SST 4-5).
   - Expected counts per volley should be hand-set under manual rules, as in `expected.yaml`.
5. **Quality limits.** With ~5 fixtures the gate is a smoke test, not accuracy evidence. For a real claim, compare to a small held-out human-coded set (3-5 sessions from a certified coder). Do not claim improvement from synthetic fixtures alone.
6. **Accept criteria** (no hard gate, per owner): counts closer to hand-coded; globals-within-1 not worse; zero persuasion-family double counts; p95 and tokens within +25% of baseline.

## Open questions for owner

| Question | Recommended default |
|---|---|
| Keep a default of 3 as the prompt's starting point, with null only on explicit abstain? | Yes. This follows manual p.4 and FAQ 6. |
| Change volley breaking to ignore short client acknowledgements (≥3 words breaks; question-answer exception)? Not in the brainstorm. | Yes. It is a manual deviation and mostly config. |
| Persuasion slot precedence when both occur in one volley? | Persuade with Permission wins (extends p.20 to the volley). |
| Context size for c? | 4 turns, ≤150 words, text only, never codable. |
| Is the full-coverage requirement worth the token and latency cost? | No. Use residual metric and warning; retry only on extreme gaps. |
| Fund the new fixtures (6,000-word, sparse-evidence) and one human-coded set? | Yes for fixtures. Human coding is optional but is the only real accuracy evidence. |

## Ranked by value over effort

1. Volley-break fix (new) - high, config only.
2. b persuasion slot - med, pack rule.
3. f remove evidence reset (null on abstain only) - high, medium effort.
4. c bounded context plus d guard - med-high, low-med.
5. a residual coverage metric - low-med, low.
6. Drop e and g.
