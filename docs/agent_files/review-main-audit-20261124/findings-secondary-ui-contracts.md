# Stage 2D — admin UI (frontend/), eval/web, Firestore rules, cross-layer contracts (raw, pre-verification)

Commit 6ffbf63. No high/critical in scope.

## Commands
| Command | Result |
|---|---|
| frontend vitest | 47 passed; tsc clean |
| eval/web vitest | 73 passed; tsc clean |
| eval/backend pytest | 193 passed |
| app.openapi() vs api/openapi.json | identical |
| onolys_api.contracts --check | exit 0 |
| openapi-typescript vs web/src/api/schema.d.ts | identical |
| Firestore rules tests | not run (firestore-rules-test/node_modules missing, disk); static only |
| Playwright eval/web (vite 18710 + real eval FastAPI 18720 in-memory) | confirmed D1, D2, D3, D7; dataset run/cancel/summary/history/upload flows OK |
| Playwright admin shell | confirmed D6 |

## Findings
- D1 (medium) eval/web/src/api.ts:~70-74 reads only body.error.message; most eval backend errors are FastAPI {"detail": str|list} (SelectionError, RunTooLarge, rerun, options, /runs 404, 422s) → UI shows generic "Request failed (422)". List detail also echoes request input. Probe + browser. High.
- D2 (medium) dataset session without gold.json makes run uncreatable: create_run always appends `human` for dataset input → "Human requires gold" 422 even for [miti]; NewRun.tsx ignores has_gold. Probe. High.
- D3 (low-med) change_goal limit 10000 in uploads.py vs 4000 in RunRequest; no maxLength in NewRun; error panel offers useless "Reload choices". Probe + browser. High.
- D4 (medium) eval audio upload 300 MiB multipart to Cloud Run HTTP/1 (32 MiB cap, no h2c) → GFE 413 non-JSON, no CORS → "Failed to fetch"; whole file in memory, concurrency 4 / 2 GiB. Static. Medium.
- D5 (medium, config-dependent) eval/web/firebase.json CSP frame-src lacks authDomain host; config.ts defaults authDomain admin.onolys.com, deploy-eval.yml reuses ADMIN_STAGING_VITE_FIREBASE_AUTH_DOMAIN → Google sign-in iframe blocked. Static. Low-med.
- D6 (low) frontend/src/Shell.tsx:~25 treats any non-5xx as ok (200 HTML from SPA rewrite when VITE_ADMIN_API_URL missing, 404, 429 → "Nothing here yet."). Browser probe. High.
- D7 (low) eval/web Runs.tsx RunView poll and NewRun upload poll stop after one failed GET. Playwright. High.
- D8 (low) eval history silently capped at 100 runs (list_runs limit=100, no cursor). High.
- D9 (low, extends eval cancel item) cancel_requested not in SUMMARY_FIELDS; `cancelled` run status never produced but in TS RunStatus; UI shows "Cancel run" with no cancelling state for up to 840 s.
- D10 (low) openapi documents 403 only on /api-key ops; current_user can return 403 email_unverified everywhere. Doc gap, not drift.
- D11 (low) eval backend ADMIN_CORS_ORIGINS (infra/eval-services.tf) lacks localhost; no eval mock mode → local dev against staging fails CORS.
- D12 (low, = Codex H6) live listener toStatusDoc drops fields SessionPage.tsx:166 consumes.
- D13 (low) admin 403 always says "not on the admin list" even for email_verified=false.
- D14 (improvement) duplicated auth/authFetch in frontend/src/auth and eval/web/src/auth; frontend/index.html no viewport meta; eval history raw ISO created_at; accept="audio/*" broader than server allowed types.

## Rules / status-doc contract
Consistent: web reads only session_status/{sid}; API always writes uid; rules owner-only get/list, write false, catch-all deny. Deployed to staging and (default) DBs. Status doc has no PHI. State set matches web union (+ web-only upload_failed).
