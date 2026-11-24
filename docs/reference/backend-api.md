# Internal evaluation auth

**Audience:** users and contributors.

The former admin backend source and its deployment workflow are retired. Existing cloud services, Hosting sites and the `admin.onolys.com` Identity Platform auth domain are retained; this repository change does not alter them. The retained [frontend](../../frontend/README.md) is the legacy sign-in shell. [ADR 0023](../decisions/0023-admin-deployment-and-auth.md) describes the original deployment.

The shared package now lives in [`eval/auth`](../../eval/auth/pyproject.toml), with its existing Python import `onolys_admin_auth` and project name `onolys-admin-auth`. The [eval backend](../../eval/backend/pyproject.toml) still uses it for staging sign-in. Its CORS settings and Identity Platform domains remain unchanged. The product API is documented in [public-api.md](public-api.md).

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

## Configuration

The package reads `ENV`, `ADMIN_AUTH`, `ADMIN_AUTH_PROJECT` (falling back to `GCP_PROJECT`) and `ADMIN_ALLOWED_EMAILS`. Auth defaults to on outside local/test; disabling it outside local/test stops startup. With auth on, a project and a nonempty email allowlist are required. Cloud Run receives the allowlist through Secret Manager when an instance starts.

CORS belongs to the calling service. Eval deployment and Hosting origin substitution use `.github/workflows/deploy-eval.yml` and `scripts/ci/set_eval_origin.sh`.
