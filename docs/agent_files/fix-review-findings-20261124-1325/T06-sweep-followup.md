# T06 follow-up — bounded sweep fairness and API branch verification

Runtime fix: `f8fbd90`.

Skipped failed-upload discard tombstones now move to the back of the ordinary deletion scan by restarting their grace period. They remain owned by their discard task; ordinary deletion never removes their tombstone/stub data.

Active-user repair scans now transactionally persist `(active_runs, document ID)` under `_maintenance/sweep_active_runs`. Each call selects at most its limit, advances across separate worker processes, and wraps when it reaches the end. The full tuple preserves tied candidates even after the prior user is repaired or deleted. Missing/malformed old checkpoints restart safely; existing user/session schemas require no migration. FakeRepo mirrors the persisted cursor.

Index/schema/cleanup audit: the active_runs single-field ascending index already includes the ascending document name tie-breaker; api/firestore.indexes.json has no disabling override. No new index or cloud apply is required. The checkpoint is one bounded server-maintenance document outside session cleanup prefixes, and existing Firestore rules deny client access to it. No owner/user route exposes the cross-user scans. Source ownership guards exempt only the exact maintenance methods and recognize nested transaction scope; a regression still rejects unscoped user queries and their nested transactions.

Deterministic fake/emulator tests use batches of 1 or 2 and verify tombstone starvation, legitimate users preceding a leaked user, persistence across independent clients, count ties, wrap, prior-candidate removal, zero limits, and malformed legacy checkpoints.

The first ordinary branch run found four stale assertions: two source ownership guards had not accounted for worker sweeps/nested scopes, the acceptance checklist named the pre-fix speaker-confirmation test, and an interview retry expected the old conflict behavior. Updated the latter two in a separate test-maintenance commit. Retry now asserts the same 202 resource and no duplicate; 409 coverage remains for a linked session beyond upload and for an idempotency key reused with a different interview.

## Verification

All commands ran in `/root/projects/onolys/iaudit/.worktrees/review-main-audit` using `/tmp/iaudit-review-venv/bin/python`, with no external services. The local emulator was started with:

`java -jar /root/.cache/firebase/emulators/cloud-firestore-emulator-v1.22.0.jar --host=127.0.0.1 --port=19157`

- Before runtime fix: `python -m pytest api/tests/test_sweep_fairness.py -k fake -q -p no:xdist`: **3 failed**, matching the two starvation defects and repeated first-page behavior.
- Focused emulator + fake: `FIRESTORE_EMULATOR_HOST=127.0.0.1:19157 GOOGLE_CLOUD_PROJECT=demo-onolys python -m pytest api/tests/test_sweep.py api/tests/test_sweep_fairness.py -q -p no:xdist`: **27 passed** (2.41s).
- Scope guard and fake follow-up: `python -m pytest api/tests/test_repo_uid_filter.py api/tests/test_sweep.py api/tests/test_sweep_fairness.py -m 'not firestore' -q -p no:xdist`: **24 passed, 7 deselected**.
- Maintenance cases: `python -m pytest api/tests/test_acceptance_checklist.py api/tests/test_interview_link.py api/tests/test_repo_uid_filter.py -q -p no:xdist`: **109 passed**.
- Final ordinary selection: `COVERAGE_FILE=/tmp/iaudit-t06-sweep-verify/unit.cov LITELLM_LOCAL_MODEL_COST_MAP=True MITI_LLM_RECORD=0 python -m pytest api -m 'not live and not flaky and not firestore and not nightly' -n 2 --durations=25 --cov=api/src --cov-report=`: **1920 passed, 5 skipped**, 126.15s.
- Final emulator selection: `COVERAGE_FILE=/tmp/iaudit-t06-sweep-verify/emulator.cov FIRESTORE_EMULATOR_HOST=127.0.0.1:19157 GOOGLE_CLOUD_PROJECT=demo-onolys LITELLM_LOCAL_MODEL_COST_MAP=True MITI_LLM_RECORD=0 python -m pytest api -m 'firestore and not live and not flaky and not nightly' --durations=25 --cov=api/src --cov-report=`: **372 passed, 1978 deselected**, 165.60s. Subsequent changes touched only ordinary-selection assertions/guards, not runtime or emulator tests.
- Combined with `COVERAGE_FILE=/tmp/iaudit-t06-sweep-verify/combined.cov python -m coverage combine --keep /tmp/iaudit-t06-sweep-verify/unit.cov /tmp/iaudit-t06-sweep-verify/emulator.cov`, then `coverage report --fail-under=94`: **6561/6782 lines, 96.741374%**, gate passed (display rounded to 97%).
- `python -m ruff check api`: passed. `git diff --check`: passed.

Full result files: `/tmp/iaudit-t06-sweep-verify/focused.log`, `unit.log` (initial failures), `unit-final.log`, `firestore.log`, `coverage.txt`, `coverage.json`, `unit.cov`, `emulator.cov`, `combined.cov`, `emulator.log`. The emulator was stopped after verification. No cloud calls, push, installs, PLAN edits, or eval-file changes.
