---
status: draft
summary: Phase 0 spikes - five time-boxed probes (Auth emulator/vitest, Admin SDK/emulator tokens, uv git-subdir deps, firebase-tools --config, api CI merge) then one combined owner report.
date: 2026-11-28
---
# Tasks: Spikes (phase 0)

Source of truth: /root/projects/onolys/onolys/.worktrees/refactor/revamp/docs/agent_files/refactor-revamp-20261128-0102/spikes/PRD.md. Runs after 01, before 02. Probes are throw-away, live inside the package they test (never /tmp), touch no tracked product file, and are deleted before the report. Fallbacks are presented to the owner, never applied. CI already exists (.github/workflows/ci.yml); probes are not wired into it.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Preflight: tooling check | none | todo |
| 2 | Spike 1: Auth emulator under vitest + jsdom | 1 | todo |
| 3 | Spike 2: Admin SDK accepts emulator tokens | 1 | todo |
| 4 | Spike 3: uv git-subdirectory deps | 1 | todo |
| 5 | Spike 4: firebase-tools `--config` paths | 1 | todo |
| 6 | Spike 5: api tests vs Firestore emulator | 1 | todo |
| 7 | Cleanup and combined owner report | 2-6 | todo |

## Task 1 — Preflight: tooling check
What it is / what it means: Spikes 1, 2, 4 need firebase-tools and Java on the dev machine (PRD Manual steps). Confirm before any probe so a missing tool is not mistaken for a spike failure.
What changes at a high level: Nothing in the repo. Record tool versions, and the pre-revamp snapshot commit sha used by spike 3 (no `engine-v0` tag yet; PRD Risks).
Done when: `firebase --version` and `java -version` print versions; sha recorded; a missing tool is logged as an owner-only blocker and the dependent spikes are marked blocked, not failed.

## Task 2 — Spike 1: Auth emulator under vitest + jsdom
What it is / what it means: Question: does the Firebase Auth emulator work under vitest + jsdom? Gates 02 and 08 (O5).
What changes at a high level: In `web/`, add a scratch probe test that starts the emulator via `firebase emulators:exec --only auth` and drives the real `createFirebaseAuthService` through sign up, sign in, email verification (action code via emulator REST) and sign out. Then replicate across ~10 test files running in parallel. Record suite time.
Done when: all flows pass; 5 repeated runs show no flake; suite time reported (owner judges the threshold). On failure, capture evidence plus the PRD options: (a) logic-free `signedInService(user)` stub, (b) keep today's fake.

## Task 3 — Spike 2: Admin SDK accepts emulator tokens
What it is / what it means: Question: does `verify_id_token` accept Auth-emulator tokens? Gates 06 (O3) and 08.
What changes at a high level: In `api/`, a scratch probe mints a token from the running Auth emulator, sets `FIREBASE_AUTH_EMULATOR_HOST`, and calls the api's existing token verifier unchanged.
Done when: the probe (pytest or script inside `api/`) shows the verifier returning the expected uid with no production-path code change. On failure, record evidence and options: (a) local-only verifier branch behind a setting, (b) shared signing stub for combined mode.

## Task 4 — Spike 3: uv git-subdirectory deps
What it is / what it means: Question: does uv resolve git-subdirectory deps whose pyprojects use `workspace = true`? Gates 03 and 10 (P4). Confidence was ~75%.
What changes at a high level: In a scratch package inside the repo, add the four git sources at the recorded pre-revamp sha, run `uv lock`, `uv sync --frozen`, and import all four.
Done when: lock and sync succeed, all four imports work, and the lock has no path/workspace entries (grep of uv.lock). On failure, record the option: build wheels in CI from the tag and install from a path. Note that the check should be repeated once `engine-v0` exists (PRD Risks).

## Task 5 — Spike 4: firebase-tools `--config` paths
What it is / what it means: Question: do rules and indexes resolve relative to `--config firebase/firebase.json` rather than cwd? Gates 09.
What changes at a high level: Copy `firebase.json`, rules and indexes into a scratch `firebase/` folder; run `firebase emulators:exec --config firebase/firebase.json` and `firebase deploy --only firestore:rules --dry-run` from the repo root.
Done when: both commands find rules and indexes beside the config file (output captured). On failure, record options: keep `firebase.json` at repo root with `firebase/` for rules/indexes only, or per-path overrides.

## Task 6 — Spike 5: api tests vs Firestore emulator
What it is / what it means: Question: what share of api tests need the Firestore emulator, i.e. can the api CI jobs merge? Informs 06 (O1). This is an estimate from current tests; 06 re-checks later.
What changes at a high level: Count api tests by emulator marker/fixture usage and runtime on the current suite; estimate merged-job time against today's longest job in ci.yml. Read-only analysis.
Done when: counts, runtimes and the estimate are reported. Merge is recommended only if emulator tests are the majority and merged time stays within today's longest job; otherwise recommend keeping two jobs (unit, emulator).

## Task 7 — Cleanup and combined owner report
What it is / what it means: One report to the owner covering all five spikes (PRD Acceptance Criteria). Owner decides every fallback.
What changes at a high level: Delete all probe and scratch files; compose one message with, per spike: pass/fail, evidence (commands, counts), confidence, and options for any failure. State which of 02, 03, 06, 08, 09, 10 each result gates.
Done when: `git status` shows no probe or product file changes and no scratch files remain; the report contains all five spikes; no fallback was applied.

Owner-only: read the combined report and decide any fallback; install firebase-tools and Java if Task 1 flagged them missing.
