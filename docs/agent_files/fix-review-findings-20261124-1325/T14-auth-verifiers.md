# T14 — defensive auth verification

Findings LM-8 (B4/B5/Codex M5), D13 and D11 are fixed in code.

Admin and task signing keys use independent instances of one single-flight cache: one-hour TTL, 30-second global refresh/failure cooldown, six-second lock wait, five-second network timeout. Expired cached keys never rescue a failed refresh. A normally rotated key can return 401 during the remaining cooldown; inability to refresh returns 503. No per-key negative-cache entries accumulate. Both middleware paths offload synchronous verification with asyncio.to_thread; eval claims capture and separate service-account identity checks remain intact.

Public admin denial codes distinguish email_unverified and not_allowlisted. Internal task mismatches remain generic forbidden. No Pydantic models or generated public schemas changed (admin/eval do not publish OpenAPI). Eval CORS includes exact localhost and 127.0.0.1 origins at Vite's default port 5173; a different dev port requires explicit configuration.

## Validation

Initial admin regression run: 25 passed, 3 failed (repeat fetches on empty/failing responses and event-loop execution). After changes:

- `/tmp/iaudit-review-venv/bin/python -m pytest admin/auth/tests/test_auth.py -q -p no:xdist` — 30 passed.
- `/tmp/iaudit-review-venv/bin/python -m pytest admin/backend/tests/test_gateway.py -q -p no:xdist` — 37 passed.
- `/tmp/iaudit-review-venv/bin/python -m pytest eval/backend/tests/test_app.py eval/backend/tests/test_runs.py eval/backend/tests/test_uploads.py -q -p no:xdist` — 147 passed (including created_by claims capture).
- `/tmp/iaudit-review-venv/bin/python -m pytest infra/scripts/test_eval_service.py -q -p no:xdist` — 4 passed.
- `/tmp/iaudit-review-venv/bin/ruff check admin/auth admin/backend eval/backend` — passed.
- `terraform fmt -check infra/eval-services.tf` — passed.
- `terraform -chdir=infra validate -no-color` — blocked: staging/prod modules not installed. No init/provider downloads performed.

Tests use local keys, fake transport/clock, and thread events; no provider calls. No push or cloud changes. Owner must apply Terraform. The network timeout is the requests transport timeout, not a hard process/thread cancellation deadline. Existing pytest-asyncio default-fixture-loop deprecation warning remains.
