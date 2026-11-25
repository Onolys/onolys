#!/usr/bin/env bash
# CI smoke for the prod LLM validator: runs the exact `docker run` shape deploy-prod.yml
# uses (read-only, no network, bind-mounted validator, prod routes at /app/config) against
# an image. Usage: smoke_prod_llm_validator.sh IMAGE [VALIDATOR]
# Keep the docker flags identical to deploy-prod.yml; test_prod_llm_smoke.py enforces it.
set -euo pipefail
IMAGE=${1:?usage: smoke_prod_llm_validator.sh IMAGE [VALIDATOR]}
VALIDATOR=${2:-$(cd "$(dirname "$0")" && pwd)/validate_staging_llm.py}

validate() {
  LLM_PROVIDER=$1 LLM_MODEL=$2 LLM_EFFORT=$3 \
  docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
    --entrypoint python -e LLM_PROVIDER -e LLM_MODEL -e LLM_EFFORT \
    --mount "type=bind,src=$VALIDATOR,dst=/tmp/validate_llm.py,readonly" \
    "$IMAGE" /tmp/validate_llm.py --environment prod --config-root /app/config --stdout
}

out=$(validate openai gpt-6.1-sol medium)
test "$out" = $'provider=openai\nmodel=gpt-6.1-sol\neffort=medium' || { echo "unexpected validator output: $out"; exit 1; }
if validate openai gpt-6.1-sol none >/dev/null 2>&1; then
  echo "invalid LLM effort was accepted by the image validator"; exit 1
fi
echo "prod LLM validator smoke passed against $IMAGE"
