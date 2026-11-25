# SP05 scheduler re-review fixes

This round supersedes the first review artifact's reliance on HTTP 503 retries for busy ticks.
The deployed shared queue allows two attempts with 5-second minimum backoff, which can expire
before the scheduler's 120-second lease. Busy delivery now creates one idempotently named
delayed recovery task before returning success. Its timer survives an owner crash, resolves
the current sequence when delivered, and gives its successor a distinct name so an already
consumed normal task name cannot suppress continuation. A failed recovery enqueue propagates
instead of acknowledging the source delivery. No infrastructure or production queue changes.

Each session's recovery/active-run lookup now runs inside isolation, once per tick, before
terminal outcomes are sorted. Failed lookup sessions skip further processing that tick, so
one failure increments the cell's error budget once. A confirmed missing session/run fails
only that cell after three errors. An uncertain read preserves a known active reference and
provider slot until its actual outcome can be established; other sessions continue. Slot
sweeping reuses current lookups and isolates errors on foreign holders too.

Accepted cancellation takes terminal status precedence even when every cell was already in
flight: any successful AI work gives `partial`, otherwise `cancelled`. The terminal-save
transaction applies the same rule, covering cancellation accepted after the last scheduler
read. Human refs and all public counters retain their existing meanings.

## Evidence

- The initial seven new regressions failed before implementation: two-attempt queue recovery
  for completed/crashed owners, pending/active missing sessions, uncertain active lookup,
  and accepted cancellation after a single in-flight success/failure.
- Additional enqueue-before-claim recovery and terminal-save cancellation race regressions
  failed before their boundary fixes. A duplicate-timer/enqueue-failure test also passes.
- `.venv/bin/pytest -q eval/backend/tests/test_eval_scheduler_rereview.py eval/backend/tests/test_eval_scheduler_review.py eval/backend/tests/test_eval_scheduler.py eval/backend/tests/test_eval_resilience.py eval/backend/tests/test_eval_cancel.py eval/backend/tests/test_eval_delete.py eval/backend/tests/test_persistence.py`
  → **89 passed, 1 deselected** (14.11 seconds).
- Targeted Ruff checks on the changed scheduler, repository and both review regression files
  → **All checks passed!**
- `git diff --check` → clean.

The scheduled fake models named-task deduplication and the actual two-attempt/5-second
retry policy, driving the task handler with a fake clock and no GET safety net. All checks
were offline. No live services, cloud operations, pushes, worker changes, or infrastructure
changes were performed.
