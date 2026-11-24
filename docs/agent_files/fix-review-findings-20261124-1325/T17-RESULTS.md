# T17 — public admin/eval UI and direct recording uploads

Fixed D5's default admin auth iframe host in both Hosting targets, D13's exact public denial codes, D8 history continuation, and structured HTTP 404 polling termination. Both auth transports inspect cloned responses and preserve the body for callers. Unknown/malformed denial codes retain generic text. Eval status polling retains its existing transient-error backoff and explicit retry.

History uses the backend's exact `{runs, next_cursor}` response and encoded `cursor` query parameter. Load more appends rows, retains accumulated rows and the failed page cursor on errors, deduplicates IDs, and aborts/ignores requests from a stale API source or unmounted view.

M-7/D4 integration now keeps transcripts and audio through 25 MiB on multipart `/v1/uploads`. Recordings above 25 MiB through 300 MiB use authenticated JSON `/v1/uploads/audio`, raw PUT to the returned signed URL with its returned method/headers and credentials omitted, then authenticated `/v1/uploads/{id}/complete`. Goal, language, coded span, filename, MIME, size and parsed optional gold JSON all reach the start request. Completion feeds the existing transcription polling and speaker selection. Pending state belongs to the form's input object: Retry reuses it, successful PUTs are not repeated after completion errors, lost PUT responses can retry against the write-once precondition and complete after 412, and expired/denied PUTs prepare a fresh target on Retry. Storage fetch is independent of the bearer-token transport. Connection/CORS and signed-permission failures have separate actionable messages. Refresh discards pending state, so the UI tells users to keep the page open and restart preparation after refresh; persisted upload resume is outside this change.

Signed PUTs now sign and return `x-goog-if-generation-match: 0`, including the in-memory contract adapter. Google documents this as allowing object-data writes only when no live object of the same name exists; existing objects return 412: [request preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions). Mocks assert the signed headers and returned client headers match; no live storage requests were made.

Infrastructure adds exact PUT origins for eval staging, eval custom domain, localhost:5173 and 127.0.0.1:5173; headers include Content-Type, x-goog-content-length-range and x-goog-if-generation-match. Eval Hosting CSP permits storage.googleapis.com. IAM tokenCreator is bound only from the eval runtime identity onto itself. Existing main.tf already enables IAM Credentials; existing deploy-eval workflow deploys backend before Hosting and was left unchanged.

An orchestrator-requested LM-11/D2 follow-up aligns dataset UI with T13: Human remains the default when gold exists, can be deselected to include sessions without gold, is unavailable on all-no-gold datasets, and is never automatically added to saved AI-only reruns. Explicit Human comparison continues to require gold.

## Verification

Initial regressions: eval API/run/auth tests 7 failed / 42 passed; admin auth/Hosting 3 failed / 21 passed; signed-header mocks 2 failed; infra CORS/IAM tests 2 failed / 5 passed. Added dataset alignment regressions failed 4 / passed 23 before the change. Final commands:

- `npm --prefix eval/web test -- src/api.test.ts src/Runs.test.tsx src/auth/AuthGate.test.tsx src/NewRun.test.tsx src/transport/authFetch.test.ts src/hosting/hosting.test.ts src/Root.test.tsx --maxWorkers=1` — **92 passed**, 7 files.
- `npm --prefix frontend test -- src/auth/AuthGate.test.tsx src/hosting/hosting.test.ts src/transport/authFetch.test.ts src/Shell.test.tsx src/auth/gate.test.tsx` — **44 passed**, 5 files.
- `COVERAGE_FILE=/tmp/t17-storage.coverage /tmp/iaudit-review-venv/bin/python -m pytest eval/backend/tests/test_signed_upload.py eval/backend/tests/test_uploads.py -q -p no:xdist` — **41 passed**.
- `COVERAGE_FILE=/tmp/t17-infra-final.coverage /tmp/iaudit-review-venv/bin/python -m pytest infra/scripts/test_eval_bucket.py infra/scripts/test_eval_service.py -q -p no:xdist` — **7 passed**.
- `npm --prefix eval/web run typecheck`; `npm --prefix frontend run typecheck`; `npm --prefix eval/web run build`; `npm --prefix frontend run build` — passed. Builds include typechecks; eval build repeated after dataset follow-up.
- `npm --prefix eval/web run lint`; `/tmp/iaudit-review-venv/bin/ruff check eval/backend infra/scripts/test_eval_bucket.py infra/scripts/test_eval_service.py` — passed. Admin frontend has no configured lint script.
- `terraform fmt -check infra/eval.tf infra/eval-services.tf` — passed.
- `terraform -chdir=infra validate -no-color` — blocked by uninstalled staging/prod modules, as in T14. No init/provider downloads performed.
- `git diff --check -- eval frontend infra/eval.tf infra/eval-services.tf infra/scripts/test_eval_bucket.py infra/scripts/test_eval_service.py` — passed.

## Caveats and owner steps

Owner must apply Terraform before using large uploads (bucket CORS and runtime signer IAM), then deploy backend and Hosting in the existing order. A different local Vite port needs matching app and bucket CORS configuration. Browser behavior is verified through deterministic local tests, mocks and production builds; no cloud/browser deployment smoke test, provider call, push or exploitation test was performed. Existing pytest-asyncio fixture-scope deprecation warning remains. Runtime signing, provider transcription and live CORS still require deployment verification. Eval publishes no OpenAPI schema, and no generated API contracts changed.
