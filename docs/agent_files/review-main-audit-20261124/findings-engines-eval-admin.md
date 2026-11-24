# Stage 1B — engines / eval / admin findings (raw, pre-verification)

Reviewer: sub-agent, commit 6ffbf63. Tests: core 315, miti 491, oneshot 66, eval/core 195 (+1 fail: test_cli console entry `onolys-eval` not on PATH in venv — env), eval/backend 193, admin/auth 25, admin/backend 47. Venv: /tmp/iaudit-review-venv (editable, points at this worktree).
No fabrication path found: all quotes re-sliced from transcript; oneshot schema forbids quotes.

## Data flow
transcript (JSON/.txt/STT) → run_validated(MitiEngine) → select_coded_span → prepare (roles by speaker id, input checks, volleys) → per run: code_pass (25 volleys/call, per-turn quote location, 20% drop gate) ∥ globals_pass → score_run → aggregate (representative run) → generate_tips → build_report_no_rating → api stores verbatim. Eval: create_run matrix (≤499 units) → Cloud Tasks unit claim → drift guard → ≤3 attempts in 840 s → finish_unit txn. Admin: Firebase ID token RS256 aud/iss/exp + email_verified + allowlist; eval /internal/tasks/* Google OIDC.

## High
- B1 (build.py:74-75) per-run warnings (quote_not_found, overlap, insufficient_evidence, capped) never reach report; only top-level result.warnings used. All globals unsupported → default 3, shows "fair", report.warnings == []. Dropped utterances under 20% gate silent. Probe confirmed.

## Medium
- B2 tone lint bypassed: build.py ships OnolysGlobal(reason=gl.reason) raw; instance rationale never linted, rendered by web codedRows.ts:49-67. Probe confirmed.
- B3 run deadline not propagated: LLMRequest in code_pass ~172, globals_pass ~150, tips ~165 omit deadline (only oneshot sets). Retries compound (transport 1+3 × _checked ×2 × halving) → ~24 calls/batch; 8-min outer timeout cancels billed calls. Static.
- B4 (extends Codex M5) admin verifier refetches certs on any unknown kid, lock held across blocking requests.get, failures not negative-cached (verifier.py:57-60,74-77). Probe: 5 bad-kid → 6 fetches.
- B5 (extends M5) eval OIDC verifier (eval/backend auth.py:19-31) uncached blocking cert fetch per dispatch.
- B6 .txt parser (transcript_txt.py:7, `^([^:\r\n]{1,40}):`) turns wrapped lines with colon into phantom speakers ("10:32 T:" → speaker "10"); pick_speaker labels all non-chosen as client → counts change, invented speaker labels. Probe confirmed.
- B7 blocking I/O in async eval handlers: uploads.upload() sync GCS write of ≤300 MB held twice in memory; execute_unit sync Firestore on loop; infra 2 GiB, concurrency 4, memory-backed /tmp.

## Low
- B8 oneshot: jsonschema accepts 1.0 as integer, strict pydantic _OneshotOutput rejects → non-retryable engine_failed after spend. Probe confirmed.
- B9 locate exact tier lacks word boundary ("you" in "young"); fuzzy accepts one-word swaps (score 94). Highlight wrong, not fabricated.
- B10 multi-run: mean counts mixed with representative-run instances (gi mean 0.667 vs instances_total 1); eval ratio-of-means vs report mean-of-ratios.
- B11 stale copy in data/report.yaml ("scores the same items you rated…", "Onolys disagrees"); layout includes always-skipped reasons_audit.
- B12 config drift: prod routes.yaml lacks oneshot route; routes.py:158 wrong models path for packaged routes; LLM_PROVIDER/LLM_MODEL without MODELS_FILE → ConfigError; pack.yaml no params: block but code reads it; compare: unconsumed; source.url PLACEHOLDER; prices.yaml prices only one model.
- B13 cancelled eval run with no completed units reports `failed`.
- B14 run_detail returns all units' inline output (≤499×500 KB) → may exceed 32 MiB response limit.
- B15 change_goal not validated at eval run creation (default "") → every unit engine_failed InputError.
- B16 repeats weight sessions unequally vs "each session equal weight" docstring in metrics.py.
- B17 cost gaps: run_validated loses first attempt usage if second raises; api real.py discards rctx.metrics on failure; one unpriced response → cost None; billed timeouts unrecorded.

## Improvements
- B18 MITI trumping rules only in prompt, not encoded; total_mia PwP inclusion unverified.
- B19 label_for compares unrounded (3.96 shows "4.0" labelled fair); duplicated span logic miti/prepare vs core/spans; _clamp_ends fabricates word end times; language defaults en on detect failure; untimed transcripts skip duration checks; third-party logs truncated not sanitized; json_schema mode inconsistency; inspect.getsource for prompt hashes; dataset id typo `suspiscious-smoker`; inferred_clinician_speaker ignores per-turn role consistency; duplicate STT jobs under at-least-once.

## Checked, no defect
Span/offset arithmetic (4000-case unicode property probe clean, code points); MITI math & zero-division; formula evaluator whitelist; admin auth pinning/allowlist/CORS; eval terminal accounting transactional; lone surrogates rejected.
