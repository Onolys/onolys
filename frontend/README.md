# Admin frontend (admin.onolys.com)

Vite + React + strict TypeScript + Vitest. Sign-in, a 401/403 gate and one empty page ("Nothing here yet.").

After sign-in the shell calls `GET {VITE_ADMIN_API_URL}/v1/me` with the Firebase ID token. 401 returns to sign-in, 403 shows "Not allowed" (account not on the admin allowlist), a network error or 5xx shows a retry button.

The admin backend source and deployment workflow are retired. This frontend and its existing cloud resources remain in place; use mock mode for standalone local development. Shared evaluation auth now lives in [`eval/auth`](../eval/auth/pyproject.toml).

## Quickstart

```bash
npm ci
cp .env.example .env.local
VITE_MOCK=true npm run dev
```

Scripts: `npm run build`, `npm run preview`, `npm test`, `npm run typecheck`.

## Settings

| Variable | Meaning |
|---|---|
| `VITE_ADMIN_API_URL` | Admin backend origin, no path. |
| `VITE_MOCK` | Exactly `true`: no login gate, no backend call (local dev). |
| `VITE_AUTH_REQUIRED` | Exactly `true` (deployed build): login gate on. |
| `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_APP_ID` | Identity Platform web config. |

Hosting (`firebase.json`, `.firebaserc`) is unchanged; `src/hosting/hosting.test.ts` guards it.
