---
status: draft
summary: Replace the eval results matrix with paired metric stories, honest label coverage, and a path from disagreement to session evidence.
date: 2026-11-24
---

# Eval Compare and Summary: proposal

## Recommendation

Make **Summary** answer “Where does this configuration differ, on which sessions, and how consistently?” Make **Compare** the session investigation reached from that answer. Both should work with or without human numeric labels. Replace the wide matrix with one selected metric, vertical configuration cards, a paired session plot, and a ranked session list. Keep all ten behavior counts and four globals discoverable through grouped metric navigation; do not collapse them into a universal quality score.

**All choices below are proposed decisions, not approved requirements.** This is a design draft only. The wireframes use invented numeric examples to demonstrate behavior; none represents a measured model result, source quotation, speaker identity, or timestamp. No live evaluation or dataset inspection was performed.

The governing [mission](../../mission.md) remains MITI 4.2.1 coding, a report, and basic tips. Evaluation measures agreement with a stated reference, not clinical correctness, official MITI validation, or overall counseling quality. Dataset high/low tags remain source metadata, never a substitute for MITI ratings.

## What the repository actually provides

- [Runs.tsx](../../../eval/web/src/Runs.tsx) currently renders Compare as configuration rows across sixteen metric columns. Summary is an even wider sortable MAE table, highlights each metric's minimum independently, and only appears when `has_human` is true. It does not show the promised cross-session raw means described in [eval-site.md](../../reference/eval-site.md). The code, rather than that stale description, is the baseline for this proposal.
- [build_compare](../../../eval/backend/src/onolys_eval_backend/read_runs.py) already returns per-session metric means, min/max and successful-value counts; human values; mean signed differences; per-repeat MAE/bias; failed counts; unit IDs; and human-reference aggregates. It does not build model-to-model comparisons or enforce a common cohort across configurations. `has_human` means the Human engine was selected, not that any numeric reference is present.
- [Core metrics](../../../eval/core/src/onolys_eval/metrics.py) support signed difference, absolute difference, MAE, mean bias and globals within one point. They omit null pairs. Although the module describes session weighting, the backend passes one comparison **per successful repeat**: three successful repeats give a session three contributions, two repeats give it two. The UI's “n sessions” currently labels this repeat-level denominator. [The read-side test](../../../eval/backend/tests/test_read_runs.py) deliberately verifies this behavior and the distinction between error of a mean and mean error.
- [Gold](../../../eval/core/src/onolys_eval/gold.py) permits partial or empty labels and optional turn codes. [Adapters](../../../eval/core/src/onolys_eval/adapters.py) expose scores independently of engine evidence; one-shot scores do not contain quote spans. [Pack formulas](../../../eval/core/src/onolys_eval/_formulas.py) recompute all six MITI summaries; the web comparison currently exposes only R:Q and %CR in addition to the fourteen authorable metrics.
- [Run creation](../../../eval/backend/src/onolys_eval_backend/runs.py) saves private transcript/gold snapshots and hashes, effective session settings, execution SHA, versions and resolved combinations. Run-detail already returns units and their `run_info`; large output bodies load separately. The browser's present provenance disclosure shows only a subset.

## The two-screen story

### Summary: choose the question, then inspect a metric

At the top, choose **Against human labels** or **Between configurations**. A configuration means engine/variant + model/tier/effort + saved prompt/pack/code identity, not a model name alone. Support two configurations initially; a user can select additional candidates as vertically stacked cards without adding metric columns.

An always-visible receipt states dataset/upload, selected sessions, language, effective span policy, available label scheme, repetitions, run status, and comparison cohort. Pending runs say “Provisional”; completion can change the cohort. Changes to filters update the receipt, figures and session list together. Summary precedes the existing unit-progress list; detailed execution progress can collapse after completion.

Metric navigation groups **Counts**, **Globals**, and **Derived summaries**. Counts use counts per coded session; globals use rating points; %CR error uses percentage points; R:Q uses ratio units. No averaged score mixes those units. The first selected metric is Questions when comparable, otherwise the first metric with valid pairs. Show unsupported metrics disabled with their reason and an explicit “Model outputs only” inspection option.

**Illustrative wireframe — model against partial human labels.** Example represents a selected subset of AnnoMI, not a real run. Every numeric value below is illustrative.

```text
Summary                                      [Compare a session]
[Against human labels ▾]   Reference: AnnoMI mapped counts
Subset: 12 sessions · 3 repeats · completed
Labels: Questions / SR / CR / GI · 0 of 4 globals labeled
[Coverage and exclusions: 11 paired sessions ▾]

[Counts ▾] [Questions ▾]               Units: count / coded session
Reference: human mapped annotations; utterance/volley mismatch applies

CONFIGURATION A                         CONFIGURATION B
MITI · saved model/tier/effort            MITI · saved model/tier/effort
MAE 1.36 counts                          MAE 1.73 counts
Bias +0.27                               Bias −0.45
11 same sessions · 32/33 repeats         11 same sessions · 33/33 repeats
[Versions and prompts]                  [Versions and prompts]

Paired session mean absolute error; lower is closer to reference
0             1             2             3 counts
Example 01    A●─────────────○B             A 1.0 · B 2.0
Example 02                  B○──────●A      A 2.5 · B 2.0
Example 03    A●○B                         A 1.0 · B 1.0
… 8 more sessions                         [Show all]
Each row = one session; A/B positions = mean absolute error over repeats

[Largest disagreement ▾] [All source quality labels ▾]
Example 02   A MAE 2.5 · B MAE 2.0 · 3/3 repeats each   [Inspect]
Example 07   A MAE 2.0 · B MAE 3.0 · 2/3 vs 3/3       [Inspect]
```

The shortened plot is schematic; it shows only three of eleven paired sessions. The card values are illustrative placeholders for the full cohort. A compact alternative to the full plot is a single horizontal dot plot of session errors for the selected metric, with one vertically stacked row per configuration. The paired session plot should be the default for two candidates because it exposes whether an apparent improvement comes from the same sessions.

### Summary without human labels: disagreement is still useful

The “Between configurations” mode explicitly chooses A and B. Replace “error” with **difference** or **disagreement**; never imply B is correct. Display signed B−A, mean absolute disagreement, the number of paired sessions, and repeat completeness. For globals show an exact 1–5 distribution per configuration and absolute differences; fractional repeat means must not be displayed as original single-run ratings.

**Illustrative wireframe — no human numeric labels.** PHAC is a real supported source with no labels; the subset, configurations, outputs and numbers here are illustrative.

```text
Summary · PHAC English · illustrative 4-session selection
[Between configurations ▾]   A [saved config A ▾] B [saved config B ▾]
No human numeric labels. Agreement between models does not establish accuracy.
4 sessions selected · 3 paired · 1 excluded [Why?]
[Counts ▾] [Questions ▾]                     B − A, count / session

Mean absolute disagreement 1.67   Mean signed difference +0.33
3 same sessions · A 9/9 repeats · B 8/9 repeats

            fewer in B       same       more in B
                   −2  −1     0    +1   +2 counts
Example A           ●─────────│                  −2
Example B                     │────●             +1
Example C                     │─────────●        +2
                    axis spans −2 to +2; each dot = B mean − A mean

Excluded: Example D · B has no successful output (3 failed units)
[Inspect Example A] [View all exclusions] [Inspect repeat spread]
```

Those three differences yield mean absolute disagreement (2+1+2)/3 = 1.67 and signed difference (−2+1+2)/3 = +0.33. Plotted points and cards must derive from the same observations, with no independently authored summary numbers.

### Compare: follow a session disagreement to its evidence

Selecting a session preserves metric, A/B, cohort and filters; Back restores them. A bounded session selector supports next/previous in the ranked order. Keep three vertically ordered sections:

1. **The result.** Selected metric, human reference if present, A/B individual repeat dots, mean/range, and clear delta labels. Expand other count/global groups below; use one metric card per row, never a horizontal all-metric matrix.
2. **The coding evidence.** A shared transcript pane, with adjacent or stacked A/B coding cards filtered to the selected metric. Each card names the exact repeat/unit and links to its quoted turn spans, rationale and warnings where supplied. Human turn labels appear only when the saved gold includes `utterance_codes`. A human aggregate without turn labels says “Reference count only; no turn-level reference supplied.” A global rating opens its actual evidence lines rather than count instances. Keep basic tips inspectable after coding evidence, without inventing a numeric tip-quality score.
3. **The input and method.** Effective clinician speaker, goal, language, coded span, transcript hash, source label/mapping notes, prompt/pack/model facts, errors and raw JSON. Source timestamps appear only when present. Missing text evidence says “Evidence unavailable for this engine”; for one-shot, show saved output/tips without synthesizing quote spans.

**Illustrative session card; counts only, no fabricated transcript.**

```text
Example session · Questions                     [Previous] [Next]
Human 10 · A repeats 8 / 10 / 12 · B repeats 11 / 11 / failed
A mean 10, range 8–12, n=3 · B mean 11, range 11–11, n=2
A mean signed difference 0 · mean absolute error 1.33
B mean signed difference +1 · mean absolute error 1.00

[A repeat 1 ▾] [B repeat 1 ▾]      [Show differing coding locations]
Transcript: load saved turns; highlight only validated source spans
Human: count only — no turn-level annotation available in this example
A: selected code instances and their supplied rationale
B: selected code instances, or explicit evidence-unavailable state
[Raw unit output] [Saved input and method]
```

The two errors explain why a mean on its own is misleading: A averages to the human value while varying around it. An automated “differing coding locations” filter is a proposed later aid, restricted to comparable saved turn IDs/spans. A matching turn does not establish a one-to-one utterance match; full confusion matrices or precision/recall require a separately defined alignment policy.

## Pairing and denominators are part of the design

**Proposed decision: metric-specific paired cohorts, session-balanced aggregates.** For a selected metric, first determine eligible sessions from the saved input and reference coverage, then retain sessions with at least one defined successful repeat in every selected configuration. Human mode also requires that metric's human value and compatible reference span. Use this same session set for all displayed candidates. Report both selected and paired totals; changing metric may change the cohort and must refresh its receipt. A strict “all planned repeats successful” filter is optional, visibly changes the cohort, and never activates silently.

For human reference value h(s), repeat output x(s,c,r), and successful defined repeats R(s,c), calculate session MAE as mean over r of |x−h| and session bias as mean over r of x−h. Then average each session statistic over the common sessions. Within-one for globals similarly averages each session's fraction of repeats within one point. Report **sessions** and **defined successful repeat observations** separately. Never calculate MAE as |mean(x)−h|. Preserve the old unit-weighted aggregate only as a clearly named diagnostic, not the Summary default.

In model-to-model mode, use each configuration's defined repeat mean per session: d(s)=mean(B)−mean(A). Average d and |d| over common sessions. Name the latter **mean absolute difference of session means**. It can hide repeat instability, so display the repeat plots beside it. Do not pair repeat index 1 with index 1 as if they shared controlled randomness, and do not create nine independent observations from three-by-three repeats. Report differences in reference error separately when human labels exist; raw model disagreement is not evidence that one is more accurate.

**Proposed decision: start within one saved run.** Later cross-run comparison requires the same transcript hash, effective clinician, change goal, language, span, and gold hash when reference-based. Model/prompt/pack/code differences are the experiment, so show them rather than demand equality. Refuse direct pairing for unequal inputs/spans or unknown historical input identity; permit separately labeled exploration without comparative headline claims. Across datasets, key by dataset + session + snapshot, and group documented source overlaps; AnnoMI/AnnoSUM and HLQC/AutoMISC must not be counted as independent confirmations. French/English PHAC sessions are not paired translations. These cautions follow [dataset coverage](../../reference/eval-datasets.md).

## Partial labels and exclusions

The [AnnoMI converter](../../../eval/core/src/onolys_eval/annomi.py) maps exactly `question`, `sr`, `cr`, and `gi`; the other six counts and all four globals are unlabeled, not zero. Its annotations are per utterance while the engine applies volley rules. The source's high/low tag is a filter only. Show this at reference selection and beside affected results, not buried among repeated footnotes.

**Proposed decision:** treat R:Q and %CR computed from those four mapped counts as **derived mapped-reference values**, off by default. AnnoMI supplies no independently annotated summaries; existing core formulas can nevertheless derive these two where inputs exist and denominators are nonzero. Make the distinction visible rather than describing a derived value as a human MITI summary. Technical/Relational and other unsupported summaries remain unavailable. For AnnoSUM empathy, display the documented approximate-reference caveat; do not present its Likert scale as MITI-anchored ground truth. HLQC quality-only and PHAC empty-gold sessions enter model-to-model mode by default even if `has_gold`/`has_human` is true.

Every selected metric has an expandable, session-linked accounting list with mutually exclusive primary reasons: not human-labeled; reference unavailable/failed; incompatible span/input; no defined output in one selected configuration; undefined formula denominator. Unit details then explain failed, cancelled, queued/running, skipped and any future model abstention; those are not all “failed.” A successful zero count is included. Null is displayed with its reason and excluded from arithmetic. A failed repeat does not automatically exclude a session if another defined repeat exists under the default policy. Different metrics can have different valid-repeat counts.

Repeat strips show the actual one or three planned eval repeats, including missing slots and failure markers. Min/max means observed repeat range, not a confidence interval. With one repeat, say “Repeat variability not measured.” Keep engine-internal `n_runs` distinct from eval repetitions: the [MITI adapter](../../../eval/core/src/onolys_eval/adapters.py) can score already-averaged counts, while globals use the representative report score. Newly nullable global handling on this branch must preserve abstention through adapters and counts. Do not plot missing globals at 3 or at 0.

## Available data versus new work

| Capability | Already available | Proposed addition |
|---|---|---|
| Human-reference error | Core MAE, bias, within-one; backend repeats and metric n | Common cohort selection, equal session weighting, clear session/repeat denominators |
| Model-to-model | Individual unit scores and per-session ranges | Pair selector, defined delta semantics, server aggregation, no-label Summary |
| Repeat variability | Per-unit scores; cell mean/min/max/n | Visible repeat dots and missing slots; distinguish internal runs |
| Coverage | Gold nulls; unit status/span/warnings; catalog label descriptions | Safe structured metric coverage and exclusion reasons; human span compatibility gate |
| Derived summaries | Core pack formulas for six summaries; UI exposes two | Explicit mapped-reference labels; optionally expose remaining pack summaries after primary metrics |
| Evidence | MITI report instances/global evidence; optional gold turn codes; output endpoint | Safe saved-transcript/gold projection, unified transcript viewer, repeat-aware linking |
| Provenance | Saved inputs/hashes privately; MITI prompt/pack/routes and one-shot config/model facts in run info | Normalized public allowlisted receipt, visible per-candidate differences and unknown fields |
| Statistical uncertainty | None supplied by compare API | Defer bootstrap intervals, ICC/kappa and significance claims; avoid misleading three-repeat intervals |
| Performance | Token usage and estimated cost; missing-price indicator at run level | Preserve completeness and STT-excluded labels in candidate cards; new measured elapsed-time fields needed before latency/p95 plots |

This is not a need for a new evaluation framework. Extend [the read-side service](../../../eval/backend/src/onolys_eval_backend/read_runs.py), [API types](../../../eval/web/src/api.ts), and existing results components. Send selected metric, configurations and cohort policy to one comparison calculation; the response supplies cards, plot observations, denominator receipt and exclusion rows together. Raw units remain the audit trail. Use semantic lists and a narrow accessible data table for the selected plot as its keyboard/screen-reader equivalent; no sideways scrolling is required at mobile widths.

The provenance receipt should expose immutable identifiers and safe metadata, never private storage paths, credentials or unrelated config. MITI [run info](../../../engines/miti/src/onolys_miti/run_info.py) has stage prompt hashes, pack hash, route parameter hashes and effective temperature; [one-shot](../../../engines/oneshot/src/onolys_oneshot/engine.py) records configuration hash/version and returned model. Show only fields genuinely saved by that engine; do not invent a one-shot prompt hash or claim a provider model alias identifies a frozen model revision. A SHA and prompt hashes identify code/templates, not guaranteed deterministic outputs. If identities differ across units inside a candidate, split or flag the candidate instead of silently merging it. Estimated cost remains an operational measure including attempted work, not a gold-paired metric; show its scope and unpriced-unit count.

## Minimal build phases and acceptance checks

1. **Truthful Summary and pairing contract.** Add coverage receipt, metric picker, vertical cards, model-to-model mode, explicit missing reasons and common-cohort/session-balanced calculations. Keep JSON as the initial drilldown. Acceptance: partial/empty gold, disjoint successes, different spans, a real zero, null denominator, unequal repeats and provisional runs produce correct labeled cohorts; the 8/10/12 versus human-10 example yields MAE 1.33, not zero; the −2/+1/+2 example yields mean absolute difference 1.67 and bias +0.33. Repeats never increase the unique-session denominator. No unlabeled metric wins a “best” badge.
2. **One metric's story and repeat inspection.** Add paired session error/delta plots, exact per-session values, ranked rows and repeat strips. Acceptance: plots/cards/list use identical observations, selected units remain identifiable, changing metric/reference/filter updates all views, missing repeats remain visible, keyboard navigation has a complete text equivalent, and 320 px layouts need no horizontal results scroll. No-human mode uses disagreement language throughout.
3. **Evidence and method drilldown.** Add authenticated saved-input projection, selected-unit evidence links, human turn labels where supplied and normalized provenance. Acceptance: linked quote offsets reproduce exact saved transcript substrings; unsupported evidence never fabricates quotes or alignments; speakers/timestamps come from saved input only; report aggregation is never presented as one repeat's evidence; prompt/model differences and unknown fields remain visible. Source paths stay private. Cross-run pairing, richer uncertainty estimates and automatic turn alignment remain deferred.

## Decisions to confirm before implementation

- **[OPEN; recommended]** Use equal session weighting and metric-specific common cohorts as the headline calculation, with successful repeats retained and their completeness visible.
- **[OPEN; recommended]** Start with two configurations within a run; postpone cross-run selection until immutable input matching is exposed safely.
- **[OPEN; recommended]** Keep mapped-derived reference ratios available behind an explicit toggle; default AnnoMI to its four mapped counts.
- **[DEFERRED]** Turn alignment metrics, reliability statistics, uncertainty intervals, latency instrumentation and a composite ranking. They need contracts beyond the current Compare/Summary redesign.

No implementation or live model calls are included in this proposal.
