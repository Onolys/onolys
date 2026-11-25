# SP05 scheduler review fixes

The scheduler now leases each grouping doc for a scheduling round and fences every snapshot
write, provider-slot admission/cleanup, and actual RunDoc start with the owner token. A later
tick retries while the lease is live (HTTP 503), and can recover after 120 seconds. The chain
is queued before ownership changes; busy deliveries do not enqueue speculative successors.
Failed enqueues leave the current sequence unchanged. A stale owner cannot overwrite recovered
counters, cursors, refs, or terminal/deleting state.

Cancellation is checked before every idle session, and start admission checks it atomically
with RunDoc creation. This requires an opt-in `eval_guard` argument on the API repository's
`start_run` transaction: a check outside that transaction cannot fence a paused creator after
lease recovery or a concurrent cancellation. Ordinary starts omit the argument. The fake eval
repository holds its cancellation/lease lock through the fake RunDoc transaction; the real
Firestore adapter reads the grouping doc inside the RunDoc transaction. No worker changes.

A recovered tick adopts deterministic RunDocs left by creation-before-save crashes before
marking unstarted cells cancelled, preserving in-flight work and its provider slot. Unexpected
creation errors release their slot and reach the existing per-cell handler-error budget;
expected busy responses continue waiting. If creation already produced a RunDoc before an API
queue error, that actual RunDoc is adopted for normal outcome accounting. Terminal status
subtracts Human gold refs from success/total counts while preserving all public counters.

## Evidence

- Test-first: the initial seven scheduler regressions all failed on the reviewed implementation.
  The additional cancellation-after-create-before-ref-save regression also failed before its fix.
- `.venv/bin/pytest -q eval/backend/tests/test_eval_scheduler_review.py eval/backend/tests/test_eval_scheduler.py eval/backend/tests/test_eval_resilience.py eval/backend/tests/test_eval_cancel.py eval/backend/tests/test_persistence.py eval/backend/tests/test_eval_delete.py`
  → **78 passed, 1 deselected** (12.35 seconds).
- `.venv/bin/pytest -q api/tests/test_start_run_eval.py api/tests/test_create_run.py api/tests/test_start_run.py -m 'not firestore and not live'`
  → **47 passed, 46 deselected** (4.59 seconds).
- Targeted Ruff check across all changed Python files → **All checks passed!**
- `git diff --check` → clean.

Tests cover overlapping/duplicate deliveries, premature next delivery, enqueue failure,
expired-owner recovery, stale writes/starts/slot cleanup, cancellation before admission and
between sessions, cancellation recovery after a created-but-unrecorded run, deleted-group
fencing, persistent creation failures, and Human-inclusive counters with no successful AI work.
The API tests cover accepted/refused guards and directly assert that the real Firestore
adapter reads cancellation using the RunDoc transaction. All checks were offline; no emulator,
live service, deployment, push, or cloud operation was run.
