---
status: draft
summary: Reorganise api/ (13.3k lines, 114 flat tests) into one folder per feature; one data layer (generic Firestore functions + thin wrappers) replaces repo/ and its 1,131-line fake; all fakes deleted in favour of the Firestore + Auth emulators and small stub clients; combined mode runs locally for web dev; HTTP contract byte-identical.
date: 2026-11-28
---
# PRD: 06 API by feature

Repo/branch: Onolys/onolys / `refactor/revamp` · Depends on: 04-engine-package (hard: `onolys_engine` public surface, STT/voice/rating already moved into `api/`); 03-eval-split (hard: eval gone, eval-mode code is ours to delete); 01-legacy-purge · Owns: `api/**` (src, tests, `scripts/dev.sh`, `README.md`, `firebase`-using test fixtures), the `api-*` jobs in `.github/workflows/ci.yml`, `api/openapi.json` + `docs/contracts/public` (regenerate only; must not change) · Does not own: engine (04/05), web (07), `infra/`, `config/` relocation and `firebase.json` consolidation (08), `docs/`.

## TL;DR
`api/src/onolys_api` becomes one folder per feature (`sessions/ audio/ transcription/ pipeline/ tasks/ data/ usage/ auth/ email/ voice/ rating/ routes/`); `jobs/ adapters/ repo/ storage/` disappear. Data access is five base functions (`get_doc set_doc update_doc query in_transaction`, owner check inside) plus one-line wrappers, written once. No fakes: tests and local dev run the real code against the Firestore and Auth emulators plus small stub clients (local-folder blobs, in-process queue, recording email, fixture STT/LLM/voice). CI already runs the Firestore emulator (Java 21 + firebase-tools, cached), so the cost is test time, not new tooling. The public HTTP contract does not change; CI's existing regeneration diff proves it.

## Problem
| Gap | Evidence |
|---|---|
| Every data method exists twice: `FirestoreRepo` 1,546 lines / 66 public methods, `FakeRepo` 1,131 lines; a parity test and `[fake]`/`[firestore]` test twins keep them honest | [verified: `wc -l`; method scan: 42 single-doc get/put/list, 24 transactional] |
| Three more parallel fakes: `adapters/fake.py` 393, `storage/fake.py` 155 (+ `fake_routes.py`), `MemoryRateStore`; `adapters/validated.py` is a bridge for the fakes only | [verified: files; `test_fake_real_parity.py`; 01 hands these to 06] |
| Folders by layer: `jobs/` (14 files) mixes session lifecycle, charging, STT, validation; `app.py` (549) hand-registers 7 task kinds with `if` branches per mode | [verified: `app.py:398-450`] |
| Literals scattered: 300 MB (`storage/base.py`), 500 KB (`repo/large.py`), 1 s (`audio.py`), `uploads/{uid}/...` keys, collection names in 1,546 lines | [verified: grep] |
| Eval code lives in prod paths: `Settings.eval_mode`, `RunDoc.eval`/`EvalRunInfo`, `create_run(is_eval)`, `EvalDisabled`, `engines.resolve_engine/eval_snapshot`, drift guard in `jobs/run.py`, skip in `jobs/first_run.py`, override in `adapters/real.py` | [verified: grep; 03 hands deletion to 06] |
| 114 test files in one folder; 59 import `FakeRepo`, 26 `FakeBlobStore`, 21 an adapter fake; names carry task ids (`test_t08_hardening`, `test_t10_durability`) | [verified: grep] |
| Local dev without mocks is not possible: `AUTH_MODE=fake` (`Bearer test:<uid>`) + in-memory repo; web needs real-shaped Auth + Firestore (02 O, 07) | [verified: `config.py:98`, `docs/testing/local-setup.md` Mode B] |

## Goals / Non-Goals
**Goals:** the target layout; one implementation of all data logic; emulators + stubs instead of fakes; `constants.py`; mirrored tests; runnable local combined mode; unchanged contract; green suite at every commit.
**Non-goals:** behaviour or HTTP shape changes; engine internals (04/05); `config/` -> `infra/<env>/`, `firebase/` consolidation (08, only a path variable here); web (07); eval; docs edits (stale pages such as `docs/testing/local-setup.md` stay [DEFERRED]); renaming `ADAPTERS`/`PROD_ENGINE` env vars (infra sets them).

## Requirements
**R1 Layout and mapping** (file-level detail by the task agent; every file keeps its logic, `git mv` first, merges second; no src file over ~300 lines except where the table says so):
| Today | New |
|---|---|
| `routes/*` (14), `docs.py`, `routes/ids.py` | `routes/<resource>.py` (HTTP only: sessions, audio, speakers, transcript, rating, runs, usage, upload_limits, scenarios, interviews, api_key, auth_email, docs); business logic in `routes/sessions.py` (613) moves to `sessions/`; `routes/tasks.py` -> `tasks/routes.py` |
| `app.py` 549, `client_info.py`, middleware | `app.py` (factory + one mode table: mode -> routers/handlers) and `http.py` (middleware, request id, body limit, client info, error handlers) |
| `jobs/machine.py`, `progress.py`, `stale.py`, `sweep.py`, `alive.py`, `delete.py`, session txns (`cancel`, `fail_stale`, `transition`, `confirm_speaker`, `publish_report`, `discard_failed_upload`) | `sessions/{state,lifecycle,sweep}.py` |
| `audio.py`, `audio_child.py`, `jobs/validate.py`, `routes/upload_limits` rules | `audio/{rules,ffmpeg,validate}.py` |
| `jobs/transcribe.py`, `transcript_store.py`, `languages.py`, `adapters/real.py` RealStt, 04's moved `stt/*` + transcript parsers | `transcription/{transcribe,providers,transcript}.py` (providers = Chirp + fixture + registry + select) |
| `jobs/run.py`, `jobs/first_run.py`, `adapters/real.py` RealEvaluation, `engines.py`, `presets.py`, `coded_span.py`, `start_run`/`start_first_run`/`retry_step` txns | `pipeline/{run,start,presets}.py` calling `Engine.load/run/check_input/protocol` only; `adapters/validated.py`, `coded_span.py`, `engines.py` deleted |
| `jobs/queue.py`, `jobs/worker.py`, `adapters/error_map.py`, `claim_step`/`claim_run` | `tasks/{queue,runner,handlers,errors}.py` (`handlers.py` = task kind -> handler table; replaces the `register(...)` block) |
| `repo/*`, `storage/*` | `data/{store,paths,docs,models,blobs}.py` (see R2); `repo/limits.py`, `jobs/caps.py`, `jobs/charging.py`, usage txns -> `usage/{limits,charge}.py` |
| `auth/` 4 files, `routes/api_key.py` | `auth/{verify,deps}.py` (verify = ID token + OIDC + emulator verifier; deps = `current_user`, API-key parse, rotate txn) |
| `email/` 3 files, `jobs/reset_email.py`, Resend/auth-link adapters | `email/{service,rate}.py` |
| `voice/` 4 + 04's moved voice/scenarios, `jobs/interviews*.py`, interview txns | `voice/{relay,providers,interviews}.py` (3 files; interview lifecycle is its own doc type) |
| `rating.py` + 04's moved rating | `rating/{validate}.py` (+ schema per O6) |
| `contracts.py`, `openapi.py` | `api/tools/gen_contracts.py` (rule 6: dev tool; CI/README command updated) |
| `config.py` 295, loose limits | `config.py` (env -> `Settings`, config-file paths in one `CONFIG_ROOT`) + `constants.py` |
**R2 Data layer** (`data/`). `Db` = `{client, blobs}` built once (`build_db(settings)`), passed as first argument.
```python
get_doc(db, path, Model, uid)            # NotFoundError if absent OR doc.uid != uid
set_doc / update_doc(db, path, ..., uid) # same owner check; create_doc fails if it exists
query(db, collection, Model, uid, where=(), order=None, limit=None, cursor=None) -> Page[M]  # uid filter always added
scan(db, collection, Model, where, limit)  # the only cross-user read (sweeps): visibly named, server-side callers only
in_transaction(db, fn)                   # owns the per-uid lock + Aborted retry (today's _contended/_retry_txn)
def get_session(db, uid, sid): return get_doc(db, paths.session(sid), SessionDoc, uid)
```
42 of today's methods become one-line wrappers in `data/docs.py`. The 24 transactional ones (start/cancel/stale/reserve/claim/rotate...) are written once as functions in their feature folder on top of `in_transaction` (the FirestoreRepo version is the source of truth; FakeRepo's copy is deleted). `paths.py` is the only file composing Firestore paths from collection names in `constants.py`. Large-object rule (500 KB inline else blob pointer) lives in `data/blobs.py`.
**R3 Constants.** `constants.py`: collection names, blob key templates (`uploads/{uid}/{sid}/{upload_id}`, canonical audio, transcript, report), 300 MB / 1 s / 500 KB, 20 min fallback, session/run/step state names, task kinds, retry/lease numbers, header names. Per-env values stay in `config/` YAML (loader path in one place, 08 changes it) or env vars.
**R4 Stubs, no fakes.**
| Client | prod / staging | combined-local, PR preview | tests |
|---|---|---|---|
| Firestore | Admin SDK | emulator (`FIRESTORE_EMULATOR_HOST`) | emulator, fresh project id per test |
| Auth | Identity Platform ID tokens | **Auth emulator** (`AUTH_MODE=emulator`, local/test only) | `StubTokenVerifier` (`test:<uid>`) injected via `create_app(token_verifier=)`, moved to `tests/helpers/`; real emulator tokens in `tests/auth/` |
| Blobs | GCS | `LocalBlobStore` (local folder + signed-URL routes) | same, tmp dir |
| Queue | Cloud Tasks | `InProcessQueue` | same |
| Email / auth links | Resend / Admin SDK | `RecordingSender` (logs the link) | same, asserts on recorded mail |
| STT / LLM / voice | real providers | `ADAPTERS=stub`: fixture STT provider, engine `FixtureClient`, fixture voice (engine runs for real) | same |
Selection stays by endpoint env for infra clients (emulator host, `AUDIO_BUCKET`, `TASKS_QUEUE`, `RESEND_API_KEY`) and by `ADAPTERS=stub|real` for providers; names unchanged because Terraform, deploy workflows and PR previews set them (`infra/modules/environment/services.tf:42`, `pr-preview.yml:199`: preview runs `ADAPTERS=stub` on real staging Firestore). Fakes deleted: `repo/fake.py`, `adapters/fake.py`, `storage/fake.py` rename-and-slim to `LocalBlobStore`, `MemoryRateStore`, `test_fake_real_parity.py`, `adapters/validated.py`.
**R5 Eval-mode deletion** (03 hand-over): `eval_mode`, `EVAL_MODE`, `RunDoc.eval`, `EvalRunInfo`, `EvalGold/EvalSessionInfo`, `reject_eval_write`, `eval_session_input_sha256`, `create_run(is_eval, eval_spec)`, `EvalDisabled`, `engines.eval_snapshot/resolve_engine`, the drift guard, the first-run skip, route override in the run adapter, and their tests (`test_eval_*`, `test_start_run_eval`, `test_engine_registry`); drop the `onolys-oneshot` dependency if 04/05 leave none. Prod `params` equal today's.
**R6 Local combined mode (for 07).** `api/scripts/dev.sh` (keeps `--check`/`--quickstart`): starts Firestore + Auth emulators from one `FIREBASE_CONFIG` path variable (08 repoints it to `firebase/firebase.json`; ports 8080/9099), then `ENV=local SERVICE_MODE=combined ADAPTERS=stub AUTH_MODE=emulator FIRESTORE_EMULATOR_HOST AUTH_PROJECT=demo-onolys` uvicorn on `:8000`. Web uses `VITE_API_BASE_URL=http://127.0.0.1:8000/v1` and the Auth-emulator URL from 02. `--quickstart` mints a token through the Auth emulator and runs the OpenAPI quickstart end to end (upload -> `report_ready`). Needs Java + `firebase-tools` locally (documented in `api/README.md`).
**R7 Tests mirror source (rule 14).** `tests/{audio,transcription,pipeline,tasks,sessions,data,usage,auth,email,voice,rating,routes}/test_<behaviour>.py`, helpers in `tests/helpers/` (emulator fixture, stub verifier, audio/voice/card builders; `miti_fixtures` replaced by the engine's public fixtures), app-level files (`test_app`, `test_config`, `test_public_contract`, `test_logging`) at the root. Tests move with their feature commit; `test_repo_contract` (1,292 lines) becomes emulator-only `tests/data/` tests plus per-feature txn tests; `[fake]` params and `FAKE_*` fixtures disappear; names lose task ids; spec-id file `test_acceptance_checklist.py` goes (O4).
**R8 CI.** Keep jobs `api-unit` (no emulator), `api-emulator`, `api-rules`, `api-flaky`, `api-coverage` (gate 94, combined data) and `api-image`; the emulator job also starts the Auth emulator (`--only firestore,auth`, matching 02 R9). The OpenAPI/contract regeneration step uses `api/tools/gen_contracts.py`. Whether to merge unit + emulator into one job is decided from T0 timings (O1).
**R9 Contract unchanged.** No edit to `api/openapi.json`, `docs/contracts/public/**`, `web/src/api/schema.d.ts` in any 06 commit. Route path, method, `operation_id`, model names stay (explicit in route decorators).

## Architecture
```
request -> routes/<resource>.py -> sessions|audio|pipeline|usage|... (logic) -> data.{wrappers,in_transaction} -> Db{Firestore client, BlobStore}
Cloud Tasks / InProcessQueue -> tasks/routes.py -> tasks/runner.py (claim, lease, retry) -> tasks/handlers.py[kind] -> audio.validate | transcription.transcribe | pipeline.run | sessions.delete | ...
pipeline.run -> Engine.load("miti").run(RunRequest, RunOptions(llm=client)) ; stub mode: client = FixtureClient
```
**Migration (strangler; each commit green; one commit per feature; no shim survives T10).**
| Task | Work | Gate |
|---|---|---|
| T0 | Baseline: time `api-unit` and `api-emulator` jobs; spikes: per-test emulator project id isolation, Admin-SDK `verify_id_token` on Auth-emulator tokens (O1, O3); note `openapi.json`/contracts/`schema.d.ts` blob ids | findings recorded |
| T1 | R5 eval-mode deletion (smaller code first) | api suite; contract diff empty |
| T2 | Fakes out: `tests/conftest` + `tests/helpers` run every test on the emulator through the existing `FirestoreRepo` (project id per test); delete `FakeRepo`, parity test, twin params, `MemoryRateStore`, adapter fakes (STT/LLM/voice/email stubs per R4); `storage/fake.py` -> `LocalBlobStore` | whole suite on emulator; CI emulator job covers it |
| T3 | `constants.py`, `data/{store,paths,docs,models,blobs}.py`; `FirestoreRepo` thin methods now delegate to them; `test_repo_contract` -> `tests/data/` | data tests; no caller changed |
| T4 | usage/ + auth/ + email/ (small, few callers) | their tests, moved to mirrored paths |
| T5 | audio/ + transcription/ (merges 04's moved STT files) | audio, STT, transcribe tests |
| T6 | sessions/ (state machine, lifecycle, sweep, txns) | session, cancel, delete, sweep tests |
| T7 | pipeline/ + tasks/ (start_run txns, claim, queue, runner, handlers table); `app.py` mode table | run, retry, first-run, worker tests |
| T8 | voice/ + rating/ (interviews, relay, scenarios) | voice, interview, rating tests |
| T9 | routes/ slimmed to HTTP; `http.py`; `tools/gen_contracts.py`; `dev.sh` R6; CI R8 | `dev.sh --quickstart`; combined integration |
| T10 | delete empty `repo/ adapters/ storage/ jobs/` and every delegating shim; final test regroup sweep; README; full gate (dev-ship) | AC below |

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | Data shape | Functions on a `Db` handle; 42 wrappers + 24 txn functions in feature folders | Keep a `Repo` class with one impl; generic ODM | Rule 8 and brief; txn logic belongs to the feature that owns the rule |
| D2 | Firestore in tests | Emulator for every test needing data | Keep `FakeRepo` for speed; in-memory client | Locked; one logic copy; removes the 59-file fake coupling |
| D3 | Test isolation | Fresh emulator project id per test (no clearing, xdist-safe if lock timeouts stay absent) | Wipe via REST between tests; one shared project | Cheap; unique uids alone miss cross-user scans (sweep, stuck sessions) |
| D4 | Mode selection | Endpoint env for infra clients, `ADAPTERS` for providers (names kept) | New `STUBS` switch; per-client flags | Terraform/CI/PR previews already set these; infra is 08's |
| D5 | Fake auth | `AUTH_MODE=emulator` replaces `fake`; `test:<uid>` verifier only in `tests/helpers/` | Keep `fake` in src for curl; emulator everywhere in tests | 02 needs emulator tokens; stub verifier is a lowest-level seam, keeps 72 test files untouched |
| D6 | Stub inference | Stub mode runs the real `Engine` with the fixture LLM client | Re-implement a `FakeEvaluation` | Rule 9; fixture replies match the fixture STT transcript |
| D7 | Order | Fakes first (T2) on the existing repo, data layer second, features third | Rewrite data layer first | Separates "swap test backend" from "rewrite txns"; contract tests already pass on both backends today |
| D8 | Path templates | Collection names + blob keys in `constants.py`; Firestore paths composed only in `data/paths.py` | All in `constants.py` | One place each for names and composition |
| D9 | Dev tools | `contracts.py`/`openapi.py` -> `api/tools/gen_contracts.py` | Keep in package | Rule 6; CI/README command changes only |
| D10 | Interviews | Lifecycle in `voice/interviews.py` | Under `sessions/` | Separate doc type and sweep; keeps `sessions/` about audio-to-report |
| D11 | Contract proof | CI regeneration diff + zero edits to generated files in 06 commits | New snapshot test | Already enforced: `ci.yml` api-unit step, web `gen:api` staleness (`ci.yml:495`), schemathesis smoke |

## Manual steps
None for cloud. Owner/dev machine: install `firebase-tools` (Java is present) to run api tests locally; a `Needs emulator` message from `tests/conftest.py` prints the exact command.

## Risks / Open Questions
- Risk: emulator-only tests are slower and `Transaction lock timeout` flakes appear when tests run in parallel (serial today for that reason). Mitigation: per-test project ids, T0 timing, serial fallback, keep `flaky` marker lane.
- Risk: txn semantics drift while rewriting (`start_run`, `cancel_session`). Mitigation: `test_repo_contract` and `test_firestore_cross_instance` run on the emulator before T3 and stay as the oracle.
- Risk: PR preview (`ADAPTERS=stub` on staging Firestore) breaks. Mitigation: a test boots the app with that exact settings set and runs a session to `report_ready`.
- [OPEN] O1: merge `api-unit` + `api-emulator` into one emulator job? Default: decide at T0 (merge if >70% of tests need the emulator); coverage gate stays 94.
- [OPEN] O2: keep `[fail:*]` magic session titles (stub failure injection used by `test_acceptance_flow`, `test_run`, `test_transcribe`, `test_delete`)? Default: keep, carried as one `stub_hint` only when `ADAPTERS=stub` (today's `stub_title` leaks into real adapters' signatures); drop if 07's e2e does not use them.
- [OPEN] O3: Admin SDK accepts Auth-emulator tokens (~85% sure, unrun). Default: use `verify_id_token`; fallback: local/test-only unsigned-JWT decode checking `aud`, `iss`, `exp`.
- [OPEN] O4: delete `test_acceptance_checklist.py` (maps spec ids AC1-AC18; rule 12/14)? Default: delete, behaviour already covered by named tests.
- [OPEN] O5: engine `FixtureClient` and the fixture evaluation reachable from api via public `make_client` (04 R9, O3). Default: yes; 04 confirms the name.
- [OPEN] O6: rating schema location. Default: api builds its validation from `Engine.protocol()` (`ProtocolInfo`) at startup, so no committed `rating.schema.json` in `api/`; 04 R8 decides if the file must stay.
- [RESOLVED: locked] Firestore emulator not in-memory; voice stays in api; constants one file per package; no compat shims.
- [DEFERRED] `ADAPTERS`/`PROD_ENGINE` renames and Terraform variable names (08); `docs/testing/local-setup.md` rewrite (docs freeze); merging `voice/` to 2 files.

## Hand-offs
01 -> 06: `adapters/validated.py`, `adapters/fake.py`, parity test, `jobs/machine.py` note (done T2/T6). 02 -> 06: API accepts Auth-emulator tokens in combined mode (R4/R6). 03 -> 06: eval-mode deletion list (R5). 04 -> 06: moved folders arrive unmerged; api imports only `onolys_engine`; AST guard stays. 05 -> 06: `Engine.output_schema()` is the report schema, so the api keeps no copy of it (`api/src/onolys_api/schemas/report.local.schema.json` re-checked at T7). 06 -> 07: `dev.sh` + env above. 06 -> 08: one `CONFIG_ROOT`, one `FIREBASE_CONFIG` variable, `api/Dockerfile` COPY lines unchanged by 06.

## Acceptance Criteria
- `repo/ adapters/ storage/ jobs/` do not exist; `git grep -nE "FakeRepo|FakeBlobStore|FakeEvaluation|FakeStt|FakeVoice|FakeEmailSender|FakeAuthLinks|MemoryRateStore|class FirestoreRepo|class Repo\b" api` returns 0; `test_fake_real_parity.py` gone.
- `git grep -nE "EVAL_MODE|eval_mode|is_eval|EvalRunInfo|EvalDisabled|eval_snapshot" api` returns 0.
- `from google.cloud import firestore` appears only under `data/` (plus a test); GCS only in `data/blobs.py`; every owner-check path has a test per collection (foreign uid -> `NotFoundError`).
- Literals: `git grep -nE "300 \* 1024|500 \* 1024|\"uploads/|sessions/\{" api/src` hits only `constants.py` and `data/paths.py`; session/run state names defined once.
- Layout matches R1; no src file over ~300 lines except named exceptions in the task list; `auth/`, `email/` at most 2 files, `voice/` at most 3.
- `tests/` mirrors src; no `tests/test_t*`; no test name contains a task or spec id; root holds only app-level files and `conftest.py`.
- `api/openapi.json`, `docs/contracts/public`, `web/src/api/schema.d.ts` unchanged: `git diff <T0 sha> -- <them>` empty and CI regeneration diff green.
- `api/scripts/dev.sh --quickstart` passes with both emulators; `test_combined_integration` and the PR-preview-settings test pass.
- Boundary guard from 04 passes (api imports `onolys_engine` top level only); ruff clean; coverage >= 94; all `api-*` jobs green, with before/after job times in the PR description.
- Every task commit passed its listed gate.
