---
status: draft
summary: Pure, offline-tested server-side calculations (session-balanced counts/globals error, cohorts, line alignment, P/R/F1, confusion, cost, time, frontier, head-to-head, reliability, verdict) plus authenticated read endpoints that feed the four compare screens from saved RunDocs, ReportDocs, gold and transcripts. Works on `done` and `partial` (cancelled, or with failed/provider-skipped cells) eval runs using only completed runs, reporting the missing ones, including cells skipped because a provider was unavailable.
date: 2026-11-25
---
# PRD: SP06 Compare calculations

Repo/branch: Onolys/iaudit / `session-report-ux` · Depends on: SP05 (grouping doc, eval backend on prod pipeline), SP04 (`RunDoc.eval`, run timing/usage) · Owns: new `eval/core/src/onolys_eval/summary/` (pure) + `eval/core/tests/test_summary_*.py`; new `eval/backend/src/onolys_eval_backend/{compare_load,compare_cache,compare_routes}.py`; edits to `read_runs.py` (remove `build_compare`, `_flat_error`, `compare` key of run detail), `costs.py` (one helper), `eval/backend/tests/test_read_runs.py` (compare tests rewritten), `eval/fixtures/compare/` · Consumed by SP07 (screens). Reads, never writes, prod docs.

## TL;DR
Today's `build_compare` counts every successful repeat as its own comparison and has no line-level, cohort, time, frontier or verdict logic. SP06 replaces it with one pure calculation package plus read endpoints. Every number is computed on the server from saved data (RunDoc, ReportDoc, gold, TranscriptDoc), is exact or "n/a + reason", and carries its n. The UI (SP07) only renders.

## Problem
| Gap | Evidence |
|---|---|
| Repeats inflate n: `errors.extend(session_errors)` adds one comparison per successful repeat, then `aggregate()` weighs each equally | [verified: `read_runs.py:114-117,149`; `metrics.py:147`; test pins it `test_read_runs.py:77`] |
| No common cohort across combos, no session-level n, no time, no line metrics | [verified: `read_runs.py:149-260`] |
| Report instances are not read at all; saved outputs only via `/units/{id}/output` | [verified: `read_runs.py` `unit_output`] |
| Unit store is eval's own (`units`, `scores`) and SP05 removes it; compare must read RunDocs/ReportDocs | proposal "Duplication to remove" |

## Goals / Non-Goals
**Goals:** exact, session-balanced, cohort-aware calculations for all four screens (Overview, Deep dive, More analysis, Line view); safe gold and transcript projections; bounded payloads for up to 499 runs; fully offline tests.
**Non-goals:** UI, copy and "How to read" text (SP07); run creation, scheduling, grouping doc, delete (SP05); cross-run comparison; significance tests; composite quality score; prompt versioning; clinical correctness.

## Requirements

**R1 Inputs (SP05 interface: grouping doc R4, `eval_view.list_cells` R11).** `EvalRunSource` protocol (fakeable), a thin wrapper over SP05's `eval_view`: `eval_run(id)` -> grouping doc `{eval_run_id, name, dataset_id, status, cancelled_at, sessions[{session_id, uid, dataset_session_id, gold_sha256}], combos[], repeats, provider_skips[{provider, after_failures, skipped_at}], runs[{session_id, run_id, combo_key, repeat, attempt, status, reason}]}` (status includes `skipped`, reason `provider_unavailable`; SP05 R4/R6d); per (session, combo, repeat) only the highest `attempt` counts, earlier failed attempts feed the time footnote only [SP05 R11]; `run_doc(uid,sid,run_id)`; `report(uid,sid,run_id)` (ReportDoc, pointer resolved); `transcript(uid,sid)`; `gold(sha256)` from eval bucket `gold/<sha256>`, hash re-verified with SP05's `eval_sessions.canonical_sha256` (SP05 R3; replaces the removed `runs.py:137 _hash`, same canonical JSON [verified: `runs.py:137-140`]). Provenance per run from `RunDoc.eval` (`combo_key`, `repeat`, `engine`, `resolved_route`) [SP04 R1]. Compare never reads outside one `eval_run_id`. Every eval run is `n_runs=1` (repeats are separate RunDocs, owner decision), so each report holds integer counts [verified: `models.py:189,334` default 1].

**R2 Report parsing (engine-keyed by `RunDoc.eval.engine`, never sniffed).**
| Engine | Counts/globals | Lines | Reasons |
|---|---|---|---|
| `miti` | reuse `miti_lean_scores` (`behaviours[].onolys_count.mean`, `globals[].onolys.score`) [verified: `adapters.py:13`] | `behaviours[].instances` of each `item_id`: `{turn_id, quote, rationale}`; `Instance.id` is an instance id, the code is the owning `item_id` [verified: `report.py:76,181-190`, `build.py:122-128`] | global `onolys.reason` + `evidence[]`; instance `rationale` (may be `""` when withheld for tone: show "withheld", never fill) [verified: `build.py:119-121`] |
| `oneshot:*` | reuse `oneshot_scores` (`counts`, `globals`) [verified: `adapters.py:56`] | none (schema has counts, globals, tips only) | none |
Fail closed (guard only; `n_runs=1` makes it unreachable today): a non-integer count (an `n_runs>1` mean), `onolys.score` null, or schema mismatch marks that run `unparseable` (excluded like failed, reason shown); never rounded. Tips are ignored. Only the saved ReportDoc is read (code.json not needed: report instances already hold the representative run's counted instances).

**R3 Gold projection.** From `Gold`, return only `{coded_span, counts (partial), globals (partial), quality_label, utterance_codes[{turn_id, codes, note}]}` [verified: `gold.py:Gold`]. Never `source` URLs, `parse` warnings or storage paths. A count/global missing or null = "not labeled". Label coverage per dataset (from manifests) drives n/a:
| Dataset | Counts labeled | Globals | Line labels |
|---|---|---|---|
| casaa-miti421-video2013, casaa-miti-practice | 10 | 4 | yes [verified: `convert.py:289,314`] |
| mi-tags-sample | 7 | 4 | yes |
| automisc-human | 9 (no seek_collab) | none | yes |
| welivita-mi | 9 (no seek_collab) | none | yes (forum threads, not sessions) |
| annomi | question, sr, cr, gi | none | yes |
| annosum-mi | question | empathy | yes |
| midas-es | question | none | yes |
| hlqc | none (quality only) | none | no |
| phac-en, phac-fr | none | none | no |
The proposal lists utterance codes for five datasets; CASAA and Welivita also write them [verified: `convert.py:314`, `welivita.py:114-120`].

**R4 Transcript projection (Line view).** From the saved `TranscriptDoc` only; `sha256` must equal `RunDoc.transcript_sha256`, else 409 `transcript_changed`. Return `turns[{id, speaker, is_clinician, text, start_ms, end_ms}]` inside the run's pinned `coded_span`; `is_clinician = speaker == RunDoc.clinician_speaker`. No storage pointers, no audio refs, no invented fields.

**R5 Per-session metrics (the one counting rule).**
- Session miss (count or global, per combo): mean over that combo's successful repeats of `|repeat value - human|`; then average across sessions. Repeat values are never averaged first. Signed bias uses the same order (linear, so equals mean signed diff).
- R:Q and %CR: computed per repeat from that repeat's exact counts (`compute_summaries`, shared pack formulas), then missed against human's. Any undefined repeat (division by zero) makes that session n/a for that combo and metric ("no Questions in this session"); counted in `excluded`.
- Cohort per metric: sessions where human labels the metric and every selected combo has at least one successful, parseable run. Shown as `{paired, of}` ("11 paired of 12"). Real zeros count; failed/unparseable excluded and listed.
- Count error = sum over the labeled codes of the per-code session miss, averaged over cohort sessions, all codes weighted equally; response states `codes_labeled` of 10 (AnnoMI: 4 of 10).
- Globals: per interview, repeat-wise bucket `same / off1 / off2plus`; interview shares averaged across interviews; `within_1 = same + off1`. Global ratings are never averaged across interviews; only per-interview compare, then aggregate.
- Heatmap cell: `value` (counts: mean of session repeat-means; see OPEN on globals), `off` (avg miss), `bias`, `n` (sessions), `repeats`, `within_tolerance` (off <= 0.6 lines for counts, <= 0.4 points for globals), `best_in_row` (lowest `off`, ties all marked). Human is a separate first column of raw values. Rare codes rank like any other.
- Reuse `eval_core.metrics.compare` for per-repeat differences and summary recompute and `gold_scores`; replace `aggregate` (per-comparison weighting) with session-balanced functions in `summary/session_metrics.py`.

**R6 Operational.** `time = RunDoc.ended - RunDoc.started`, mean per combo over runs with both set; retried runs are kept and `time.retried_runs` count feeds the footnote ("`started` resets on re-claim") [verified: `firestore.py:785`, `worker.py:238`]. `failures` = runs with `status=failed` or unparseable, with `error` codes; cells `skipped` by the provider breaker are NOT failures and not runs: they are reported only in `excluded`/`coverage` (R10). Overload waits and internal-error retries (SP05 R6b/R6) show as extra attempts on the time footnote like other retries. Cost per run: `run_info.usage.cost_usd` if set, else price book on `RunDoc.eval.resolved_route.litellm_id` with `run_info.usage` tokens; `combo_routes` points every route at one litellm id, so one price is sound [verified: `routes.py:288-310`, `costs.py:estimate`]. Unknown price -> cost n/a ("no price for <model>"), never 0; failed runs still count their cost.

**R7 Line alignment (by `turn_id`).** Aligned lines = clinician turns inside the run's `coded_span` that have a gold `utterance_codes` row. Code universe L = codes the dataset labels (R3); codes outside L are masked on both sides. A combo's codes on a turn = set of `item_id`s with a counted instance at that `turn_id`; none -> "none", only for engines with line output (`miti`); `oneshot` gets no line metrics and its lane says "no line-level output". No human line labels -> all line outputs omitted with `missing: "human"`. Metrics, per code per combo: P, R, F1 as presence-per-turn (handles multi-code turns), macro F1 over L (rare codes equal weight), line accuracy = exact set equality share. Confusion: human code (rows) x combo code (cols, plus none) for turns with exactly one label each side; turns with several labels on either side go to a separate `multi` bucket, so matrix total + multi = aligned lines. Repeats: each repeat aligned separately, then averaged within session, then across sessions (same rule as R5); the popup also returns `agree: k of r repeats`. AnnoMI per-utterance grouping caveat flagged in payload (`dataset_notes`) [verified: manifest note, proposal].

**R8 More analysis.**
- Frontier: x = mean cost per run, y = Count error; combo is on the frontier if no other has <= cost and <= error with one strict. Combos with cost n/a are listed, not plotted.
- Human-vs-human baseline: always `n/a - needs a second human coder, not in this dataset`. Verified: `gold.v1` has one coder per session (`metrics.py:132` note; AnnoMI is single annotator or majority vote; MI-TAGS "one annotator"; no second-coder field in `gold.py` or any manifest).
- Reliability per combo: share with same MITI level as human per summary with a reference (technical, relational, %CR, R:Q), level from the pack thresholds, inclusive boundaries, applied to human's recomputed value [verified: `formula.py:96-108`, `pack.yaml:285-305`]; repeat agreement = share of (session, global) and (session, line) where all successful repeats agree (needs >= 2 repeats, else n/a); failures; time. No blended score.
- Head-to-head: per session Count error; "X closer than Y on N of M sessions" plus ties, M = sessions in the cohort for both.
- Interview x combo grid: session Count error (repeat-averaged) with `repeats`.
- Error vs length: per (session, combo) Count error against `turns` and `words` of the coded span.

**R9 Verdict line.** Server builds structured clauses `{text, claims[{metric, combo, value, n}]}` only from values in the same payload; never names a winner on an n/a metric; names n ("1 session"). Templates are fixed; no free text.

**R10 Partial (cancelled) eval runs.** An eval run in `partial` state (SP05 R7/R6d: cancelled with at least one run completed, some runs failed, or some cells skipped because a provider was unavailable) is compared like a finished one using ONLY runs with status `done`; `cancelled`, `failed`, `skipped`, `unparseable` and never-started cells are excluded. n is shown as usual (sessions with `paired` of `of`, repeats counted from completed runs). The missing runs are reported, never imputed or counted as 0: header `coverage {eval_status, cancelled_at|null, runs_done, runs_total, runs_skipped, skipped_providers[{provider, after_failures}]}` and `excluded[{session_id, combo_key, repeat, reason}]` with reason `cancelled` (not started when Cancel was requested, SP05 R7), `provider_unavailable` (skipped by the provider breaker after N failures in a row, SP05 R6d; the structured `skipped_providers` entry lets SP07 write the notice), `failed:<code>`, `unparseable` or `not_started`. A combo whose provider was skipped has n/a cells (reason "skipped: provider unavailable"), never 0, and the verdict never names it a winner; other providers' combos compare as usual over the cohort (R5). The cohort rule (R5) already drops sessions where a selected combo has no completed run, so a partial run can show "4 paired of 12". An eval run with no completed non-human run (status `cancelled`/`failed`) returns 409 `no_completed_runs`; `queued|running|deleting` returns 409 `not_finished`. Compare reads only; it never writes a status.

**R11 No composite score; min/max = observed range (`{min,max,n}` of repeat values), no statistics claims.**

## Architecture
```
SP05 grouping doc + RunDocs + ReportDocs + gold/<sha> + TranscriptDoc
        |  compare_load.py  (EvalRunSource, parse per R2, verify hashes, bounded reads)
        v
Projection (per run: counts, globals+reason+evidence, turn->codes, instances sans rationale; per session: gold, turns)  -- cached
        v  eval_core.summary (pure: no I/O, no clock)
overview | deep_dive | analysis | session_lines | reasoning  -> compare_routes.py (allowlist auth)
```
Endpoints (prefix `/v1/eval-runs/{id}` [RESOLVED: owner — default], behind the eval allowlist auth), all `GET`, all take `combos=a,b,c` (default all; cohort is computed over the requested set):
| Path | Returns |
|---|---|
| `/compare/overview` | header (sessions, repeats, `label_coverage`, `coverage` per R10), `verdict`, `leaderboard[]`, `heatmap{rows[],human[],cells}`, `cohorts`, `footnotes` |
| `/compare/deep-dive` | globals (per-interview dots, bucket bars, miss, within-1), counts (totals, bias %), line metrics (P/R/F1 per code, confusion per combo), rationale counts per code (no text) |
| `/compare/analysis` | frontier, baseline, reliability, head-to-head, grid, error-vs-length |
| `/compare/reasoning?code=&combo=&cursor=` | verbatim rationale snippets, 50 per page, grouped by code only |
| `/compare/sessions/{sid}/lines` | turns, lanes (human + combos, codes per turn, no rationale), disagreement flags, per-session globals table |
| `/compare/sessions/{sid}/lines/{turn_id}` | popup: text, human code (+note), each combo's code, rationale, `agree k of r` |
Cell shape: `{value, off, bias, n, of, repeats, within_tolerance, best, na: {reason}|null}`. Sizing: units <= 499 means sessions x combos <= 499, so heatmap + grid stay under ~1 MB; rationale text and per-turn detail are the only large items and are paged/on demand. Errors: 404 unknown run, 409 `not_finished` (queued/running/deleting), 409 `no_completed_runs` (R10), 409 `transcript_changed`; `no_human_reference` returns 200 with `has_human=false`. `done` and `partial` eval runs both return 200.

Compute-on-read with an in-process LRU of projections keyed by `(eval_run_id, sha256 of sorted (run_id, status, ended))`; terminal eval runs (`done|partial|failed|cancelled`) cache indefinitely, running ones recompute (TTL 10 s). Materialising into Firestore is rejected for now (new schema, invalidation, per-instance caches).

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| 1 | Where pure code lives | `eval/core` `summary/`, loaders in backend | All in backend | Testable with no cloud; core already holds `compare`/formulas |
| 2 | Existing `build_compare` | Replace; keep `compare()`, `compute_summaries`, `gold_scores`, `miti_lean_scores`, `oneshot_scores`, `PriceBook` | Patch in place | Repeat-as-comparison is the core bug; old eval data is dropped (decision 5/11), no legacy shape to keep |
| 3 | Report source | ReportDoc only | Also code.json | Report instances already = counted instances of the (single) run |
| 4 | Engine detection | `RunDoc.eval.engine` | Sniff report keys | Explicit, fails closed |
| 5 | Line unit | Turn, set-valued, presence-based P/R/F1 | Single code per turn | Gold `codes` is a list |
| 6 | Cohort scope | Over requested combos | Always all | Deep dive subset stays an honest like-for-like comparison |
| 7 | Cache | Compute-on-read + LRU | Materialise on completion | No new schema; revisit if slow |
| 8 | Cost pricing | `resolved_route.litellm_id` + usage | Per-call metrics | Combo routes share one model; per-call metrics exist only on failures [verified: `run.py:105-117`] |
| 9 | Head-to-head measure | Per-session Count error | Per-code wins | One locked, unweighted measure; no composite |
| 10 | Partial eval runs | Compare completed runs only; report missing runs (`excluded`, `coverage`) incl. `provider_unavailable` skipped cells with a structured `skipped_providers` list | Refuse until all done; impute | Owner Cancel keeps completed work; owner round 2: a failing provider is skipped, others compare; no invented numbers |

## Risks / Open Questions
- [RESOLVED: owner 2026-11-25 — default: `value=null`, `off` is the headline, per-interview values in Deep dive] Heatmap `value` for globals.
- [RESOLVED: owner 2026-11-25 — default: `within_tolerance=null` (uncolored), `best` still marked] Tolerance and `best` for R:Q/%CR.
- [RESOLVED: owner 2026-11-25 — default: mask and print `codes_labeled` beside line metrics] Codes outside the labeled universe L.
- [RESOLVED: owner 2026-11-25 — default: `multi` bucket (R7); revisit if gold shows many] Multi-code turns in confusion.
- [RESOLVED: owner — default] Endpoint prefix: `/v1/eval-runs/{id}/compare/*` behind the eval allowlist auth.
- [RESOLVED: owner — default; owner 2026-11-25 round 2: no live runs by agents] Cold compute time for 499 reports: agents add an offline synthetic-fixture timing test (499 runs, advisory bound 5 s); the owner measures cold load on a real run after deploy and SP06 materialises the projection only if that is > 5 s.
- [RESOLVED: owner 2026-11-25 — default: exclude the session, report in `excluded`] A session with an undefined R:Q repeat.
- [RESOLVED: owner 2026-11-25 — partial eval runs compare completed runs only; missing runs reported as `cancelled`] See R10.
- [RESOLVED: owner 2026-11-25 (round 2) — cells skipped by the provider breaker (5 consecutive failures, SP05 R6d) are reported in `excluded` with reason `provider_unavailable` and in `coverage`; the eval run is `partial`] See R10.
- [RESOLVED: no] Any second human coder in `eval/datasets`? None found; baseline is n/a for all datasets today.
- [DEFERRED] Cross-run comparison; significance tests; statistical intervals.

## Acceptance Criteria
All tests offline: pure fixtures in `eval/fixtures/compare/`, fake `EvalRunSource`, fake price book, no network.
- Golden: human 10, repeats 8/10/12 -> session miss 1.33 (not 0); two sessions with misses 1.33 and 2 -> `off` 1.67, `n` 2 sessions, `repeats` 3.
- A session with 3 repeats counts once in n, cohort and head-to-head; old per-repeat test is replaced, not kept.
- 12 sessions, one combo failed in one session -> every combo shows "11 paired of 12" for that metric; a real zero count is included.
- Partial labels (AnnoMI fixture): the six unlabeled counts and all globals are `na` with reason "not labeled in this dataset", never 0; technical/relational n/a "needs cct, sst, partnership, empathy"; R:Q and %CR are values; Count error `codes_labeled=4`.
- Division by zero (human or a repeat with Question 0) -> n/a "no Questions in this session"; SR=3, CR=1, Q=2 -> R:Q 2.0, %CR 0.25.
- Confusion matrix total plus `multi` equals aligned lines, for every combo; oneshot combo has no line metrics and lane "no line-level output"; HLQC/PHAC -> line outputs hidden, `missing: "human"`.
- Every heatmap, leaderboard, grid cell has `n`; 1-session cell has `within_tolerance` computed and `best` can be set.
- Heatmap tolerance edges: off 0.6 lines and 0.4 points are green; 0.61 and 0.41 are not.
- Verdict text contains only values present in the payload, names n, and never names a winner on an n/a metric.
- Frontier: dominated combo excluded; unpriced combo listed not plotted; baseline always n/a.
- Reliability level uses inclusive pack thresholds (value 3.5 relational = fair/good boundary check per `formula.py`); repeat agreement n/a with 1 repeat.
- Partial eval run (cancel after 4 of 12 sessions complete, one combo missing in a session): only `done` runs counted, `n`/`paired of` reflect them, `excluded` lists the cancelled cells with reason `cancelled`, `coverage` has `runs_done`/`runs_total`/`runs_skipped`/`cancelled_at`, nothing imputed as 0; eval run with no completed run -> 409 `no_completed_runs`; `running` -> 409 `not_finished`.
- Time: `ended - started`, retried count reported; cost n/a for unknown model, never 0.
- Gold projection contains none of `source`, `parse`; transcript projection 409s on sha mismatch; rationale text appears only in `/reasoning` and popup, verbatim, `""` -> "withheld".
- Provider skipped (fixture: 12 sessions x 3 combos, the Gemini combo has 5 failed then the rest `skipped`): `excluded` lists those cells with reason `provider_unavailable`, `coverage.runs_skipped`/`skipped_providers` carry `{provider, after_failures: 5}`, the skipped combo's cells are n/a with a reason (never 0), the other combos compare over their own cohort, the verdict never names the skipped combo a winner, status `partial` returns 200; a run that is only skipped/failed with no `done` run returns 409 `no_completed_runs`.
- 499-run fixture: overview payload < 1.5 MB and no per-instance rationale; second call hits the cache. Synthetic timing test: cold compute of the 499-run fixture is asserted offline (advisory 5 s bound) and printed; the real cold-load measurement is the owner's after deploy.
- All tests offline: agents build and run offline tests only; no deploy, no terraform apply, no live LLM/STT eval run or staged-run measurement (the owner runs the first eval and measures cold load).
