---
status: done
summary: 8 tasks - offline audit tooling + golden regen + baseline, volley break, new fixtures, one persuasion slot, globals reset removal, bounded context + guard, coverage metric, audit/summary docs.
date: 2026-11-24
---
# Tasks: SP02 MITI coding manual alignment
Source of truth: docs/agent_files/session-report-ux-20261124-1738/02-miti-manual-alignment/PRD.md. All PRD Open Questions are RESOLVED or DEFERRED (none OPEN); DEFERRED items are out of scope. SP01 commits land first; SP02 owns `engines/miti/**` only and the engine call signature stays unchanged. No CI change needed (`.github/workflows/ci.yml` runs on push to main and on pull requests, with a `miti` job). No live LLM, no API key anywhere: every test and script is offline. Every commit is green; each rule step also commits its `measurements/stepN.json`.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Offline audit script, golden regen script, baseline | - | done |
| 2 | R1 volley breaks (step 1) | 1 | done |
| 3 | New fixtures: batch_edge, sparse_evidence, 6,000-word generator test | 2 | done |
| 4 | R2 one persuasion slot (step 2) | 2 | done |
| 5 | R3 globals: remove reset (step 3) | 4 | done |
| 6 | R4 bounded context + `context_quote` guard (step 4) | 5 | done |
| 7 | R5 coverage metric, info only (step 5) | 6 | done |
| 8 | Audit and summary documents | 3, 7 | done |

Completion: Tasks 1–8 are committed through `b0d22a8`; review fixes are committed as `739dfc7`. Task 7: `6af8a73` (102 focused tests). Task 8: `b0d22a8` (manual audit, measurements summary and engine README). Final verification: 587 passed, 3 live tests excluded; Ruff passed; golden regeneration reported No changes. See [implementation result](code-2026-11-24-2203.md) and [review — PASS](review-2026-11-24-2203.md).

## Task 1 — Offline audit script, golden regen script, baseline
What it is / what it means: The measuring stick and the safety net come before any rule change. Traces to R6, R8, D9, D10, acceptance criteria 6, 7, 9.
What changes at a high level: Add `audit_report.py` in `engines/miti` (no network, no client): runs `prepare` volleys and `score.apply_rules` over all fixtures and writes volley count, batch count (25 volleys per call), rendered-request words, persuasion double counts on hand-authored instances, and coverage residual where defined. Add `engines/miti/tools/regen_goldens.py`: rebuilds requests per fixture, computes `FixtureClient.key_for`, rewrites golden files reusing previous responses, and updates the hash set in `test_golden.py`. Run the audit at current HEAD and commit `measurements/baseline.json`. No `check.py` change, no latency/token/cost numbers.
Done when: a new test runs the audit script on the fixtures offline and checks the output shape; a test shows the regen script on unchanged code is a no-op and `test_golden.py` still passes; `baseline.json` is committed and no code path needs a network or key.

## Task 2 — R1 volley breaks (step 1)
What it is / what it means: Short facilitative client turns ("yeah", "mm-hm") stop splitting volleys unless they answer a clinician question. Traces to R1, D1, D2, D8, acceptance criterion 1.
What changes at a high level: `build_volleys` skips a client turn below the size threshold (pack `min_other_words: 3`, `min_other_chars: 6`) and keeps it available as non-codable text; size uses words for spaced scripts and characters for Thai/Chinese/Japanese. The question exception breaks the volley when the prior clinician turn's last sentence ends in `?`, `？` or `؟` (or the terminator is followed by a fragment of at most 3 words/6 characters). Audit existing `expected.yaml` and change a count only where the manual requires it, with the page noted. Regenerate goldens (volley ids change) and commit `step1.json`.
Done when: `test_prepare.py` replaces the pinned `prev_other` and "mm-hm breaks" tests with the PRD AC1 cases (one volley, `?`/`？`/`؟` breaks, short-fragment break, earlier-question no break, 3-word "I can do that" breaks, spaceless-script lengths, facilitative turn kept as context); existing fixture `volleys:` structures match `build_volleys`; `test_golden.py` and `test_data.py` pass via the regen script.

## Task 3 — New fixtures: batch_edge, sparse_evidence, 6,000-word generator test
What it is / what it means: Fixtures that exercise the batch edge and thin-evidence cases the rules must handle. Traces to R7, acceptance criterion 6.
What changes at a high level: Add `batch_edge` (~1,500 words, 26+ volleys, permission-then-persuade pattern across the 25-volley batch edge, facilitative "yeah"s plus one question-answer "yeah") and `sparse_evidence` (short, little change talk, no sustain talk, expected SST 4-5 per p.38). Hand-set `expected.yaml` with a `volleys:` structure (count and turn-id grouping) plus code counts for hand-authored instances, each with its rule/page. Add an in-test generator for a ~6,000-word transcript (not committed as a fixture).
Done when: `test_prepare.py` checks both new `volleys:` structures; `score.apply_rules` tests check the hand-authored counts; generator test asserts at least 2 batches and disjoint batches; `test_data.py` and `test_golden.py` pass; audit script includes the new fixtures.

## Task 4 — R2 one persuasion slot (step 2)
What it is / what it means: A volley can no longer count both Persuade and Persuade with Permission. Traces to R2, D3, acceptance criterion 2.
What changes at a high level: Add an `exclusive_group` rule in `pack.yaml` (unit volley, codes `persuade_permission`, `persuade`, precedence permission first) using the existing `superseded_by_persuade_permission` down-count. Add the same-utterance rule to the `code_system` prompt and pack text, citing p.20. Regenerate goldens; commit `step2.json` showing persuasion double counts at 0.
Done when: `test_score.py` shows a volley with both codes counts only permission, the loser is `superseded_by_persuade_permission`, Total MINA excludes it, and no counted volley exceeds 8 codes; `test_miti_pack.py` asserts the rule; `test_golden.py` passes.

## Task 5 — R3 globals: remove reset (step 3)
What it is / what it means: The model's global score stands; thin evidence no longer forces a 3. Traces to R3, D4, D5, acceptance criterion 3.
What changes at a high level: Delete the reset branch in `_rate` (`globals_pass.py`); cap-on-poor-practice unchanged. Keep `insufficient_evidence` as an info diagnostic with no "reset" wording. Stop emitting `source: "default"`. Add the one prompt line to `globals_system.md`: low scores need evidence of the clinician behavior, not of its absence. No schema or web change. Regenerate goldens; commit `step3.json`.
Done when: `test_globals_pass.py` shows a rating with one located quote keeps its model score, the info warning remains, no `source: "default"` appears, SST 5 with empty evidence is kept, and the new prompt line is present; `test_golden.py` passes.

## Task 6 — R4 bounded context + `context_quote` guard (step 4)
What it is / what it means: The coder sees bounded client context and the previous clinician volley, and cannot code from it. Traces to R4, D6, D11, acceptance criterion 4, plus the StubClient part of R8.
What changes at a high level: Replace `previous_other_turn` with text-only `context_before` in the user message: up to 4 prior client turns within 150 words (300 characters for spaceless scripts, oldest whole turns dropped), plus the previous clinician volley bounded to its last 100 words, also across a batch boundary. Update `code_fewshot.json`. When a quote is missing from the batch turns but present in that volley's context, warn `context_quote` instead of `quote_not_found`, excluded from `MAX_DROP_RATE`. Add the `StubClient` test helper. Regenerate goldens; commit `step4.json`.
Done when: `test_code_pass.py` (StubClient) shows the context bounds, no turn ids, previous-batch clinician text, few-shot uses `context_before`, a context-only quote is dropped as `context_quote` without moving the drop rate, `cache_prefixes` equal across batches, and batches disjoint; `test_golden.py` passes.

## Task 7 — R5 coverage metric, info only (step 5)
What it is / what it means: Silent drops become visible; nothing is retried or failed. Traces to R5, D7, acceptance criterion 5.
What changes at a high level: After location, compute uncovered clinician words per volley and per run. Emit info warning `coverage_gap` when a volley with at least 40 clinician words returns no utterance. It never raises `CodePassFailed` and never retries. Feed the residual into the audit script. Regenerate goldens only if a request changes; commit `step5.json`.
Done when: tests show the residual on a hand transcript, `coverage_gap` firing at 40 words with no utterance, and (StubClient, call count asserted) no `CodePassFailed` and no retry; audit output carries the residual column.

## Task 8 — Audit and summary documents
What it is / what it means: The deterministic evidence is written down with its limits. Traces to R6, D8, D9, acceptance criteria 7, 8, 9.
What changes at a high level: Write `measurements/summary.md` (per-step table; reading rule: volley counts move only where R1 says, counts not farther from hand-set expected, double counts 0 after step 2; limits stated: synthetic hand-set fixtures, no accuracy claim, no live measurement). Write `audit.md` mapping each rule (volley, 8-code slots, persuasion, globals, not-coded list, formulas) to manual page (corrected pages per D8) and file:line, marked match or fixed here. Update `engines/miti/README.md` for the new rules, the audit script and the regen script.
Done when: summary and audit files exist and reflect the committed `baseline`/`step1..step5` JSON; a final check that the impacted `engines/miti/tests` pass and that no test or script needs a network or API key.

## Owner steps
- None required; no credential or live run needed.
- Optional, deferred: a certified-coder human-coded set (3-5 sessions) is the only real accuracy evidence; not needed to merge.
