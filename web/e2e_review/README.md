# e2e_review: Playwright regression suite (web/, main app)

Real-browser checks only (36 tests, 5 specs; trimmed in FX48). Behaviour already covered by vitest (auth pages, /auth/action, flows) is not repeated here. Specs assert the CORRECT behaviour. Finding IDs (E#, W#) in test names refer to the review findings; all were fixed (FX1-46). Findings: `docs/agent_files/review-full-app-20261121/findings-e2e.md`.

## Run (mock mode: MSW + fake auth, nothing else needed)

From `web/`:

```
npm run e2e                      # mock mode; add args after `--`, e.g. `npm run e2e -- login`
```

`@playwright/test` is a web devDependency (pinned to the preinstalled 1.65.1). Chromium is preinstalled on this machine; do not run `playwright install` here (CI does). The config starts `npm run dev:mock` on :5173 itself
(or reuses a server already there). Tests are independent and `fullyParallel`. CI runs them in the `web-e2e` job (`CI=1`: 2 workers, no retries, `github` reporter). Single spec: `npm run e2e -- login`.

## Projects

- `e2e` (dev:mock on :5173, no CSP): every spec except the two below.
- `csp` (`E2E_CSP_PORT`, default :4173): `csp.spec.cjs` (zero CSP violations) and `visual.spec.cjs` (light/dark screenshots to `test-results/shots/{light,dark}-*.png` + axe color-contrast/critical gate). Its webServer builds `--mode mock` into `node_modules/.cache/csp-preview` and runs `vite preview`, which serves the prod `firebase.json` CSP (`preview.headers` in `vite.config.ts`). Run one: `npm run e2e -- csp.spec --project=csp`. Waived axe screens go in `TODO` in `visual.spec.cjs`.

## Notes

- Open the app as `localhost`, not `127.0.0.1` (api CORS).
- Fake auth lives in page memory: a reload signs the user out, so specs navigate in-app (`spa()` helper) after login.
- Real Firebase Auth cannot be exercised (no auth emulator): invalid-email, missing-password, too-many-requests,
  valid `/auth/action` oobCodes, cross-tab sign-out and Google sign-in are not covered.
- Do not write logs/artifacts under `web/` outside `e2e_review/test-results/` (vite full-reloads the page on file changes,
  which signs fake-auth users out mid-test). Screenshots are off by default; `E2E_SHOTS=1` writes `test-results/shots/spec-*.png` (gitignored).
- Specs: signed-out (nav/guards by auth phase, back/reload), login (logout+back, `?next=`), signup (double submit, unverified phase), mobile (iPhone 13 horizontal scroll), session-flow (file precheck, double Start, unmount autosave, missing session, clipboard, interview page).
- Fixtures: `fixtures/ten-min.mp3` (10:30 sine), `one-min.wav`, `notaudio.txt`.
