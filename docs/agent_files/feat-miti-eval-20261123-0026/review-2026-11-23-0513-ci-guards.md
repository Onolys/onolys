---
status: done
summary: PASS — CI-guard addendum; route isolation and exact approved import paths
date: 2026-11-23
---
# Review — 2026-11-23 05:13 UTC — CI-guard addendum

Diff: `fbf150f..046f84f`   Personas: Bug Hunter, Security, Architect

## Verdict: PASS

All three independent reviewers PASS. Changes are test-only; runtime and deployment are unchanged.

## Changes and guard strength

- `test_isolation.py` includes new PUT transcript route in the 18-route OpenAPI/privacy matrix for Bearer and API-key authentication. Actual cross-user 404 and unchanged Alice-data checks now run for this route; the guard is extended rather than bypassed.
- `test_no_old_imports.py` limits direct root-package `MitiEngine` import exceptions to two exact relative paths: `src/onolys_api/engines.py` and `src/onolys_api/adapters/validated.py`. The latter is the approved MITI-only fake/legacy public-schema bridge. A broad basename exception is removed; engine-specific submodule, old-package and shared-core boundary restrictions remain.

## Reproduction / validation evidence

PR CI [45115960101](https://github.com/Onolys/onolys/actions/runs/45115960101): API unit 2 failed, 1,305 passed, 5 skipped. Every other completed job passed, including preview; API coverage failed as a unit-job dependency cascade.

The two exact CI assertions failed before correction; then seven affected tests passed and ruff passed. Evidence verified by orchestrator; no tests ran during this bookkeeping stage. No assertions weakened, no application files changed.

## Next step

Push reviewed fix `046f84f` and this artifact together once. Third CI round is pending; ship agent monitors PR53 and owns its body. No additional deployment is needed for these test guards; reviewed runtime08faaf5 and its119-hash proof remain unchanged. Existing Gemini billing, DNS, workflow registration and actual tab-close proof qualifications remain.
