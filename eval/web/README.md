# Eval web

The allowlisted MITI 4.2.1 evaluation app. This independent Vite + React + TypeScript app signs in with the prod app's login (shared from `web/src/auth` via the `@prod-auth` alias, one copy; react/firebase are deduped to this package's `node_modules`); it always requires sign-in and checks backend access before showing evaluation inputs.

Run `npm ci`, then `npm run dev`. Configure `VITE_EVAL_API_URL` with the eval backend origin and the prod Firebase web-app values (auth domain `eval.onolys.com`) as `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, and `VITE_FIREBASE_APP_ID`. Put local values in `.env.local` (ignored). No auth bypass is available.

Run `npm test -- src/NewRun.test.tsx src/api.test.ts src/Root.test.tsx src/transport/authFetch.test.ts src/bundle.test.ts`, `npm run typecheck`, `npm run lint`, and `npm run build` for the new-run/auth checks. These tests use fake providers and API responses and make no paid calls.

The API contract is [api-ui-contract.md](../../docs/agent_files/feat-miti-eval-20261123-0026/05-eval-site/api-ui-contract.md). `NewRun` calls `onRunCreated(runId)` after successful creation. The root currently shows a creation confirmation; the run progress, comparison and history screens attach at that boundary.

Sign-up, email verification and password reset happen in the prod app (https://app.onolys.com); accounts need a verified email and a spot on the eval access list (a 403 shows a "No access" screen with sign out).
