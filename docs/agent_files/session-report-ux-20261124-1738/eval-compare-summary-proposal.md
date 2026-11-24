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

## Storage and pipeline: one codebase, two deployments

Status: proposal, not decided. Based on a code read of `eval/backend`, `api/` and `infra/` on this branch (2026-11-24). Owner direction (updated): eval is allowlisted users only, so it may have its own API endpoint and its own database. But it must use the same infra and the same code: same document shapes, same run pipeline, same storage layout. Reason: a change to the prod pipeline must not force a significant change to eval, or the reverse. Two copies of the same logic is a maintenance headache. This replaces the earlier "same database, synthetic uid, `eval = true`" recommendation (kept below as the alternative).

### Principle

One shared code path. Eval is the same image and code run with eval config: its own endpoint, its own Firestore database (for example `eval`), its own bucket, its own Cloud Tasks queue, and allowlist auth. It is not a parallel implementation. Eval adds fields and an outer layer (grouping, gold, compare); it does not re-implement session, transcript, run or report handling.

### What this branch changed (the data model eval should build on)

The run-input-lock work (`01-run-input-locks/PRD.md`) makes a run self-describing. Verified in the diff:

- `RunDoc` pins `change_goal`, `clinician_speaker`, `language`, `transcript_sha256` as required fields (`api/src/onolys_api/repo/models.py:325-329`), alongside the existing `stt`, `coded_span`, `preset`, `n_runs`, `code_version` (`:330-338`).
- `TranscriptDoc` has `sha256` and `language`, built only by `TranscriptDoc.build()` (`models.py:278-296`); `transcript_sha256()` is the one hash function (`models.py:267`).
- The worker reads only `RunDoc` inputs, recomputes the transcript hash and fails with `internal_error` (log `reason=run_input_mismatch`) before any model call (`api/src/onolys_api/jobs/run.py:165-178`, `_input_mismatch` at `:159`).
- Speaker is write-once (R1), goal locks after the first run starts (R2), per the PRD.
- Eval side on the same branch: `runs.py` now keeps `saved_config` (`base_preset`, `resolved_combos`) and rejects a rerun whose combo snapshot changed (`eval/backend/.../runs.py:268-326`), and runs carry `RunMetadata` name/description (`runs.py:103-108`, `read_runs.py`).

Key finding: eval's per-session snapshot already looks like a RunDoc, field for field. Its `input_ref.sessions[]` stores `transcript_sha256`, `change_goal`, `language`, `coded_span`, `speaker_map.subject` (`runs.py:191-246, 342`), which are the same pinned inputs as the new RunDoc fields. Its `_hash` (`runs.py:137`) is byte-for-byte the same canonical JSON sha256 as `transcript_sha256()`, written twice.

### Mapping: eval concept to the prod shape it reuses

| Eval concept | Prod shape reused on this branch | Verdict |
|---|---|---|
| Dataset session / upload as input | `SessionDoc` (`models.py:180`) + `TranscriptDoc` via `TranscriptDoc.build` (`:278`) | Reuse; eval fields `dataset_id`, `dataset_session_id`. One session per dataset session, created once and shared by many runs |
| Transcript hash (`input_ref...transcript_sha256`, `_hash`) | `transcript_sha256()` (`models.py:267`), stored as `TranscriptDoc.sha256` and `RunDoc.transcript_sha256` | Reuse; delete eval's `_hash` for transcripts. Eval's integrity check (`runs.py:200`) becomes the worker's check (`jobs/run.py:165-178`) |
| `speaker_map.subject`, `language`, `change_goal`, `coded_span` per source | `RunDoc.clinician_speaker`, `language`, `change_goal`, `coded_span` (`models.py:326-330`) | Reuse as-is. Eval's `inferred_clinician_speaker` is also what the prod transcript route uses (`routes/transcript.py:174`); keep that call in one place |
| One unit (session x combo x repeat) | `RunDoc` (`models.py:325`): lease, attempts, `run_info`, artifacts | Reuse; eval units are prod-shaped RunDocs plus `eval_run_id`, `combo_key`, `repeat`, route override |
| Unit status / lease / retry (`execute_unit` loop, `MAX_ATTEMPTS`) | `claim_run` (`repo/firestore.py:767`), run handler `jobs/run.py` | Reuse; delete eval's own lease/retry |
| Unit output | `ReportDoc` (`models.py:356`) + `{uid}/{sid}/runs/{run_id}/{code,tips}.json` | Reuse; eval reads the saved report for compare |
| Engine call | `evaluate_validated` -> `run_validated` (`adapters/validated.py:35`, `adapters/real.py:159`) | Reuse; eval calls `run_validated` directly today (`runs.py:782`) |
| Provenance (`engine_git_sha`, `engine_versions`, resolved combos, drift guard) | `RunDoc.code_version`, `run_info` | Reuse + extra fields: resolved route snapshot on the run; drift check stays as an eval rule |
| Combo route override (model/tier/effort) | Only `preset` names today (`adapters/real.py:145`) | Extra field `route_override` on the run, accepted only when the deployment is eval |
| Engines other than prod (oneshot, miti_lean configs) | Worker runs only `settings.prod_engine` (`adapters/real.py:144`) | Extra field `engine` on the run, allowed only in eval deployment (open question 1) |
| Cost / usage | `run_info.usage` | Reuse; price book and cost estimate are eval-only |
| Per-user usage cap | `counted`, `released`, `cap_date` on `RunDoc` | Eval deployment: caps off (or `counted = false`) |
| Eval run grouping (`eval_runs`: sessions x combos x repeats, name, description, base preset) | None (prod has no multi-session group) | Eval-only doc; its units are references to RunDocs |
| Human gold labels, human "unit" | None (`ratings` are user ratings, not gold) | Eval-only; read-only dataset files, referenced by dataset id and sha |
| Datasets, uploads manifest | None | Eval-only |
| Compare aggregation, leaderboard, UI | None | Eval-only; reads RunDocs and ReportDocs |
| Owner identity | `uid` | Allowlisted eval user email mapped to a `uid` in the eval database; no synthetic uid needed because the whole database is eval |

### Duplication to remove today

Eval code that re-implements prod logic (all in `eval/backend/src/onolys_eval_backend/` unless noted):

1. Input snapshot and validation: `_inputs` / `_validate_sources` (`runs.py:191-246`) re-do transcript validation, speaker resolution, span check, language and goal resolution that prod does in `routes/transcript.py` and the run start txns. Replace with creating prod sessions/transcripts and starting prod runs.
2. Transcript hashing: `_hash` (`runs.py:137`) duplicates `transcript_sha256()`.
3. Unit execution: `execute_unit` (`runs.py:622-790`) re-implements claim/lease/retry/progress and calls `run_validated` itself, instead of the api run handler (`jobs/run.py`) and `claim_run`.
4. Per-unit store: `eval_runs/{id}/units` (`repository.py`) is a second run-document format instead of `RunDoc`.
5. Output store: `runs/<run>/<unit>.json` and per-run copies of `inputs/<session>/transcript.json` (`runs.py:340-348`, `storage.py`) instead of the shared `{uid}/{sid}/...` layout and `ReportDoc`.
6. Queue and handler wiring: own Cloud Tasks queue and `queue.py` dispatch, instead of the shared run task handler.
7. Rerun/retry rules: `saved_config` and snapshot-equality checks (`runs.py:268-326`) grew this branch to mimic what a pinned RunDoc gives for free.

Each time the prod run input changes (as on this branch: four new pinned fields), items 1 to 3 would need the same edit in eval. That is the headache the owner described.

### What genuinely stays eval-only

- Eval run grouping doc (`eval_runs`): name, description, sessions x combos x repeats, base preset, status roll-up, pointing at RunDoc ids.
- Human gold labels and the human "engine" (gold is a read-only reference, not a run).
- Datasets, upload manifests, gold validation.
- Compare aggregation, leaderboard, heatmap, line view, and the compare UI.
- Per-run model/tier/effort override and non-prod engine selection, as fields on the run, honoured only when the deployment is eval (config flag on the shared code, for example `EVAL_MODE=true`; prod rejects the fields).
- Price book and cost estimate; allowlist auth.

### Infra: same environment module

Today eval is hand-written in `infra/eval-services.tf` and `infra/eval.tf`: its own service account, Cloud Tasks queue, Cloud Run service, bucket and IAM, bound to the `staging` database (`eval-services.tf:92-100`). Proposal: instantiate the same `infra/modules/environment` (as `module "staging"` and `module "prod"` do in `infra/main.tf:95,129`) a third time as `module "eval"` with `env = "eval"`, `database_id = "eval"`, so it gets its own database, bucket (`onolys-audio-eval`), queue, service accounts and run handler from the same definitions. Eval-specific config goes in as variables (allowlist secret, `EVAL_MODE`, higher queue concurrency, no caps). `eval-services.tf` shrinks to what the module cannot express (the compare UI hosting site, if any). Datasets live in a separate read-only bucket (the current `onolys-eval-data-staging` role), not under session prefixes, so deleting a session never touches gold or datasets.

### Alternative: same database, synthetic owner

The earlier proposal: eval sessions and runs in the existing database under a synthetic eval uid, `eval = true` on runs, `counted = false`, eval filtered from lists, alerts and billing. Cheaper on infra, but it mixes research data with real client data, shares the prod queue (a 499-unit run can starve users; prod concurrency is `worker_concurrency x worker_max_instances`, `modules/environment/main.tf:63`), and adds an `eval` filter to every aggregate. The separate database avoids all of these and still shares all code, so it is preferred. Staging-only eval remains a fallback if a third environment is too heavy.

### Risks

- Run handler concurrency: many runs on one shared session may conflict on session `state` / `latest_report_version`; unverified. Fallback: one session per unit sharing transcript content by reference.
- Engine choice and route override widen the run API; they must be rejected outside eval mode, tested in both modes.
- The prod report schema validation must accept every engine eval compares, or those engines stay out of the worker.
- Eval deletes: removing one eval run must not delete a shared dataset session used by other combos.
- Dataset licensing: datasets must not land in a database or bucket with real client data (another reason for a separate database).
- Migration: existing `eval_runs` data in the `staging` database would need a one-off import or stay read-only legacy; no compat layer proposed.

### Open questions

1. Engines other than the prod engine (oneshot, miti_lean configs): add an engine selector to the shared run handler (eval mode only), or keep a thin eval wrapper that still writes prod-shaped RunDocs?
2. One session with many runs, or one session per unit?
3. Eval database name and bucket naming; is a third Terraform environment acceptable on cost and ops?
4. Do existing `staging` eval runs need migrating, or may they be dropped (owner has said no legacy handling for the lock work)?
5. Human gold: does gold need a prod-shaped home (for example a `GoldDoc`) or stay as bucket files with a sha reference?
6. Route override: a field on `RunDoc`, or a named eval-only preset resolved by the same preset code (smaller surface)?
7. Retention: eval data deleted with its eval run, or kept until manual removal as today?

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
