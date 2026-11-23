#!/usr/bin/env bash
# Eval is hosted against Cloud Run only; accept an exact HTTPS Cloud Run origin.
set -euo pipefail
origin="${1:-}"; file="${2:-}"
[[ "$origin" =~ ^https://[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.run\.app$ ]] \
  || { echo 'origin must be an exact HTTPS Cloud Run host, without a path or port' >&2; exit 1; }
[[ -f "$file" ]] || { echo "no such file: $file" >&2; exit 1; }
grep -q '__EVAL_BACKEND_ORIGIN__' "$file" || { echo "placeholder not found in $file" >&2; exit 1; }
sed -i "s|__EVAL_BACKEND_ORIGIN__|$origin|g" "$file"
! grep -q '__EVAL_BACKEND_ORIGIN__' "$file"
echo "set eval origin $origin in $file"
