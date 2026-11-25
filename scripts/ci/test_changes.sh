#!/usr/bin/env bash
# Tests for changes.sh against fake diffs and a fake repo tree.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir -p "$T/engines/miti" "$T/frontend" "$T/api"
touch "$T/engines/miti/pyproject.toml" "$T/api/pyproject.toml"
# web/infra/eval absent at first
mkdir -p "$T/web/src"   # web dir without package.json must still skip
fail=0
# run <force> <expected "name=val ..."> <files...>
run() {
  local force="$1" want="$2"; shift 2
  local got
  got="$(printf '%s\n' "$@" | ROOT="$T" FORCE_ALL="$force" GITHUB_OUTPUT=/dev/stdout bash "$HERE/changes.sh" | tr '\n' ' ' | sed 's/ $//')"
  if [[ "$got" == "$want" ]]; then echo "ok   $*"; else echo "FAIL $*"; echo "  got:  $got"; echo "  want: $want"; fail=1; fi
}
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=false frontend=true web=false infra=false" frontend/src/a.ts
# miti: engines/miti/** sets miti and api (api depends on miti)
run false "core=false oneshot=false miti=true api=true eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" engines/miti/src/x.py
# Python-shared paths hit every existing python package
run false "core=false oneshot=false miti=true api=true eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" uv.lock
run false "core=false oneshot=false miti=true api=true eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" pyproject.toml
# CI-shared paths hit everything that exists
run false "core=false oneshot=false miti=true api=true eval=false eval-backend=false eval-web=false frontend=true web=false infra=false" .github/workflows/ci.yml
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" docs/readme.md
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" infra/main.tf web/a.ts
# FORCE_ALL: every existing package
run true "core=false oneshot=false miti=true api=true eval=false eval-backend=false eval-web=false frontend=true web=false infra=false" docs/readme.md
run false "core=false oneshot=false miti=false api=true eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" firestore.rules
run false "core=false oneshot=false miti=false api=true eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" firestore-rules-test/rules.test.mjs
touch "$T/web/package.json"; mkdir -p "$T/infra"   # web (package.json) and infra (dir) now exist
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=false frontend=false web=true infra=false" web/src/a.ts
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=false frontend=false web=false infra=true" infra/main.tf
# generated-type inputs (api/openapi.json, report.schema.json) trigger the web gen:api staleness check
run false "core=false oneshot=false miti=false api=true eval=false eval-backend=false eval-web=false frontend=false web=true infra=false" api/openapi.json
run false "core=false oneshot=false miti=true api=true eval=false eval-backend=false eval-web=false frontend=false web=true infra=false" engines/miti/src/onolys_miti/data/report.schema.json
run false "core=false oneshot=false miti=true api=true eval=false eval-backend=false eval-web=false frontend=false web=true infra=false" engines/miti/src/onolys_miti/data/fixtures/evaluation/case1.json
run true "core=false oneshot=false miti=true api=true eval=false eval-backend=false eval-web=false frontend=true web=true infra=true" docs/readme.md
# web extra paths are end-anchored: a stray suffix must not trigger the web job
run false "core=false oneshot=false miti=false api=true eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" api/openapi.json.bak
run false "core=false oneshot=false miti=true api=true eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" engines/miti/src/onolys_miti/data/report.schema.json.bak
rm -r "$T/web/package.json" "$T/infra"
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" .dockerignore
# root lock/manifest changes also run infra (when infra exists)
mkdir -p "$T/infra"
run false "core=false oneshot=false miti=true api=true eval=false eval-backend=false eval-web=false frontend=false web=false infra=true" uv.lock
rm -r "$T/infra"
# api does not propagate to miti
run false "core=false oneshot=false miti=false api=true eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" api/src/x.py
# eval is optional until its Python package exists, even when dataset metadata changes.
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" eval/datasets/synthetic/manifest.yaml
mkdir -p "$T/eval/core"; touch "$T/eval/core/pyproject.toml"
run false "core=false oneshot=false miti=false api=false eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" eval/core/src/onolys_eval/metrics.py
run false "core=false oneshot=false miti=false api=false eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" eval/datasets/synthetic/manifest.yaml
run false "core=false oneshot=false miti=true api=true eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" engines/miti/src/x.py
run false "core=false oneshot=false miti=true api=true eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" pyproject.toml
run false "core=false oneshot=false miti=true api=true eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" uv.lock
run false "core=false oneshot=false miti=true api=true eval=true eval-backend=false eval-web=false frontend=true web=false infra=false" scripts/ci/changes.sh
run false "core=false oneshot=false miti=true api=true eval=true eval-backend=false eval-web=false frontend=true web=false infra=false" .github/workflows/ci.yml
run true "core=false oneshot=false miti=true api=true eval=true eval-backend=false eval-web=false frontend=true web=false infra=false" docs/readme.md
# Evaluation changes do not trigger the engine or API; unrelated eval siblings stay separate.
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" eval/backend/src/app.py
run false "core=false oneshot=false miti=false api=true eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" api/src/x.py
# Core is optional until its manifest exists, then propagates to every engine consumer.
run false "core=false oneshot=false miti=true api=true eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" engines/core/src/onolys_engine_core/context.py
mkdir -p "$T/engines/core"; touch "$T/engines/core/pyproject.toml"
run false "core=true oneshot=false miti=true api=true eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" engines/core/src/onolys_engine_core/context.py
run false "core=true oneshot=false miti=true api=true eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" uv.lock
run false "core=true oneshot=false miti=true api=true eval=true eval-backend=false eval-web=false frontend=true web=false infra=false" .github/workflows/ci.yml
run true "core=true oneshot=false miti=true api=true eval=true eval-backend=false eval-web=false frontend=true web=false infra=false" docs/readme.md
run false "core=false oneshot=false miti=true api=true eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" engines/miti/src/x.py
run false "core=false oneshot=false miti=false api=false eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" eval/core/src/onolys_eval/metrics.py
run false "core=false oneshot=false miti=false api=true eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" api/src/x.py
# One-shot is optional, depends on core only, and reads MITI reference data without importing it.
run false "core=false oneshot=false miti=false api=true eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" engines/oneshot/src/onolys_oneshot/engine.py
mkdir -p "$T/engines/oneshot"; touch "$T/engines/oneshot/pyproject.toml"
run false "core=false oneshot=true miti=false api=true eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" engines/oneshot/src/onolys_oneshot/engine.py
run false "core=true oneshot=true miti=true api=true eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" engines/core/src/onolys_engine_core/validated_run.py
run false "core=false oneshot=false miti=true api=true eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" engines/miti/src/onolys_miti/engine.py
run false "core=false oneshot=true miti=true api=true eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" engines/miti/src/onolys_miti/data/pack.yaml
run false "core=false oneshot=true miti=true api=true eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" engines/miti/src/onolys_miti/data/report.schema.json
run false "core=false oneshot=true miti=true api=true eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" engines/miti/src/onolys_miti/data/prompts/code_system.md
run false "core=false oneshot=true miti=true api=true eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" engines/miti/src/onolys_miti/data/prompts/globals_system.md
run false "core=false oneshot=true miti=true api=true eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" engines/miti/src/onolys_miti/data/fixtures/good_practice.json
run false "core=false oneshot=true miti=false api=true eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" scripts/gen_miti_schema.py
run false "core=false oneshot=true miti=false api=true eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" config/staging/routes.yaml
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" scripts/gen_miti_schema.py.bak
run false "core=false oneshot=false miti=true api=true eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" engines/miti/src/onolys_miti/data/pack.yaml.bak
run false "core=true oneshot=true miti=true api=true eval=true eval-backend=false eval-web=false frontend=false web=false infra=false" uv.lock
run false "core=true oneshot=true miti=true api=true eval=true eval-backend=false eval-web=false frontend=true web=false infra=false" .github/workflows/ci.yml
run true "core=true oneshot=true miti=true api=true eval=true eval-backend=false eval-web=false frontend=true web=false infra=false" docs/readme.md
# Eval service and SPA remain optional until their own package markers exist.
mkdir -p "$T/eval/backend" "$T/eval/web"
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" eval/backend/src/app.py eval/web/src/Root.tsx
# A node manifest, rather than the directory alone, enables the SPA.
touch "$T/eval/backend/pyproject.toml" "$T/eval/web/package.json"
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=true eval-web=true frontend=false web=false infra=false" eval/backend/src/app.py
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=true frontend=false web=false infra=false" eval/web/src/Root.tsx
run false "core=false oneshot=true miti=false api=true eval=false eval-backend=true eval-web=false frontend=false web=false infra=false" engines/oneshot/src/engine.py
run false "core=false oneshot=false miti=false api=false eval=true eval-backend=true eval-web=false frontend=false web=false infra=false" eval/core/src/onolys_eval/adapters.py
run false "core=true oneshot=true miti=true api=true eval=true eval-backend=true eval-web=false frontend=false web=false infra=false" engines/core/src/context.py
run false "core=false oneshot=false miti=true api=true eval=true eval-backend=true eval-web=false frontend=false web=false infra=false" engines/miti/src/engine.py
run false "core=false oneshot=true miti=false api=true eval=false eval-backend=true eval-web=false frontend=false web=false infra=false" config/staging/routes.yaml
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=true eval-web=false frontend=false web=false infra=false" protocols/miti/pack.yaml
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=true eval-web=false frontend=false web=false infra=false" .dockerignore
# eval/web aliases prod web auth/client/classes sources; stale frontend/ paths no longer select it.
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=true frontend=false web=false infra=false" web/src/auth/AuthGate.tsx
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=true frontend=false web=false infra=false" web/src/api/client.ts
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=true frontend=false web=false infra=false" web/src/components/classes/Badge.tsx
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" web/src/api/client.ts.bak
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" web/src/api/other.ts
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=false frontend=true web=false infra=false" frontend/src/auth/AuthGate.tsx
run false "core=false oneshot=false miti=false api=true eval=false eval-backend=true eval-web=true frontend=false web=false infra=false" api/openapi.json
run false "core=false oneshot=false miti=false api=true eval=false eval-backend=true eval-web=false frontend=false web=false infra=false" api/openapi.json.bak
run false "core=false oneshot=false miti=false api=true eval=false eval-backend=true eval-web=true frontend=false web=false infra=false" docs/contracts/public/transcript.v1.schema.json
run false "core=true oneshot=true miti=true api=true eval=true eval-backend=true eval-web=false frontend=false web=false infra=false" uv.lock
run false "core=true oneshot=true miti=true api=true eval=true eval-backend=true eval-web=false frontend=false web=false infra=false" pyproject.toml
run false "core=true oneshot=true miti=true api=true eval=true eval-backend=true eval-web=true frontend=true web=false infra=false" scripts/ci/changes.sh
run false "core=true oneshot=true miti=true api=true eval=true eval-backend=true eval-web=true frontend=true web=false infra=false" .github/workflows/ci.yml
run true "core=true oneshot=true miti=true api=true eval=true eval-backend=true eval-web=true frontend=true web=false infra=false" docs/readme.md
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" docs/readme.md
# Shared runtime settings/contracts must run API validation; action changes affect all jobs.
run false "core=false oneshot=true miti=false api=true eval=false eval-backend=true eval-web=false frontend=false web=false infra=false" config/staging/routes.yaml
run false "core=false oneshot=false miti=false api=true eval=false eval-backend=true eval-web=true frontend=false web=false infra=false" docs/contracts/public/session.schema.json
run false "core=true oneshot=true miti=true api=true eval=true eval-backend=true eval-web=true frontend=true web=false infra=false" .github/actions/setup-python/action.yml
# Retired source paths select no active package.
run false "core=false oneshot=false miti=false api=false eval=false eval-backend=false eval-web=false frontend=false web=false infra=false" admin/backend/src/app.py
exit $fail
