# Pre-release checklist

**Audience:** contributors.

1. `uv run --package onolys-miti pytest engines/miti -q` and `ruff check engines/miti` pass; the api, web and admin suites pass in CI.
2. One live run with the owner's key: `uv run --package onolys-miti python -m onolys_miti.check --preset <p>` passes its thresholds (`fixtures/thresholds.yaml`). Note the estimated cost.
3. Refresh golden recordings if prompts changed (`MITI_LLM_RECORD=1` on a live run), then check the offline replay passes.
4. `api/openapi.json` and `docs/contracts/public/` are regenerated and unchanged (`python -m onolys_api.openapi`, `python -m onolys_api.contracts --check`).
5. Sample the logs from a run: ids, counts and durations only, no transcript text ([logging-and-phi.md](../implementation/logging-and-phi.md)).
6. `CORS_ORIGINS` (api) and `ADMIN_CORS_ORIGINS` (admin) hold the deployed origins.
7. Docs: `python3 scripts/ci/check_links.py` passes.
