---
status: done
summary: SP5 complete and reviewed PASS after two fix rounds; full branch review in progress
date: 2026-11-23
---
# Code Run — 2026-11-23 04:47 UTC — SP5 completion

Branch: feat/miti-eval   Scope: SP5   Review: e0aa5f2..d11ca6c

## Completed tasks

Evidence is supplied and verified by the orchestrator; this bookkeeping stage ran no tests.

| Task | Commit | Evidence |
|---|---|---|
| 1 — Backend/auth/config | 59146bc | 41 backend + 25 auth passed |
| 2 — Storage/prices | e2b898c | 48 backend passed; packaged prices verified |
| 3 — Options/catalog | b3aaca0 | 55 backend/auth passed |
| 4 — Uploads/transcription | b84eb23 | 85 backend passed |
| 5 — Background units | 0d3ca4d | 110 backend passed |
| 6 — Compare/history/rerun | 4bc6073 | 83 targeted passed; immutable saved-input reruns |
| 7 — Infra/apply | d8a224b | 18 infra passed; 19 new eval resources, one local-exec marker replacement; targeted plan clean, seven unrelated baseline drifts |
| 8 — Web/auth/New Run | 8f538eb | 31 tests plus types/lint/build; compact-lock fix b46a36c |
| 9 — Progress/compare/history | e481ac2 | 44 tests plus types/lint/build; cancel polling cfc4091, 18 focused passed |
| 10 — CI | 46eabb8 | 120 backend + 45 web; 83 CI scenarios; actionlint/key guard |
| 11 — Deploy/image guard | a911dff | Actual earlier full Dockerfile build; 119 runtime hashes; derivative auth/isolation smoke |
| 12 — Live smoke/docs | d11ca6c | 41 auth/app + 36 run/read + 29 upload passed; live browser defaults/count 104/compare/history/rerun/upload speaker pick |

## Live corrections and provenance

- `c005c59`: null/full-session dataset-span correction. `4808722`: normalize default English Google STT locale. Both corrected actual live failures with targeted regressions; exact details in `code-2026-11-23-task12.md`.
- Current staging revision `onolys-eval-backend-staging-00005-hfh`, source `48087223cc1d6564fe17c01aa23cc6c17be56345`, digest `sha256:241021e07e01bbe62a59ce7b5429e93015e6776e80bee9cf62e8557b363c5b74`; all 119 managed hashes match committed source.
- A full Dockerfile build succeeded earlier; a second full rebuild failed due to disk exhaustion. Subsequent explicitly authorized tiny derivatives changed runtime files/metadata on that verified filesystem. No second successful full rebuild is claimed.
- LLM cost $0.3452497 excludes STT and Kane. No further paid calls planned. Task credentials, proof helpers and disposable test accounts cleaned; existing authorized account verification remains as approved.

## Decisions / scope

Immutable one-shot config binding and internal class validated-marker bridge remain approved. Backend validates gold, engine selection and spans; reruns preserve snapshots. Private CASAA material/evidence stay outside Git. No diagnosis, clinical correctness or official MITI claim.

## Remaining review and acceptance limits

- SP5 reviewed PASS by all three personas after two fix rounds (ea9afe5, 789d4ff). Full branch three-persona review is in progress; final review fixes are not deployed.
- Gemini HTTP 402 blocks default-provider live acceptance; DNS/certificate pending; feature-only deploy workflow unregistered on default branch.
- Actual in-flight tab closure is unverified: Kane opened a fresh signed-out browser; no tab was closed before completion. API asynchronous completion alone is not that acceptance proof.
- See `code-2026-11-23-task12.md` for qualified acceptance matrix and private evidence locations.

## Review fix history

- Round 1 `ea9afe5`: recoverable pre-claim reads and safe execution-config SHA/version/model guards resolved; each correction had an observed red test first, then 43 backend and 20 web tests green, types/lint passed.
- Round-1 re-review NEEDS_CHANGES: UI spill test depended on output_ref stripped by actual detail projection; Bug Hunter and Architect agreed. Security reran only at final round.
- Round 2 `789d4ff`: omit only reference-backed null output placeholders in backend projection while hiding private paths; preserve inline values. Red 1 failed/5 passed; green 16 read + 20 web passed.
- Final three personas PASS. Full branch review range: cf3a2a2207fc3846a39b435b8ac01c28ac24e558..789d4ff.
- Live revision remains 00005-hfh/source4808722/digest241021e0…; review-fix redeploy pending.
