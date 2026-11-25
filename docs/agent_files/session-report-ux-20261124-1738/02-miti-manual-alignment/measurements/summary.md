---
status: done
summary: Deterministic rule alignment and request-size evidence; final offline verification passes 587 tests after review fixes.
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

At implementation commit `6af8a73`, a fresh `audit_report.py` output byte-matched committed `step5.json`; `regen_goldens.py` printed `No changes.` After review fix `739dfc7`, the audit was refreshed: only `source_sha256.code_pass.py` changed, from `61e9627767d7335fb8d732d6fd09b42d0740d952a46c6a896ac1b2981806e515` to `a4738f940c206401a41cd5815d6b987be224b562026f710bb5381bae89ed0a8c`. All fixture measurements, request sizes and residuals remain unchanged; `step4.json` remains historical. Both tools run offline and require no API key. The snapshots carry source, pack and expected-data fingerprints. Golden regeneration maintains the existing good-practice synthetic response set; it does not generate responses for all five fixtures.

Request words count whitespace-separated words in cache prefixes, system and user strings for every initial code batch and the globals request; repeated prefixes count for each call. Schemas, tips and retries are excluded. This is a request-size proxy only: no tokenizer, cache savings, latency, p95, cost, live outputs or clinical accuracy were measured. Hand-set synthetic targets are not independent human coding. Short-turn semantics, reflection acknowledgements, permission outside the bounded context, transcript-only cues and unvalidated model judgments remain limitations; see the [manual audit](../audit.md).

Verification command:

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python -m pytest engines/miti/tests -m "not live" -q
```

Result after review fix `739dfc7`: **587 passed, 3 deselected in 7.22s**. The three live tests were excluded. Ruff passed for `engines/miti`; golden regeneration printed `No changes.` No network, live checks or credentials were used.

The initial Task 8 verification had 581 passed, 2 failed and 3 deselected: the two builder-fixture assertions assumed matching provenance and an absent evaluation span. The review fix explicitly asserts each intentionally different provenance field and both span contracts while preserving complete report and adapter parity. Its new context-guard regressions first produced 3 failures / 1 pass; the builder baseline produced 2 failures / 19 passes. The fixed focused set passed 73 tests before the final 587-test verification. See the [review-fix evidence](../code-2026-11-24-2202-review-fixes.md) and [final review](../review-2026-11-24-2203.md).

The Task 8 repository link check reported `0 broken relative link(s)`, with historical artifact links checked directly, and `git diff --check` passed. Final documentation changes were also checked for relative-link validity and whitespace errors.
