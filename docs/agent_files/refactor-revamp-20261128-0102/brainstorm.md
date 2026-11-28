---
status: approved
summary: Onolys revamp — agreed code rules plus the concrete engine, code-structure, eval, web and infra changes
date: 2026-11-28
---
> Source of truth while discussing: the Claude doc "Onolys revamp: rules and changes" (https://claude.ai/artifact/Y3U9taxgT4XKUXANc6wqTa). This file is the snapshot taken on 2026-11-28 for the dev loop. "Agreed" items are decided; open questions are at the end.

# Onolys revamp: rules and changes

Nov 27, 2026 · @Tejit Student Account

## Purpose

This is the single doc for the Onolys revamp. It replaces two earlier docs, the engine redesign notes and the code-structure draft.

- **Rules** says how all code is structured and written. It becomes the rules file that drives the revamp and keeps future code in order.
- **Changes** lists the concrete work: what moves, what gets rebuilt, what gets fixed.
- **Scope:** English transcripts only for now.

Nothing is implemented yet.

## Rules

These apply to all code: `api/`, `engines/`, `eval/`, `web/`, and anything new. All are **Agreed** unless marked *proposed*.

### Structure

1. **Organize by feature, not by layer.** One folder per feature (`audio/`, `llm/`, `pipeline/`, `data/`, `auth/`...). Everything for a feature lives in its folder.
2. **Fewer files.** One file per feature by default. Split a file only when it passes about 300 lines *(proposed number)*.
3. **Libraries + YAML.** Code is a library of reusable pieces: pipeline steps, rules, scoring, evaluations, charts. YAML decides which pieces run, in what order, with which settings. A runner loops through the YAML list; there is no `if/elif` on kinds. A new variant is a YAML change, not a code change.
4. **One folder per evaluation type.** Everything for MITI (pipeline YAML, prompts, definitions, fixtures) sits in one folder; the same for one-shot and any future type. Shared protocol definitions sit in `protocols/`.
5. **Clear boundaries between packages.** The engine has one entry point (`Engine.run`) plus a small public module of input/output types and errors. Callers never import engine internals. Product features (STT, voice, rating cards, scenarios) live in the product, not in the engine.
6. **Dev tools stay out of shipped code**, in `tools/`.

### Code shape

7. **Base class + derived classes.** Shared behaviour lives in a base class; variants derive and add only what differs. One level of inheritance *(proposed)*. Create a base only when there are two real variants.
8. **Generic base functions + thin named wrappers.** For example `get_doc(path)` → `get_session(sid)`, `send(messages, model)` → `send_json(...)`. Wrappers only fill in parameters.
9. **One implementation of every piece of logic.** Tests and local dev pass in a stub client at the lowest level (Firestore, GCS, LLM, queue, email). No parallel fake classes.
10. **Constants in one file.** Provider names, model ids, collection and storage paths, limits and state names go in `constants.py`. Values that differ per environment go in `config/` YAML or env vars. No literals anywhere else.
11. **One source per instruction.** Prompts and rule text shared by several evaluation types are generated from one source, so they cannot drift.

### Docs and tests

12. **Docstrings in plain words:** what the code does and, where not obvious, why. No spec or planning ids (`PRD R6`, `SP09`, `FX46`...).
13. **One `architecture.md`** kept current, instead of a folder of ADRs.
14. **Tests mirror the source layout:** `src/x/audio/validate.py` → `tests/audio/test_validate.py`. File names describe behaviour, never task ids. Shared helpers go in `tests/helpers/`.

### UI and clean-up

15. **`@onolys/ui` is the Onolys design system.** It holds themes, tokens and every reusable component, from buttons, fields and notices up to whole common pieces such as the header, footer, account menu and theme toggle. It also holds generic UI helpers (number/date formatting, text highlight spans). The main app, eval, the landing page and future projects all use it. A product folder keeps only what is specific to that product.
16. **No legacy code.** Before launch, anything retired, superseded or kept "for compatibility" is deleted, not kept alongside. That covers old setups, compat layers, migration shims, migration and guard tests, and legacy CSS layers. Git history is the archive.

## Changes: engine

The engine becomes one package. It holds a library of steps and scoring, plus one folder per evaluation type whose YAML says what runs.

### Layout

```
engine/
  engine.py        one Engine class: loads an evaluation folder, runs its pipeline
  runner.py        step registry + the loop over pipeline steps
  steps/           library: prepare, segment, code, globals, verify, rules, tips, report
  scoring/         library: counts, formulas, summaries, coverage, aggregate, compare
  llm/  transcript/  logging/  constants.py
  protocols/
    miti-4.2.1/    protocol.yaml (codes such as sr/cr, globals, formulas), definitions/*.md
  evaluations/
    miti/            pipeline.yaml, prompts/, fewshot/, fixtures/
    oneshot-single/  pipeline.yaml, prompts/
    oneshot-split/   pipeline.yaml, prompts/
  tools/           dev-only scripts
```

- **One `engine.py`.** There are four today (the core base class, MITI, one-shot, and the API's registry setup). With YAML, one `Engine` runs any evaluation folder, so derived engine classes are needed only if a type requires code YAML can't express.
- **The registry** shrinks to "evaluation name → folder".
- **The report** is built from 7 files today (`report`, `result`, `build`, `compare`, `run_info`, `hashes`, `coverage`); that collapses to the `report` step plus `scoring/`.

### Pipeline YAML

```yaml
# evaluations/miti/pipeline.yaml
protocol: miti-4.2.1
steps:
  - use: prepare.mark_roles
  - use: checks.duration_max      {with: {minutes: 25, severity: error}}
  - use: checks.param_required    {with: {param: change_goal}}
  - use: segment.volleys          {with: {min_other_words: 3, break_on: [question, reflection]}}
  - use: segment.units            {with: {split_on: [sentence, ";", "—"]}}
  - parallel:
      - use: llm.code_batches     {with: {prompt: prompts/code.md, fewshot: fewshot/code.json, batch: 25, context_turns: 6}}
      - use: llm.rate_globals     {with: {prompt: prompts/globals.md}}
  - use: verify.map_units         {with: {max_drop_rate: 0.20}}
  - use: rules.one_code_per_utterance
  - use: rules.max_per_volley     {with: {n: 1}}
  - use: rules.exclusive_group    {with: {codes: [sr, cr], winner: cr}}
  - use: rules.exclusive_group    {with: {codes: [persuade_permission, persuade], winner: persuade_permission}}
  - use: globals.cap              {with: {max: 4, when: poor_practice_cited}}
  - use: score.count
  - use: score.formulas
  - use: llm.tips                 {with: {prompt: prompts/tips.md, keep: 5}}
  - use: report.build
```

**How it runs:**

- **Registration:** each step registers under its name (`@step("rules.exclusive_group")`), with one signature: `fn(state, **with) -> state`.
- **Load-time checks:** each step declares what it reads and writes, so an impossible order (counting before verifying) fails at load time. An unknown step name fails at load time too.
- **Control forms:** only `parallel:` and `repeat: n_runs`.
- **Model choice:** models come from constants or env config, never from the step.

### Code-pass input

- **Context in order:** send the conversation in order. Use the last 4–8 turns of both speakers as read-only context (setting, default 6), then the batch of about 25 volleys in real order, client turns included. There is no word cap; the 150 / 100-word limits are dropped.
- **Volley building** stays deterministic, as today.
- **Utterance ids:** code over-splits clinician turns into numbered units at `.` `?` `!` `;` `—` `:`.
  - The model groups contiguous units into utterances and returns `{units: ["u14", "u15"], code, rationale}`.
  - This fits MITI: an utterance is a "thought unit", often several sentences, and the rule is "when unsure, split less" (§E.1–E.3).
  - Fallback: quotes, if ids don't work.

### One-shot

One-shot uses the same prepared input and returns the same raw shape. All post-processing is the shared steps, and the model never counts.

| Variant | Calls | Output | Tips |
| --- | --- | --- | --- |
| MITI | \~25-volley batches + 1 globals call | codes per batch; globals | separate call on the scored reading |
| one-shot single | 1 | one ordered response: utterances → globals → tips | same call |
| one-shot split | 2 in parallel (all coding; globals) | codes; globals | third call |

- **Truncation:** a truncated single call fails, with no halving retry.
- **Optional:** keep today's model-counted one-shot as `oneshot-raw`.

## Changes: code structure

### api/ layout

```
src/onolys_api/
  app.py  constants.py  config.py
  routes/          one file per /v1/{resource}
  sessions/        state machine + lifecycle (create, cancel, delete, stale, sweep)
  audio/           upload rules, validate, ffmpeg, transcode
  transcription/   STT providers (moved out of the engine), call + poll
  pipeline/        run task: first-run gate, Engine.run, charge usage
  tasks/           queue, retry wrapper, task kind → handler
  data/            Firestore base + per-collection helpers, blob store
  usage/  auth/  email/
  voice/           AI interview relay + Gemini Live provider + scenarios (moved out of the engine)
  rating/          rating-card validation (moved out of the engine)
```

- **`jobs/`, `adapters/`, `repo/` and `storage/` dissolve** into the feature folders above.
- **auth (4 files), email (3) and voice (4)** each shrink to 1–2 files.

### API ↔ engine boundary

Today the API imports about 50 names from `onolys_engine_core` and 39 from `onolys_miti`. Some of these reach engine internals: for example, `coded_span.py` imports the private `_duration_ms` from `prepare.py`. 22 of the 39 are STT or voice.

After: the API imports `Engine.run` plus one public module of types and errors. STT, voice, rating cards and scenarios move to the API.

### Data layer

- **Base functions:** `get_doc`, `set_doc`, `update_doc`, `query`, `in_transaction`. The owner (uid) check lives inside them.
- **Thin wrappers:** `get_session(uid, sid) = get_doc(paths.session(sid), SessionDoc, uid)`. They replace the 80 hand-written methods, which exist twice today (real and fake).
- **Paths:** templates in one place.

### LLM layer

- **Base call:** `send(messages, model, params)` with multi-turn `messages`. Today only one system + one user message is possible.
- **Wrappers:** `send_json` and `send_cached`.
- **Route names:** drop the prompt-specific ones (`miti_code`, `miti_globals`, `tips`). Steps pass the model in.
- **Kept from today:** `engines/core/llm/` already handles providers via litellm, retries, concurrency and cache warm-up.

### Fakes

Delete `repo/fake.py` (1,131 lines), `adapters/fake.py` and `storage/fake.py`, plus the parity test. Tests use stub clients instead: the Firestore emulator or a small in-memory client, a local-folder blob client, the LLM fixture client, an in-process queue, and an email recorder.

### Constants to collect

These values are scattered today:

- storage paths (`uploads/{uid}/{sid}/{upload_id}`...)
- collection names
- the 300 MB / 1 s / 500 KB limits
- the 25-min max, 20% drop rate and 25 volleys per call
- model ids in three `routes.yaml` files
- session state names

### Clean-up

- Remove spec ids from every docstring.
- Fold the useful ADRs (10 files) into `architecture.md`.
- Decide on `docs/agent_files/` (569 of the 631 files in `docs/`).
- Remove leftover migration and guard tests (`test_no_old_imports`, `test_naming_guard`, `test_transcript_migration`).
- Regroup tests to mirror the source layout.
- Done 2026-11-27: deleted the local, untracked `backend/` leftover.

### web/, frontend/, infra/, config/, scripts/

- **`frontend/` (admin site):** its backend is retired and the page shows "Nothing here yet.". Delete it, with its cloud resources, unless an admin site is planned.
- **`web/src/mocks/` (1,090-line `stateMachine.ts`):** a fake backend in the browser that mirrors the API's session state machine. This is the same "parallel fake" problem. Replace it with the API running in `combined` mode with stub clients.
- **`web/` layout** is already mostly by feature (`features/session`, `upload`, `report`, `interview`...). Keep that; shared pieces move to `@onolys/ui` (see below).
- **`infra/`** has two Terraform roots: the original prod root (`infra/`) and `isolated-environment/` for the new staging and eval projects. Pick one parameterized root for prod and staging; eval's part leaves with eval.
- **`config/`** already holds the per-environment YAML (model routes, STT, voice) and `models.yaml`. That fits the constants rule: environment values stay here, fixed values go to `constants.py`.
- **`scripts/ci/`** holds about 30 CI guard scripts plus tests for the workflows themselves. Review which still earn their keep; move `gen_miti_schema.py` next to the engine's schema code.
- **`firestore-rules-test/`** tests `firestore.rules`. Move both into `data/` (or one `firebase/` folder) with the other Firebase config.

All of the above are **Agreed**. Also agreed:

- **Delete `frontend/`.** Done in PR #85 (merged 2026-11-28), branch `chore/remove-admin-frontend`. The owner retires its cloud resources and the `admin.onolys.com` domain.
- **One `tests/` folder in `web/`.**
  - Today the 85 unit test files sit next to their source files.
  - The Playwright checks live in `web/e2e_review/`.
  - Move them to `web/tests/` (mirroring `src/`) and `web/tests/e2e/`.
- **`web/src/` layout:** `app/` (shell + route table, today's `routes/`), `features/` (one folder per screen), and nothing else shared beyond product-specific helpers. Today's `components/` (Field, Notice, StatusChip...) and the layout pieces (header menu, footer, theme toggle) move to `@onolys/ui`. `lib/format.ts`, `lib/spans.ts` and `lib/theme.ts` move there too, since eval and the landing page need the same. This app-shell + features split is the common React layout (e.g. the "bulletproof-react" structure).
- **Fold `web/src/auth/` into `features/auth/`.** It is the sign-in feature (pages, Firebase service, route guards), so it follows the same layout as the other features.
- **Delete `web/src/mocks/`** (15 files, including the 1,090-line `stateMachine.ts`). Local dev and tests run the real API in `combined` mode with stub clients (rule 9).
- **Shrink `infra/`.** Of its 62 files, 24 are Terraform (one is a Terraform test), 6 are examples and 3 are lock files. Another 24 are helper scripts and their tests, and 18 of those 24 are tests; the last 5 are small config files. One Terraform root for prod + staging, plus a pass over the script tests, cuts most of it.
- **`infra/` with one folder per environment** (Agreed): `infra/prod/` and `infra/staging/` each hold that environment's Terraform variables and the app's runtime YAML (model routes, STT, voice) that `config/` holds today. Shared Terraform modules sit in `infra/modules/`. `config/` and `isolated-environment/` go away.
- **Simplify `scripts/ci/`.** It has 30 files: about 13 guard scripts, about 15 tests of those guards, and fixtures. Keep the few that protect releases (previews, the prod-image check, no LLM keys in PR workflows). Replace `changes.sh` with GitHub `paths:` filters where possible, and drop the tests of tests.
- **Firebase config in one place.** That means `firestore.rules`, `firestore-rules-test/`, `firebase.json` and `api/firestore.indexes.json`. The rules only govern **browser** access: the web app listens to its own `session_status` doc for live progress (`web/src/api/firestoreListener.ts`). The backend uses the Admin SDK, which bypasses rules.

## Changes: eval

**Agreed in principle:** eval reports are defined in YAML. They pick from a library of metrics and a library of charts, so a new report type is a YAML file, not a code change. The chart layer may change to make this work. `eval/` has not been reviewed folder by folder yet; this section is the direction only.

- **Metrics library:** each comparison metric is a named function, for example the existing `globals_within_1`, `line_accuracy` and `macro_f1` in `eval/backend/.../compare_routes.py`.
- **Charts library:** each chart type is a named component that takes rows and options.
- **Report YAML** says which metrics feed which charts, in what order.

Illustrative only; chart names are placeholders:

```yaml
# eval/reports/engine-comparison.yaml
report: engine-comparison
inputs: {engines: [miti, oneshot-single, oneshot-split], dataset: casaa-miti421-video2013}
sections:
  - title: Global ratings vs human coders
    metric: globals_within_1
    chart: {use: bars.grouped, by: [global, engine]}
  - title: Line-level agreement
    metric: line_accuracy
    chart: {use: table.ranked, sort: desc}
  - title: Counts per code
    metric: count_diff
    chart: {use: dots.per_item, by: code}
```

### Split eval into its own repo (Agreed)

Eval is a separate product, with its own server, site, deploy and cloud project. Staging stays in this repo because it is pre-prod, the same product. Eval moves out, along with `deploy-eval.yml`, the eval Terraform examples and `scripts/ci/test_eval_image.sh`.

Three ties have to be cut first:

1. **Engine code.** Eval imports `onolys_miti` and `onolys_engine_core` as workspace packages. After the split it depends on the engine as a versioned package (a git tag, like `@onolys/ui` today).
2. **Sign-in.** `eval/web` reuses the main app's `web/src/auth` through the `@prod-auth` alias. That moves into a shared package, or eval keeps its own copy.
3. **Prod sessions.** `eval_sessions.py` imports each dataset session as a prod session record. After the split, eval stores its own sessions.

**No registry release is needed** *(proposed)*. Eval can depend on the engine by git tag, the same way `web/` uses `@onolys/ui`. In eval's `pyproject.toml`: `onolys-engine = { git = "https://github.com/Onolys/onolys", subdirectory = "engine", tag = "engine-v1.0.0" }`. Eval's CI then needs read access to this private repo (a deploy key or token). A private package registry (Artifact Registry) is the heavier alternative.

### eval/ structure changes

- **Duplicated features move to shared modules.** The eval backend re-implements its own auth, Firestore repository, blob storage, task queue, delete flow and an STT upload/poll chain (`uploads.py`, 626 lines). These use the same shared `data/`, `auth/`, `tasks/` and `transcription/` features as the API.
- **Dataset converters.** Nine near-parallel modules of 150–220 lines each become one base converter class. Each dataset becomes a small derived class, or a YAML mapping next to its `manifest.yaml`.
- **One metrics library.** Metrics are spread across `core/metrics.py`, `core/_formulas.py`, `core/summary/*` (line, session, analysis, operations) and the route file `compare_routes.py`; they move to one library.
- **One chart library.** The 13 bespoke chart components get a shared base, plus a report YAML that picks charts.
- **Non-English datasets** (`midas-es`, `phac-fr`) are out of scope for now.
- **Local leftovers:** `eval/src/iaudit_eval/` and `eval/tests/` were untracked, empty folders from iaudit; deleted 2026-11-28, like `backend/`.

## Inconsistencies and bugs found

Five issues so far: three are one-shot drifting from the manual and the MITI engine, two are in volley building and context.

| # | Issue | Where | Evidence | Effect |
| --- | --- | --- | --- | --- |
| 1 | One-shot says "any client turn ends a volley" | `oneshot/configs/miti/instructions.md` | Manual §E.1/E.3 and the MITI engine keep facilitative input inside a volley | One-shot counts more volleys, so more codes |
| 2 | One-shot's Affirm / Seek / Autonomy wording leans to the higher code | same file | Manual §E.4.f and `code_system.md`: when unsure, use the **lower** code | Inflated MI-adherent codes |
| 3 | One-shot counts in the model and returns no evidence | same file + `schema.json` | "Do not return evidence instances, quotes, offsets" | Can't be scored on line metrics; not comparable |
| 4 | A volley breaks on a client answer to a question, but not to a reflection | `prepare.py` `_asks_question` | Manual §E.3: "direct question **or reflection**" | Some volleys too long, so slot caps undercount |
| 5 | Context is out of order, capped at 150 / 100 words | `prepare.py` `_client_context` | PRD D6 "eng sizes" | Order lost, text repeated across volleys |

## Research: Jev, per-volley and per-global calls

Recommendation: try Jev as a cheap **checker** of which codes each volley has, not as the coder. Test per-volley and per-global calls as eval A/Bs first. Agent findings from vendor and secondary pages; nothing was run.

**Jev** (likely TypeSafe's [Jev](https://openrouter.ai/docs/cookbook/evaluate-and-optimize/jev-classification.md), \~85% confidence; awaiting owner confirmation):

- **What it is:** a non-generative classifier on OpenRouter (`typesafe/jev-1.13`, alpha).
- **What it returns:** probabilities per option (`choice`) or per yes/no.
- **Vendor claims, unverified:** $0.042 per million input tokens, 400 requests in 8.6 s, about 67% accuracy on its own datasets.

| Change | Calls per 20-min session | Gains | Costs | Verdict |
| --- | --- | --- | --- | --- |
| One call per volley | \~60–120 vs 3–5 (estimate) | full attention per volley; per-volley retry | \~40–80 s at concurrency 8 vs \~10–25 s | A/B; also try batch = 5 |
| One call per global | 4 vs 1 | one definition per call | globals are a holistic judgment (manual §D); calibration across dimensions lost | A/B; also try Technical / Relational pairs |

**Several codes in one volley:** counts are per volley, with each code once. So 8 yes/no questions per volley ("contains a CR?") give correct counts with no boundaries, but no line evidence. The LLM keeps splitting and coding; Jev's 8 answers flag volleys where it disagrees. Measure Jev's per-slot agreement with human coders offline first.

Related work (abstracts only): [AutoMISC](https://aclanthology.org/2025.nlpai4health-main.4), [behavioural decomposition for MITI](https://neurips.cc/virtual/2026/177190).

## Current state reference

### How a session flows today

`api/` is the product server: HTTP, accounts, storage, background tasks. `engines/` is a library: transcript in, report out. They share one uv workspace.

```
POST /sessions → audio upload (GCS) → validate (ffprobe, FLAC) → transcribe (STT) → awaiting_input
  → speakers confirmed + rating → run task → Engine.run (MITI) → report_ready
```

### MITI engine steps today

| # | Step | LLM? | File |
| --- | --- | --- | --- |
| 1 | Prepare: roles, span, input checks, volleys + context | No | `prepare.py` |
| 2a | Code pass: 25 volleys per call; utterances as quote + code + rationale | Yes | `code_pass.py` |
| 2b | Globals pass: 4 globals in one call; never sees counts | Yes | `globals_pass.py` |
| 3 | Verify quotes (exact → normalized → fuzzy); over 20% dropped means retry, then fail | No | `locate.py` |
| 4 | Rules, counts, summary formulas | No | `score.py`, `formula.py` |
| 5 | Aggregate over `n_runs` | No | `run.py` |
| 6 | Tips: up to 7 proposed, 5 kept after validation | Yes | `tips.py` |
| 7 | Report | No | `build.py` |

All three LLM routes run `gemini/gemini-4-neon` (`config/prod/routes.yaml`).

### api/ today

One package (\~13.3k lines). It runs as `api`, `worker`, `voice` or `combined`.

- **Folders:** `routes/`, `jobs/`, `adapters/`, `repo/`, `storage/`, `auth/`, `email/`, `voice/`, plus 14 loose modules.
- **Tests:** about 115 test files in one flat folder.

### engines/ today

| Package | Files | Holds |
| --- | --- | --- |
| `core` | 31 | LLM client, `Engine` base + registry, transcript types (4 files), spans, errors, retry, logging (3), validation (2) |
| `miti` | 48 | the MITI pipeline, plus STT, voice, rating cards, interview scenarios, `data/` (pack.yaml, prompts, schemas, fixtures), dev tools |
| `oneshot` | 7 | single-call engine + `configs/miti/` |

### eval/ today

This is the staging evaluation tool: it runs engines on human-coded datasets and compares the results. It is a separate product from the main app, with its own server, site and deploy (`deploy-eval.yml`), and about 9.3k lines of Python.

| Part | Files | Holds |
| --- | --- | --- |
| `core/` (`onolys_eval`) | 33 | 9 dataset converters (AnnoMI, AnnoSUM, AutoMISC, HLQC, MIDAS, MI-TAGS, PHAC, Welivita, CASAA PDFs), gold contract, fetch/upload, engine projections, metrics, `summary/` compare calculations |
| `backend/` (`onolys_eval_backend`) | 23 | FastAPI eval server: own auth + allowlist, Firestore repository, storage, queue, uploads with their own STT poll chain, run scheduler (754 lines), compare routes (516 lines) |
| `web/` | 158 | React eval site: New run, History, run detail, Compare (78 files, 13 chart components, each with its own CSS) |
| `datasets/` | 11 manifests | per-dataset metadata (source URLs, PDF layout, change goal); no transcript text |
| `fixtures/compare/` | 14 | synthetic compare payloads for tests |

### Other folders today

| Folder | Files | What it is |
| --- | --- | --- |
| `web/` | 251 | main app site (React 19 + Vite). `src/features/` holds session, upload, report, interview, rating, usage, dashboard, settings, speakers and legal. Also `auth/` (28), `mocks/` (15, browser fake backend), `api/` (generated `schema.d.ts`, 3,661 lines), `routes/`, `components/`, `lib/`, `hosting/` |
| `frontend/` | 34 | admin site shell; its backend is retired |
| `infra/` | 62 | Terraform: prod root (`main.tf`, `identity.tf`, `domains.tf`, `budget.tf`...), `modules/environment/` (services, secrets, alerts, voice), `isolated-environment/` (staging + eval projects), helper scripts and their tests |
| `config/` | 7 | per-environment YAML: model routes, STT providers, voice providers (prod, staging), plus `models.yaml` |
| `scripts/` | 38 | `ci/` release guards, preview helpers, workflow tests; `gen_miti_schema.py` |
| `firestore-rules-test/` | 4 | tests for `firestore.rules` |
| `.github/` | 9 | CI, deploy prod / staging / eval, PR previews, nightly |
| `docs/` | 631 | 569 in `agent_files/` (45 branch folders); the rest is architecture, mission, reference, testing, contracts, 10 ADRs |

## Decisions and open questions

| Topic | Decision | Status |
| --- | --- | --- |
| Scope | English only for now | Agreed |
| Volley building | Keep as is | Agreed |
| Context | In order, both speakers, 4–8 turns, no word cap | Agreed |
| Utterance location | Numbered units; quotes as fallback | Agreed |
| One-shot | Same input and output shape; we count; tips in a third call for the split variant | Agreed |
| Prompts | One source for all evaluation types | Agreed |
| Truncation in one call | Fail, no halving | Agreed |
| Pipelines | Library of steps + YAML | Agreed |
| Folders | One folder per evaluation type; protocols separate | Agreed |
| Eval reports | Library of metrics + charts + YAML | Agreed in principle |
| Report files | Collapse the 7 report files | Agreed |
| STT, voice, rating, scenarios | Move out of the engine | Agreed |
| Docs | Two earlier docs merged into this one | Done 2026-11-28 |
| Eval | Split into its own repo; staging stays | Agreed |

- [ ] Is Jev = TypeSafe Jev on OpenRouter? Is an alpha API and an extra vendor acceptable? Coder or checker?
- [ ] Per-volley calls: goal = speed, cost or accuracy? Can concurrency go above 8? What are the Gemini rate limits?
- [ ] Run `prepare.py` on real eval sessions to get the true volleys-per-session count.
- [ ] Eval: add per-volley, per-slot metrics next to the line metrics?
- [ ] Test stubs: Firestore emulator, or a small in-memory client?
- [ ] Constants: one file per package, or one shared?
- [ ] Should `voice/` stay in the `api` package or become its own service?
- [ ] `docs/agent_files/`: delete after merge, or move out of the main tree?
- [ ] Where does the rules file live: `AGENTS.md`, `.claude/` rules, or both?
- [ ] Pipeline YAML: one file per evaluation, or a base file + overrides?
