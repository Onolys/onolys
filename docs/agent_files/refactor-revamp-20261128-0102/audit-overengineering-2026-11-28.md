---
status: done
summary: Over-engineering audit against coding rules 1-17 (new rule 17 "Use the library; don't rebuild it"): 11 code findings from a read-only repo audit, plus PRD findings for 02-10; each assigned to an owner sub-project and applied to the PRDs.
date: 2026-11-28
---
# Over-engineering audit (2026-11-28)

Basis: `docs/rules/coding-rules.md` rules 1-17 (rule 17 is Block), `docs/rules/design-rules.md`, owner standing rules (no over-engineering; nothing custom if a library/vendor does it; vendor test hooks over custom fakes; remove all legacy; staging/eval data may be deleted; ignore rare races; no cross-repo copies or random deps). Applied to PRDs 02-10 and README the same day; marks are `[RESOLVED 2026-11-28: owner rule 17]` unless a real trade-off remains (`[OPEN]`, with a default).

## A. Code audit (read-only, current repo)

| # | Finding | Replace with | Owner | Conf. | Status in PRD |
|---|---|---|---|---|---|
| 1 | `api/src/onolys_api/config.py` (295) + `api/tests/test_config.py` (464): hand-rolled env parsing (`_int/_float/_bool`, ~45 `e.get`, per-field `ConfigError`); same in eval/backend `config.py` | pydantic-settings `BaseSettings` ([docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)); tests shrink to a few defaults/required cases | 06 (api), 10 (eval) | High | 06 R1/T-list; 10 P4 rule pass |
| 2 | ~6 hand-written fake LLM clients / fake `acompletion` shims: `engines/core/tests/test_llm*.py`, `test_retry.py`, `test_is_transient.py`, `engines/miti/tests` `FakeClient` (`test_run`, `test_code_pass`, `test_globals_pass`), `engines/oneshot` `FakeLLM` | the one engine stub seam (04 R9) and LiteLLM `mock_response` ([docs](https://docs.litellm.ai/docs/completion/mock_requests)) for `LiteLLMClient` payload tests | 04 | Med | 04 R9, T4/T5 |
| 3 | One-off review fuzz/property/mutation harnesses: `api/tests/test_fuzz_review.py` (326), `web/src/__fuzz_review__/` (414), `web/nightly/fast-check.ts`, `web/stryker.conf.json` + `@stryker-mutator/*` devDeps, `api/tests/test_schemathesis_smoke.py` (58), `hypothesis` dep | delete (rules 16, 17) | 06 (api), 07/08 (web), 02 (auth mutation entries) | Med | 06 T1, 07 R2/R3, 08 R2, 02 R9 |
| 4 | Docs-grep tests: `api/tests/test_logging_docs.py`, `test_engine_errors_doc.py`, `test_usage_limits_docs.py` | delete | 06 | High | 06 T1 |
| 5 | `api` `repo/firestore.py` custom txn retry rounds (`_retry_txn/_contended/_uid_lock/_is_exhausted`, `_TXN_ROUNDS=12` x `_TXN_ATTEMPTS=5`, sleep jitter) + per-uid in-process locks, duplicated in `email/rate.py` | vendor `client.transaction(max_attempts=)` / `@firestore.transactional`, and `google.api_core.retry.Retry(predicate=if_exception_type(Aborted))`; verify on the emulator first | 06 | Med | 06 R2 (`in_transaction`), T0, T3 |
| 6 | `engines/core` `retry.py` (48) + `test_retry.py` (215) + `litellm_client.py` custom 429/529 backoff and `retry-after` parsing | LiteLLM built-in retries (`num_retries`, `retry_policy`; [routing docs](https://docs.litellm.ai/docs/routing)) or tenacity; keep deadline-awareness and the output-schema retry (product logic); verify against 04 T0 goldens | 04 | Low-Med | 04 R9 + `[OPEN]` |
| 7 | Custom JSON logging: `engines/core` `json_logging.py` (178), `log_context.py` (57), api `logs.py` (95) | `google-cloud-logging` `StructuredLogHandler` ([docs](https://cloud.google.com/python/docs/reference/logging/latest/handlers-structured-log)) or `python-json-logger`; keep PHI allowlist (`safe_log.py`) as a `logging.Filter`; keep fields alerts rely on (`jsonPayload.status`, `request_id`) | 04 (consumed by 06) | Low-Med | 04 R8/D4 + `[OPEN]` |
| 8 | Tests of tooling/shims: `web/src/lint.test.ts`, `web/src/test/radixShims.test.tsx`, `web/src/hosting/{build,hosting}.test.ts` | delete | 07/08 | High | 07 R2, 08 R2 |
| 9 | eval `compare_cache.py` hand LRU+TTL | `cachetools.TTLCache` ([docs](https://cachetools.readthedocs.io/en/latest/), confirmed: LRU eviction + per-item TTL) | 10 | Med-High | 10 P4 rule pass |
| 10 | api `email/rate.py` `client_ip()` hop counting while `docker-entrypoint.sh` runs uvicorn `--proxy-headers --forwarded-allow-ips='*'` (trusts spoofable entries) | one standard approach for Cloud Run; must not weaken the limiter | 06 | Low | 06 `[OPEN]` with default |
| 11 | eval scheduler per-provider breaker/cooldown (~150 lines) | LiteLLM Router `allowed_fails` / `cooldown_time` ([routing docs](https://docs.litellm.ai/docs/routing), confirmed), only if 10 P4 runs eval on the engine in-process | 10 (P4) | Low | 10 P4 `[OPEN]` |

Kept, justified (no vendor emulator or provider field): `infra/scripts/identity-config.py`, Cloud Tasks `InProcessQueue` fake, GCS `LocalBlobStore` fake, vendored Redoc.

Evidence for #10 (web, 2026-11-28): Cloud Run/Google front ends append the address they saw, so the left entries are client-controlled and the right entries are Google's ([discussion](https://discuss.google.dev/t/cloud-run-which-client-ip-can-i-safely-use-for-rate-limiting/409611); the Google docs page itself did not load). Uvicorn with `--forwarded-allow-ips='*'` trusts every peer, so `request.client` becomes a spoofable entry. The uvicorn docs page was unreachable (no DNS), so that half is from memory of uvicorn's `ProxyHeadersMiddleware`; the 06 task re-checks it.

## B. PRD audit (Part 2)

| PRD | Finding (rule) | Change applied |
|---|---|---|
| README | Rule list says 1-16; no pointer to this audit | Rule 17 + audit link, owner-decision block "Rule 17 audit" |
| 00/01/spikes | Done; not edited. 01 left-overs handed on (below) | README hand-on list |
| 02 | Fuzz/mutation entries moved into the package (rule 16/17); `bundle.test.ts` rewritten and `hosting/privacy.test.ts` paths fixed = tests of tooling (#8) | Delete, not move; `resolve.dedupe` config instead of a bundle test; delete hosting tests |
| 03 | Ports shell tests of CI scripts (`test_deploy_eval.sh` already failing, `test_eval_image.sh`, `test_hosting_targets.sh`, `test_workflow_run_guard.py`, `verify_staging_release` test): tests of tooling | Copy the scripts, drop their tests; `actionlint` + the deploy smoke are the check |
| 04 | Load-time static analysis in the runner (reads/writes graph, disjoint branches, run-scope check) = custom machinery for author errors; custom AST boundary test; 6 equivalence fixtures + hand payload-patching; 4 client classes; custom retry/logging; custom `{{}}` renderer | Runner checks cut to unknown step + bad `with` keys; boundary via ruff `banned-api`; 3 fixtures; clients collapsed to `FixtureClient` + `StubClient`; LiteLLM retries + structured logging as `[OPEN]` verify tasks; Jinja2 renderer (see 05) |
| 05 | Own placeholder renderer + "unresolved placeholder" loader check; prompt-source test (fragment byte-identity, "no fragment sentence appears literally") = test of a rendering rule; hand-written `output_format` | Jinja2 with `StrictUndefined` (unresolved = render error), delete the prompt-source test, `output_format` from pydantic `model_json_schema()` |
| 06 | Custom txn retry + locks (#5); custom config parsing (#1); import-graph test for leaf modules and ownerless names; `api-flaky` quarantine lane (rare races ignored); "stub verifier" left in R7 helpers; schemathesis in D11; `client_ip` | Items applied; ruff `banned-api` replaces the import-graph test; `api-flaky` dropped; `[OPEN]` emulator share resolved; `[OPEN]` client IP |
| 07 | Pixel-for-pixel baseline + throwaway compare script for a pure move (custom visual machinery; Playwright `toHaveScreenshot` exists); fuzz/stryker/nightly paths repointed instead of deleted (#3); hosting tests moved (#8) | Baseline dropped (typecheck + test count + e2e smoke gate a move); delete #3/#8 files; `@smoke` tag stays (Playwright `--grep`) |
| 08 | `tests/hosting` asserts prod CSP header unchanged and `.env.stack` loopback-only (tests of config); reuses 07 baseline shots; `build/hosting` mock tests | Assertions deleted; owner glance only; csp project kept (browser reports real violations) |
| 09 | `terraform_data.state_identity` (guard for operator mix-up, a new prod state change) on top of `tf.sh` + `TF_DATA_DIR`; `check_config.sh`/image tests fine | `state_identity` dropped (`project` validation + `tf.sh` remain); rule 17 cited |
| 10 | Hand-rolled config (#1), LRU+TTL (#9), breaker (#11); `charts.yaml` manifest + unique-id/"web registry equals charts.yaml" tests duplicate the registry; allowed-modules guard test; hand golden capture | `charts.yaml` dropped (one web test loads shipped report YAML and checks `chart.use` ids; backend load check for metric ids); ruff `banned-api` for the `onolys_api` allow-list; snapshot library for characterization goldens |

## C. Hand-ons from 01 (done; leftovers, from `01-legacy-purge/code-2026-11-28-0538.md` and its review)

- `api/tests/test_engine_errors_doc.py` matches a docs heading: deleted now by audit #4 (06 T1).
- Eval guard scripts (`test_deploy_eval.sh`, `test_hosting_targets.sh`, `test_workflow_run_guard.py`), dead `vars.DEPLOYER_STAGING_SA` fallback in `_deploy-cloudrun.yml`, spec ids in `deploy-eval.yml:93`: 03 (do not port the shell tests, see above).
- Eval `presets`/`resolved_presets` + `preset:` handling in `eval/web/comboFields.ts`: 10 (remove if legacy).
- Prod Terraform state still holds `google_secret_manager_secret.provider[...]`; `google_billing_budget.monthly` absent: 09 (already in its Manual steps).
- Unset GH vars `GCP_PROJECT`, `GCP_REGION`, `PROD_LLM_*`: 09/owner.
- Stale docs refs (`infra-staging-first-apply.md`, `docs/reference/testing.md`, pre-release checklist): docs freeze, deferred.
- After merge: delete GH vars `STAGING_VITE_FIREBASE_{API_KEY,APP_ID,AUTH_DOMAIN,MESSAGING_SENDER_ID,STORAGE_BUCKET}`: owner or agent via `gh`.
- `test_miti_import_boundary.py` (api) and `test_transcript_imports.py` kept by 01: 04 replaces the boundary test with ruff `banned-api`.

## D. `[OPEN]` items added (all have a default)

1. 04: adopt LiteLLM retries instead of `retry.py` (backoff timing for 429/529 may change).
2. 04: structured logging via `StructuredLogHandler` (alert fields must survive).
3. 06: client IP on Cloud Run (entrypoint flags vs `client_ip()`).
4. 10: replace eval scheduler breaker with Router cooldowns (only if eval runs the engine in-process).
