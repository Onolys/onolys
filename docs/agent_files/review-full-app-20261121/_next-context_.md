# Next context — review/full-app (updated 2026-11-22)

Read this first in the next session. The owner will fix the bugs themselves. Nothing is pushed.

## State
- Worktree: /root/projects/onolys/iaudit/.worktrees/review-full-app, branch `review/full-app` (local only, unpushed), rebased on origin/main d83e6be (PR #48).
- Review is DONE. App code is UNCHANGED (the partial FX1 edit to web/src/auth/next.ts was reverted). No bug fixes, by owner decision.
- The fix run (dev-code) was started then STOPPED by the owner: "no need to fix the bugs, just note them, I'll fix later".

## Files in this folder (docs/agent_files/review-full-app-20261121/)
- `FINDINGS.md`: the master list. 56 deduped rows FX1–FX56 grouped P0 (7) / P1 (17) / P2 (17) / owner decision (5, now resolved below) / test cleanup (10). It maps each owner UX decision to its FX rows. **Start here.**
- `review-2026-11-22-0100.md`: dev-review (Bug Hunter / Security / Architect) verdict NEEDS_CHANGES, plus the CI fit table for the test suites.
- Raw sources: `findings-web-static.md` (W1–32), `findings-api-static.md` (A1–24), `findings-e2e.md` (E1–24, screenshots in `e2e-shots/`), `findings-fuzz-mutation.md` (F1–9, mutation scores, M1–21).
- `RUN.md`: how to run the app locally (mock mode; live-ish mode = Firestore emulator + api stub adapters + fake auth; open at localhost:5173, not 127.0.0.1).

## Tests already added (committed on branch)
- Playwright suite `web/e2e_review/`: 78 specs (76 mock, 2 @live). Run with `cd web && npm run e2e -- --trace off`, about 1 min. Known bugs are marked `test.fail()` with their E#/W# id; remove the marker when the bug is fixed.
- API fuzz: `api/tests/test_fuzz_review.py`, `api/tests/test_schemathesis_smoke.py`. Already split per PR #48 (unit cases xdist-safe, emulator cases `firestore`-marked). Known bugs are strict xfail with their id.
- Web property tests: `web/src/__fuzz_review__/*.property.test.ts`, using `it.fails` for F5/F6/F7.
- Mutation configs: `[tool.mutmut]` in `api/pyproject.toml`, `web/stryker.conf.json`, plus the doc `docs/testing/fuzz-and-mutation.md` (manual/nightly only).
- New dev deps: hypothesis, schemathesis (api); fast-check, Stryker, @playwright/test 1.65.1 (web).

## Test-suite cleanup TODO (not done; FINDINGS FX47–FX51 + review AR5–AR7, N1–N3)
1. FX47/AR5: the e2e `shot()` helper writes 33 PNGs into tracked `docs/agent_files/.../e2e-shots/` on every run. Change it to take shots only when `E2E_SHOTS=1`, into `test-results/`. Move the RUN.md "Mode B" recipe into `docs/testing/local-setup.md` and repoint the README, `playwright.config.cjs` and fuzz-and-mutation.md.
2. FX48/AR6: trim Playwright from 76 to ~35. Keep only real-browser behaviour: nav by auth phase, back/forward/reload, mobile layout and horizontal scroll, real file-length precheck, E17 unmount autosave, E3 next crash, beforeunload. Delete the specs that duplicate vitest (auth-action.spec vs AuthAction.test.tsx; signup/login/forgot vs auth/pages.test.tsx; happy path/delete/sample vs flows/flows.test.tsx), the W17 spec (can't reproduce) and live.spec.cjs.
3. Add a `web-e2e` CI job in `.github/workflows/ci.yml`:
   - Triggers: `needs: changes`, `if: needs.changes.outputs.web == 'true'`, parallel to `web`.
   - Browser: cache `~/.cache/ms-playwright` keyed on the @playwright/test version, then `npx playwright install --with-deps chromium`.
   - Playwright config when CI is set: forbidOnly, retries 0, github reporter, @live excluded.
   - Workers 2; upload test-results/ on failure only; shard only if the run exceeds 3 min.
   - Blocking, about 2–3 min.
4. FX49/AR7: mark the A11/A23 race tests in `test_fuzz_review.py` (~:293, :304; currently non-strict xfail) `@pytest.mark.flaky` so they run in the non-blocking `api-flaky` job. Delete `test_isolation_random_ids_between_users` (~:325), which duplicates `test_isolation.py`.
5. FX50/N1/N3: pin fast-check and Stryker exactly (the repo pins exact versions). Consider dropping Stryker from devDeps and using `npx -p` (it adds ~2.3k lockfile lines to every CI npm ci). Re-encode the e2e audio fixtures (3.4 MB, mainly ten-min.mp3) to under 1 MB.
6. FX51/N2: Stryker `inPlace: true` mutates tracked files, so set it to false. Gitignore web/reports/, api/mutants/ and the dirs mutmut copies into api/. Fix the `[tool.mutmut]` comment, which points to a nonexistent tests/MUTATION.md.
7. FX52–56: add tests for surviving mutants (oidc.py has zero coverage; idtoken sub bounds; limits.py cap overrides; run.py release_once/report validation; guards; parseErrorBody). Best done together with the matching bug fix.
8. When each bug is fixed: remove its test.fail / xfail / it.fails marker.

## Owner UX decisions (MVP: keep simple, but prod-quality)
- D1 nav by auth state:
  - Signed out: Log in, Sign up, Sample report.
  - Signed in and verified: Sessions, New session, Settings, Sign out + email.
  - Unverified: Verify email + Sign out.
  - Loading: brand only.
- D2 signup: show-password toggle AND confirm-password field; keep the 8-char minimum.
- D3 after password reset: "Password updated", then the login page with email prefilled.
- D4 never-uploaded sessions: "Upload incomplete" with Resume upload + Delete.
- D5 Google sign-in on an email that has a password account: message "use your password".
- D6 interview reload: warn before leaving (beforeunload). If they leave, the interview ends; no rejoin. Basic design.
- D7 live status listener drop: auto-retry with backoff, then poll; show an error after a retry limit.
- D8 defaults:
  - Sample report public.
  - Signup says the email exists; forgot-password hides whether it exists.
  - Keep ?next through verify-email.
  - Dashboard auto-refreshes in-progress chips.
  - Forgot-password with a malformed email: "enter a valid email".
  - Keep it simple.

## Owner product decisions (FX42–46 resolved)
- FX42 n_runs: charge 1 unit per run (n_runs=3 costs 3 units; blocked if not enough left).
- FX43 presets: public allowlist. Users get the default Gemini preset only; claude via config/admin only; test-* presets in staging only.
- FX46 caps: ONE limit per user flow, nothing else.
  - AI interview: 1 unit at start, counted even if never rated. It covers rating its own recording (keep the A10 free first run, but bind the audio to the relay recording).
  - Upload flow: free until the user clicks "Run rating", then 1 unit. Plain session create or upload doesn't count.
  - Keep the <30s interview refund, capped at 3 refunds per user per day.
- FX45 rating: once submitted it's FINAL, with no edit and no "Run again".
  - A successful report is final.
  - A system failure (provider outage, worker crash) refunds the unit and shows "Try again", which re-runs the same submission.
  - A bad file shows "Upload a different file".
- FX44: keep A10, bind the audio.

## Other notes
- Nightly (`.github/workflows/nightly.yml`): green 15 of 15 runs, and the live test really runs. Owner: don't touch. Failing scheduled notifications come from other repos (crontick Security Audit, kyro Nightly); the owner chose not to fix those.
- The suggested fix order, when the owner wants it, is in FINDINGS.md: P0 first (FX1 auth phase/nav, FX2 rating data loss, FX3 stuck sessions, FX4 JWKS DoS, FX5 stale coded_span, FX6 Run-again dead end, FX7 live updates).
- Owner preferences: sub-agents on sonnet, max 2 concurrent, commit per task, CI time bounded and shardable, no test bloat.
