---
status: draft
summary: Phase 0 spikes run before 02 starts - five time-boxed checks (Auth emulator under vitest, Admin SDK with emulator tokens, uv git-subdirectory deps, firebase-tools --config paths, api CI job merge); one combined report to the owner, who decides any fallback.
date: 2026-11-28
---
# PRD: Spikes (phase 0)

Repo/branch: Onolys/onolys / `refactor/revamp` (probes only, never merged) · Depends on: 01 (legacy purge) · Runs before: 02, and gates 03, 06, 08, 09, 10 as listed · Owns: throw-away probe scripts inside the package they test (never `/tmp`), deleted after the report. Does not own: any product change, any fallback.

## TL;DR
Five assumptions carry real cost if wrong, and each is cheap to test now. Run all five once, in phase 0 (after 01, before 02), and send the owner ONE combined report: result, evidence, confidence, and for any failure the options below. The owner decides every fallback; nothing is applied automatically.

## Problem
| Gap | Evidence |
|---|---|
| 02 and 08 assume the Firebase Auth emulator works under vitest + jsdom | [unverified, ~80% confident] |
| 06 and 08 assume the Admin SDK `verify_id_token` accepts Auth-emulator tokens | [unverified] |
| 03 and 10 (P4) assume uv resolves git-subdirectory deps whose pyprojects use `workspace = true` | [unverified, ~75% confident] |
| 09 assumes firebase-tools resolves rules/indexes relative to `--config firebase/firebase.json` | [unverified] |
| 06 O1 (merge api CI jobs) depends on how many api tests need the Firestore emulator | [unverified; estimate from current tests] |

## Goals / Non-Goals
**Goals:** five pass/fail answers with evidence; one report; options ready if a spike fails.
**Non-goals:** implementing any fallback; touching product code; deciding for the owner.

## Requirements
Each spike: question, test (probe scripts live inside the package they probe), pass criterion, options to present on failure.
| # | Question | How to test | Pass criterion | Options if it fails (owner decides) | Gates |
|---|---|---|---|---|---|
| 1 | Does the Firebase Auth emulator work under vitest + jsdom? | In `web/`, probe test: start emulator (`firebase emulators:exec --only auth`), run real `createFirebaseAuthService` against it (sign up, sign in, verify via action code from emulator REST, sign out); repeat across ~10 files in parallel | all flows pass; no flake in 5 repeated runs; suite time acceptable (owner threshold: reported, not fixed) | (a) logic-free `signedInService(user)` stub for incidental tests, emulator only for flows (bends rule 9); (b) keep today's fake for now | 02, 08 (O5) |
| 2 | Does Admin SDK `verify_id_token` accept Auth-emulator tokens? | In `api/`, probe: mint token via emulator, set `FIREBASE_AUTH_EMULATOR_HOST`, call the api's token verifier | verifier returns the uid; no production-path code change | (a) local-only verifier branch behind a setting; (b) shared signing stub for combined mode | 06 (O3), 08 |
| 3 | Does uv resolve git-subdirectory deps whose pyprojects use `workspace = true`? | In a scratch package inside the repo, add the four git sources at the pre-revamp tag (use a commit sha until `engine-v0` exists); `uv lock`, `uv sync --frozen`, import all four | lock and sync succeed; imports work; no path/workspace entries in the lock | build wheels in CI from the tag and install from a path | 03, 10 (P4) |
| 4 | Does firebase-tools resolve rules and indexes relative to `--config firebase/firebase.json`? | Copy `firebase.json` + rules + indexes into a scratch `firebase/` folder; run `firebase emulators:exec --config firebase/firebase.json` and `firebase deploy --only firestore:rules --dry-run` | rules and indexes found beside the config file, not the cwd | keep `firebase.json` at repo root with `firebase/` holding rules/indexes only; or per-path overrides | 09 |
| 5 | What share of api tests need the Firestore emulator (can the api CI jobs merge)? | Count tests by emulator marker/fixture usage and runtime on the current suite; estimate merged job time | numbers reported; merge recommended if emulator tests are the majority and job time stays within today's longest job | keep two jobs (unit, emulator) | 06 (O1) |

## Architecture
Probes are run one after another or two at a time. A probe never edits tracked product files; it adds scratch files under the package it tests and removes them before the report. The report is one message to the owner: per spike result, evidence (commands, counts), confidence, and, if failed, the options column above.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| 1 | When | Phase 0, once, after 01 and before 02 | Each SP runs its own spike first | One report, owner decides once, later SPs start unblocked |
| 2 | Fallbacks | Presented, never auto-applied | Auto fallback | Owner decision (2026-11-28) |
| 3 | Probe location | Inside the package under test | `/tmp` | Dependencies and configs resolve as in real use |

## Manual steps
- Owner reads the combined report and decides any fallback.
- Dev machine needs `firebase-tools` and Java (spikes 1, 2, 4).

## Risks / Open Questions
- Risk: spike 3 may need `engine-v0` which 03 creates; use a commit sha of the pre-revamp snapshot and re-check after the tag exists.
- Risk: spike 5 is an estimate from current tests; 06 re-checks after the data layer lands.

## Acceptance Criteria
- One report to the owner covers all five spikes with pass/fail, evidence, and options for each failure.
- No probe file remains in the tree; no product file changed.
- 02, 03, 06, 08, 09, 10 reference the report result before they start.
