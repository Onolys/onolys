---
status: done
summary: Baseline audit and deterministic synthetic golden maintenance commands; historical SP01 adapter evidence is unchanged.
date: 2026-11-24
---
# Offline audit and golden maintenance

Run from the `session-report-ux` worktree with its installed `.venv` packages. Neither tool constructs a model client or calls a provider. No credentials are needed.

```bash
.venv/bin/python engines/miti/audit_report.py --output docs/agent_files/session-report-ux-20261124-1738/02-miti-manual-alignment/measurements/step1.json
.venv/bin/python engines/miti/tools/regen_goldens.py
.venv/bin/python -m pytest engines/miti/tests/test_offline_tools.py engines/miti/tests/test_data.py engines/miti/tests/test_golden.py -q
```

Use `step2.json` through `step5.json` at the corresponding rule-change commits. `baseline.json` records the current pre-alignment rules. The audit renders requests for **every fixture listed in expected.yaml**. Regeneration maintains the **existing request-stub golden set**, currently only `good_practice`; it does not invent responses for other sessions.

The audit calls real `prepare` and `score.apply_rules`. It locates every hand-authored utterance exactly inside its clinician turn, derives current volley ids and applies current rules. Count drift is actual minus hand target; summaries use hand global scores, not newly evaluated global ratings. Request words include each initial code batch and the globals request: cache prefixes, system and user strings, with repeated prefixes counted once per batch. Templates, fewshots, language and change goal use production renderers. Schema text, tips and retries are excluded. These are whitespace-word proxies, never tokens, latency or cost. Coverage is union-of-located-span coverage, including uncoded or down-counted utterances. A whitespace word overlaps coverage if any character does; missing hand utterances give null coverage. Synthetic complete hand utterances currently leave zero residual, which says nothing about live-model coverage or accuracy.

Baseline: good_practice has 10 volleys / 1 code batch / 4,527 rendered words; poor_practice 12 / 1 / 4,191; short_session 5 / 1 / 3,681. All three currently match hand count targets and have no same-volley counted double persuasion. The new batch-edge fixture must exercise the persuasion change: these existing fixtures alone do not.

## Re-keying after a request change

`regen_goldens.py` reconstructs initial code and globals requests and calls `FixtureClient.key_for` without instantiating a client. It retains original response bytes when only request content changed, updates the exact request hash set in `test_golden.py`, and repins `test_data.py` plus report pack-hash metadata when needed. It validates every response before writes and removes obsolete keyed files only after successful validation. A repeated unchanged invocation prints `No changes.` and preserves bytes and modification times.

When a merge changes volley ids, copy the existing response bodies into one JSON object keyed by current call tag, edit the volley grouping using the new rendered batch, and retain only quotes present in that volley's actual clinician turns. New batches require hand-supplied responses. Example structure (each placeholder is an actual complete existing response object):

```json
{
  "miti_code:r0:b1": {"volleys": []},
  "miti_globals:r0:g": {"globals": {}}
}
```

The empty lists/objects above illustrate structure only: code needs exactly the current batch's volley ids and globals needs all four ratings. Never fabricate transcript text. Store the completed edits under this measurements folder, then run:

```bash
.venv/bin/python engines/miti/tools/regen_goldens.py --responses docs/agent_files/session-report-ux-20261124-1738/02-miti-manual-alignment/measurements/step1-responses.json
```

The utility does not silently recompute report behavior. If deterministic rule output changes, inspect a locally replayed report against hand targets and deliberately refresh `data/fixtures/evaluation/report_no_rating.json` in that rule commit. The existing offline `tests/test_golden.py::_run()` helper returns the current report using the keyed synthetic responses and the old report's tips; it is a suitable source for a local candidate. Keep the synthetic-data provenance explicit.

## Full adapter evidence after an intentional rule change

`tests/fixtures/adapter_pre_input_locks.json` and its full-byte parity test are the historical SP01 proof (verified at commit `ce65eef`). They remain unchanged in Task 1. They must not be quietly repinned by request regeneration, since that would erase the meaning of the input-lock non-regression check.

After a subsequent alignment rule intentionally changes adapter output:

1. Run the original full adapter parity check first and inspect the differences. Record the rule, expected count/global/request-hash changes, and the old fixture's path plus commit `ce65eef` in the step artifact. That git commit retains the historical assertion and bytes.
2. Refresh request stubs and engine report first; validate the hand count targets and focused engine tests. Use `test_golden.py::_adapter_run()` for a deterministic local candidate, then `adapter_bytes(candidate)` to normalize **only generated created_at timestamps**, exactly as SP01 does.
3. Inspect the complete candidate (report, artifacts, run_info). Commit an explicitly named alignment baseline, e.g. `adapter_manual_alignment.json`, and update the adapter test name/docstring/path to describe its new rule baseline and point back to SP01's verified commit. Do not mask additional fields just to make it pass.
4. Re-run the full-byte adapter parity test, engine golden tests and changed rule tests. Record their local output and the audit `stepN.json` in the same rule-change commit.

Task 1 also corrects a pre-existing stale test-only pack pin: `test_data.py` had `d98e79648859d15e`, while the current pack and committed golden report already carry `e068479e6bb821dd`. No pack, prompt, scoring rule, request stub, report or adapter-baseline bytes change here.
