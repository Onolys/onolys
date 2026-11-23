---
stage: brainstorm
status: draft
summary: MITI eval site (eval.onolys.com), transcript.v1 + upload, engines/core, one-shot engine; CASAA first dataset
date: 2026-11-23
---
# MITI eval site, transcript upload, engine core + one-shot engine

## TL;DR
Build an internal eval site at eval.onolys.com (staging, same email allowlist as admin) where you pick a stored dataset and an engine, run it, and see our MITI coding side by side with expert human coding. First dataset: CASAA (UNM, MITI 4.2.1, 8 sessions from 2013 series). Alongside: a shared transcript format `transcript.v1` with transcript upload in the main app, an `engines/core` package with a common engine interface, and a generic `oneshot` engine (one model call: transcript + instructions + output schema), so lean MITI vs one-shot vs human can be compared.

## Problem
We do not know how close Onolys' MITI 4.2.1 coding is to expert human coders. Public coded datasets exist (see Drive doc "MITI Datasets"), but they come as transcripts, not audio, and the app only accepts audio. We also want to try other engine styles (one-shot now, e.g. ADHD later) without duplicating plumbing. Users of the eval site: the founders only.

## Decision log
| Decision | Alternative rejected | Why |
|---|---|---|
| First dataset = CASAA 2013 series (8 sessions, MITI 4.2.1) (user) | MI-TAGS sample CSV, AnnoMI | Same MITI version, made by MITI authors |
| Same repo Onolys/onolys (user) | Separate repo | Eval imports engines, reuses admin auth + infra |
| Host at eval.onolys.com (user) | Page inside admin.onolys.com | User choice |
| Access = same allowlist as admin (`admin_allowed_emails`), reuse `onolys_admin_auth` (user) | Separate eval allowlist | Simpler, same people |
| Staging only (user) | Prod | Matches admin |
| Code full session by default; dataset may specify a window (user) | Engine's own seeded window | Compare like with like vs human coding |
| API param `coded_span` accepts `{start_ms,end_ms}` or `{start_turn,end_turn}`; absent = full transcript (user) | Time-only | CASAA transcripts have no timestamps |
| Datasets stored in private GCS bucket (staging); repo holds only download/convert scripts + format spec; site lists datasets (user) | Commit data to git | Repo is PUBLIC; CASAA reuse terms unclear |
| Transcript format `transcript.v1` = engine `Turn` shape (Claude's call, user delegated) | New format | Engine already uses it |
| STT output saved as `transcript.v1`; no migration — no real transcripts exist and breaking changes are acceptable, product has no users (user) | Migrate old data | Nothing to migrate |
| Transcript upload in main app app.onolys.com + API (user) | Eval site only | Users can submit transcripts |
| Upload accepts .json (`transcript.v1`) and .txt (`T:`/`C:` or `Name:` prefixes), counts as 1 session against usage limits, same as a normal audio session (user); speaker gate runs if roles missing (user accepted default) | PDF/DOCX | Keep small |
| Gold format stores session-level codes + optional per-utterance codes; compare session-level now (user) | Utterance alignment now | Alignment is extra work |
| Compare: behavior counts, 4 globals, summary scores (R:Q, %CR), per-session diff + average error (user) | — | — |
| Save every eval run (dataset, engine, engine git sha, preset/model, date, results) in staging Firestore (user) | Ephemeral | Track accuracy over engine changes |
| Preset dropdown defaulting to prod preset; 1 run per session, option 3 (user) | — | — |
| No cost cap; show tokens + rough $ after run (user) | Hard cap | User choice |
| CLI spike first: 1 CASAA session through lean engine, print comparison, before building site (user) | Site first | Cheapest check |
| `engines/core` = engine-agnostic basics only, no MITI-specific code (user) | Put MITI shared bits in core | Future engines (oneshot, adhd) |
| Common engine interface: base class with overridable `run(ctx, transcript, params) -> output` + declared output schema; API picks engine by name from a registry (user liked override approach) | Ad hoc per-engine entrypoints | Plug-in engines |
| `oneshot` engine generic: inputs (transcript.v1 etc.) + instructions + output schema -> one model call (user) | MITI-specific | Reusable for any task |
| "MITI one-shot" config = MITI instructions + same MITI report schema as lean engine, versioned in repo `engines/oneshot/configs/miti/`, picked by name, not UI-editable (user) | UI-editable prompts | Comparable output, simple |
| Output validated in API layer with core validator for all engines; on failure retry once with validation errors + stronger schema-conformance instruction, then fail run (user) | Engine-only validation | One validation path |
| Lean MITI engine internal checks kept; API validation added on top (Claude's call) | Rewrite engine validation | Don't break working code |
| One-shot available on eval site only (user) | Main app | Experimental |
| Eval backend = own Cloud Run service `eval/backend`, reusing `onolys_admin_auth` and `admin_allowed_emails`; runs execute in background, site polls (Claude's call) | Extend `admin/` backend | Long runs, separate scaling |
| `coded_span` support is an intended engine change in SP1; 'no behavior change' applies only to core extraction (Claude's call) | — | Clarifies anti-goal |
| `.txt` uploads with `Name:` prefixes use the existing speaker gate to pick the clinician (Claude's call) | New UI | Reuse |
| Gold schema and metrics (MAE per behavior code and per global; R:Q and %CR computed with the same formula for gold and ours) defined in SP2 (Claude's call) | — | — |
| Dataset size not a concern; add MI-TAGS later (user) | — | Owner task: submit MI-TAGS access form |

## Design — sub-projects (in order; 1 and 2 may run in parallel)
| # | Sub-project | Contents |
|---|---|---|
| 1 | Transcript format + upload | `transcript.v1` spec + JSON schema; STT writes it; .txt/.json upload in API + web (app.onolys.com); `coded_span` param (time or turn range) |
| 2 | CASAA data + CLI spike | Download CASAA 8 MITI 4.2.1 sessions (uncoded + coded PDFs from casaa.unm.edu/tools/miti.html), convert to `transcript.v1` + gold format, upload to private GCS bucket; CLI runs lean engine on 1 session (full span) and prints ours vs gold |
| 3 | `engines/core` | Extract engine-agnostic pieces from `engines/miti` (transcript types, LLM client + route presets, RunContext/progress, PHI-safe logging, schema validation helper); define engine base class + registry; miti engine adopts it without behavior change |
| 4 | `engines/oneshot` + API validation | Generic one-shot engine, MITI one-shot config, API-layer validation + retry-with-errors |
| 5 | Eval site | eval.onolys.com (Firebase hosting site + domain + CORS), backend reusing admin auth + allowlist, dataset list from bucket, run (dataset × engine × preset × n_runs), compare table, run history, token/$ display |

Existing facts: engine entry `run_miti(ctx, transcript, speaker_map, params, progress_cb)`; `Turn{id, speaker, text, start_ms?, end_ms?, role?, language?}`; admin shell = `admin/` (FastAPI + `onolys_admin_auth`, secret `admin_allowed_emails`), admin.onolys.com, staging only; `eval/` currently holds only untracked `__pycache__` leftovers.

## Goals, non-goals, anti-goals
- Goals: pick CASAA on eval site, run lean or one-shot, see per-session and average agreement vs human; transcripts uploadable in main app; new engines plug in via core interface.
- Non-goals: utterance-level alignment metrics; MI-TAGS/AnnoMI now; one-shot in main app; UI prompt editing; prod eval.
- Anti-goals: dataset files committed to the public repo; lean MITI engine behavior changing during core extraction; eval site reachable by anyone off the allowlist.

## Open risks
| Risk | Cheapest test |
|---|---|
| CASAA PDF parsing loses speaker/turn boundaries | Convert 1 session in SP2 spike, eyeball |
| Lean engine far off gold | SP2 CLI spike before building site |
| Core extraction changes MITI output | Golden fixture tests (`engines/miti/tests/test_golden.py`) must pass unchanged |
| CASAA licence for commercial AI use unclear | Internal-only use, private bucket; owner to confirm terms |
| Breaking API/contract changes | Acceptable: no users yet (user) |

## Owner tasks
- Confirm CASAA reuse terms. Submit MI-TAGS access form (later). DNS for eval.onolys.com if not automatable.
