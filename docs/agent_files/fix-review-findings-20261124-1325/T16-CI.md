# T16 — CI tiers and deterministic route focus

PR classification now runs independently of the complete guard suite. Complete ordinary API unit/emulator suites and the combined 94% coverage threshold remain unchanged; the reducer uses the identical coverage 7.17.3 version from uv.lock without synchronizing the application environment. PR browser selection contains nine existing Chromium cases, including production CSP and native evidence-dialog focus. Runtime image checks, full Chromium and contention tests remain exact-main candidate checks. Contention failures now fail visibly rather than being swallowed. No deploy workflow or deployment pin changed.

Nightly reuses CI with every package selected, then adds isolated Python 3.13/3.14 emulator runners, Firefox/WebKit, a fixed-seed auth property campaign (5,000 examples, three-minute cap) and a narrow auth redirect mutation campaign (eight-minute cap). Existing pinned tools are reused. Browser-only compatibility adjustments avoid unsupported clipboard permission names and Firefox's unsupported mobile emulation flag while retaining viewport/touch coverage. Stryker's related-test discovery found no tests on this installed toolchain; disabling that optimization and explicitly selecting the redirect baseline produces actual tests and mutants.

The required aggregate rejects missing/failing/unexpectedly skipped jobs and requires every package flag on exact-main candidates. PR timing comes from GitHub's latest-attempt job list: initial queue time and skipped/queued jobs are excluded, subsequent runner gaps, setup, coverage tail and aggregate work through its timing request count. Ten seconds are reserved for completion. Missing timestamps, unknown job state, incomplete job pages, API/auth errors and budget overruns fail closed. A running workflow may take longer before the aggregate reports an overrun; this check is not a promise of runner availability. Historical hosted observations supplied by the orchestrator were 148s (all-package PR #56) and 90s (eval-only PR #57). There is **no new/cold hosted timing measurement for this branch**: no push, PR creation, dispatch or cloud mutation was requested or performed.

The old route test failed deterministically before modification: its Sample report footer link opens a new tab, so the memory router stays on /login. The blocking replacement uses the same-tab Sign up link and waits on observable focus effects without retries.

## Validation

- Before fix: `FLAKY=1 ./node_modules/.bin/vitest run src/routes/routes.flaky.test.tsx --maxWorkers=1` — 1 failed (including both old retries); expected /sample, got /login.
- `python3 scripts/ci/test_ci_gate.py` — 10 passed; selection, main completeness, missing/failed/skipped jobs, workflow aggregation, timing states/budget, reusable caller permissions.
- `bash scripts/ci/test_changes.sh` — 86 routing cases passed; `python3 scripts/ci/test_changes_deps.py` passed. `bash -n scripts/ci/changes.sh scripts/ci/test_changes.sh` passed.
- `/root/.local/bin/actionlint -color`, key guard, relative link check, `git diff --check` passed.
- `bash scripts/ci/test_deploy_eval.sh`, `bash scripts/ci/test_deploy_admin.sh`, `python3 scripts/ci/test_workflow_run_guard.py`, `python3 scripts/ci/test_workflow_checkout_before_auth.py` passed. `python3 scripts/ci/test_staging_ran_image.py` — 9 passed.
- In web/: `./node_modules/.bin/vitest run src/routes/routes.focus.test.tsx src/__fuzz_review__/auth.property.test.ts --maxWorkers=1` — 11 passed. `./node_modules/.bin/tsc --noEmit -p .` and ESLint of changed TS/CJS files passed.
- `NIGHTLY_PROPERTIES=1 ./web/node_modules/.bin/vitest run src/__fuzz_review__/auth.property.test.ts --root web --maxWorkers=1` — 10 passed; fast-check 4.10.3, seed 20261124, 5,000 examples.
- In web/: `CI=1 E2E_PORT=19733 E2E_CSP_PORT=19734 npm run e2e -- --config e2e_review/playwright.smoke.config.cjs --trace off` — 9 passed in 22.8s, including both server starts and production build.
- `NIGHTLY_MUTATION=1 timeout 180s ./node_modules/.bin/stryker run --mutate src/auth/next.ts --concurrency 1` — baseline 15 tests, 70 mutants, 61 killed / 5 survived / 4 uncovered / 0 errors or timeouts, 90s. This is an observed baseline, not a score target; report remains ignored under web/reports/mutation/.
- API collection: ordinary unit selection 1,915/2,336; emulator selection 365/2,336; contention selection 2/2,336. These are collection checks, not a new full coverage measurement.
- Local JVM emulator on 127.0.0.1:19735: `FIRESTORE_EMULATOR_HOST=127.0.0.1:19735 GOOGLE_CLOUD_PROJECT=demo-onolys /tmp/iaudit-review-venv/bin/python -m pytest api/tests/test_fuzz_review.py -m "flaky and not live" -q -p no:xdist` — 2 passed, 107 deselected in 1.90s; emulator terminated afterward.
- Ruff checks of both new Python scripts passed.

## Limits and follow-ups

Firefox/WebKit binaries and their system dependencies are absent locally, so those engine runs were collected (91 cases per full engine config) but not executed. No Docker image runs or Python-version matrix environments were created locally; nightly owns those bounded checks. The orchestrator owns final whole-branch verification. Owner-only follow-up: make the new required aggregate a protected check if desired; GitHub settings were not modified. Surviving/uncovered redirect mutants are recorded baseline opportunities, outside this CI task.
