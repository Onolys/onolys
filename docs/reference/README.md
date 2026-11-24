# Reference

What exactly is supported? Precise, lookup-oriented facts.

**Audience:** users.

- [public-api.md](public-api.md): the public `/v1` API (OpenAPI, `/v1/docs`, auth, idempotency, errors).
- [backend-api.md](backend-api.md): the admin shell backend (`GET /v1/me`, auth, CORS, environment).
- [configuration.md](configuration.md): environment variables for the api and the MITI engine.
- [warnings.md](warnings.md): when the engine emits each warning code.
- [testing.md](testing.md): test markers (`unit`/`integration`/`live`), fixtures, local commands, emulator, coverage, adding a package to CI.
- [staging-e2e.md](staging-e2e.md): measured staging end-to-end results.
- [web-email-actions.md](web-email-actions.md): in-app `/auth/action` handler for verify-email and reset-password links, and why.
- [logging.md](logging.md): finding a session's logs (Reference = session id, Logs Explorer link), log fields, `error_code` table, PHI rules.
- [infra.md](infra.md): GCP resources, env vars, Terraform outputs, DNS records, GitHub settings, provider how-to, failure runbook, rollback.

- [eval-site.md](eval-site.md): staging evaluation usage, authenticated API, storage, costs and method limits.
