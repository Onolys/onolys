---
status: done
summary: Spikes - S1 PASS, S2 FAIL (owner decides), S3 PASS, S4 PARTIAL (owner decides), S5 keep two jobs
date: 2026-11-28
---
# Spikes report (phase 0) — 2026-11-28
Tools: firebase-tools 15.37.0 (needs Node 22), openjdk 21, Node 22.23.4. Snapshot sha 78fc3371 (no engine-v0 tag yet). All probes deleted; no product files changed; no fallback applied.

| # | Question | Result | Conf. | Gates |
|---|---|---|---|---|
| 1 | Auth emulator under vitest+jsdom | PASS — real createFirebaseAuthService: sign up/in/verify/out; 10 files parallel, 5 runs, 0 flakes, 4.6–7.5s vitest (8–12s wall) | high | 02, 08 |
| 2 | API verifier accepts emulator tokens | FAIL — prod uses custom IdTokenVerifier (RS256 only); emulator tokens are alg=none → InvalidToken. Admin verify_id_token accepts them. | high | 06, 08 |
| 3 | uv git-subdirectory deps w/ workspace=true | PASS — lock/sync/import of api+core+miti+oneshot at 78fc3371; lock has only git sources. Re-check at engine-v0. | ~95% | 03, 10 |
| 4 | firebase `--config` path resolution | PARTIAL — rules resolve beside `--config` (object or single-db array form). Current 3-db array firebase.json loads NO rules in emulator (today too). Deploy dry-run needs a real project; indexes unproven. | medium | 09 |
| 5 | Merge api unit+emulator CI jobs? | Keep two jobs — emulator tests 470/2675 (17.5%); merged ≈160–170s vs longest api job ≈117–126s | ~85% | 06 |

## Notes for later sub-projects
- 02: test helper must call `connectAuthEmulator(getAuth(initializeApp(cfg)), "http://127.0.0.1:9099")` before `createFirebaseAuthService`; `emailApi: null`; verification code from emulator REST oobCodes.
- 09/rules tests: emulator needs single-db config form, separate from the 3-db deploy config.

## Owner decisions needed
- S2 (gates 06, 08): (a) local/test-only verifier branch behind a setting (e.g. when FIREBASE_AUTH_EMULATOR_HOST set + env local/test → accept emulator tokens, check iss/aud); (b) shared RS256 signing stub via IdTokenVerifier's injectable fetch_certs (emulator not in token path).
- S4 (gates 09): (a) keep firebase.json at repo root, firebase/ holds rules+indexes only; (b) per-path overrides. Plus: verify deploy/indexes against real staging project in 09.
