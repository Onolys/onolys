---
status: done
summary: R4 context exemption now requires absence from the actual current batch; report builder assertions distinguish explicit fixture provenance; 587 offline MITI tests pass.
date: 2026-11-24
---
# SP02 review fixes

Branch: `session-report-ux`; existing linked worktree. Scope: Task 6 guard and Task 8 offline compatibility findings. No provider, credential or live work. Scores, schemas, request content, golden responses, complete report and adapter baselines are unchanged. The orchestrator owns `TASKS.md`; this fix does not edit or commit it.

## Changes

- `_locate_volley` continues to anchor only in the owning volley. After owning-turn overlap detection, only quotes found in rendered context become candidates for exemption. A candidate present in any other current batch-owned clinician turn remains `quote_not_found` and contributes to retries. `_attempt` supplies its actual batch, including the actual half after bad-output fallback. Other owned turns are scanned only for context candidates; owning-turn rescan is skipped when no prior location cursor exists.
- Regression cases compare the same text in one batch versus across two batches, require a same-batch confusion to retry then fail above the drop threshold, and distinguish inside/outside the actual fallback half. Assertions keep every surviving anchor in its owning turn. The earlier clinician-context-only case now places the context source across the batch edge.
- `test_build_report.py` retains exact shared report payload equality while explicitly asserting every intentionally different builder/adapter header provenance field (`models`, `preset`, `code_version`, `params`). Both report headers retain `coded_span: null`; no span mask was added. Evaluation run-info keys now include the validated nullable `span` on both sides, the full builder MITI provenance must equal its supplied result, and the adapter whole-session span is asserted explicitly. Existing complete report and adapter byte parity assertions are unchanged.

## Red / green evidence

Before fixes:

```bash
.venv/bin/python -m pytest engines/miti/tests/test_build_report.py -q
```

**2 failed, 19 passed in 0.30s**: stale exact header provenance equality and the stale expectation that the golden omitted `evaluation.span`.

New guard regressions, before implementation:

```bash
.venv/bin/python -m pytest engines/miti/tests/test_code_pass.py -q -k 'context_quote_requires_absence or same_batch_context or actual_half_batch'
```

**3 failed, 1 passed, 42 deselected in 0.25s**: same-batch text was incorrectly exempt, failed to trigger the required retry, and remained exempt inside a fallback half.

After implementation:

```bash
.venv/bin/python -m pytest engines/miti/tests/test_code_pass.py engines/miti/tests/test_build_report.py engines/miti/tests/test_golden.py -q
```

**73 passed in 1.54s**, including full adapter bytes and complete report parity.

After the final redundant-scan optimization, the explicitly requested full MITI-only offline verification:

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python -m pytest engines/miti/tests -m 'not live' -q
.venv/bin/ruff check engines/miti
LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python engines/miti/tools/regen_goldens.py
```

**587 passed, 3 deselected in 7.22s**; **All checks passed!**; **No changes.** The three live tests are excluded by the project marker. No other project suite ran.

## Audit provenance after review

Regenerated `measurements/step5.json` with:

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python engines/miti/audit_report.py --output docs/agent_files/session-report-ux-20261124-1738/02-miti-manual-alignment/measurements/step5.json
```

The only output change is `source_sha256.code_pass.py`:

- Before review: `61e9627767d7335fb8d732d6fd09b42d0740d952a46c6a896ac1b2981806e515`.
- After review: `a4738f940c206401a41cd5815d6b987be224b562026f710bb5381bae89ed0a8c`.

`step4.json` remains historical and unchanged. The initial step5 fingerprint is preserved above and in git history; all step5 fixture measurements, requests and residuals are byte-for-byte unchanged. The review fix corrects classification of model-generated misattributions; the offline audit uses valid hand-authored instances and therefore changes source provenance only. The final summary should cite this post-review verification count and source-only refresh without rewriting the historical step4/step5 comparison.
