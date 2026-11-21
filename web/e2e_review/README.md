# e2e_review: Playwright regression suite (web/, main app)

Browser checks written during the full-app review (2026-11-21). Specs assert the CORRECT behaviour. Known bugs are
marked `test.fail(...)` with the finding ID (E#, and W# from `findings-web-static.md`); such a test shows as
passing-as-expected today and turns red ("expected to fail, but passed") once the bug is fixed, which is the cue to
delete its `test.fail` line. Findings: `docs/agent_files/review-full-app-20261121/findings-e2e.md`.

## Run (mock mode: MSW + fake auth, nothing else needed)

From `web/`:

```
npm run e2e                      # mock mode; add args after `--`, e.g. `npm run e2e -- login`
```

`@playwright/test` is a web devDependency (pinned to the preinstalled 1.65.1). Chromium is preinstalled on this machine; do not run `playwright install`. The config starts `npm run dev:mock` on :5173 itself
(or reuses a server already there). Tests are independent and `fullyParallel`, so a CI job can shard: `npm run e2e -- --shard=1/3`. Single spec: `npm run e2e -- login`.

## Live-ish mode

Start Firestore emulator + api (AUTH_MODE=fake, ADAPTERS=stub) as in `docs/testing/local-setup.md` (section "Main app (web + api)", mode B),
then run `E2E_MODE=live npm run e2e`; the config starts `npm run dev:live` with the right `VITE_*` env.
Only tests tagged `@live` (live.spec.cjs) run in that mode; everything else is mock-only and is the CI-intended set.
Stop emulator/api afterwards.

## Notes

- Open the app as `localhost`, not `127.0.0.1` (api CORS).
- Fake auth lives in page memory: a reload signs the user out, so specs navigate in-app (`spa()` helper) after login.
- Real Firebase Auth cannot be exercised (no auth emulator): invalid-email, missing-password, too-many-requests,
  valid `/auth/action` oobCodes, cross-tab sign-out and Google sign-in are not covered.
- Do not write logs/artifacts under `web/` outside `e2e_review/test-results/` (vite full-reloads the page on file changes,
  which signs fake-auth users out mid-test). Screenshots are off by default; `E2E_SHOTS=1` writes `test-results/shots/spec-*.png` (gitignored).
- Fixtures: `fixtures/ten-min.mp3` (10:30 sine), `one-min.wav`, `notaudio.txt`.
