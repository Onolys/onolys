#!/usr/bin/env bash
# Docs scope gate: root docs are MITI-only; each docs README lists only existing files.
set -u
cd "$(dirname "$0")/../.."
fail=0
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

hits=$(grep -inE 'eaudit|paudit|caudit|Interview Evidence' README.md AGENTS.md docs/mission.md docs/architecture.md || true)
if [ -n "$hits" ]; then
  echo "FAIL: legacy terms in root docs:"; echo "$hits"; fail=1
fi

for readme in docs/README.md docs/*/README.md; do
  case "$readme" in docs/agent_files/*) continue;; esac
  dir=$(dirname "$readme")
  # relative markdown link targets, skipping urls and anchors
  grep -oE '\]\(([^)#]+)(#[^)]*)?\)' "$readme" | sed -E 's/^\]\(//; s/(#[^)]*)?\)$//' \
  | while read -r target; do
    case "$target" in http*|mailto:*|"") continue;; esac
    [ -e "$dir/$target" ] || echo "FAIL: $readme lists missing $target"
  done
done | tee "$tmp"
[ -s "$tmp" ] && fail=1
[ $fail -eq 0 ] && echo "docs scope OK"
exit $fail
