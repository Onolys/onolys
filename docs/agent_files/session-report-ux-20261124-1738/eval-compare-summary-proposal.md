---
status: draft
summary: Redesign eval Compare/Summary around one question, which combo is closest to human coding and where, in three levels (Overview, Deep dive, Session/line view).
date: 2026-11-24
---

# Eval Compare and Summary: combos vs human

All numbers, names and sessions in the wireframes below are invented examples. None is a measured result, a source quote, or a timestamp. A visual mockup lives at `docs/agent_files/session-report-ux-20261124-1738/eval-compare-mockup.html` (another agent is building it).

This is a design draft. All choices are proposals, not approved requirements. Evaluation measures closeness to human coding, not clinical correctness or official MITI validation (see [mission](../../mission.md)).

## Scope

- **One run = one fixed prompt/pack.** Combos ("configurations") vary provider, model, tier and effort. Compare within one run only.
- **Out of scope for now:** prompt versioning and cross-run comparison.
- **Human coding is always the reference.** "Better" means closer to human. Any number of combos can be compared against human; the views below scale rather than cap (see "Scaling to many combos").
- **Goal:**
  1. Decide which combo to use in prod.
  2. See WHERE each combo is better or worse, so the owner can study why. Example: A best at Cultivating Change Talk, B best at Softening Sustain Talk and handling discord, C best at Complex Reflections.

## The story: three levels

1. **Overview** answers "Which combo for prod?"
2. **Deep dive** answers "Where is each combo better or worse, and how does it reason?"
3. **Session / line view** answers "What exactly happened on this line?"

Each level links to the next: a heatmap cell opens the deep dive for that code; a deep-dive bar or confusion cell opens the matching lines.

## Level 1: Overview

### Verdict line

One plain sentence generated from the data, for example:

> B is closest to human overall; A is best on Partnership; all combos over-count Questions.

Rules: built only from table values shown below; says "too few sessions to say" when n is small; never names a winner on a metric with no human label.

### Leaderboard

One row per combo (any number; sortable by any column, default sort by Count error, scrolls vertically). Best value in each column is marked (`*`).

```text
Run: 12 sessions, 3 repeats each. Human labels: all counts, 4 globals.
Combo            Count error   Globals     Line match        Line match   Fails  Cost    Time
                 (avg miss/    within      (accuracy)        (macro F1)
                 session)      +-1
A  prov/model/hi   4.1          72%         61%               0.48         0      $3.20   41m
B  prov/model/lo   3.2 *        81% *       66% *             0.53 *       1      $1.10 * 18m *
C  prov2/model     5.0          64%         58%               0.44         0      $2.40   25m
(example numbers)
```

Column meanings (one line each; fuller rules in the appendix):

- **Count error:** on average, how many tallies per session the combo misses versus human, summed over the 10 behavior codes. Example: human has 5 Questions, combo has 8, miss = 3.
- **Globals within +-1:** share of global ratings (1 to 5) that are no more than one point from human. Example: human 4, combo 3 counts as within.
- **Line match (accuracy):** share of lines where the combo gave the same code as human. Only shown when human line labels exist.
- **Line match (macro F1):** one score from 0 to 1 that averages how well each code is found and correctly named, so rare codes count as much as common ones.
- **Failures, cost, time:** operational. Cost and time are not compared with human.

### Heatmap: who is best at what

Rows are the 10 behavior codes, the 4 globals, R:Q and %CR. Columns are the combos, as compact columns with short labels (A, B, C, ...) and a legend mapping each label to provider/model/effort; beyond about 8 columns the grid scrolls horizontally with the row labels frozen. Each cell shows closeness to human; color intensity shows closeness. The winner per row is marked. This is the main "who is best at what" view.

```text
                          A       B       C
Questions                 -2.1    -0.4 *  -1.8     (avg miss; closer to 0 is better)
Simple Reflections         0.9     1.2     0.3 *
Complex Reflections        1.5     0.8     0.2 *
Affirmations               0.7 *   1.1     1.4
Cultivating Change Talk    0.3 *   1.0     0.9
Softening Sustain Talk     1.2     0.2 *   0.8
...
Partnership (global)       0.2 *   0.4     0.6
R:Q                        0.3     0.2 *   0.5
(example numbers; grey = fewer than 5 paired sessions, no winner marked)
```

Cell reading: a signed number shows direction (negative = under-counts vs human, positive = over-counts). Color shows size only, so over- and under-counting are not confused. Click a cell to open the Deep dive on that row.

### Sample-size note

Beside the tables: "12 sessions, 3 repeats each; 11 paired for this metric." Cells with too little data go grey and cannot win. Sessions, not repeats, are the n shown first.

## Level 2: Deep dive

Human is always shown. Default selection is the top 3 combos by Count error; tick more (or any) to add them, so charts stay readable. Four sections, stacked vertically.

### Globals

Per global (Evocation, Collaboration, Autonomy/Support, Empathy and so on, as in the pack), a dot chart with one row per session: human dot and one dot per combo. Beside it: average miss and share within +-1.

```text
Partnership        human H   A   B   C         avg miss   within +-1
Session 01         4  H--------A3--B4  C5      A 1.0      A 70%
Session 02         3  HB-------A4----C2        B 0.3      B 90%
(example numbers)
```

### Counts

Per code, grouped bars of total counts across selected sessions: human next to each combo. Under each group, a bias word: "over-counts by 12%" or "under-counts by 8%".

```text
Questions    H ████████ 80   A ██████████ 101  B ████████ 83  C ██████ 62
             A over-counts, B close, C under-counts          (example numbers)
```

### Per-line agreement

Needs human line labels (gold `utterance_codes`). Not every dataset has them; AnnoMI maps only Question, SR, CR and GI. Where labels are missing the section says so and shows nothing for the unmapped codes.

Per code, per combo, three numbers in plain words:

- **Precision:** when the combo says SR, how often the human agreed. Example: 8 of 10 SR calls were human SR, so 80%.
- **Recall:** of the lines the human called SR, how many the combo found. Example: human called 16 lines SR, combo found 8, so 50%.
- **F1:** one number that is low if either of the two is low.

**Confusion matrix:** human code (rows) by combo code (columns), one combo at a time with a switch. It shows things like "A called 14 lines SR that human called CR". Click a cell to jump to those lines in the Level 3 view.

```text
Combo A          A says: Q   SR   CR   GI   none
Human: Q               40    1    0    0    3
Human: SR               2    22   9    0    4
Human: CR               0    14   11   1    5     <- A called 14 CR lines SR
(example numbers)
```

### Reasoning roll-up

Per code, one panel per combo next to human: total count, plus grouped rationale snippets taken from the combo's saved report (`rationale` on each coded instance). Rationales are grouped by similarity so the owner can read "how does A reason about Complex Reflections" in one place. Human has no rationale in most datasets; its column shows counts and, where present, the gold note. Snippets are shown verbatim from saved output, never rewritten.

## Level 3: Session / line view

A transcript with narrow code lanes beside it. Lanes: Human plus each selected combo. Beyond about 5 lanes, lanes collapse to chips that show only the combos that disagree with human on that line (agreeing combos are summarized as "+N agree"); expand to see all.

```text
Session 03   [x] only disagreements  [code: all v]  [combo: all v]
 #   Line text (from saved transcript)              Hum   A    B    C
 12  ..........................................     SR    SR   CR*  SR
 13  ..........................................     Q     Q    Q    Q
 14  ..........................................     CR    SR*  CR   SR*
 (* differs from human; row highlighted)            (example only)
```

- Lines where any combo differs from human are highlighted.
- Filters: only disagreements, by code, by combo.
- **Click a line** opens a popup: the line text, the human code, each combo's code with its rationale, and the repeat spread when several repeats exist (for example "2 of 3 repeats said SR").
- **Per-session globals table** under the transcript: human rating versus each combo's rating, with the combo's stated reason and the evidence lines it cites.

Line text, speakers and any timestamps come only from the saved input. Nothing is invented. If a combo's engine produced no line-level output, its lane says "no line-level output" and is left blank, not filled with "none".

## What data exists today vs what is new

| Need | Exists today | New work |
|---|---|---|
| Per-session metric values per combo | `build_compare` returns per-session, per-combo cells: mean/min/max, n, failed, unit ids, human values, signed diff | Nothing for raw values |
| Avg miss and within +-1 per combo | `aggregates` rows (only when the human engine is selected): MAE, bias, within_1, usage, cost, failed. Backend counts per successful repeat | Session-balanced aggregation per combo vs human; common cohort across combos; "which combo wins" flags per row |
| Heatmap (code x combo) | Underlying per-metric errors are in `aggregates[].metrics` | Reshape to row-per-metric with winner and grey-out rules |
| Verdict line | None | Generate from leaderboard and heatmap values |
| Time per combo | Per unit `started_at` (set at claim) and `finished_at` (set on completion) in `runs.py` | Time = `finished_at` - `started_at` per unit, averaged per combo. Caveat: `started_at` resets if a unit is re-claimed after a lease expiry, so time can be understated for retried units |
| Human line labels | Gold `utterance_codes` (turn_id, codes), present for AnnoMI, AnnoSUM, MiTags, MIDAS, AutoMISC; absent for HLQC, PHAC | Safe projection of saved gold to the web |
| Combo line codes and rationale | MITI report instances carry `turn_id`, `quote`, `id` (code) and `rationale`; read via the saved output endpoint, not in `build_compare` | Aggregate instances per turn and combo; return compactly |
| Precision/recall/F1, confusion matrix | None | New server calculation using the alignment policy below |
| Rationale roll-up grouping | None | Group by code and combo; similarity grouping is a later nicety (plain grouping by code first) |
| Global reasons and evidence lines | MITI report global evidence | Surface per session |
| Transcript for line view | Saved private input snapshots | Authenticated projection of saved turns |

**Per-line alignment policy.** Match human and combo lines by `turn_id`. A line counts only when the combo's report and the gold share that turn id. A turn the human coded and the combo did not code becomes "none" for the combo, only when the combo's engine produces line-level output at all. If an engine has no line-level output (for example one-shot scores without spans), it gets no line metrics and its lane says so. Dataset caveat: AnnoMI codes per utterance while the engine applies volley rules, so some lines legitimately differ in grouping; note this beside line metrics for that dataset.

## Scaling to many combos

There is no limit on the number of combos in a run (the backend caps a run at 499 units, not combos). Views scale as follows.

- **Leaderboard:** one row per combo, sortable, vertical scroll.
- **Heatmap:** metrics as rows, combos as compact columns with short labels and a legend; frozen row labels, horizontal scroll past about 8 columns.
- **Deep dive:** Human plus the top 3 combos by default; tick more to add.
- **Line view:** lanes collapse to only-disagreeing chips beyond about 5 combos.

## Storage: eval runs reuse prod runs

Status: proposal, not decided. Based on a code read of `eval/backend`, `api/` and `infra/` on this branch (2026-11-24). Owner direction: eval should use the same DB and storage as a real run and just mark the run `eval = true`, adding only what a prod run lacks.

**How eval stores data today.** Firestore database `staging` (the same database the staging app uses; `infra/main.tf:101`) holds `eval_uploads`, `eval_runs` and `eval_runs/{id}/units` (`eval/backend/.../repository.py:144-145,193`). The private bucket `onolys-eval-data-staging` holds datasets, `uploads/<id>/` and `runs/<run>/inputs/<session>/transcript.json|gold.json`, plus `runs/<run>/<unit>.json` (`runs.py:340-348`; `eval/backend/.../storage.py`). Each run copies a transcript and gold snapshot per session. Engines are called in process through the shared engine registry, not through the api/worker pipeline (`runs.py:717-783`). Work runs on its own Cloud Tasks queue (`infra/eval-services.tf:57-58`, 4 concurrent), with its own lease/retry in `execute_unit`. Identity is an allowlisted admin email (`created_by`, `runs.py:380`), with no per-user uid and no usage cap (`docs/reference/eval-site.md`).

**How a prod run stores data.** `sessions/{sid}` (owner `uid`, state, step, language, `change_goal`, `coded_span`, `clinician_speaker`, `steps`) with subcollections `recordings`, `transcripts` (`current`), `runs/{run_id}`, `reports/{report_id = run_id}` and `ratings`; `session_status/{sid}` is the only client-readable doc (`firestore.rules`; `repo/models.py:180-356`). Blobs live under `{uid}/{sid}/...` and `{uid}/{sid}/runs/{run_id}/{code,tips}.json` (`jobs/run.py`). Upload staging `uploads/{uid}/{sid}/` expires after 1 day (`infra/modules/environment/main.tf:37-44`). Hard delete removes every object and doc for the session (`jobs/delete.py`). The run handler has its own lease/attempts (`claim_run`), `run_info` with usage, and a per-user day cap with `counted`/`released` flags (`repo/limits.py`, `models.py:348-353`). A run takes only an allowlisted `preset` name; there is no per-run model/tier/effort override (`routes/runs.py:62,179-181`, `adapters/real.py:145`).

### Mapping: eval concept to prod equivalent

| Eval concept | Prod equivalent | Verdict |
|---|---|---|
| Dataset session as input | `sessions` + `transcripts/current` | Reuse + field (`eval`, `dataset_id`, `dataset_session_id`) |
| Transcript-only input, no audio | Prod accepts transcript.v1 JSON or label-prefixed text upload (`routes/transcript.py:99`) | Reuse as-is |
| Audio upload, STT, speaker confirm | Same flow in prod (signed PUT, `recordings`, STT, speakers) | Reuse as-is |
| Clinician speaker, change goal, language, coded_span | Session fields of the same names | Reuse as-is |
| One unit = one engine run | `runs/{run_id}` doc with lease, attempts, `run_info`, artifacts | Reuse + field (`eval_run_id`, `combo_key`, `repeat`) |
| Output / report | `reports/{run_id}` and `{uid}/{sid}/runs/{run_id}/` | Reuse as-is, if the eval engine emits the prod report schema |
| Per-unit status, lease, retry | `claim_run`, `attempts`, task retries | Reuse as-is |
| Cost / token usage | `run_info.usage`; `usage` docs are per user | Reuse + price book (cost estimate in eval) |
| run_info / provenance | `run_info`, `code_version` | Reuse + fields (git SHA, resolved models, drift guard) |
| Eval run grouping (sessions x combos x repeats) | None; prod has no multi-session group | Missing: keep an `eval_runs` doc, pointing at prod run ids |
| Combo config (model/tier/effort route override) | Only `preset` names | Missing: allow a route override on a run, accepted only when `eval = true` |
| Engines other than the prod engine (oneshot, miti_lean variants) | Worker runs only the configured engine | Missing: either keep running them in the eval backend, or add an engine selector to the worker |
| Human gold labels (counts, globals, utterance_codes) | `ratings` are user ratings of a report, not gold | Missing: keep gold in the eval bucket as a read-only dataset reference; store only a ref and sha on the run |
| Dataset manifest and files | None | Missing: stays eval-only |
| Comparison aggregation (`build_compare`, leaderboard) | None | Missing: stays eval-only, reads prod run docs |
| Owner identity | `uid` of a real user | Reuse + decision: one synthetic uid per eval user (see below) |
| Usage caps | Per-uid day cap (`EVAL_CAP_DAY`, in prod this counts report runs) | Reuse + field: `counted = false` for eval runs; the field already exists for the exempt first run |
| Prod vs staging | One env per database | Reuse: eval stays in staging first; prod only after the risks below are settled |
| Retention | Delete removes everything; `uploads/` 1 day | Reuse + decision: eval data kept until its eval run is deleted |
| Listing / metrics that must exclude eval | Session list and usage are filtered by `uid` | Reuse + field: `eval: true`, then filter in alerts and billing metrics |

### Genuinely missing (keep or add)

1. The eval run grouping doc (`eval_runs`), with units as references `{session_id, run_id, combo_key, repeat}`.
2. A per-run route/combo override on the prod run path, rejected unless `eval = true`.
3. Gold labels and dataset manifests (eval bucket, read-only, referenced by dataset id and sha).
4. Comparison aggregation, price book and the compare UI.
5. Engines other than the prod engine, if they must be compared (open question 2).

### Risks

- **Leaking into user views.** Eval sessions must not show in user lists, usage, caps, alerts, billing or product metrics. A synthetic owner uid handles the user lists; `eval: true` must be added to every aggregate query and log metric.
- **Load on the prod worker and queue.** Prod queue concurrency is `worker_concurrency x worker_max_instances` (`infra/modules/environment/main.tf:63`). A 499-unit eval would starve real users on the same queue. Safer: a separate eval queue (or throttled enqueue) that targets the same run handler.
- **Rules exposure.** `session_status` is readable by its `uid`. A synthetic uid that nobody logs in as keeps eval statuses unreadable from the client; keep the rest deny-all.
- **Dataset licensing and privacy.** Research datasets copied into prod Firestore and the prod bucket may violate their terms and mix with real client data. Safer: eval in staging only, or a separate prod bucket prefix with its own lifecycle and access.
- **Deletion semantics.** Delete of a session removes its runs and reports. Deleting one run from an eval must not delete the shared dataset session used by other combos. Gold and dataset files must never be under the session prefix.
- **Concurrent runs in one session.** One session with many runs works for retries today; many parallel runs on a shared session may conflict on session `state`/`latest_report_version`. Unverified. Fallback: one session per unit, sharing the same transcript content by reference.
- **Different engines.** Eval calls engines directly with its own output shape and `scores`; the prod worker validates the prod report schema. A mismatch would force changes to report validation.
- **Cap naming.** `EVAL_CAP_DAY` in prod is the report-run cap, not an eval-system cap; reuse needs `counted = false`, not a new cap.

### Recommendation

Reuse the prod session, recording, transcript, run and report documents and the `{uid}/{sid}/` bucket layout. Do not copy transcripts or gold per run: create the dataset session once and point many runs at it. Put eval runs under a synthetic eval owner uid with `eval: true`, `eval_run_id`, `combo_key`, `repeat` and `counted = false` on the run. Keep `eval_runs` (grouping), the dataset manifest and gold in eval-owned storage, and keep the compare aggregation and UI eval-only. Run eval against staging only until the open questions are settled. The safer variant of the owner's direction is therefore "same collections and layout, separate owner, separate queue, separate gold", not "same everything": putting research datasets and 499-unit batches on the real prod queue and bucket carries privacy and load risk.

### Open questions

1. Should a prod run accept a route override (model/tier/effort) when `eval = true`, or should the eval backend keep calling engines in process and only write prod-shaped documents?
2. Must eval compare engines other than the prod engine (oneshot and miti_lean variants)? If yes, those need an engine selector on the worker or stay in the eval backend.
3. One session with many runs, or one session per unit?
4. Synthetic owner: one shared eval uid, or one per eval user (for audit)?
5. Is eval ever run on the prod database, and if so with which datasets (licensing)?
6. Retention: should eval data be deleted with its eval run, or kept like today until manually removed?
7. Does the human unit stay out of the run store (gold is a reference, not a run)? Proposed: yes.

## Phased build order

1. **Overview.** Backend per-combo aggregation vs human, verdict line, leaderboard, heatmap, sample-size notes. Acceptance: partial labels show "not labeled" not zero; each session counts once; grey cells cannot win; no human numeric labels means the view says "no human reference" instead of showing a table.
2. **Deep dive.** Globals dots, count bars with bias, per-line precision/recall/F1 and confusion matrix, reasoning roll-up. Acceptance: matrix totals equal the number of aligned lines; datasets without line labels show a clear message.
3. **Line view.** Transcript lanes, disagreement filters, click-through popup, per-session globals table. Acceptance: every cited line shows exact saved text; unsupported evidence is blank, never invented.

## Open questions

- Should the overview default to "all 4 combos selected" or require choosing combos first? Default proposed: all combos in the leaderboard and heatmap; deep dive starts at the top 3 plus Human with a picker for the rest.
- What is the minimum number of paired sessions before a heatmap cell is colored (proposed 5)?
- Should "Count error" sum all 10 codes equally, or let the owner weight codes that matter for prod? Proposed: equal, with per-code rows visible.
- Time understates retried units (`started_at` resets on re-claim after lease expiry). Accept with a footnote, or exclude retried units from the Time average?
- How should the roll-up group rationale snippets: by code only (simple) or by similarity (useful, more work)?
- Do we show AnnoMI-derived R:Q and %CR (computed from the four mapped counts) in the heatmap, marked "derived", or hide them? Proposed: show, marked.
- Datasets where the human has line labels but the combo's engine does not (or reverse): confirm "no line-level output" is acceptable wording.

## Appendix: Calculation rules (plain language)

- **Each session counts once.** If a combo ran a session three times, average the repeats within the session first, then average across sessions. Repeats never inflate the number of sessions. Today's backend counts each successful repeat as its own comparison; the new aggregation changes that and shows "sessions" and "repeats" as separate numbers.
- **Miss per session.** For one session and one metric: absolute difference between combo and human. Example: human 10, repeats 8/10/12 give misses 2, 0, 2, so the session's average miss is 1.33. Never average the repeats first: their mean is 10, a miss of 0, which hides the instability.
- **Over/under bias.** Signed difference, combo minus human. Positive means over-counts.
- **Partial human labels.** A code or global the human did not label is "not labeled", not zero. It is excluded from that row and shown as such. AnnoMI labels only Question, SR, CR and GI; the other six counts and all four globals are not labeled.
- **Same sessions for everyone.** For a given metric, only sessions where every selected combo has a result and human has a label are used, so combos are compared on the same sessions. The cohort is shown ("11 paired of 12").
- **A real zero counts.** A successful count of 0 is included. A failed or missing run is excluded and shown as such.
- **Honest n.** Sample sizes sit next to every number. Too few sessions turns the cell grey and removes any winner mark.
- **No invented evidence.** No quotes, speakers or timestamps beyond what the saved input and saved outputs contain. Missing evidence says "unavailable".
- **No composite score.** Counts, ratings, ratios and percentages stay in their own units; no single blended quality score.
- **Derived ratios.** R:Q and %CR from AnnoMI's four mapped counts are derived values, labeled as such.
- **Not statistics.** Min/max across repeats is the observed range, not a confidence interval. No significance claims at this stage.
