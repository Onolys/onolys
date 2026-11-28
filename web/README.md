# web/ (main app)

React 19 + Vite + TypeScript. Scripts: `npm run dev:mock`, `npm run build`, `npm test`, `npm run lint`, `npm run typecheck`, `npm run e2e` (see `e2e_review/README.md`).

## Design system and sign-in (`@onolys/common`)

- Dependency: `git+https://github.com/Onolys/onolys-common.git#v0.4.0` (public repo, https, no SSH or token; the tag commit ships `dist/`, so install needs no build). Keep the lockfile `resolved` as `git+https://...`: after `npm i`, npm may rewrite it to `git+ssh://`; change it back and check `GIT_SSH_COMMAND=false npm ci` still works.
- It owns the theme, tokens, shared components, the account/theme/footer shell pieces and the whole sign-in feature (`@onolys/common/auth`, `/auth/firebase`, `/auth/testing`). This app keeps only `src/auth/createAuthService.ts` (wires the email routes into the Firebase service) and `src/auth/useApiClient.ts`.
- CSS entry: `src/styles/index.css` (cascade layers `theme, base, components, utilities`). Fonts come from `@onolys/common/theme.css`; keep `build.assetsInlineLimit` default so the font stays a `.woff2` file (CSP).
- `/theme-init.js` is not in this repo: `vite.config.ts` serves it in dev and emits it into the build from the installed package.
- Bump: `npm i git+https://github.com/Onolys/onolys-common.git#vX.Y.Z`, fix `resolved` as above, run tests and e2e.
- Local development against a checkout (do not commit): `npm i file:../../onolys-common` (path to your clone), run `npm run build:watch` there. npm symlinks it at `node_modules/@onolys/common`, and the existing `@source "../../node_modules/@onolys/common/dist"` follows that symlink. Restore the git spec and lockfile before committing.

## Sign-in in tests and mock mode

Unit tests (`npm test`) and mock mode (`npm run dev:mock`, the Playwright suite) use the real Firebase service against the Firebase Auth emulator (port 9099 in `api/firebase.json`); there is no fake auth mode. Run tests under the emulator:

```
firebase emulators:exec --only auth --config ../api/firebase.json --project demo-onolys "npm test"
```

Mock mode reads `VITE_FIREBASE_AUTH_EMULATOR_URL` from `.env.mock`; start the emulator first (`firebase emulators:start --only auth --config ../api/firebase.json --project demo-onolys`).
