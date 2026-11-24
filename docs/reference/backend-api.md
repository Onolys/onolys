# Admin backend API

What the admin backend accepts, returns, and reads from the environment. Code: `admin/backend/src/onolys_admin_backend/app.py`, `admin/auth/src/onolys_admin_auth/`.

**Audience:** users.

The internal admin site (`admin.onolys.com`, also `onolys-admin-staging.web.app`) is a single environment, staging (owner decision 2026-11-21; no prod admin). It runs one Cloud Run service, `onolys-admin-backend-staging`, and is a sign-in shell: it has no engine and no user data. Why it is built this way: [ADR 0023](../decisions/0023-admin-deployment-and-auth.md). The public product API is documented in [public-api.md](public-api.md).

## Routes

| Method and path | Purpose |
|---|---|
| `GET /v1/me` | Returns `{"status": "ok"}` for a signed-in, allowed user. The shell calls it after sign-in. |

There is no other route, no OpenAPI page and no docs page.

## Auth

Every request except a CORS preflight (`OPTIONS`) must carry `Authorization: Bearer <Identity Platform ID token>` (`middleware.py`). The token is checked for an RS256 signature, `aud` equal to the project (`ADMIN_AUTH_PROJECT`), `iss` equal to `https://securetoken.google.com/<project>`, and expiry (`verifier.py`). Then `email_verified` must be true and the email must be in `ADMIN_ALLOWED_EMAILS` (case-insensitive). No second factor is required. Token and email are never logged.

| HTTP | `error.code` | When |
|---|---|---|
| 401 | `unauthenticated` | No bearer header, or the token is invalid or expired. Reply carries `WWW-Authenticate: Bearer`. |
| 403 | `email_unverified` | Valid token, but the email is missing or unverified. |
| 403 | `not_allowlisted` | Verified email is not on the allowlist. |
| 503 | `upstream_unavailable` | The token signing keys could not be fetched. |

Signing keys are cached for one hour. Refreshes (including unknown key IDs and failed fetches) share a 30-second cooldown. Expired keys are never used after a failed refresh; that returns 503. A newly rotated key may return 401 until the cooldown ends. Network calls have a five-second timeout and cache lock waits have a six-second limit. Verification runs outside the ASGI event loop. The eval backend shares this cache policy for its separate Google service-account verifier; its internal task identity mismatches retain the generic `forbidden` code.

These replies use a small body `{"error": {"code", "message"}}`.

## CORS

Handled before auth, so preflights need no token and 401/403 replies also carry CORS headers (`app.py`). Only the exact origins in `ADMIN_CORS_ORIGINS` are allowed (a wildcard or `null` stops startup). Methods: `GET`, `OPTIONS`. Allowed headers: `authorization`, `content-type`. Credentials are off. The browser calls the Cloud Run URL directly, so the site's CSP `connect-src` lists that origin (`frontend/firebase.json`, filled in by `scripts/ci/set_admin_origin.sh`).

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `ENV` | none (image sets `prod`) | `local` or `test` allows auth off. Any other value or unset counts as non-local. |
| `ADMIN_AUTH` | `on` (`off` when `ENV` is `local`/`test`) | `on` or `off`. `off` with a non-local `ENV` stops startup. |
| `ADMIN_AUTH_PROJECT` | `GCP_PROJECT` | Project whose ID tokens are accepted. Required with auth on. |
| `ADMIN_ALLOWED_EMAILS` | none | Comma list. Empty stops startup with auth on. Cloud Run reads it from Secret Manager `admin-allowed-emails-{env}` (version `latest`, read when an instance starts, so a change needs a new revision). |
| `ADMIN_CORS_ORIGINS` | empty (no origin allowed) | Comma list of exact origins. |
| `PORT` | `8080` | Listen port (image). |

The service is public at Cloud Run (`allUsers` invoker); access is enforced only by the app. Terraform: `infra/modules/environment/services.tf`. Deploy: `.github/workflows/deploy-admin.yml`. The Firebase Hosting rewrite limit (60 s) does not matter here: the site has no `/v1` rewrite. The frontend is built with `VITE_AUTH_REQUIRED=true`, `VITE_ADMIN_API_URL` (the Cloud Run origin) and the `VITE_FIREBASE_*` values ([frontend README](../../frontend/README.md)).
