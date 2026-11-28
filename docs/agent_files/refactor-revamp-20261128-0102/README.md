---
status: draft
summary: Onolys revamp — index of 11 sub-project PRDs plus phase-0 spikes
date: 2026-11-28
---
# refactor/revamp

Design stage. PRDs reviewed, over-engineering audit applied (the 4 former open items were answered by the owner 2026-11-28, see audit file); next dev-critique then dev-tasks. Nothing implemented. Base: main. Scope: English transcripts only.

## Files

| File | What |
| --- | --- |
| [audit-overengineering-2026-11-28.md](audit-overengineering-2026-11-28.md) | Rule 17 audit: 11 code findings + per-PRD findings, owners, owner-resolved former-open list; applied to PRDs 02-10 |
| [brainstorm.md](brainstorm.md) | Agreed rules (1-16) + changes; snapshot of the Claude doc, 2026-11-28 |
| [owner-follow-ups.md](owner-follow-ups.md) | Things only the owner can do (committed copy; the original is untracked in the primary checkout) |
| [00-rules-file/PRD.md](00-rules-file/PRD.md) | Rules 1-16 into `docs/rules/coding-rules.md` (copied per repo); `design-rules.md` moves beside it; `AGENTS.md` + one-line `CLAUDE.md` point at both; no new CI |
| [01-legacy-purge/PRD.md](01-legacy-purge/PRD.md) | Delete migration/guard tests, compat code, spec ids, dead staging fallbacks, ~20 CI-guard tests, eval pre-matrix readers; no Terraform/cloud change |
| [spikes/PRD.md](spikes/PRD.md) | Phase 0 (after 01, before 02): 5 spikes (Auth emulator under vitest; Admin SDK + emulator tokens; uv git-subdir deps; firebase-tools `--config`; api CI job merge); one combined report (done 2026-11-28; decisions D-A..D-E below) |
| [02-ui-package/PRD.md](02-ui-package/PRD.md) | Rename `onolys-ui` to `onolys-common` (`@onolys/common` v0.4.0); shared sign-in, shell, components, helpers move in; rewire web + eval/web; auth fakes deleted, Auth emulator (spike 1 PASS); drop all `@prod-*` aliases; `legacy.css`, `spans.ts` deleted |
| [03-eval-split/PRD.md](03-eval-split/PRD.md) | Move `eval/` (+ deploy workflow, Terraform root, CI) to new PUBLIC repo `Onolys/onolys-eval`, pinned to immutable tag `engine-v0`; same cloud project and state; eval Firestore rules deny-all |
| [04-engine-package/PRD.md](04-engine-package/PRD.md) | One `engine/` package (`onolys_engine`): YAML pipelines over step + scoring library, typed state, one public surface; STT/voice/rating/scenarios move to api; same outputs proven by goldens |
| [05-engine-behaviour/PRD.md](05-engine-behaviour/PRD.md) | In-order uncapped context, volley split after reflection, one instruction source, one-shot rebuilt (`oneshot-single`, `oneshot-split`); no numbered units now (quotes kept; units follow-up) |
| [06-api-by-feature/PRD.md](06-api-by-feature/PRD.md) | `api/` one folder per feature; one data layer replaces `repo/` + fake (`query_unowned` is the one cross-user read, scan merged in); fakes replaced by Firestore + Auth emulators and stubs; combined local mode; HTTP contract unchanged |
| [07-web-layout/PRD.md](07-web-layout/PRD.md) | `web/src` into `app/` + `features/`; all tests and Playwright in one `web/tests/`; `ROUTES` constant; `features/auth` split; moves only, no visual change |
| [08-web-real-stack/PRD.md](08-web-real-stack/PRD.md) | Delete web `mocks/` + MSW worker; local dev and e2e run real API stack (06 combined mode); unit tests stub only HTTP; emulator-backed `npm test`; e2e + CI re-platform |
| [09-infra-per-env/PRD.md](09-infra-per-env/PRD.md) | One Terraform root, folder per env (tfvars, backend, runtime YAML); `config/` + isolated-environment deleted; Firebase config in `firebase/`; infra tests 15 to 3; plan-proven `moved` blocks, agent plans and applies |
| [10-eval-libraries/PRD.md](10-eval-libraries/PRD.md) | In eval repo: metrics registry, chart registry, converter base class, report YAML; then own run path (engine pin `engine-v0` then `engine-v1`, own sessions, reuse api leaf modules by tag) |

## Build order

```
00 rules → 01 legacy-purge → spikes (phase 0) → 02 ui-package → 03 eval-split → 04 engine-package ─┬→ 05 engine-behaviour
                                                       │                                           └→ 06 api-by-feature ─┬→ 08 web-real-stack (needs 06 + 07)
                                                       └→ 07 web-layout ─────────────────────────────────────────────────┘ └→ 09 infra-per-env
03 → 10 eval-libraries (eval repo; its P4 engine-pin upgrade waits for 04/05/06)
```
- Spikes ran (2026-11-28; `spikes/spike-report-2026-11-28.md`); owner decisions D-A..D-E apply. Gates cleared; open re-checks: spike 3 at `engine-v0` (03) and `engine-v1` (06 T10).
- Cross-PRD ordering from D-A/D-B: 02 adds the Auth emulator block; 06 CI (`api-emulator`) and 08 (`npm test`, e2e) need it; 06 replaces the custom verifiers (eval backend frozen at `engine-v0` until 10); 09 replaces staging's named DB by `(default)` after 06 drops `FIRESTORE_DATABASE`; eval's DB switch is in the eval repo (10).

- Every PRD cites rule 17 where it lists rules; task specs say "follow `docs/rules/coding-rules.md`".
- 03 must land before 04: 04 deletes the old engine packages; eval must already be out (04 O1).
- 07 needs only 02 (no dependency on 06); 08 needs 06 (combined local mode) and 07.
- 09 assumes order 01 → 03 → 04 → 06 → 09. 09 only moves `routes.yaml`; 04 owns its content.

## Locked decisions (brainstorm)

| Topic | Decision |
| --- | --- |
| Scope | English only for now |
| Volley building | Keep as is |
| Context | In order, both speakers, 4–8 turns, no word cap |
| Utterance location | Quotes kept; numbered units moved to a follow-up (2026-11-28) |
| One-shot | Same input and output shape; we count; tips in a third call for the split variant |
| Prompts | One source for all evaluation types |
| Truncation in one call | Fail, no halving |
| Pipelines | Library of steps + YAML |
| Folders | One folder per evaluation type; protocols separate |
| Eval reports | Library of metrics + charts + YAML (agreed in principle) |
| Report files | Collapse the 7 report files |
| STT, voice, rating, scenarios | Move out of the engine |
| Docs | Two earlier docs merged into brainstorm (done) |
| Eval | Split into own repo; staging stays |
| Rules file | Coding rules in `docs/rules/coding-rules.md`; design rules separate doc in same folder |
| Test stubs | Firestore emulator (not in-memory client) |
| Constants | One `constants.py` per package (engine, api, eval) (default) |
| Voice | `voice/` stays in `api` package, run as its `voice` mode (default) |
| Docs changes | None except the rules files; ADR fold-in and other docs clean-up out of scope (06 R10 asks for a narrow exception to delete limiter text: see the 06 PRD [OPEN]) |
| `docs/agent_files/` | Keep as is |
| Pipeline YAML | One file per evaluation; no base + overrides |
| Eval sign-in | Uses `@onolys/common` sign-in pieces (moved from `web/src/auth`), not own copy |
| Jev, per-volley/per-global calls, per-slot eval metrics | Deferred; separate PR later |

## Owner decisions (2026-11-28)

**General**
- Spikes ran in phase 0 ([spikes/PRD.md](spikes/PRD.md), report `spikes/spike-report-2026-11-28.md`). Decisions D-A..D-E below.
- [RESOLVED 2026-11-28] **D-A Auth (spike 2):** official Google tools, nothing custom. Replace custom `IdTokenVerifier` (`auth/idtoken.py`) with `firebase_admin.auth.verify_id_token`; custom `OidcVerifier` (Cloud Tasks OIDC) with `google.oauth2.id_token.verify_oauth2_token`; delete the custom cert cache; delete fake auth (`AUTH_MODE=fake`, `Bearer test:<uid>`, web `fakeService.ts`, `VITE_AUTH_MODE=fake`). Tests and local dev set `FIREBASE_AUTH_EMULATOR_HOST` and use the Auth emulator; prod never sets it; NO startup guard or extra branch (over-engineering). Web test helper: `connectAuthEmulator(getAuth(initializeApp(cfg)), "http://127.0.0.1:9099")`. `email_verified`: one claim check on the decoded token if required. Eval backend reuses the same Admin call (10). Owners: 02, 06, 08, 10.
- [RESOLVED 2026-11-28] **D-B Firestore (spike 4):** each env has its own GCP project (prod `onolys`/`(default)`, staging `onolys-staging`/`staging`, eval `onolys-eval`/`eval`; names are leftovers). Every env uses the `(default)` database of its own project. `firebase.json`: ONE firestore entry (object form: rules + indexes); deploy picks env with `--project`; emulator auto-loads rules; rules tests still load rules explicitly via `@firebase/rules-unit-testing`. Remove `FIRESTORE_DATABASE`/`firestore_database` from api (06) and eval (10) config. Create `(default)` in staging via Terraform (09) and eval (10, eval repo); delete the named databases. Owner addition: any existing staging/eval records may be deleted; no data migration, export or backup. Owners: 06, 09, 10 (03 notes).
- [RESOLVED 2026-11-28] **D-C CI (spike 5):** keep `api-unit` and `api-emulator` as two jobs (06).
- [RESOLVED 2026-11-28] **D-D Spike 3 PASS:** uv git-subdirectory deps work; re-check once `engine-v0` exists (03) and `engine-v1` (06 T10); wheels fallback not needed (03, 10).
- [RESOLVED 2026-11-28] **D-E Spike 1 PASS:** Auth emulator works under vitest+jsdom; fallback options (`signedInService` stub, keep fake) removed (02, 08).
- Coding rule 17 "Use the library; don't rebuild it" (Block) is added to `docs/rules/coding-rules.md` in parallel; D-A is its first application.
- [RESOLVED 2026-11-28: owner rule 17] **Over-engineering audit** ([audit file](audit-overengineering-2026-11-28.md)) applied: pydantic-settings for api and eval config (06, 10); vendor Firestore transaction retry, no custom rounds/locks (06); LiteLLM `mock_response` and one stub seam instead of ~6 fake LLM clients (04); Jinja2 prompt templating, no prompt-source test (04, 05); ruff `banned-api` instead of custom AST/import-graph boundary tests (04, 06, 10); one-off fuzz/mutation/schemathesis harnesses, docs-grep tests and tests of tooling deleted (02, 03, 06, 07, 08); `cachetools.TTLCache` (10); runner load checks cut to unknown step + bad `with` keys, equivalence fixtures cut to 3 (04); no pixel baseline for 07's pure move; `api-flaky` lane, `state_identity` resource and `charts.yaml` manifest dropped (06, 09, 10). Owner decisions 2026-11-28 on the four former open items: [RESOLVED 2026-11-28: owner] 04 LiteLLM built-in retries replace `retry.py` and the custom 429/529 loop; [RESOLVED 2026-11-28: owner] 04 `StructuredLogHandler` + PHI `logging.Filter`, alert fields unchanged; [RESOLVED 2026-11-28: owner] email rate limit removed entirely (06 R10 api; 02 drops the `email/rate-limited` code while moving auth into `@onolys/common`, 08 only web-side remnants; 09 R6c; proxy-headers flags dropped if unused); [RESOLVED 2026-11-28: owner] 10 eval goes through LiteLLM Router, custom breaker deleted. 06's emulator-share question is RESOLVED (two jobs; T0 re-measures).
- No cross-repo copies/random deps, except those listed under "Accepted cross-repo copies" below.
- Agents run Terraform plan and apply and other cloud actions (owner granted this); only steps needing credentials the agent lacks stay with the owner.
- Pin tag `engine-v0` (not `eval-base-v0`), created by 03 (snapshot still has api + engine packages + config). Second tag `engine-v1` after 04-06 merge, for 10 P4.
- New repo `Onolys/onolys-eval` is PUBLIC.
- All old eval runs/data dropped; no mapping/migration of ids or runs.
- English only: delete `midas-es`, `phac-fr` and all non-English converters; keep `phac-en` (strip non-English parts of `phac.py`).
- Rename `onolys-ui` to `onolys-common`, `@onolys/ui` to `@onolys/common`, inside 02 (incl. landing imports). Agent does the repo rename (`gh repo rename`).
- Terraform apply for 09 is done by the agent, not the owner.
- STT/voice/rating/scenarios move into api as-is in 04, consolidated in 06: accepted.

**00 rules**: rule 2 (~300 lines) guidance only, not a CI gate. Rule 7 rewritten: class for major concepts even with one variant, plain/static functions otherwise, no over-engineering, max one inheritance level. Engine shared via git tag, no registry. Rules copied into each repo, synced by hand. TS `constants.ts` per app/package adopted.
**01** (done): leftovers handed on, see the audit file section C. `dorny/paths-filter` approved. Delete eval pre-matrix readers. Edit the 2 README lines.
**02**: Auth-emulator spike 1 PASS (D-E); fakes deleted. `legacy.css` removed entirely, unconditionally (plus landing import if any). `lib/spans.ts` deleted. `theme-init.js` shipped by package, apps copy into `public/`. onolys-common keeps own rules copy; design-rules gains "UI pieces come from `@onolys/common`". 02 owns the rename.
**03**: Own sessions moves to 10. Eval repo public. uv spike 3 PASS (D-D). Eval Firestore rules deny-all (Admin SDK only). Worker image = tag + eval's own `config/` overlay.
**04**: 03 lands first, creates `engine-v0`. Engine passes unknown preset keys through. Fixtures ship in wheel. `oneshot:miti` renamed `oneshot-single`; old runs dropped. Provenance hash change accepted. `oneshot-raw` dropped. Pipeline deviation (no `verify.map_units`; rules/caps in `protocol.yaml`) approved.
**05**: No numbered units now; units-vs-quotes is a follow-up (quotes kept; in-order uncapped context stays). No gating, baseline or measurement: comparison gate (O5) and live/eval measurement checks removed; batch size 25 unmeasured. Reflection split reads last 1 clinician utterance. One-shot honours `n_runs`, tips from the representative run.
**06**: O1 keep two jobs (D-C). Keep `[fail:*]` as `stub_hint` only when `ADAPTERS=stub`. O3 Admin `verify_id_token` (D-A); `FIRESTORE_DATABASE` removed (D-B). Delete `test_acceptance_checklist.py`. `FixtureClient` via public `make_client`. Rating schema built from `Engine.protocol()` at startup (landed by 04 PRD T4; 06 T8 only moves the code).
**07**: `ROUTES` holds ALL web URL paths. Split `features/auth` (`useApiClient` to `api/`, `createAuthService` to `app/`).
**08**: O1, O2, O4 default; O5 spike 1 PASS (D-E). e2e pauses status requests via `page.route`; no API stub change.
**09**: Keep `create-test-user.py`. `models.yaml` stays in `infra/`. `--config` spike 4 PARTIAL; `(default)` DB per env (D-B). CHANGED: staging gets prod's password-policy/email-URL provisioner (live change; agent applies Terraform).
**10**: No fallback copies: 06 makes data/auth/tasks/transcription leaf modules, fix api rather than copy. Eval on `engine-v0`, then `engine-v1` for P4. Delete old eval run data. Worker = second Cloud Run service from the same eval image. Delete non-English converters. Keep DataTable/Disclosure/StatTile in eval. Eval config follows 04's format.

## Accepted cross-repo copies

- Eval `config/` (own copy of `models.yaml`, `staging/{routes,stt_providers}.yaml`; 09 moves the originals).
- Rules files (`docs/rules/*`), copied per repo (eval, `onolys-common`), synced by hand.
- 03 copies into the eval repo (exactly this list; tests of CI scripts such as `test_hosting_targets.sh` are NOT copied):
  - Terraform: `infra/isolated-environment/` root (with `tests/` and eval examples), `infra/modules/environment/`, `infra/scripts/{create-test-user,seed-secrets,identity-config}.py` and their tests (verbatim; `identity-config.py` unedited).
  - CI/deploy: `release_target.py` (eval role only), `check_config.sh`, `verify_staging_release.cjs`, `set_eval_origin.sh`, `_deploy-cloudrun.yml` (trimmed to eval).
  - Firebase: `firestore.indexes.json` snapshot; eval's own root `firebase.json` (Hosting `eval-staging`, named `eval` DB) whose Auth emulator block (port 9099) mirrors the one 02 adds to `api/firebase.json`.
  - Docs: `eval-site.md`, `eval-datasets.md`, eval parts of `isolated-environments.md`.

## Cross-PRD ownership (consistency pass 2026-11-28)

- **Firebase config path:** until 09 Task 1, the emulator config is `api/firebase.json` (02 T7 adds the Auth block; 02/06/08 CI, web `npm test` and 06's `dev.sh` `FIREBASE_CONFIG` default use it). 09 Task 1 moves it to `firebase/firebase.json` and repoints every consumer. The eval repo has its own root `firebase.json` with the Auth block (03) and never references this repo's.
- **Web deletions 02 vs 07:** 02 deletes `hosting/privacy.test.ts`, `lint.test.ts`, `test/radixShims.test.tsx`, `stryker.conf.json`, `@stryker-mutator/*` devDeps, `__fuzz_review__/auth.property.test.ts`, the `NIGHTLY_MUTATION` include and the nightly mutation step. 07 deletes the rest: `hosting/{build,hosting}.test.ts`, remaining `__fuzz_review__/`, `nightly/fast-check.ts`, `NIGHTLY_PROPERTIES`/flaky globs, the nightly fuzz step.
- **Logging:** 04 owns `api/.../logs.py` (`StructuredLogHandler` + PHI `logging.Filter`); 06 does not redo it.
- **Rating schema:** 04 PRD T4 (Task 5) deletes `rating.schema.json` and builds the schema from `Engine.protocol()` at startup in the api rating code; 06 T8 only moves that code into `rating/validate.py`.
- **LLM test seam:** engine `FixtureClient` (via public `make_client`) for all app-level tests (engine, api, eval; also api `ADAPTERS=stub`); LiteLLM `mock_response` only for `LiteLLMClient` tests. No `acompletion` patching after 04's old-code baseline (04 PRD T0) is retired.
- **Ruff `banned-api` chain:** 04 PRD T2 (Task 3) creates the config (bans `onolys_engine.<submodule>`); 06 T10 adds the api leaf rules and ownerless-name bans before tag `engine-v1`; 10 T11 checks they exist in `engine-v1` and adds eval's own allow-list.
- **Eval DB:** 03 copies eval Terraform/`firebase.json` verbatim (named `eval` DB, no `(default)` switch); 10 (Task 16) does the switch.
- **CI job/gate names:** 04 replaces `engine-core`/`oneshot`/`miti` by one `engine` job, including the `required` job `needs:` and `scripts/ci/required_gate.py` `JOB_FLAGS`; 06 drops `api-flaky` the same way.

## Owner-only follow-ups

See [owner-follow-ups.md](owner-follow-ups.md) (committed copy). Spike report reviewed; decisions recorded above. Dev machine needs `firebase-tools` + Java (spikes, 06, 08).

## Next steps

1. Run `dev-critique` (on request), then `dev-tasks` per PRD in build order.
2. Phase-0 spikes done (2026-11-28); regenerate TASKS.md for 02-10 (the audit changed all of them; 05 and 07 lightly).
