# T13 follow-up — Prevent stale upload writers

The independent review identified reads followed by unconditional upload writes. Reproduced five failures before repairs: GET timeout and task timeout/failure regressed a completed upload, duplicate STT completion rewrote transcript bytes after speaker choice, and a stale provider start published its handle after losing ownership.

Upload transitions now optionally compare expected fields atomically in both repositories. Transcription updates compare status, handle, phase timestamps, and initial-start owner/lease fields. GET timeout re-reads after losing its comparison. Invalid direct-upload completion compares awaiting_upload before publishing its failure.

Provider submission acquires a 120-second lease before invoking start. Concurrent deliveries defer through the queue; expired submission leases can be reclaimed, and old owners cannot publish handles. Queue errors on deferral remain retryable rather than becoming terminal transcription failures. Persisted uploads without these lease fields continue to work.

Each completed poll and clinician choice writes a fresh transcript object, then atomically publishes its reference. A stale poll cannot rewrite the already published transcript. Failed comparisons remove only the unpublished candidate on a best-effort basis; already published paths remain retained because readers/runs may still hold them. Cleanup errors do not change winning metadata. A conflicting clinician choice returns 409 speaker_conflict with a reload/retry message; a concurrent matching clinician choice succeeds idempotently.

## Verification

- `COVERAGE_FILE=/tmp/t13-followup.coverage /tmp/iaudit-review-venv/bin/python -m pytest eval/backend/tests/test_upload_concurrency.py eval/backend/tests/test_uploads.py eval/backend/tests/test_persistence.py eval/backend/tests/test_runs.py eval/backend/tests/test_read_runs.py eval/backend/tests/test_signed_upload.py -q -p no:xdist`: **161 passed, 2 deselected**, 10.37s.
- Local Firestore emulator, with `FIRESTORE_EMULATOR_HOST=127.0.0.1:19834 GOOGLE_CLOUD_PROJECT=demo-test COVERAGE_FILE=/tmp/t13-followup-emulator.coverage`: `/tmp/iaudit-review-venv/bin/python -m pytest eval/backend/tests/test_upload_concurrency.py::test_firestore_upload_field_comparisons_are_atomic eval/backend/tests/test_persistence.py::test_firestore_pagination_survives_deleted_cursor_and_fences_completion -m live -q -p no:xdist`: **2 passed**, 2.17s. Emulator terminated afterward.
- `/tmp/iaudit-review-venv/bin/ruff check eval/backend`: passed.
- `git diff --check`: passed.

No cloud calls or push. Existing test_uploads.py and T17 signing changes were preserved. The new regression file covers timeout/failure/success races, handle replacement, initial submission fencing/reclaim, normalization and speaker flow, invalid direct completion, conflicting speaker choices, and safe candidate cleanup.

## Remaining limitations

Provider acceptance followed by process death before handle persistence can still produce an additional provider operation after lease expiry. The lease fences publication, not the remote provider. Failed/best-effort candidate cleanup or uncertain repository errors may leave unreferenced objects; deleting published transcript history and broader retention remain outside this repair.
