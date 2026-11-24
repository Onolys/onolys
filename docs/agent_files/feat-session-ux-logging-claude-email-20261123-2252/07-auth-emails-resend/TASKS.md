---
status: draft
summary: 10 tasks - settings, email/links ports, unverified-ok auth dep, Firestore rate limits, two endpoints, contract regen, web switch, infra gated on resend_secret_wired.
date: 2026-11-23
---
# Tasks: SP07 Auth emails via Resend
Source of truth: `docs/agent_files/feat-session-ux-logging-claude-email-20261123-2252/07-auth-emails-resend/PRD.md`. API sends verify and reset emails via Resend behind a port; links are rebuilt on `APP_BASE_URL/auth/action`; web calls the two new endpoints. Staging only; API must deploy and serve without the Resend secret. No PRD open items remain. No CI task needed (existing `ci.yml` already runs drift checks and tests).

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Settings and log fields | - | done |
| 2 | Email port and adapters | 1 | done |
| 3 | Unverified-allowed auth dependency | - | done |
| 4 | AuthLinks port and link builder | 1 | done |
| 5 | Email templates and service | 2, 4 | done |
| 6 | Firestore rate limiter | 1 | done |
| 7 | Auth email endpoints | 2, 3, 4, 5, 6 | done |
| 8 | Contract and docs regeneration | 7 | done |
| 9 | Web switch to new endpoints | 8 | done |
| 10 | Infra and deploy env wiring | 1 | done |

## Task 1 — Settings and log fields
What it is / what it means: Config the feature needs, plus the log field names the later tasks emit (R7, R10).
What changes at a high level: `Settings` gains `app_base_url`, `email_from`, `resend_api_key`. Startup fails with `ConfigError` unless `app_base_url` is https (or `http://localhost:*` in local/test) and its host is on the known app-host list from `web-email-actions.md`. `API_FIELDS` in `logs.py` gains `email_kind`, `outcome`, `provider_status` (extend the existing set; do not touch SP02's separate allowlist).
Done when: unit tests prove valid staging/prod/localhost URLs load; http non-localhost, unknown host and missing value raise `ConfigError`; missing `resend_api_key` does not fail startup (AC7 part); the three new fields are accepted by the log allowlist.

## Task 2 — Email port and adapters
What it is / what it means: The `EmailSender` seam with fake, Resend and unconfigured implementations (R4, D7, D8).
What changes at a high level: Add the protocol to `adapters/base.py`; `FakeEmailSender` (in-memory record, no network) in `fake.py`; `ResendEmailSender` (`requests`, Bearer key, 5 s timeout, no retry) and `UnconfiguredEmailSender` (raises `AdapterError("email_unconfigured")`) in `real.py`. Factory picks fake for `ADAPTERS=stub`, Resend for real plus key, unconfigured for real without key. Errors never carry provider bodies.
Done when: tests cover factory selection for all three cases; Resend adapter with a mocked HTTP layer sends the right request shape and maps timeout/non-2xx to `AdapterError` without echoing the body; fake records messages; unconfigured raises.

## Task 3 — Unverified-allowed auth dependency
What it is / what it means: Verify-email callers have unverified tokens, which today get 403 `email_unverified` (R2).
What changes at a high level: `IdTokenVerifier.verify` accepts `allow_unverified=True`; new `current_user_unverified_ok` dep (token only, API keys rejected). Signature, iss, aud, sub checks unchanged. Existing `current_user` behavior untouched.
Done when: tests show unverified token passes only via the new dep and still yields 403 on the old dep; no token gives 401; API key gives 403; bad signature/aud still rejected with the new dep.

## Task 4 — AuthLinks port and link builder
What it is / what it means: Generate Firebase action codes server-side and rebuild the link on our own host (R3, D1, D6).
What changes at a high level: Add `firebase-admin` to `pyproject.toml`; `AuthLinks` protocol plus real (lazy single Admin SDK init; email from uid via `get_user` for verify; `None` for unknown reset account) and fake implementations. A builder parses the SDK URL, keeps only `oobCode`, and emits `<APP_BASE_URL>/auth/action?mode=<hard-coded>&oobCode=…` with optional `continueUrl` only when `next` matches `^/[^/\\]`.
Done when: tests prove the output host always equals `APP_BASE_URL` even when the SDK URL has another host or `Host`/`Origin`/`X-Forwarded-Host` vary (AC3 builder part); mode is hard-coded per kind; bad `next` values (`//x`, `/\x`, absolute URLs) are dropped; unknown account returns `None`.

## Task 5 — Email templates and service
What it is / what it means: Branded content and the one function that turns a code into a sent email (R5).
What changes at a high level: `email/templates/{verify,reset}.{html,txt}.tmpl` with one button/link, single-use and ignore-if-not-requested copy; fixed subjects; sender from `EMAIL_FROM`. Service renders (link only interpolated, HTML-escaped) and calls `EmailSender`.
Done when: tests render all four templates, assert subject/from/link presence, assert link HTML-escaping, and with the fake sender assert the recorded message has link host equal to `APP_BASE_URL` with mode `verifyEmail` or `resetPassword` (AC1 service part).

## Task 6 — Firestore rate limiter
What it is / what it means: Cross-instance abuse limits, since none exist today (R6, D4).
What changes at a high level: Transactional fixed-window counters in `email_rate/{key}` with a TTL field; doc ids are HMACs (`UID_HMAC_KEY`), never raw emails. Policies: verify per uid 1/60 s and 5/h; reset per email-HMAC 1/60 s and 5/h plus per-client-IP 20/h (first `X-Forwarded-For` hop). Returns allow/deny only; routes decide the response.
Done when: tests against the Firestore fake/emulator pattern used in the repo prove each window and cap, window rollover, TTL field set, independent keys, concurrent increments not double-allowing, and that no doc id contains a raw email or IP.

## Task 7 — Auth email endpoints
What it is / what it means: The two routes tying everything together with PHI-safe logging (R1, R10, D5, D6).
What changes at a high level: New `routes/auth_email.py` under `/v1`, registered in `app.py`. Verification: unverified-ok token dep, already-verified gives `202` with no send, over-limit `429 rate_limited`, send/config failure `503 email_unavailable`. Password reset: no auth, same `202 {}` for known, unknown, disabled, Admin SDK error and rate-limited; send runs in a `BackgroundTask`; failure after 202 only logged. Logs use `email_kind`, `outcome`, `provider_status`; verify logs `uid_hash`, reset logs no identifier; never email, link or `oobCode`.
Done when: API tests with fakes cover AC1, AC2 (identical status/body, nothing recorded for unknown), AC3 end to end, AC4, AC5, AC6 (capture handler finds no email/link/oobCode), and AC7 (no `RESEND_API_KEY` returns 503 `email_unavailable` while the app serves other routes).

## Task 8 — Contract and docs regeneration
What it is / what it means: Keep published contracts and docs in sync with the new routes (R11, AC8).
What changes at a high level: Regenerate `api/openapi.json` (`python -m onolys_api.openapi`), `docs/contracts/public/*` (`python -m onolys_api.contracts`) and `web/src/api/schema.d.ts` (`npm run gen:api`). Add the two routes and `email_unavailable` to `docs/reference/public-api.md`; update the "who sends" section of `docs/reference/web-email-actions.md`.
Done when: the regeneration commands run clean twice with no diff, the CI drift checks (`ci.yml` openapi/contracts/schema steps) pass locally, and the new routes plus error code appear in the docs.

## Task 9 — Web switch to new endpoints
What it is / what it means: Web stops using Firebase's client email senders (R9, D3).
What changes at a high level: In `firebaseService.ts` replace `sendEmailVerification` (signup and `sendVerificationEmail`) with the verification POST using the current user's ID token, and `sendPasswordReset` with the token-less reset POST (also serves `AuthAction` and `ForgotPassword`). Update `errors.ts`/`types.ts`, `fakeService` keeps its contract. Apply the PRD copy for success, 429 and 503/network. Signup still swallows send failure. `VerifyEmail` Resend button disabled 60 s after click. No fallback to the Firebase sender.
Done when: web tests cover the two calls (token present or absent), reset message identical for any outcome, 429 and 503/network copy, the 60 s disable, signup tolerating failure, and a grep/lint check shows no remaining imports of `sendEmailVerification` or `sendPasswordResetEmail` (AC9).

## Task 10 — Infra and deploy env wiring
What it is / what it means: Terraform and deploy config so staging can run the feature and any environment can deploy without the secret (R7, R8, D2).
What changes at a high level: `secrets.tf` adds shell secret `resend-api-key-${env}` plus accessor for the api SA. `services.tf` adds `APP_BASE_URL`, `EMAIL_FROM` and `RESEND_API_KEY` via `secret_key_ref` gated by new variable `resend_secret_wired` (default false, false in prod). Api SA gets `roles/firebaseauth.admin`. `variables.tf`/`main.tf` carry app base URLs (staging `https://onolys-app-staging.web.app`, prod `https://app.onolys.com`). Mirror `APP_BASE_URL`/`EMAIL_FROM` in `deploy-staging.yml` `env_vars`.
Done when: `terraform validate` and plan show only the secret shell, IAM and env vars with prod otherwise unchanged and no secret ref while `resend_secret_wired=false` (AC10); a workflow lint or review check confirms the staging env_vars include the new names.

## Owner steps
1. Verify `onolys.com` in Resend (SPF/DKIM DNS).
2. Create a sending-only Resend API key.
3. Store it as Secret Manager `resend-api-key-staging`.
4. Set `resend_secret_wired=true` for staging, re-apply Terraform, redeploy.
5. Staging smoke: signup, email arrives from `no-reply@onolys.com`, link opens `/auth/action` and verifies; then narrow the `firebaseauth.admin` role.
(GitHub vars `LLM_PROVIDER`/`LLM_MODEL` are not relevant to this sub-project.)
