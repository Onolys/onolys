---
status: done
summary: Pure session-balanced compare calculations in eval/core, loaders and cache and read endpoints in eval/backend, removal of build_compare, offline fixtures and tests.
date: 2026-11-25
---
# Tasks: SP06 Compare calculations
Source of truth: docs/agent_files/session-report-ux-20261124-1738/06-compare-calculations/PRD.md. Pure calculations land first in `eval/core`, then loaders, cache and endpoints in `eval/backend`, then the old `build_compare` is removed. All tests are offline on synthetic fixtures. CI already runs `eval-core` and `eval-backend` jobs (path-gated in `.github/workflows/ci.yml`); Task 9 confirms they cover the new files.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Synthetic fixtures and fake source | - | done |
| 2 | Projections: report parsing, gold, transcript | 1 | done |
| 3 | Session-balanced counts, globals, cohorts, cells | 2 | done |
| 4 | Line alignment, P/R/F1, confusion | 2 | done |
| 5 | Cost, time, partial/excluded, coverage | 3 | done |
| 6 | More-analysis calculations and verdict | 3, 4, 5 | done |
| 7 | Loader, cache, price helper | 2, 5 | done |
| 8 | Compare routes and payload shaping | 6, 7 | done |
| 9 | Remove build_compare, CI check, timing test | 8 | done |

## Task 1 — Synthetic fixtures and fake source
What it is: shared offline test data. Traces to Acceptance Criteria (all offline) and Decision 1.
What changes at a high level: add `eval/fixtures/compare/` with synthetic RunDocs, ReportDocs (miti and oneshot), gold (full labels, AnnoMI-style partial, no-label HLQC/PHAC-style), transcripts, and a grouping doc. Include a fake `EvalRunSource` and fake price book. Cover repeats, a failed cell, a cancelled cell, and a provider-skipped combo (5 failed then skipped).
Done when: fixtures load through the fake source in a smoke test, and no network or cloud access is needed.

## Task 2 — Projections: report parsing, gold, transcript
What it is: engine-keyed parsing and safe projections (R2, R3, R4; Decisions 3, 4).
What changes at a high level: new pure `eval_core.summary` modules. Parse by `RunDoc.eval.engine` (miti reuses `miti_lean_scores`, oneshot reuses `oneshot_scores`). Non-integer counts, null global score or schema mismatch mark the run `unparseable`. Project gold to the allowed fields only, with the per-dataset label-coverage table. Project the transcript to the coded span, with `is_clinician`.
Done when: tests prove engine routing, fail-closed `unparseable`, withheld rationale kept as empty, gold output has no `source` or `parse`, and transcript sha mismatch is signalled.

## Task 3 — Session-balanced counts, globals, cohorts, cells
What it is: the one counting rule (R5; Decisions 6, 9, resolved globals and R:Q items).
What changes at a high level: add `summary/session_metrics.py`: per-session repeat-mean miss then session average, signed bias, R:Q and %CR per repeat, cohort `{paired, of}` over the requested combos, Count error with `codes_labeled`, global buckets per interview, heatmap and leaderboard cell shape with tolerance edges and `best`. Reuse `compare` and `compute_summaries`. Globals `value=null`; R:Q and %CR `within_tolerance=null`.
Done when: tests cover golden 8/10/12 gives 1.33 and two sessions give 1.67 with n 2 and repeats 3; 11 paired of 12; real zeros kept; AnnoMI partial labels give n/a with reasons; divide-by-zero gives n/a; SR=3, CR=1, Q=2 gives 2.0 and 0.25; tolerance edges 0.6/0.61 and 0.4/0.41; every cell has n.

## Task 4 — Line alignment, P/R/F1, confusion
What it is: turn-level alignment and metrics (R7; Decision 5).
What changes at a high level: align clinician turns in the coded span with gold codes by `turn_id`, mask codes outside the labeled universe, set-valued per-turn codes ("none" for miti only), presence-based P/R/F1, macro F1, line accuracy, confusion with a `multi` bucket, per-repeat then session then cross-session averaging, `agree k of r`, AnnoMI `dataset_notes`. Oneshot gets no line metrics; no human line labels returns `missing: "human"`.
Done when: tests prove confusion total plus multi equals aligned lines per combo, oneshot lane text, HLQC/PHAC-style hidden output, masking with `codes_labeled`, and multi-code turns.

## Task 5 — Cost, time, partial/excluded, coverage
What it is: operational numbers and partial-run handling (R6, R10; Decision 10).
What changes at a high level: time as `ended - started` with `retried_runs`; cost from `usage.cost_usd` or price book, n/a with reason for unknown models, failed runs still cost; only the highest attempt per cell counts; only `done` runs are compared; build `coverage` and `excluded` with reasons `cancelled`, `provider_unavailable`, `failed:<code>`, `unparseable`, `not_started`; `skipped_providers`; skipped combos n/a, never 0. Status gating: 409 `not_finished` and `no_completed_runs` decisions as pure functions.
Done when: tests cover unknown-model cost n/a, retry footnote, partial run (4 of 12 sessions) with nothing imputed, the Gemini-skipped fixture, and status gating including a skipped/failed-only run.

## Task 6 — More-analysis calculations and verdict
What it is: frontier, baseline, reliability, head-to-head, grid, error-vs-length, verdict (R8, R9, R11).
What changes at a high level: pure functions for the cost vs Count error frontier (unpriced combos listed not plotted), baseline always n/a with reason, MITI-level agreement with inclusive pack thresholds, repeat agreement (n/a with 1 repeat), head-to-head with ties, interview x combo grid, length series, observed `{min,max,n}`, and fixed-template verdict clauses built only from payload values.
Done when: tests prove dominated combos excluded, inclusive threshold at 3.5, head-to-head M equals the shared cohort, and the verdict never names a winner on n/a or a skipped combo and states n.

## Task 7 — Loader, cache, price helper
What it is: backend I/O boundary and caching (R1, Decisions 7, 8).
What changes at a high level: new `compare_load.py` (EvalRunSource wrapper over SP05 `eval_view`, bounded reads, gold hash re-verified with `canonical_sha256`, `transcript_changed` check), `compare_cache.py` (in-process LRU keyed by eval run id plus a hash of sorted run id, status and ended; terminal states cache indefinitely, running 10 s TTL), and one helper in `costs.py` for the route-based price.
Done when: tests with the fake source prove hash mismatch handling, cache hit on the second call, TTL for running runs, invalidation when a run changes, and the price helper.

## Task 8 — Compare routes and payload shaping
What it is: the authenticated read endpoints (Architecture table; Endpoint prefix decision).
What changes at a high level: new `compare_routes.py` under `/v1/eval-runs/{id}/compare/` with overview, deep-dive, analysis, reasoning (50 per page, cursor), session lines and turn popup. All GET, `combos=` filter, eval allowlist auth, 404 and 409 mapping, `has_human=false` as 200, rationale text only in reasoning and popup.
Done when: route tests prove auth, partial and done return 200, 404 and the three 409 cases, subset cohorts, rationale only where allowed, paging, and gold/transcript projections without forbidden fields.

## Task 9 — Remove build_compare, CI check, timing test
What it is: cleanup and verification (Decision 2, performance acceptance).
What changes at a high level: remove `build_compare`, `_flat_error` and the `compare` key of run detail from `read_runs.py`; rewrite the compare tests in `test_read_runs.py`, with no per-repeat test kept. Add the 499-run synthetic fixture test: overview under 1.5 MB, no per-instance rationale, cache hit on the second call, and a printed cold-compute time with an advisory 5 s bound. Confirm the existing `eval-core` and `eval-backend` CI jobs and path filters pick up the new files.
Done when: `eval/core/tests/test_summary_*.py` and `eval/backend/tests` pass offline, no references to `build_compare` remain, and CI path filters are confirmed.

## Owner steps (not tasks)
- After deploy, measure cold load on a real eval run; materialise the projection only if it exceeds 5 s.
- Run the first live eval; agents run no live runs, deploys or terraform.

## Completion evidence — 2026-11-25

All 9 tasks done through `4bb66ea`, including Task 5 `0086e6f`; review fixes `4054a98`; recorded fix verification **32 + 42 passed**. Independent re-review PASS. See [code evidence](code-2026-11-25-0300.md) and [final review](review-2026-11-25-0300.md). Full-branch review and shipping remain pending.
