---
status: done
summary: Deterministic rule alignment and request-size evidence; offline suite has two pending fixture-baseline failures.
date: 2026-11-24
---
# Offline alignment measurements

These snapshots apply deterministic preparation and counting rules to synthetic hand-authored utterances. They do not evaluate model accuracy. `baseline.json` is the pre-alignment checkpoint; steps 1–5 are the corresponding rule checkpoints. Task 3 introduced two fixtures between steps 1 and 2, so rows added at step 2 are new coverage, not improvements measured against baseline.

## Per-step results

Words are rendered initial code + globals request words. Batches are code batches (25 volleys each), excluding the separate globals request. Drift is the largest absolute difference from hand-set count targets. Residual is uncovered clinician words in the supplied hand utterances.

| Snapshot | Fixture | Volleys | Batches | Request words | Count drift | Double persuasion | Residual |
|---|---|---:|---:|---:|---:|---:|---:|
| [baseline](baseline.json) | good_practice | 10 | 1 | 4,527 | 0 | 0 | 0 |
| [baseline](baseline.json) | poor_practice | 12 | 1 | 4,191 | 0 | 0 | 0 |
| [baseline](baseline.json) | short_session | 5 | 1 | 3,681 | 0 | 0 | 0 |
| [step1](step1.json) | good_practice | 10 | 1 | 4,527 | 0 | 0 | 0 |
| [step1](step1.json) | poor_practice | 12 | 1 | 4,191 | 0 | 0 | 0 |
| [step1](step1.json) | short_session | 5 | 1 | 3,681 | 0 | 0 | 0 |
| [step2](step2.json) | good_practice | 10 | 1 | 4,615 | 0 | 0 | 0 |
| [step2](step2.json) | poor_practice | 12 | 1 | 4,279 | 0 | 0 | 0 |
| [step2](step2.json) | short_session | 5 | 1 | 3,769 | 0 | 0 | 0 |
| [step2](step2.json) | batch_edge | 27 | 2 | 8,910 | 0 | 0 | 0 |
| [step2](step2.json) | sparse_evidence | 5 | 1 | 3,616 | 0 | 0 | 0 |
| [step3](step3.json) | good_practice | 10 | 1 | 4,628 | 0 | 0 | 0 |
| [step3](step3.json) | poor_practice | 12 | 1 | 4,292 | 0 | 0 | 0 |
| [step3](step3.json) | short_session | 5 | 1 | 3,782 | 0 | 0 | 0 |
| [step3](step3.json) | batch_edge | 27 | 2 | 8,923 | 0 | 0 | 0 |
| [step3](step3.json) | sparse_evidence | 5 | 1 | 3,629 | 0 | 0 | 0 |
| [step4](step4.json) | good_practice | 10 | 1 | 5,507 | 0 | 0 | 0 |
| [step4](step4.json) | poor_practice | 12 | 1 | 4,920 | 0 | 0 | 0 |
| [step4](step4.json) | short_session | 5 | 1 | 4,003 | 0 | 0 | 0 |
| [step4](step4.json) | batch_edge | 27 | 2 | 11,760 | 0 | 0 | 0 |
| [step4](step4.json) | sparse_evidence | 5 | 1 | 3,743 | 0 | 0 | 0 |
| [step5](step5.json) | good_practice | 10 | 1 | 5,507 | 0 | 0 | 0 |
| [step5](step5.json) | poor_practice | 12 | 1 | 4,920 | 0 | 0 | 0 |
| [step5](step5.json) | short_session | 5 | 1 | 4,003 | 0 | 0 | 0 |
| [step5](step5.json) | batch_edge | 27 | 2 | 11,760 | 0 | 0 | 0 |
| [step5](step5.json) | sparse_evidence | 5 | 1 | 3,743 | 0 | 0 | 0 |

## Reading the changes

- Step 1 fixes facilitative volley parsing. The original three fixtures have no affected intervening short client turns, so their volley groupings and counts remain unchanged. Targeted parsing tests supply the positive examples; unchanged fixture counts alone do not demonstrate the fix. The strict threshold is **under** 3 words / 6 non-space characters, not inclusive (see [step 1](step1.md)).
- The new `batch_edge` fixture has 27 volleys and two batches; `sparse_evidence` has five volleys. They first appear in a committed measurement at step 2. A controlled offline replay with only the persuasion exclusive-group rule removed gives `batch_edge` both persuasion codes in `v26`, Persuade 1 versus target 0, and Total MINA 1 versus target 0. With the rule, both drifts and the double are zero. This replay establishes the pre-slot counterexample; it is not a missing baseline measurement or model prediction. The other original fixtures already had zero doubles.
- Step 2 adds 88 code-request words per initial code call; the two-batch fixture includes the addition twice. Step 3 adds 13 globals-request words per fixture. Step 4 adds bounded context: total words increase by 879 / 628 / 221 / 2,837 / 114 for good / poor / short / batch-edge / sparse. Step 5 leaves requests unchanged.
- All recorded count drifts are zero; all comparable numeric summary drifts are zero. `poor_practice` has undefined `% CR` because it contains no reflections; its null drift is not a measured zero. Audit globals are supplied hand targets, so preservation of sparse-evidence global scores is established by tests, not these summary numbers.
- No recorded volley count moves after fixture introduction. The reading rule is satisfied for these fixtures: only a change allowed by the facilitative parsing rule may move a volley; counts do not move farther from hand targets; doubles are zero from step 2.

## Final counts and coverage

Count order: GI, Persuade, Persuade with Permission, Question, SR, CR, Affirm, Seeking Collaboration, Emphasizing Autonomy, Confront. Each vector equals the fixture target.

| Fixture | Final counts | Covered / clinician words | Residual |
|---|---|---:|---:|
| good_practice | 1, 0, 1, 6, 2, 4, 2, 2, 2, 0 | 294 / 294 | 0 |
| poor_practice | 2, 5, 0, 3, 0, 0, 0, 0, 0, 4 | 184 / 184 | 0 |
| short_session | 1, 0, 0, 1, 2, 1, 1, 1, 0, 0 | 70 / 70 | 0 |
| batch_edge | 24, 0, 1, 0, 0, 0, 0, 1, 1, 0 | 749 / 749 | 0 |
| sparse_evidence | 0, 0, 0, 1, 3, 0, 0, 0, 1, 0 | 27 / 27 | 0 |

Coverage counts a whitespace word once when any located utterance span overlaps it, including uncoded and down-counted utterances. All these hand-authored spans cover their clinician text completely; zero residual says nothing about omitted speech in a real model response. Tests separately check partial/overlapping spans and the informational `coverage_gap` at 40 words with no located utterance, including no retry or failure caused by that gap. This whitespace proxy is limited for spaceless languages even though volley parsing has a character-based heuristic.

## Reproducibility and limits

At implementation commit `6af8a73`, a fresh `audit_report.py` output byte-matched committed `step5.json`; `regen_goldens.py` printed `No changes.` Both tools run offline and require no API key. The snapshots carry source, pack and expected-data fingerprints. Golden regeneration maintains the existing good-practice synthetic response set; it does not generate responses for all five fixtures.

Request words count whitespace-separated words in cache prefixes, system and user strings for every initial code batch and the globals request; repeated prefixes count for each call. Schemas, tips and retries are excluded. This is a request-size proxy only: no tokenizer, cache savings, latency, p95, cost, live outputs or clinical accuracy were measured. Hand-set synthetic targets are not independent human coding. Short-turn semantics, reflection acknowledgements, permission outside the bounded context, transcript-only cues and unvalidated model judgments remain limitations; see the [manual audit](../audit.md).

Verification command:

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python -m pytest engines/miti/tests -m "not live" -q
```

Result: **581 passed, 2 failed, 3 deselected in 7.93s**. The three live cases were excluded. Two existing builder-fixture comparisons in `test_build_report.py` remain pending repair after the Task 6 golden refresh:

- `test_matches_golden_except_volatile_and_run_info` (line 38): header provenance differs. The builder helper supplies `preset=fixture`, `code_version=fixture`, and Anthropic fixture routes; the refreshed golden uses null preset, `fixture-build`, Gemini fixture routes, null tips route, and additional parameter fields including the change goal. Both `header.coded_span` values are null.
- `test_run_info_renames` (line 48): the assertion removes `span` only from actual keys, but the refreshed golden now includes that key. Actual spans are null; the golden MITI span records whole-session provenance (`duration_s=1205`, `seed=req-golden`).

These failures expose stale fixture assumptions, not an established production scoring defect. Repair should deliberately align the builder input/baseline contract and compare span provenance explicitly; Task 8 does not edit tests, fixtures or production code. The suite is therefore **not fully green**. Repository link validation reported `0 broken relative link(s)`; an additional direct check covered all relative links in these three changed documents because the repository checker skips historical agent artifacts. `git diff --check` passed. No network, live checks or credentials were used.
