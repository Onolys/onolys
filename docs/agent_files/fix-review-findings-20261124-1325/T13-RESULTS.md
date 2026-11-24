# T13 — Eval backend review repairs

Completed the inherited T13 backend work. H-6/H2 uses expiring leases, bounded reclaim attempts, owner-fenced progress/final accounting, and separate output objects per lease attempt. Interrupted work releases its lease; live duplicate delivery schedules a later task. LM-18/M3 bounds persisted transcription polling to two hours and reconciles lost poll chains on reads. B13/D9 finalizes entirely cancelled runs as cancelled and exposes cancel_requested. B14 bounds inline output bytes to 8 MiB, with existing per-unit fetch for omitted output. B15 rejects one-shot runs without a change goal before writes. D3 aligns upload goals at 4000 characters. LM-11/D2 allows datasets without gold while explicit human selection still requires gold. D8 adds bounded history pages and stable cursors, including timestamp ties/deleted cursor documents. B7 moves blocking upload/unit storage and repository operations off the event loop.

M-7/D4 backend is complete; frontend and infrastructure are assigned to T17. Multipart audio is capped at 25 MiB, below Cloud Run's body limit. Direct audio accepts up to 300 MiB without proxying recording bytes through the app.

## Direct-upload client contract

1. Authenticated POST `/v1/uploads/audio`, JSON `{filename, content_type, size, change_goal?, language?, coded_span?, gold?}`. `size` is an integer 1..314572800; goal max 4000; gold is the parsed object, not a multipart file.
2. Response includes normal upload fields with `status: awaiting_upload` plus `upload: {url, method: PUT, headers: {Content-Type, x-goog-content-length-range}}`.
3. Send the raw File to `upload.url` with exactly the returned method/headers. Do not attach the backend bearer token to the signed URL request.
4. Authenticated POST `/v1/uploads/{upload_id}/complete`, then use existing polling and speaker selection. Completion retries repair failed enqueue or enqueue-marker writes. A stable initial Cloud Task ID deduplicates repeated completion; the state transition is atomic and cannot regress finished transcription.

Deployment needs bucket CORS allowing PUT from the eval origins (`https://onolys-eval-staging.web.app`, `https://eval.onolys.com`) and the returned Content-Type/x-goog-content-length-range headers. Runtime eval service account needs signBlob permission through roles/iam.serviceAccountTokenCreator on itself and IAM Credentials API. No cloud changes or push performed.

## Verification

- `COVERAGE_FILE=/tmp/t13.coverage /tmp/iaudit-review-venv/bin/python -m pytest eval/backend/tests/test_runs.py eval/backend/tests/test_read_runs.py eval/backend/tests/test_uploads.py eval/backend/tests/test_persistence.py -q -p no:xdist`: **143 passed, 1 deselected**, 10.22s.
- With local Firestore emulator on 127.0.0.1:19833: `FIRESTORE_EMULATOR_HOST=127.0.0.1:19833 GOOGLE_CLOUD_PROJECT=demo-test COVERAGE_FILE=/tmp/t13-emulator.coverage /tmp/iaudit-review-venv/bin/python -m pytest eval/backend/tests/test_persistence.py::test_firestore_pagination_survives_deleted_cursor_and_fences_completion -m live -q -p no:xdist`: **1 passed**, 1.88s. Emulator terminated afterward.
- `/tmp/iaudit-review-venv/bin/ruff check eval/backend`: passed.
- `git diff --check`: passed.

The initial inherited suite had 126 passed/3 failed: two multiple-client fixtures used one-off names incompatible with the accepted R1 parser policy; their client labels now repeat and still verify distinct client speakers through upload/run execution. The third was a missing injected verifier in the new async responsiveness test. Additional regression tests were observed failing before their fixes: UTF-8 detail budget, attempt-scoped output storage, failed completion enqueue retry, and stale concurrent completion state regression.

Eval disables OpenAPI output and has no generated contract artifacts. Existing API schemas were not changed. T14 owns auth/CORS application changes; T17 owns direct-upload UI and deployment configuration.

## Remaining limitations

Cloud Tasks/provider delivery remains at least once: a process crash after provider acceptance but before persisting the STT handle can still start an additional provider operation on delivery retry, as in the prior multipart path. Named completion tasks prevent duplicate logical initial tasks caused by repeated complete calls; they do not claim provider exactly-once execution. Owner/product retention decisions remain outside this task.
