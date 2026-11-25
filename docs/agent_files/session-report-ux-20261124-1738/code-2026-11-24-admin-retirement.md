---
status: done
summary: Retired admin source and deployment automation while preserving evaluation auth and existing resources.
date: 2026-11-24
---

# Admin source retirement

Removed the admin backend, its deployment workflow, exclusive image/origin guards and the obsolete root local launcher. Relocated auth source, tests and package metadata byte-for-byte to `eval/auth`; Python imports and project name are unchanged. Updated workspace lock, both image inputs, CI routing/required checks, evaluation deployment inputs, preview triggers and active docs. Historical ADRs remain unchanged.

Verification:

- Retirement regression failed before implementation and passes afterwards.
- `uv lock --offline` could not resolve uncached google-auth metadata; `uv lock` succeeded and changed only admin-backend removal and the auth path.
- `uv sync --offline --frozen --all-packages`: checked 124 packages.
- `LITELLM_LOCAL_MODEL_COST_MAP=True MITI_LLM_RECORD=0 uv run --no-sync --package onolys-eval-backend pytest eval/auth eval/backend -m 'not live' -q`: 284 passed, 2 deselected.
- `LITELLM_LOCAL_MODEL_COST_MAP=True uv run --no-sync --package onolys-api pytest api/tests/test_dev_script_and_image.py -q`: 10 passed.
- `uv run --no-sync --package onolys-admin-auth pytest infra/scripts/test_admin_env_wiring.py -q`: 2 passed.
- Auth ruff, CI routing/dependencies/required gate, deploy-eval image/context guard, preview/Hosting guards, links/docs scope and actionlint passed.
- Compared relocated auth source/tests/manifest bytes against commit 7f238a3: unchanged.
- Docker daemon is available; only prior eval images are cached, with no build cache or Python base image. New image builds were skipped under the cached-build constraint.

Existing Terraform, cloud services, Hosting, Identity Platform domains (including admin.onolys.com), evaluation staging sign-in/CORS, credentials and data were left unchanged. No cloud commands, deployments or provider calls were made. `frontend/` remains; its README now explains standalone mock development.
