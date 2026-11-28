# e2e_review: Playwright regression suite (web/, main app)

Real-browser checks only. Behaviour already covered by vitest (auth pages, /auth/action, flows) is not repeated here. Specs assert the CORRECT behaviour. Finding IDs (E#, W#) in test names refer to the review findings; all were fixed (FX1-46). Findings: `docs/agent_files/review-full-app-20261121/findings-e2e.md`.

## Run (mock mode: MSW for the API, the Firebase Auth emulator for sign-in)

From `web/`, with the Auth emulator up (port 9099 in `api/firebase.json`; `.env.mock` points the app at it). Either wrap the run:

```
firebase emulators:exec --only auth --config ../api/firebase.json --project demo-onolys "npm run e2e"   # add args after `--`, e.g. `npm run e2e -- login`
```

or start `firebase emulators:start --only auth --config ../api/firebase.json --project demo-onolys` once and run `npm run e2e`. Each spec signs up its own fresh user through the app; `verifyEmail()` in `helpers.cjs` follows the verification link out of band through the emulator's REST API.

`@playwright/test` is a web devDependency (pinned to the preinstalled 1.65.1). Chromium is preinstalled on this machine; do not run `playwright install` here (CI does). The config starts `npm run dev:mock` on :5173 itself
(or reuses a server already there). Tests are independent and `fullyParallel`. CI runs them in the `web-e2e` job (`CI=1`: 2 workers, no retries, `github` reporter). Single spec: `npm run e2e -- login`.

## Projects

- `e2e` (dev:mock on :5173, no CSP): every spec except the two below.
- `csp` (`E2E_CSP_PORT`, default :4173): `csp.spec.cjs` (zero CSP violations) and `visual.spec.cjs` (light/dark screenshots to `test-results/shots/{light,dark}-*.png` + axe color-contrast/critical gate). Its webServer builds `--mode mock` into `node_modules/.cache/csp-preview` and runs `vite preview`, which serves the prod `firebase.json` CSP (`preview.headers` in `vite.config.ts`). Run one: `npm run e2e -- csp.spec --project=csp`. Waived axe screens go in `TODO` in `visual.spec.cjs`.

## Notes

- Open the app as `localhost`, not `127.0.0.1` (api CORS).
- Specs navigate in-app (`spa()` helper) after login: a full reload restarts the app and drops the mock backend's state (the signed-in user itself survives it).
- Not covered here: `/auth/action` oobCodes, cross-tab sign-out and Google sign-in (the unit suite covers the auth pages on the same emulator).
- Do not write logs/artifacts under `web/` outside `e2e_review/test-results/` (vite full-reloads the page on file changes,
  which restarts the app mid-test). Screenshots are off by default; `E2E_SHOTS=1` writes `test-results/shots/spec-*.png` (gitignored).
- Specs: signed-out (nav/guards by auth phase, back/reload), login (logout+back, `?next=`), signup (double submit, unverified phase), mobile (iPhone 13 horizontal scroll), session-flow (file precheck, double Start, unmount autosave, missing session, clipboard, interview page).
- Fixtures: `fixtures/ten-min.mp3` (10:30 sine), `one-min.wav`, `notaudio.txt`.

## CI tiers

PRs use `npm run e2e -- --config e2e_review/playwright.smoke.config.cjs`: nine existing Chromium cases, including production CSP, focus, native dialog and auth/upload sentinels. Both servers start intentionally because the CSP sentinel needs the built app. Main candidates and nightly retain the complete suite. Nightly also runs the full suite with `E2E_BROWSER=firefox` and `E2E_BROWSER=webkit`; those jobs install their pinned Playwright browsers and system dependencies. Firefox retains the mobile viewport/touch checks with `isMobile: false`, since that browser does not support Playwright's mobile emulation flag. Clipboard permission grants apply only to Chromium; other engines use the Copy button's user activation.
