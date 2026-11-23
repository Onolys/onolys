# web/ (main app)

React 19 + Vite + TypeScript. Scripts: `npm run dev:mock`, `npm run build`, `npm test`, `npm run lint`, `npm run typecheck`, `npm run e2e` (see `e2e_review/README.md`).

## Design system (`@onolys/ui`)

- Dependency: `git+https://github.com/Onolys/onolys-ui.git#v0.1.0` (public repo, https, no SSH or token; the tag commit ships `dist/`, so install needs no build). Keep the lockfile `resolved` as `git+https://...`: after `npm i`, npm may rewrite it to `git+ssh://`; change it back and check `GIT_SSH_COMMAND=false npm ci` still works.
- CSS entry: `src/styles/index.css` (cascade layers `theme, base, legacy, components, utilities`; old app styles live in `legacy-app.css` inside the `legacy` layer). Fonts come from `@onolys/ui/theme.css`; keep `build.assetsInlineLimit` default so the font stays a `.woff2` file (CSP).
- Bump: `npm i git+https://github.com/Onolys/onolys-ui.git#vX.Y.Z`, fix `resolved` as above, run tests and e2e.
- Local development against a checkout (do not commit): `npm i file:../../onolys-ui` (path to your clone), run `npm run build:watch` there. npm symlinks it at `node_modules/@onolys/ui`, and the existing `@source "../../node_modules/@onolys/ui/dist"` follows that symlink (verified: identical CSS output), so no path change is needed. Restore the git spec and lockfile before committing.
