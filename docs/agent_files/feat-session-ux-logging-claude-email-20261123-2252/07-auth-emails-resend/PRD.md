---
status: draft
summary: API sends verification and password-reset emails via Resend (Admin SDK links rewritten to our /auth/action); web calls two new endpoints instead of Firebase's client senders; fake sender locally; safe to deploy before the Resend secret exists.
date: 2026-11-23
---
# PRD: SP07 Auth emails via Resend

Repo/branch: Onolys/onolys (local `iaudit`) / `feat/session-ux-logging-claude-email` · Depends on: none (Phase 1) · Owns: `api/src/onolys_api/routes/auth_email.py` (new), `api/src/onolys_api/email/**` (new: service, templates), `api/src/onolys_api/adapters/{base,fake,real}.py` (email ports only), `api/src/onolys_api/{config,app,logs}.py` (small additions), `api/pyproject.toml` (+`firebase-admin`), `api/openapi.json`, `docs/contracts/public/*` (regenerated), `web/src/api/schema.d.ts` (regenerated), `web/src/auth/{firebaseService,errors,types,fakeService}.ts`, `web/src/auth/pages/{ForgotPassword,VerifyEmail}.tsx`, `infra/modules/environment/{secrets,services,variables}.tf`, `infra/main.tf`, `.github/workflows/deploy-staging.yml` (env_vars), `docs/reference/web-email-actions.md`

## TL;DR
Two API endpoints generate the Firebase link with the Admin SDK, rewrite it to `<APP_BASE_URL>/auth/action?mode=…&oobCode=…`, and send branded email through Resend behind a port (fake locally/tests). Web stops calling `sendEmailVerification` / `sendPasswordResetEmail`. Reset never reveals whether an account exists. Without the Resend secret the API deploys fine and answers "couldn't send".

## Problem
Firebase's emails come from Firebase's sender and hosted action config [verified: `docs/reference/web-email-actions.md`: hosted handler fails with `401 CREDENTIALS_MISSING`; the action URL is project-wide and only partly overridable]. We want our own sender, branding, and links that always land on our working `/auth/action` page (already handles `verifyEmail`, `resetPassword`, `verifyAndChangeEmail`, `recoverEmail` [verified: `AuthAction.tsx:56-63`]).

## Goals / Non-Goals
**Goals:** verify + reset emails via Resend; links on our page; no enumeration; abuse-limited; PHI/PII-safe logs; deploys before the secret exists; staging only.
**Non-goals:** change-email / recover-email senders (stay Firebase client calls, rare, unchanged; [DEFERRED]); changing `/auth/action`; marketing mail; Resend webhooks/bounce handling; prod rollout; custom SMTP in Firebase.

## Requirements
**R1 Endpoints** (under the existing `/v1` router, `routes/auth_email.py`):
| Endpoint | Auth | Body | Response |
|---|---|---|---|
| `POST /v1/auth/email/verification` | Bearer ID token, **unverified allowed** (new dep) | `{next?: "/path"}` | `202 {}` |
| `POST /v1/auth/email/password-reset` | none | `{email}` | `202 {}` always |
Errors: `429 rate_limited` (existing code [verified: `errors.py:26`]), `503 email_unavailable` (generic: not configured or Resend failed). Verification for an already-verified user: `202`, no send. API keys rejected (token only, as `current_user_token_only`). Reset: unknown email, disabled user, Admin SDK error, and success all return the same `202` after the same work; send runs in a `BackgroundTask` so latency does not leak existence. Resend failure on reset after the 202 is logged only (known trade-off, D5).
**R2 Auth dep.** Today `IdTokenVerifier.verify` raises `EmailNotVerified` for unverified tokens and `current_user` maps it to 403 `email_unverified` [verified: `idtoken.py:163`, `deps.py:76`]. Add `verify(token, allow_unverified=True)` and `current_user_unverified_ok`; signature, iss, aud, sub checks unchanged. Only these verify-email routes use it.
**R3 Links.** `AuthLinks` port: real = `firebase_admin.auth.generate_email_verification_link` / `generate_password_reset_link` (email taken from the token's uid via `get_user`, never from the request, for verify). Server parses the returned URL, takes `oobCode`, builds `<APP_BASE_URL>/auth/action?mode=<verifyEmail|resetPassword>&oobCode=…[&continueUrl=<APP_BASE_URL>/verify-email?next=…]`. `APP_BASE_URL` is `Settings` only (never `Host`/`Origin`). `next` must match `^/[^/\\]` (same rule family as web `readNext`) else dropped. Mode is hard-coded per endpoint, not read from the Firebase URL.
**R4 Email port.** `EmailSender.send(to, subject, html, text)` in `adapters/base.py`. `ResendEmailSender` (`real.py`): `POST https://api.resend.com/emails`, Bearer key, `requests`, 5 s timeout, no retry (user can resend). `FakeEmailSender` (`fake.py`): records messages in memory for tests; no network. `UnconfiguredEmailSender`: raises `AdapterError("email_unconfigured")`. Selection in factory: `ADAPTERS=stub` → fake; `real` + key present → Resend; `real` + no key → unconfigured.
**R5 Templates.** `api/src/onolys_api/email/templates/{verify,reset}.{html,txt}.tmpl`; simple inline-styled HTML + plain text, one button/link, sender "Onolys <no-reply@onolys.com>" (`EMAIL_FROM`), subject "Verify your email for Onolys" / "Reset your Onolys password". Only the link is interpolated (HTML-escaped). Copy states the link is single-use and to ignore if not requested.
**R6 Rate limits** (no limiter exists today; only the daily caps in `repo/limits.py` [verified]). Cloud Run is multi-instance, so counters live in Firestore (`email_rate/{key}`, fixed window, transactional increment, TTL field). Keys: verify = `uid`, 1 per 60 s and 5/hour; reset = HMAC(email, `UID_HMAC_KEY`) 1 per 60 s and 5/hour, plus per-client-IP 20/hour (first hop of `X-Forwarded-For` on Cloud Run). Reset over-limit returns the same `202` (no oracle) but sends nothing; verify over-limit returns `429`. Doc ids are HMACs, never raw emails.
**R7 Config.** `Settings`: `app_base_url`, `email_from`, `resend_api_key`. `app_base_url` required (https, or `http://localhost:*` when env local/test) else `ConfigError` at startup; staging `https://onolys-app-staging.web.app`, prod `https://app.onolys.com` (from Terraform vars; mirrored in `deploy-staging.yml` `env_vars` because that workflow overrides Terraform env [verified: `deploy-staging.yml:104-107`]). Link-domain allowlist: startup check that `app_base_url` host is one of the known app hosts (same list as `web-email-actions.md`).
**R8 Infra.** `secrets.tf`: shell `resend-api-key-${env}` + accessor for the api SA. `services.tf`: env `APP_BASE_URL`, `EMAIL_FROM`, and `RESEND_API_KEY` via `secret_key_ref`, the latter gated by variable `resend_secret_wired` (default false; false in prod). Api SA gets a Firebase Auth role for link generation ([OPEN] minimal role).
**R9 Web.** `firebaseService.ts`: replace `sendEmailVerification` (signup ~98, `sendVerificationEmail` ~127) with `POST /v1/auth/email/verification` (Bearer from `currentUser.getIdToken()`), and `sendPasswordReset` (~124, also used by `AuthAction.tsx:316` and `ForgotPassword.tsx:34`) with `POST /v1/auth/email/password-reset` (no token). `fakeService` unchanged in contract. Copy: reset always "If an account exists for that address, we've emailed a link."; verify "Verification email sent to {email}"; 429 "Too many requests. Wait a minute and try again."; 503/network "We couldn't send the email. Try again in a moment." Signup still swallows a send failure (account exists; VerifyEmail page offers Resend [verified: comment at `firebaseService.ts:97`]). `VerifyEmail` Resend button disabled for 60 s after click (matches server limit).
**R10 Logging** (`docs/implementation/logging-and-phi.md`: allowlist, class names only). Add fields `email_kind` (verify|reset), `outcome` (sent|rate_limited|unknown_account|send_failed|unconfigured), `provider_status` to `logs.py` `API_FIELDS` (the same frozenset SP04 extends with `from_state`, `counted`; SP02's `safe_log.ALLOWED_FIELDS` is a separate set). Never log email, link, `oobCode`, or Resend/Admin SDK error bodies (they can echo the address). Verify logs `uid_hash`; reset logs no identifier.
**R11 Contract.** New routes appear in `api/openapi.json`; regenerate with `python -m onolys_api.openapi` then `python -m onolys_api.contracts`, then `npm run gen:api` in `web/`; CI fails on drift [verified: `ci.yml:238-240`, `docs/contracts/README.md`]. Add the two routes + `email_unavailable` to `docs/reference/public-api.md`; update `web-email-actions.md` ("who sends").

## Architecture
```
web ──POST /v1/auth/email/{verification|password-reset}──► api
        rate limit (Firestore) ─► AuthLinks.generate (Admin SDK) ─► rewrite to APP_BASE_URL/auth/action
        ─► templates ─► EmailSender (Resend | Fake | Unconfigured) ─► 202
user clicks link ─► web /auth/action?mode&oobCode (existing, applies code client-side)
```
```py
class EmailSender(Protocol):
    def send(self, to: str, subject: str, html: str, text: str) -> None: ...  # raises AdapterError
class AuthLinks(Protocol):
    def verification(self, uid: str) -> str: ...   # returns oobCode only
    def password_reset(self, email: str) -> str | None: ...  # None = unknown account
```

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| D1 | Link source | Admin SDK `generate_*_link`, keep only `oobCode`, rebuild URL | Parse and trust Firebase's returned host | Host comes from our config; no open-redirect or phishing via request or SDK output |
| D2 | Missing secret | Deploy OK; `RESEND_API_KEY` env wired only when `resend_secret_wired=true`; no key → `Unconfigured` → 503 generic | Always wire `secret_key_ref` | Cloud Run revision fails if the secret has no version; shell secrets exist before owner seeds them |
| D3 | Fallback to Firebase sender when unconfigured | None | Web falls back to client SDK | Two paths double the test matrix and send off-brand mail; owner step is one-off |
| D4 | Rate-limit store | Firestore transactional counters | In-memory per instance; Cloud Armor | Multi-instance Cloud Run; no new infra; matches existing repo pattern |
| D5 | Reset async send | `202` first, send in background | Sync send and surface failure | Sync timing/errors reveal account existence |
| D6 | Verify email address source | From uid via Admin SDK | From request body | Cannot be abused to mail arbitrary addresses |
| D7 | Resend HTTP client | `requests` (already a dep) | `resend` SDK, `httpx` | No new dependency for one call |
| D8 | Ports | `EmailSender`, `AuthLinks` in `adapters/` | Inline calls in route | Follows `Stt/Evaluation/Voice` seam; fakes for tests |

## Manual steps (owner-only, deferred)
1. Verify `onolys.com` in Resend (SPF/DKIM DNS).
2. Create a sending-only API key.
3. Store as Secret Manager `resend-api-key-staging` (seed script or console).
4. Set `resend_secret_wired=true` for staging and re-apply Terraform / redeploy.
5. Staging smoke: signup → email arrives from `no-reply@onolys.com`, link opens `/auth/action`, verifies.

## Risks
- `email_unavailable` for every user until steps 1-4 (staging only, accepted).
- Web deploy to prod before prod API/Resend is wired would break prod auth emails: gate the web change to staging until a prod rollout PRD ([DEFERRED]).
- Domain deliverability (spam folder) untestable until owner steps.
- Admin SDK adds a dependency and cold-start cost (init once, lazily).
- Shared-file conflicts: `logs.py` (SP02), `_deploy-cloudrun.yml`/`deploy-staging.yml` env_vars (SP01), `openapi.json` regeneration (SP03/SP04).

## Open Questions
- [OPEN] Minimal IAM role for api SA to call `generate_*_link` (try `roles/firebaseauth.admin`, narrow after smoke).
- [OPEN] Does `generate_*_link` need `ActionCodeSettings.url` on an authorized domain? Assume yes: pass `APP_BASE_URL` continue URL; confirm `onolys-app-staging.web.app` is authorized.
- [OPEN] Should the two routes be in the published `docs/contracts/public` or hidden (web-only)? Default: included.
- [RESOLVED: R6] Client IP source = first `X-Forwarded-For` hop (Cloud Run).
- [DEFERRED] Prod rollout, `resend-api-key-prod`, bounce/complaint webhooks, change-email senders.

## Acceptance Criteria
1. Fake adapter: verify endpoint records one email whose link host equals `APP_BASE_URL`, mode `verifyEmail`; reset records `resetPassword`.
2. Reset returns identical status/body for known, unknown and rate-limited emails; no email recorded for unknown.
3. `Host`/`Origin`/`X-Forwarded-Host` manipulation never changes the link host.
4. Unverified-token user can call verify; no-token → 401; API key → 403; verified user → 202, no send.
5. 2nd verify within 60 s → 429; resend failure → 503 with generic body.
6. No log line contains the email, link or `oobCode` (test with a capture handler).
7. API starts and serves with no `RESEND_API_KEY` (staging config); send returns 503 `email_unavailable`.
8. `openapi.json`, `docs/contracts/public`, `web/src/api/schema.d.ts` regenerate clean (CI drift checks pass).
9. Web: no remaining imports of `sendEmailVerification`/`sendPasswordResetEmail`; copy and 429/503 states covered by tests.
10. Terraform plan: secret shell + IAM + env vars only; prod unchanged.
