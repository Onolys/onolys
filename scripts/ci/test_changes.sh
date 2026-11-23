#!/usr/bin/env bash
# Tests for changes.sh against fake diffs and a fake repo tree.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir -p "$T/engines/miti" "$T/frontend" "$T/api"
touch "$T/engines/miti/pyproject.toml" "$T/api/pyproject.toml"
# web/infra/admin absent at first
mkdir -p "$T/web/src"   # web dir without package.json must still skip
fail=0
# run <force> <expected "name=val ..."> <files...>
run() {
  local force="$1" want="$2"; shift 2
  local got
  got="$(printf '%s\n' "$@" | ROOT="$T" FORCE_ALL="$force" GITHUB_OUTPUT=/dev/stdout bash "$HERE/changes.sh" | tr '\n' ' ' | sed 's/ $//')"
  if [[ "$got" == "$want" ]]; then echo "ok   $*"; else echo "FAIL $*"; echo "  got:  $got"; echo "  want: $want"; fail=1; fi
}
run false "core=false miti=false api=false admin-auth=false admin-backend=false eval=false frontend=true web=false infra=false" frontend/src/a.ts
# miti: engines/miti/** sets miti and api (api depends on miti)
run false "core=false miti=true api=true admin-auth=false admin-backend=false eval=false frontend=false web=false infra=false" engines/miti/src/x.py
# Python-shared paths hit every existing python package
run false "core=false miti=true api=true admin-auth=false admin-backend=false eval=false frontend=false web=false infra=false" uv.lock
run false "core=false miti=true api=true admin-auth=false admin-backend=false eval=false frontend=false web=false infra=false" pyproject.toml
# CI-shared paths hit everything that exists
run false "core=false miti=true api=true admin-auth=false admin-backend=false eval=false frontend=true web=false infra=false" .github/workflows/ci.yml
run false "core=false miti=false api=false admin-auth=false admin-backend=false eval=false frontend=false web=false infra=false" docs/readme.md
run false "core=false miti=false api=false admin-auth=false admin-backend=false eval=false frontend=false web=false infra=false" infra/main.tf web/a.ts
# FORCE_ALL: every existing package
run true "core=false miti=true api=true admin-auth=false admin-backend=false eval=false frontend=true web=false infra=false" docs/readme.md
run false "core=false miti=false api=true admin-auth=false admin-backend=false eval=false frontend=false web=false infra=false" firestore.rules
run false "core=false miti=false api=true admin-auth=false admin-backend=false eval=false frontend=false web=false infra=false" firestore-rules-test/rules.test.mjs
touch "$T/web/package.json"; mkdir -p "$T/infra"   # web (package.json) and infra (dir) now exist
run false "core=false miti=false api=false admin-auth=false admin-backend=false eval=false frontend=false web=true infra=false" web/src/a.ts
run false "core=false miti=false api=false admin-auth=false admin-backend=false eval=false frontend=false web=false infra=true" infra/main.tf
# generated-type inputs (api/openapi.json, report.schema.json) trigger the web gen:api staleness check
run false "core=false miti=false api=true admin-auth=false admin-backend=false eval=false frontend=false web=true infra=false" api/openapi.json
run false "core=false miti=true api=true admin-auth=false admin-backend=false eval=false frontend=false web=true infra=false" engines/miti/src/onolys_miti/data/report.schema.json
run false "core=false miti=true api=true admin-auth=false admin-backend=false eval=false frontend=false web=true infra=false" engines/miti/src/onolys_miti/data/fixtures/evaluation/case1.json
run true "core=false miti=true api=true admin-auth=false admin-backend=false eval=false frontend=true web=true infra=true" docs/readme.md
# web extra paths are end-anchored: a stray suffix must not trigger the web job
run false "core=false miti=false api=true admin-auth=false admin-backend=false eval=false frontend=false web=false infra=false" api/openapi.json.bak
run false "core=false miti=true api=true admin-auth=false admin-backend=false eval=false frontend=false web=false infra=false" engines/miti/src/onolys_miti/data/report.schema.json.bak
rm -r "$T/web/package.json" "$T/infra"
mkdir -p "$T/admin/auth"; touch "$T/admin/auth/pyproject.toml"   # admin/auth now exists
run false "core=false miti=false api=false admin-auth=true admin-backend=false eval=false frontend=false web=false infra=false" admin/auth/a.py
mkdir -p "$T/admin/backend"; touch "$T/admin/backend/pyproject.toml"   # admin/backend now exists
run false "core=false miti=false api=false admin-auth=false admin-backend=true eval=false frontend=false web=false infra=false" admin/backend/a.py
# admin-backend depends on admin-auth
run false "core=false miti=false api=false admin-auth=true admin-backend=true eval=false frontend=false web=false infra=false" admin/auth/a.py
run false "core=false miti=false api=false admin-auth=false admin-backend=true eval=false frontend=false web=false infra=false" .dockerignore
# infra tests import admin/auth, so admin/auth changes also run infra (when infra exists)
mkdir -p "$T/infra"
run false "core=false miti=false api=false admin-auth=true admin-backend=true eval=false frontend=false web=false infra=true" admin/auth/a.py
run false "core=false miti=true api=true admin-auth=true admin-backend=true eval=false frontend=false web=false infra=true" uv.lock
rm -r "$T/infra"
# api does not propagate to miti
run false "core=false miti=false api=true admin-auth=false admin-backend=false eval=false frontend=false web=false infra=false" api/src/x.py
# eval is optional until its Python package exists, even when dataset metadata changes.
run false "core=false miti=false api=false admin-auth=false admin-backend=false eval=false frontend=false web=false infra=false" eval/datasets/synthetic/manifest.yaml
mkdir -p "$T/eval/core"; touch "$T/eval/core/pyproject.toml"
run false "core=false miti=false api=false admin-auth=false admin-backend=false eval=true frontend=false web=false infra=false" eval/core/src/onolys_eval/metrics.py
run false "core=false miti=false api=false admin-auth=false admin-backend=false eval=true frontend=false web=false infra=false" eval/datasets/synthetic/manifest.yaml
run false "core=false miti=true api=true admin-auth=false admin-backend=false eval=true frontend=false web=false infra=false" engines/miti/src/x.py
run false "core=false miti=true api=true admin-auth=true admin-backend=true eval=true frontend=false web=false infra=false" pyproject.toml
run false "core=false miti=true api=true admin-auth=true admin-backend=true eval=true frontend=false web=false infra=false" uv.lock
run false "core=false miti=true api=true admin-auth=true admin-backend=true eval=true frontend=true web=false infra=false" scripts/ci/changes.sh
run false "core=false miti=true api=true admin-auth=true admin-backend=true eval=true frontend=true web=false infra=false" .github/workflows/ci.yml
run true "core=false miti=true api=true admin-auth=true admin-backend=true eval=true frontend=true web=false infra=false" docs/readme.md
# Evaluation changes do not trigger the engine or API; unrelated eval siblings stay separate.
run false "core=false miti=false api=false admin-auth=false admin-backend=false eval=false frontend=false web=false infra=false" eval/backend/src/app.py
run false "core=false miti=false api=true admin-auth=false admin-backend=false eval=false frontend=false web=false infra=false" api/src/x.py
# Core is optional until its manifest exists, then propagates to every engine consumer.
run false "core=false miti=true api=true admin-auth=false admin-backend=false eval=true frontend=false web=false infra=false" engines/core/src/onolys_engine_core/context.py
mkdir -p "$T/engines/core"; touch "$T/engines/core/pyproject.toml"
run false "core=true miti=true api=true admin-auth=false admin-backend=false eval=true frontend=false web=false infra=false" engines/core/src/onolys_engine_core/context.py
run false "core=true miti=true api=true admin-auth=true admin-backend=true eval=true frontend=false web=false infra=false" uv.lock
run false "core=true miti=true api=true admin-auth=true admin-backend=true eval=true frontend=true web=false infra=false" .github/workflows/ci.yml
run true "core=true miti=true api=true admin-auth=true admin-backend=true eval=true frontend=true web=false infra=false" docs/readme.md
run false "core=false miti=true api=true admin-auth=false admin-backend=false eval=true frontend=false web=false infra=false" engines/miti/src/x.py
run false "core=false miti=false api=false admin-auth=false admin-backend=false eval=true frontend=false web=false infra=false" eval/core/src/onolys_eval/metrics.py
run false "core=false miti=false api=true admin-auth=false admin-backend=false eval=false frontend=false web=false infra=false" api/src/x.py
exit $fail
