---
status: draft
summary: Strip admin.onolys.com to sign-in + an empty page; admin-backend drops eaudit/paudit and serves only GET /v1/me behind the existing allowlist auth; deploy pipeline, hosting and allowlist unchanged in shape.
date: 2026-11-22
---
# PRD: SP04 Admin shell (login + empty page)

Repo/branch: Onolys/onolys (local `iaudit`) / `feat/miti-lean-engine` · Depends on: none (SP05 depends on this) · Owns: `admin/backend/**`, `frontend/**`, `.github/workflows/deploy-admin.yml`, `scripts/ci/{test_admin_image.sh,test_deploy_admin.sh,changes.sh,test_changes.sh,test_changes_deps.py}`, admin jobs in `.github/workflows/ci.yml`, `infra/modules/environment/{services,secrets}.tf` (admin parts only)

## TL;DR
admin.onolys.com keeps deploying and signing allowlisted users in, then shows "Nothing here yet". `admin-backend` loses eaudit, paudit, core and every engine dependency; it keeps auth + CORS and gains one route, `GET /v1/me` (auth-gated, returns `{"status":"ok"}`), which the shell calls so a non-allowlisted account still gets the "Not allowed" screen. `frontend/` keeps its name; everything except sign-in, the 401/403 plumbing and one empty page is deleted. The Cloud Run service, Hosting site, allowlist secret and deploy workflow stay. LLM secrets/routes on the admin service are removed from Terraform.

## Problem
- Admin still mounts eaudit at `/` and serves `/v1/paudit*`; it imports `eaudit`, `onolys-core`, `onolys-paudit` [verified: `admin/backend/pyproject.toml`, `app.py`]. SP05 cannot delete those packages while admin depends on them (and `uv sync --frozen` in the Dockerfile would break).
- `frontend/` is the old review UI + eval UI + paudit tab (~150 files) and builds against `docs/contracts`, `eval/api`, `engines/paudit/schemas` via vite aliases [verified: `vite.config.ts`, `compile-validators.mjs`].
- Client-side "forbidden" is only set when a backend call returns 403 [verified: `frontend/src/auth/session.ts` `onForbidden`]. With no backend call, a signed-in non-allowlisted user would see the empty page.

## Goals / Non-Goals
**Goals:** admin deploys green with no engine code; allowlisted sign-in then empty page; non-allowlisted sees "Not allowed"; anonymous backend calls get 401; smaller image and CI; no dangling LLM secret access on the admin service.
**Non-goals:** new admin features; 2FA; rename of `frontend/`; changing `admin/auth` (middleware, verifier, allowlist secret); prod admin (still off, `admin_enabled["prod"]=false`); copying the old UI to the iaudit repo (SP05 tag, SP06 repo); deleting engines (SP05).

## Requirements
**R1 Backend app.** `create_app(env=None, verifier=None)` builds FastAPI with CORS (outermost) then `AdminAuthMiddleware`, unchanged order and config. No eaudit param, no mount, no lifespan. One route `GET /v1/me` → 200 `{"status":"ok"}`. Unknown paths 404 (after auth). No docs/openapi (as today).
**R2 Backend deletions.** Delete `paudit_routes.py`, `tests/test_paudit.py`; rewrite `tests/test_gateway.py` and `tests/test_dockerfile.py` (see R9). `pyproject.toml` deps = `onolys-admin-auth`, `fastapi`, `uvicorn` only; drop the `eaudit`/`onolys-core`/`onolys-paudit` `tool.uv.sources`; dev group drops nothing else. `__init__.py` exports updated.
**R3 Dockerfile.** Manifest layer copies only `pyproject.toml`, `uv.lock`, `admin/auth`, `admin/backend` pyprojects, plus `api/pyproject.toml` and any other workspace member manifests uv needs (until SP05/01 change membership; `--no-install-workspace` sync with `--package onolys-admin-backend`). Remove `COPY engines/*`, `protocols`, `config`, `docs/contracts`, and `PAUDIT_PROTOCOLS_DIR` / `IAUDIT_CONTRACTS_DIR` env. Keep `ENV=prod ADMIN_AUTH=on`, user, CMD. Header comments updated.
**R4 Frontend shell.** Keep: `src/auth/**` (firebase, session, AuthGate, gate, types, fakeProvider + tests), `src/transport/authFetch.ts` (+ test, + whatever it imports), `src/tokens/**`, `src/hosting/hosting.test.ts`, `main.tsx`, `Root.tsx`, `config.ts` (trimmed), minimal `app.css`. New `Shell.tsx`: on mount calls `GET {VITE_ADMIN_API_URL}/v1/me` via `session.createFetch()`; 200 → shows header (signed-in email, existing Sign out) + "Nothing here yet."; 401/403 handled by existing gate; network error → small retry message. With gate off (local dev/`VITE_MOCK`) the shell renders directly, no call.
**R5 Frontend deletions.** Delete `eval/`, `paudit/`, `claim-detail/`, `contract/`, `app/` (review UI), `fixtures/`, `e2e/`, `utils/`, `EauditApp.tsx`, `products*.ts`, `productViews.ts`, `App*.test.tsx`, `eval-schema.test.ts`, `contracts.test.ts`, `transport/*` except authFetch (+errors if imported), `scripts/compile-validators.mjs`, `src/generated` handling. `package.json`: drop `ajv`, `pre*` hooks, rename `name` to `onolys-admin-frontend`. `vite.config.ts`/`tsconfig.json`: drop `@contracts`, `@eval-api`, `@paudit-schema` aliases and `/eval-api` proxy. `config.ts`/`env.d.ts`/`.env.example`: drop eval, mock-audit vars; `VITE_AUDIT_URL` becomes `VITE_ADMIN_API_URL` (origin only). Delete `.env.production` (its only content is `VITE_EVAL_ENABLED=false`). Rewrite `frontend/README.md`. Each deletion must be preceded by a grep proving no kept file imports it; `npm run typecheck && npm test` is the gate.
**R6 Hosting config.** `firebase.json` and `.firebaserc` unchanged (targets `admin`, `admin-staging`, CSP incl. `__ADMIN_BACKEND_ORIGIN__` placeholder, still needed for `/v1/me`). `hosting.test.ts` stays green.
**R7 Deploy workflow.** `deploy-admin.yml`: trigger paths drop `engines/**`, `protocols/**`, `docs/contracts/**` (keep `admin/**`, `frontend/**`, `pyproject.toml`, `uv.lock`, `.dockerignore`, workflow files); build env sets `VITE_ADMIN_API_URL=<backend url>` instead of `VITE_AUDIT_URL`; smoke loop = `/v1/me` only (expect 401); image-smoke step text "no eval data" kept as a cheap guard. `test_deploy_admin.sh` updated to match (paths list, `VITE_ADMIN_API_URL`); its prod-absent, WIF, 401, `set_admin_origin.sh` checks unchanged.
**R8 Image smoke.** `test_admin_image.sh`: anonymous `/healthz` stays 401; second probe becomes `/v1/me` -> 401; empty-allowlist refusal unchanged; no-eval-data `find` kept (drop the `/protocols` exclusions); delete the "protocols pack present" check.
**R9 Tests.** Backend: `/v1/me` 401 without token, 403 non-allowlisted/unverified, 200 allowlisted (reuse `keys` fixture), preflight allowed origin / rejected origin, `ADMIN_AUTH=off` refused outside local/test, empty allowlist fails startup, no `/v1/audit` or `/v1/paudit*` route (404/401). `test_dockerfile.py` becomes: no `COPY engines|protocols|config|docs/contracts`, `uv sync` targets `onolys-admin-backend`. Frontend: Shell renders for 200, forbidden on 403, no fetch when gate off.
**R10 CI scripts.** `changes.sh`: `DEPS` `admin-backend:admin-auth`; `ADMIN_BACKEND_EXTRA_RE='^(admin/auth/|\.dockerignore)'`; delete `FRONTEND_EXTRA_RE` and its use. `test_changes.sh` expectations updated (admin-backend no longer fires on eaudit/paudit/protocols paths; frontend no longer fires on `engines/paudit/schemas/**`). `test_changes_deps.py` needs no logic change (it reads pyprojects). `ci.yml` job definitions for admin-auth/admin-backend/frontend unchanged; `npm run typecheck`/`npm test` still exist.
**R11 Infra (Terraform).** Remove from `admin_backend` service the `routes_env` and `llm_secrets` env blocks; remove `admin_llm` IAM bindings and its `depends_on`. Keep `ADMIN_ALLOWED_EMAILS` secret + `admin_emails` IAM, `ADMIN_AUTH*`, CORS, `allUsers` invoker, SA, Hosting site/domain, Firebase web app, authorized domains. Optional trim (timeout 130s, 1Gi) left alone.

## Architecture
```
Browser admin.onolys.com ── Firebase Hosting (admin-staging; static frontend/dist)
  ├─ Firebase Auth sign-in (email/password, Google)   [unchanged]
  └─ Bearer ID token ──► Cloud Run onolys-admin-backend-staging
                           CORS -> AdminAuthMiddleware(allowlist from secret) -> GET /v1/me
Image: python + admin/auth + admin/backend only. No engines, protocols, config, contracts.
```
Shared files touched by other SPs: `uv.lock` and root `pyproject.toml` (SP01 adds `engines/miti`, SP05 removes members), `.github/workflows/ci.yml` and `scripts/ci/changes.sh`/`test_changes.sh` (SP01/05 edit package lists; this SP touches only admin/frontend lines), `.dockerignore`, `docs/reference/backend-api.md` + `review-ui.md`/`eval-ui.md` (SP05 owns doc cleanup; this SP only rewrites `frontend/README.md`).

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | Remaining endpoint | `GET /v1/me` behind auth, body `{"status":"ok"}` | No endpoint (shell static); `/v1/me` returning email via middleware change | Without a call the allowlist is not visible to the user [verified: session.ts]. Email comes from the Firebase user client-side, so `admin/auth` stays untouched |
| D2 | Folder name | Keep `frontend/` | Rename `admin/web` | Rename touches deploy-admin (paths, 3 `working-directory`/cache paths, `--config`), ci.yml, `changes.sh`, `test_hosting_targets.sh` (loops `web frontend`), `.firebaserc` lookup, docs. No value for "ship fast"; revisit if SP06 wants it |
| D3 | Frontend strip | Delete code, rely on git history/`iaudit-archive` tag (SP05) | Keep behind a flag; move to `legacy/` | Locked decision; flags keep Ajv, aliases and cross-folder imports alive and block SP05 |
| D4 | Env var | Rename `VITE_AUDIT_URL` -> `VITE_ADMIN_API_URL`, origin only | Keep old name | Old name meant the eaudit endpoint; the variable is internal to the workflow, cheap |
| D5 | Infra LLM secrets/routes | Remove from admin service now | Leave until later | Least privilege; unused after R1; small diff. `llm_secrets` variable itself stays (api/worker use it) |
| D6 | Order of infra vs code | Merge/deploy code first, `terraform apply` after | Apply first | Old image still reads `ANTHROPIC_API_KEY`/routes until replaced; applying first could crash it |
| D7 | Prod admin | Unchanged (off) | Remove prod admin TF | Out of scope; already gated by `admin_enabled` |

## Manual steps (owner)
- `terraform apply` for R11 after the deploy-admin run on `main` succeeds (affects only the staging admin service; no secret values change).
- Confirm one allowlisted login and one non-allowlisted login on admin.onolys.com after deploy (no new repo variables are needed; existing `ADMIN_STAGING_VITE_FIREBASE_*` stay).

## Risks / Open Questions
- [RESOLVED: keep `frontend/` name, D2]
- [RESOLVED: `/v1/me` returns no email; no `admin/auth` change, D1]
- [OPEN] Does `infra/scripts/check-staging.py` or its tests assert admin env contains LLM keys/`ROUTES_FILE`? Grep showed LLM keys only for the worker (`worker_env_problems`); implementer must confirm before R11.
- [OPEN] Other uv workspace manifests the Dockerfile layer must still COPY (`uv sync --frozen` needs every member's pyproject). Depends on whether SP01 lands first; implementer re-reads root `pyproject.toml` at coding time.
- [OPEN] `uv.lock` will change (admin-backend deps shrink); rebase conflicts with SP01 likely. Mitigation: regenerate with `uv lock` after rebase, never hand-merge.
- [DEFERRED] Trim Cloud Run timeout/memory of admin service; rename `frontend/`; session email display; prod admin.
- Risk: removing `docs/contracts` copy while web/api still use it is safe (only the admin image drops it); `.dockerignore` stays shared.

## Acceptance Criteria
1. `rg -n "eaudit|paudit|onolys_core|onolys-core" admin/ frontend/ scripts/ci/test_admin_image.sh scripts/ci/test_deploy_admin.sh .github/workflows/deploy-admin.yml` returns nothing; `uv sync --frozen --package onolys-admin-backend` installs no engine package.
2. Backend tests (R9) pass; `ruff check admin/backend` clean.
3. Image builds from the new Dockerfile; `bash scripts/ci/test_admin_image.sh` passes (anonymous `/v1/me` 401, empty allowlist refused).
4. `cd frontend && npm ci && npm run typecheck && npm test && npm run build` pass; `dist` contains no eval/paudit/review strings (grep the bundle for `Eval`, `paudit`, `claim`).
5. `bash scripts/ci/test_changes.sh`, `python3 scripts/ci/test_changes_deps.py`, `bash scripts/ci/test_deploy_admin.sh`, `bash scripts/ci/test_hosting_targets.sh` pass.
6. Staging after merge: deploy-admin green (build, smoke, site, anonymous `/v1/me` 401); allowlisted account sees "Nothing here yet"; non-allowlisted sees "Not allowed"; anonymous visitor sees sign-in.
7. After the infra apply, `admin_backend` has no LLM/`ROUTES_FILE` env and no `admin_llm` IAM; allowlist access still works.
