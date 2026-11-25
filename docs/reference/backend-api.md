# Internal evaluation auth

**Audience:** users and contributors.

The eval backend ([`eval/backend`](../../eval/backend/pyproject.toml)) signs users in with the prod Identity Platform login and checks the verified email against an allowlist. It verifies tokens with the api's `IdTokenVerifier` (`onolys_api.auth.idtoken`). The product API is documented in [public-api.md](public-api.md).

## Auth

Every request except a CORS preflight (`OPTIONS`) must carry `Authorization: Bearer <Identity Platform ID token>`. The token is checked for an RS256 signature, `aud` equal to the project (`AUTH_PROJECT`, falling back to `GCP_PROJECT`), `iss` equal to `https://securetoken.google.com/<project>`, and expiry. Then `email_verified` must be true and the email must be in `EVAL_ALLOWED_EMAILS` (case-insensitive). No second factor is required. Token and email are never logged.

| HTTP | `error.code` | When |
|---|---|---|
| 401 | `unauthenticated` | No bearer header, or the token is invalid or expired. Reply carries `WWW-Authenticate: Bearer`. |
| 403 | `email_unverified` | Valid token, but the email is missing or unverified. |
| 403 | `not_allowlisted` | Verified email is not on the allowlist. |
| 503 | `upstream_unavailable` | The token signing keys could not be fetched. |

Signing keys are cached for one hour. Refreshes (including unknown key IDs and failed fetches) share a 30-second cooldown. Expired keys are never used after a failed refresh; that returns 503. A newly rotated key may return 401 until the cooldown ends. Network calls have a five-second timeout and cache lock waits have a six-second limit. Verification runs outside the ASGI event loop. The eval backend shares this cache policy for its separate Google service-account verifier; its internal task identity mismatches retain the generic `forbidden` code.

These replies use a small body `{"error": {"code", "message"}}`.

## Configuration

The service reads `ENV`, `AUTH_PROJECT` (falling back to `GCP_PROJECT`), `CORS_ORIGINS` and `EVAL_ALLOWED_EMAILS`. `AUTH_MODE` must be `idp` in every environment. A project and a nonempty email allowlist are required, otherwise startup fails. Cloud Run receives the allowlist through Secret Manager (`eval-allowed-emails-{env}`) when an instance starts. The pre-R14 `EVAL_AUTH*` and `EVAL_CORS_ORIGINS` settings are refused at startup.

CORS belongs to the calling service. Eval deployment and Hosting origin substitution use `.github/workflows/deploy-eval.yml` and `scripts/ci/set_eval_origin.sh`.
