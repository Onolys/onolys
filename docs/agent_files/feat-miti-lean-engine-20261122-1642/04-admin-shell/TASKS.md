---
status: draft
summary: Strip admin backend to auth + GET /v1/me, frontend to sign-in + empty page, align Docker/CI/deploy scripts, then trim Terraform and apply.
date: 2026-11-22
---
# Tasks: SP04 Admin shell (login + empty page)

Source of truth: /root/projects/onolys/iaudit/.worktrees/feat/miti-lean-engine/docs/agent_files/feat-miti-lean-engine-20261122-1642/04-admin-shell/PRD.md. Admin keeps deploying and signing allowlisted users in, but carries no engine code. Backend tasks and frontend tasks are independent; CI/deploy alignment follows both; infra last.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | Backend: auth + `/v1/me` only | — | todo |
| 2 | Image: slim Dockerfile and image smoke | 1 | todo |
| 3 | Frontend: sign-in + empty-page shell | — | todo |
| 4 | CI and deploy scripts alignment | 1, 2, 3 | todo |
| 5 | Terraform: drop admin LLM secrets/routes, apply | 1 | todo |

## Task 1 — Backend: auth + `/v1/me` only
What it is: admin-backend stops being a gateway to eaudit/paudit and becomes a thin authenticated shell (R1, R2, R9, D1).
What changes at a high level: remove the eaudit mount, lifespan and paudit routes with their tests; dependencies shrink to admin-auth, fastapi, uvicorn (workspace sources for engines dropped); CORS then allowlist auth stay in the same order; add one `GET /v1/me` returning `{"status":"ok"}`. Tests are rewritten first around the new surface.
Done when: tests pass for 401 without token, 403 non-allowlisted/unverified, 200 allowlisted, preflight allowed/rejected origin, auth-off refused outside local/test, empty allowlist fails startup, and no eaudit/paudit routes; `ruff check admin/backend` is clean; no engine imports remain in `admin/`.

## Task 2 — Image: slim Dockerfile and image smoke
What it is: the admin container contains only python, admin/auth and admin/backend (R3, R8).
What changes at a high level: Dockerfile copies only the needed workspace manifests and syncs `--package onolys-admin-backend`; engines, protocols, config, contracts copies and their env vars go. Per the resolved default, copy every workspace member pyproject listed in the root at coding time. Dockerfile test and image smoke script switch to `/v1/me` 401, keep empty-allowlist refusal and no-eval-data check, drop the protocols-present check.
Done when: rewritten Dockerfile test passes (no forbidden COPYs, sync targets the admin package), the image builds, and `scripts/ci/test_admin_image.sh` passes.

## Task 3 — Frontend: sign-in + empty-page shell
What it is: `frontend/` keeps only auth, the 401/403 gate and one empty page (R4, R5, R6, D2, D3, D4).
What changes at a high level: new Shell calls `/v1/me` through the session fetch so non-allowlisted users hit "Not allowed", shows email, Sign out and "Nothing here yet", and retries on network error; with the gate off it renders with no call. Delete eval, paudit, review UI and the rest per R5, each only after a grep proves no kept file imports it; drop Ajv, aliases, proxy, validator script, eval/mock env vars; rename `VITE_AUDIT_URL` to `VITE_ADMIN_API_URL`; remove `.env.production`; rewrite README. Hosting config untouched.
Done when: Shell tests (200 renders, 403 forbidden, gate-off no fetch) written first and passing; `npm ci`, typecheck, tests and build pass; the built bundle has no Eval/paudit/claim strings; `hosting.test.ts` stays green.

## Task 4 — CI and deploy scripts alignment
What it is: pipeline triggers and checks match the slimmed admin (R7, R10).
What changes at a high level: deploy-admin workflow drops engine/protocol/contract trigger paths, builds with `VITE_ADMIN_API_URL`, smokes `/v1/me` only (expect 401); `changes.sh` admin-backend deps become admin-auth only and the frontend extra-path rule is removed; the matching script tests are updated first. Only admin/frontend lines are touched, leaving other siblings' package lists alone.
Done when: `test_deploy_admin.sh`, `test_changes.sh`, `test_changes_deps.py`, `test_hosting_targets.sh` pass; admin-backend no longer fires on engine paths and frontend no longer fires on paudit schemas; the AC1 `rg` check returns nothing.

## Task 5 — Terraform: drop admin LLM secrets/routes, apply
What it is: least privilege for the admin service now that it uses no LLM (R11, D5, D6, D7).
What changes at a high level: remove routes and LLM secret env blocks from `admin_backend`, the `admin_llm` IAM binding and its `depends_on`; api/worker keep theirs; allowlist secret, auth, CORS, hosting untouched. First grep that `check-staging.py` asserts LLM keys only for the worker (resolved default). Then run `terraform apply` for staging and prod; if credentials are missing, mark BLOCKED and continue.
Done when: `terraform validate` and plan show only the intended removals; apply succeeded (or recorded BLOCKED) and a follow-up plan is clean; deploy-admin smoke still shows the allowlist working.
