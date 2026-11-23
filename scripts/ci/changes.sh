#!/usr/bin/env bash
# Per-package CI flags. Reads changed file paths on stdin (one per line).
# Env: FORCE_ALL=true -> every existing package runs (push to main).
#      ROOT=<dir>     -> repo root for directory-exists checks (default: .).
#      GITHUB_OUTPUT  -> where flags are appended (default: stdout).
# A flag is true iff the package exists (python kind: <dir>/pyproject.toml; node kind: <dir>/package.json; else the dir) AND (FORCE_ALL, or its paths or
# shared paths changed). Moving a package = edit its dir in PACKAGES below.
set -euo pipefail

ROOT="${ROOT:-.}"
OUT="${GITHUB_OUTPUT:-/dev/stdout}"

# name:dir:kind (kind python => also triggered by Python-shared paths; node => needs package.json)
PACKAGES=(
  "core:engines/core:python"
  "oneshot:engines/oneshot:python"
  "miti:engines/miti:python"
  "api:api:python"
  "admin-auth:admin/auth:python"
  "admin-backend:admin/backend:python"
  "eval:eval/core:python"
  "frontend:frontend:other"
  "web:web:node"
  "infra:infra:other"
)

# Shared paths: Python-shared hit python packages; CI-shared hits everything.
PY_SHARED_RE='^(pyproject\.toml|uv\.lock)'
CI_SHARED_RE='^(\.github/workflows/|scripts/ci/)'
# Extra paths per package: Firestore rules and their emulator tests run in the api job.
API_EXTRA_RE='^(firestore\.rules|firebase\.json|firestore-rules-test/)'
# The web job also runs on the contracts its generated types come from (gen:api staleness check).
WEB_EXTRA_RE='^(api/openapi\.json$|engines/miti/src/onolys_miti/data/report\.schema\.json$|engines/miti/src/onolys_miti/data/fixtures/evaluation/)'

# One-shot drift tests read these repo data files; MITI is not a runtime dependency.
ONESHOT_EXTRA_RE='^(scripts/gen_miti_schema\.py$|config/staging/routes\.yaml$|engines/miti/src/onolys_miti/data/(pack\.yaml$|report\.schema\.json$|prompts/(code|globals)_system\.md$|fixtures/good_practice\.json$))'

# Dataset manifests and metadata-only overrides are inputs to eval/core.
EVAL_EXTRA_RE='^eval/datasets/'

# The infra job's tests import admin/auth (onolys_admin_auth), so admin/auth changes also run infra.
INFRA_EXTRA_RE='^(admin/auth/|pyproject\.toml$|uv\.lock$)'

# The admin backend serves only /v1/me via admin/auth, so it re-runs when admin/auth or .dockerignore changes.
ADMIN_BACKEND_EXTRA_RE='^(admin/auth/|\.dockerignore)'

# Direct workspace dependencies (name: deps), mirrored from each pyproject [project].dependencies.
# A change in a package also runs every package that (transitively) depends on it.
# test_changes_deps.py fails if this drifts from the pyprojects.
DEPS=(
  "oneshot:core"
  "miti:core"
  "api:core miti"
  "eval:core miti"
  "admin-backend:admin-auth"
)

mapfile -t FILES

declare -A HIT=()
for entry in "${PACKAGES[@]}"; do
  IFS=: read -r name dir kind <<<"$entry"
  for f in "${FILES[@]}"; do
    if [[ "$f" == "$dir/"* || "$f" =~ $CI_SHARED_RE ||
          ( "$kind" == python && "$f" =~ $PY_SHARED_RE ) ||
          ( "$name" == oneshot && "$f" =~ $ONESHOT_EXTRA_RE ) ||
          ( "$name" == eval && "$f" =~ $EVAL_EXTRA_RE ) ||
          ( "$name" == api && "$f" =~ $API_EXTRA_RE ) ||
          ( "$name" == admin-backend && "$f" =~ $ADMIN_BACKEND_EXTRA_RE ) ||
          ( "$name" == infra && "$f" =~ $INFRA_EXTRA_RE ) ||
          ( "$name" == web && "$f" =~ $WEB_EXTRA_RE ) ]]; then
      HIT[$name]=1
      break
    fi
  done
done

# Propagate to dependents until stable.
changed=true
while [[ "$changed" == true ]]; do
  changed=false
  for entry in "${DEPS[@]}"; do
    name="${entry%%:*}"
    [[ -n "${HIT[$name]:-}" ]] && continue
    for dep in ${entry#*:}; do
      if [[ -n "${HIT[$dep]:-}" ]]; then HIT[$name]=1; changed=true; break; fi
    done
  done
done

for entry in "${PACKAGES[@]}"; do
  IFS=: read -r name dir kind <<<"$entry"
  run=false
  marker="$ROOT/$dir"
  [[ "$kind" == python ]] && marker="$ROOT/$dir/pyproject.toml"
  [[ "$kind" == node ]] && marker="$ROOT/$dir/package.json"
  if [[ -e "$marker" ]]; then
    if [[ "${FORCE_ALL:-false}" == "true" ]]; then
      run=true
    else
      [[ -n "${HIT[$name]:-}" ]] && run=true
    fi
  fi
  echo "$name=$run" >>"$OUT"
done
