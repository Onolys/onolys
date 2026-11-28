---
status: draft
summary: Onolys revamp — index of 11 sub-project PRDs plus phase-0 spikes
date: 2026-11-28
---
# refactor/revamp

Design stage. PRDs reviewed, OPENs resolved; next dev-critique then dev-tasks. Nothing implemented. Base: main. Scope: English transcripts only.

## Files

| File | What |
| --- | --- |
| [brainstorm.md](brainstorm.md) | Agreed rules (1-16) + changes; snapshot of the Claude doc, 2026-11-28 |
| [owner-follow-ups.md](owner-follow-ups.md) | Things only the owner can do (committed copy; the original is untracked in the primary checkout) |
| [00-rules-file/PRD.md](00-rules-file/PRD.md) | Rules 1-16 into `docs/rules/coding-rules.md` (copied per repo); `design-rules.md` moves beside it; `AGENTS.md` + one-line `CLAUDE.md` point at both; no new CI |
| [01-legacy-purge/PRD.md](01-legacy-purge/PRD.md) | Delete migration/guard tests, compat code, spec ids, dead staging fallbacks, ~20 CI-guard tests, eval pre-matrix readers; no Terraform/cloud change |
| [spikes/PRD.md](spikes/PRD.md) | Phase 0 (after 01, before 02): 5 spikes (Auth emulator under vitest; Admin SDK + emulator tokens; uv git-subdir deps; firebase-tools `--config`; api CI job merge); one combined report to owner, owner decides fallbacks |
| [02-ui-package/PRD.md](02-ui-package/PRD.md) | Rename `onolys-ui` to `onolys-common` (`@onolys/common` v0.4.0); shared sign-in, shell, components, helpers move in; rewire web + eval/web; auth fakes replaced by Auth emulator (spike first); drop all `@prod-*` aliases; `legacy.css`, `spans.ts` deleted |
| [03-eval-split/PRD.md](03-eval-split/PRD.md) | Move `eval/` (+ deploy workflow, Terraform root, CI) to new PUBLIC repo `Onolys/onolys-eval`, pinned to immutable tag `engine-v0`; same cloud project and state; eval Firestore rules deny-all |
| [04-engine-package/PRD.md](04-engine-package/PRD.md) | One `engine/` package (`onolys_engine`): YAML pipelines over step + scoring library, typed state, one public surface; STT/voice/rating/scenarios move to api; same outputs proven by goldens |
| [05-engine-behaviour/PRD.md](05-engine-behaviour/PRD.md) | In-order uncapped context, volley split after reflection, one instruction source, one-shot rebuilt (`oneshot-single`, `oneshot-split`); no numbered units now (quotes kept; units follow-up) |
| [06-api-by-feature/PRD.md](06-api-by-feature/PRD.md) | `api/` one folder per feature; one data layer replaces `repo/` + fake; fakes replaced by Firestore + Auth emulators and stubs; combined local mode; HTTP contract unchanged |
| [07-web-layout/PRD.md](07-web-layout/PRD.md) | `web/src` into `app/` + `features/`; all tests and Playwright in one `web/tests/`; `ROUTES` constant; `features/auth` split; moves only, no visual change |
| [08-web-real-stack/PRD.md](08-web-real-stack/PRD.md) | Delete web `mocks/` + MSW worker; local dev and e2e run real API stack (06 combined mode); unit tests stub only HTTP; emulator-backed `npm test`; e2e + CI re-platform |
| [09-infra-per-env/PRD.md](09-infra-per-env/PRD.md) | One Terraform root, folder per env (tfvars, backend, runtime YAML); `config/` + isolated-environment deleted; Firebase config in `firebase/`; infra tests 19 to 3; plan-proven `moved` blocks, agent plans and applies |
| [10-eval-libraries/PRD.md](10-eval-libraries/PRD.md) | In eval repo: metrics registry, chart registry, converter base class, report YAML; then own run path (engine pin `engine-v0` then `engine-v1`, own sessions, reuse api leaf modules by tag) |

## Build order

```
00 rules → 01 legacy-purge → spikes (phase 0) → 02 ui-package → 03 eval-split → 04 engine-package ─┬→ 05 engine-behaviour
                                                       │                                           └→ 06 api-by-feature ─┬→ 08 web-real-stack (needs 06 + 07)
                                                       └→ 07 web-layout ─────────────────────────────────────────────────┘ └→ 09 infra-per-env
03 → 10 eval-libraries (eval repo; its P4 engine-pin upgrade waits for 04/05/06)
```
- Spikes run once, after 01 and before 02, reported to the owner in one combined report; they gate 02, 03, 06, 08, 09, 10 (P4).

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
| Docs changes | None except the rules files; ADR fold-in and other docs clean-up out of scope |
| `docs/agent_files/` | Keep as is |
| Pipeline YAML | One file per evaluation; no base + overrides |
| Eval sign-in | Uses `@onolys/common` sign-in pieces (moved from `web/src/auth`), not own copy |
| Jev, per-volley/per-global calls, per-slot eval metrics | Deferred; separate PR later |

## Owner decisions (2026-11-28)

**General**
- Spikes (02 Auth emulator under vitest; 03 uv git-subdir deps; 06 O1 CI job merge; 06 O3 Admin SDK + emulator tokens; 08 O5; 09 O3 firebase-tools `--config`): now phase 0 in [spikes/PRD.md](spikes/PRD.md), run before 02, ONE combined report to owner, owner decides. No automatic fallback; fallbacks are options to present.
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
**01**: `dorny/paths-filter` approved. Delete eval pre-matrix readers. Edit the 2 README lines.
**02**: Auth-emulator spike first, report before choosing fallback. `legacy.css` removed entirely, unconditionally (plus landing import if any). `lib/spans.ts` deleted. `theme-init.js` shipped by package, apps copy into `public/`. onolys-common keeps own rules copy; design-rules gains "UI pieces come from `@onolys/common`". 02 owns the rename.
**03**: Own sessions moves to 10. Eval repo public. uv spike, report. Eval Firestore rules deny-all (Admin SDK only). Worker image = tag + eval's own `config/` overlay.
**04**: 03 lands first, creates `engine-v0`. Engine passes unknown preset keys through. Fixtures ship in wheel. `oneshot:miti` renamed `oneshot-single`; old runs dropped. Provenance hash change accepted. `oneshot-raw` dropped. Pipeline deviation (no `verify.map_units`; rules/caps in `protocol.yaml`) approved.
**05**: No numbered units now; units-vs-quotes is a follow-up (quotes kept; in-order uncapped context stays). No gating, baseline or measurement: comparison gate (O5) and live/eval measurement checks removed; batch size 25 unmeasured. Reflection split reads last 1 clinician utterance. One-shot honours `n_runs`, tips from the representative run.
**06**: O1 decide after test. Keep `[fail:*]` as `stub_hint` only when `ADAPTERS=stub`. O3 decide after spike. Delete `test_acceptance_checklist.py`. `FixtureClient` via public `make_client`. Rating schema built from `Engine.protocol()` at startup.
**07**: `ROUTES` holds ALL web URL paths. Split `features/auth` (`useApiClient` to `api/`, `createAuthService` to `app/`).
**08**: O1, O2, O4 default; O5 after 02 spike. e2e pauses status requests via `page.route`; no API stub change.
**09**: Keep `create-test-user.py`. `models.yaml` stays in `infra/`. `--config` spike, report. CHANGED: staging gets prod's password-policy/email-URL provisioner (live change; agent applies Terraform).
**10**: No fallback copies: 06 makes data/auth/tasks/transcription leaf modules, fix api rather than copy. Eval on `engine-v0`, then `engine-v1` for P4. Delete old eval run data. Worker = second Cloud Run service from the same eval image. Delete non-English converters. Keep DataTable/Disclosure/StatTile in eval. Eval config follows 04's format.

## Accepted cross-repo copies

- Eval `config/` (own copy of `models.yaml`, `staging/{routes,stt_providers}.yaml`; 09 moves the originals).
- Rules files (`docs/rules/*`), copied per repo (eval, `onolys-common`), synced by hand.
- 03 copies into the eval repo: `infra/modules/environment`, `release_target.py`, `check_config.sh`, `verify_staging_release.cjs`, `set_eval_origin.sh`, `test_hosting_targets.sh`, `_deploy-cloudrun.yml`, `firestore.indexes.json`, docs incl. `isolated-environments.md`.

## Owner-only follow-ups

See [owner-follow-ups.md](owner-follow-ups.md) (committed copy). Owner reviews the one combined phase-0 spike report and decides. Dev machine needs `firebase-tools` + Java (spikes, 06, 08).

## Next steps

1. Run `dev-critique` (on request), then `dev-tasks` per PRD in build order.
2. Run the phase-0 spikes (after 01, before 02); one combined report to owner.
