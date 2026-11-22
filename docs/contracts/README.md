# Contracts

Machine-readable schemas for the public `/v1` API live in [public/](public/). Nothing else is kept here.

- The api generates them from its request and response models: `python -m onolys_api.contracts` (`--check` verifies them). The error schema, `public-error-response.schema.json`, is hand-written. CI fails if `api/openapi.json` or `public/` drift from the code.
- The web app generates its client types from `api/openapi.json` (`npm run gen:api` in `web/`, output `web/src/api/schema.d.ts`), and the report types from the MITI report schema.
- The MITI report schema ships with the engine: `engines/miti/src/onolys_miti/data/report.schema.json` ([engine README](../../engines/miti/README.md)).

Rules and behavior (auth, errors, idempotency): [reference/public-api.md](../reference/public-api.md). Why: [ADR 0020](../decisions/0020-public-api-contract.md).
