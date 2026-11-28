---
status: draft
summary: Onolys revamp — index of 10 sub-project PRDs
date: 2026-11-28
---
# refactor/revamp

Design stage. 10 PRDs drafted, awaiting owner review; then `dev-tasks`. Nothing implemented. Base: main. Scope: English transcripts only.

## Files

| File | What |
| --- | --- |
| [brainstorm.md](brainstorm.md) | Agreed rules (1-16) + changes; snapshot of the Claude doc, 2026-11-28 |
| [00-rules-file/PRD.md](00-rules-file/PRD.md) | Rules 1-16 into `docs/rules/coding-rules.md`; `design-rules.md` moves beside it; `AGENTS.md` + one-line `CLAUDE.md` point at both; no new CI |
| [01-legacy-purge/PRD.md](01-legacy-purge/PRD.md) | Delete migration/guard tests, compat code, spec ids, dead staging fallbacks, ~20 CI-guard tests; no Terraform/cloud change |
| [02-ui-package/PRD.md](02-ui-package/PRD.md) | Shared sign-in, shell, components, helpers into `@onolys/ui` v0.4.0; rewire web + eval/web; auth fakes replaced by Auth emulator; drop all `@prod-*` aliases |
| [03-eval-split/PRD.md](03-eval-split/PRD.md) | Move `eval/` (+ deploy workflow, Terraform root, CI) to new repo `Onolys/onolys-eval`, pinned to immutable snapshot tag; same cloud project and state |
| [04-engine-package/PRD.md](04-engine-package/PRD.md) | One `engine/` package (`onolys_engine`): YAML pipelines over step + scoring library, typed state, one public surface; STT/voice/rating/scenarios move to api; same outputs proven by goldens |
| [05-engine-behaviour/PRD.md](05-engine-behaviour/PRD.md) | In-order uncapped context, numbered clinician units, volley split after reflection, one instruction source, one-shot rebuilt (`oneshot-single`, `oneshot-split`) |
| [06-api-by-feature/PRD.md](06-api-by-feature/PRD.md) | `api/` one folder per feature; one data layer replaces `repo/` + fake; fakes replaced by Firestore + Auth emulators and stubs; combined local mode; HTTP contract unchanged |
| [07-web-layout/PRD.md](07-web-layout/PRD.md) | `web/src` into `app/` + `features/`; all tests in one `web/tests/`; delete `mocks/`; local dev and e2e run real API stack; no visual change |
| [08-infra-per-env/PRD.md](08-infra-per-env/PRD.md) | One Terraform root, folder per env (tfvars, backend, runtime YAML); `config/` + isolated-environment deleted; Firebase config in `firebase/`; infra tests 19 to 3; plan-proven `moved` blocks, owner applies |
| [09-eval-libraries/PRD.md](09-eval-libraries/PRD.md) | In eval repo: metrics registry, chart registry, converter base class, report YAML; then own run path (engine pin, own sessions, reuse api features by tag) |

## Build order

```
00 rules → 01 legacy-purge → 02 ui-package → 03 eval-split → 04 engine-package ─┬→ 05 engine-behaviour
                                                                                 └→ 06 api-by-feature ─┬→ 07 web-layout
                                                                                                       └→ 08 infra-per-env
03 → 09 eval-libraries (eval repo; its P4 engine-pin upgrade waits for 04/05/06)
```

- 03 must land before 04: 04 deletes the old engine packages; eval must already be out (04 O1).
- 08 assumes order 01 → 03 → 04 → 06 → 08. 08 only moves `routes.yaml`; 04 owns its content.

## Locked decisions (brainstorm)

| Topic | Decision |
| --- | --- |
| Scope | English only for now |
| Volley building | Keep as is |
| Context | In order, both speakers, 4–8 turns, no word cap |
| Utterance location | Numbered units; quotes as fallback |
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
| Eval sign-in | Uses `@onolys/ui` sign-in pieces (moved from `web/src/auth`), not own copy |
| Jev, per-volley/per-global calls, per-slot eval metrics | Deferred; separate PR later |

Open measurement task: run `prepare.py` on real eval sessions for true volleys-per-session count.

## Cross-cutting conflicts and decisions for the owner

Each has a recommended default.

a. **Eval pin tag name.** 03 says `eval-base-v0` (snapshot of api + 3 engine packages; eval/backend imports `onolys_api` in 41 lines and the eval worker is the api image in `EVAL_MODE`). 04 and 05 say `engine-v0`; 09 O2 flags it. Default: `eval-base-v0` per 03; update 04/05 references at dev-tasks time. (09 O2 also proposes a later `eval-base-v1` cut after 04-06 for P4.)

b. **Eval "own sessions".** Brainstorm locks it in the split; 03 O1 moves it to 09; 09 puts it in P4 (with engine pin upgrade, `eval_sessions`/`eval_cells` collections, `/tasks/cell` handler). Default: accept 09's placement.

c. **Repo visibility.** `Onolys/onolys` is PUBLIC (verified by 03 via `gh`), not private as brainstorm said, so git-tag deps need no deploy key. New eval repo proposed private (03 O2). Default: private.

d. **STT/voice/rating/scenarios move.** 04 T1 moves them into api as-is; 06 consolidates. Default: accept.

e. **Spikes needed before tasks** (unverified assumptions):
   - Auth emulator under vitest/jsdom (02, 07 O7), ~80%.
   - Admin SDK accepts Auth-emulator tokens (06 O3), ~85%.
   - uv resolves git-subdirectory deps with `workspace = true` (03 O3), ~75%.
   - firebase-tools resolves rules/indexes relative to `--config` (08 O3), ~85%.

f. **Deviations from defaults/brainstorm needing a yes:**
   - 09 O5: port `midas-es`/`phac-fr` converters (`phac.py` also serves `phac-en`).
   - 05 / 04 O6: drop `oneshot-raw`.
   - 02: delete `lib/spans.ts` (no production importer) instead of moving.
   - 04: depart from brainstorm pipeline sample (no `verify.map_units` step; counting rules/caps in `protocol.yaml`).
   - 01 O1: third-party `dorny/paths-filter` action.
   - 07 O4: split `features/auth`'s two files into `api/` and `app/`.

## Per-PRD open questions

| PRD | [OPEN] ids |
| --- | --- |
| 00 | O1 rule 2 ~300-line threshold; O2 rule 7 inheritance limit; O3 engine via git tag, no registry; O4 eval copies rules at split; O5 TS `constants.ts` rule |
| 01 | O1 `dorny/paths-filter` vs `paths:`; O2 delete eval pre-matrix readers; O3 edit two READMEs outside `docs/` |
| 02 | Auth emulator under vitest/jsdom spike; `lib/spans.ts` move or delete; landing page `legacy.css` use; API accept Auth-emulator tokens (06/07); `theme-init.js` shipping; rules for `onolys-ui` repo |
| 03 | O1 own sessions to 09; O2 eval repo private vs public; O3 uv git-subdir spike; O4 eval Firestore rules; O5 worker image config overlay |
| 04 | O1 03 lands first; O2 `stt:` preset key passthrough; O3 fixtures shipped in wheel; O4 rename `oneshot:miti` ids; O5 provenance hashes change; O6 drop `oneshot-raw` |
| 05 | O1 units vs quotes go/no-go; O2 reflection split reads last utterance; O3 one-shot `n_runs>1` tips; O4 batch size 25; O5 comparison gate thresholds |
| 06 | O1 merge api-unit + api-emulator jobs; O2 keep `[fail:*]` stub titles; O3 Admin SDK + emulator tokens; O4 delete acceptance-checklist test; O5 engine `FixtureClient` via `make_client`; O6 rating schema location |
| 07 | O1 CORS + Auth emulator env name; O2 `[fail:*]` hook kept; O3 `ROUTES` scope; O4 split `features/auth`; O5 stub pacing knob; O6 interview e2e needs voice stub; O7 emulator-backed `npm test` |
| 08 | O1 keep `create-test-user.py`; O2 `models.yaml` into engine; O3 firebase-tools `--config` spike; O4 staging identity provisioner gap |
| 09 | O1 06 leaf-module requirements; O2 tag name/timing; O3 delete old eval run data; O4 worker second service; O5 port `midas-es`/`phac-fr`; O6 promote eval components to `@onolys/ui`; O7 follow 04 config format |

## Owner-only follow-ups

See `/root/projects/onolys/onolys/docs/agent_files/owner-follow-ups.md` (untracked, primary checkout). PRDs with owner actions in "Manual steps": 00 (confirm proposals), 01, 02 (tag push), 03, 05, 08, 09. 04, 06, 07: none for cloud (06/07: dev machine needs `firebase-tools` + Java).

## Next steps

1. Owner reviews PRDs; marks each [OPEN] as `[RESOLVED: …]` or `[DEFERRED]` in the PRD.
2. Run `dev-tasks` per PRD in build order.
3. Optional `dev-critique` on request only.
