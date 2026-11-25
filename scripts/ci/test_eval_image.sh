#!/usr/bin/env bash
# Build/import/auth/data-isolation smoke for the deployable eval image. No cloud/provider calls.
# SKIP_BUILD=1 reuses a local tag or a registry image already pulled by the caller.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IMG="${1:-onolys-eval-backend:ci}"
EXPECTED_GIT_SHA="${EXPECTED_GIT_SHA:-$(git -C "$ROOT" rev-parse HEAD)}"
NAME="onolys-eval-smoke-$$"
PORT="${SMOKE_PORT:-18081}"
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT
if [[ -z "${SKIP_BUILD:-}" ]]; then
  DOCKER_BUILDKIT=1 docker build -f "$ROOT/eval/backend/Dockerfile" --build-arg "GIT_SHA=$EXPECTED_GIT_SHA" -t "$IMG" "$ROOT"
fi
# Network isolation also proves imports, schema/config resolution and auth need no cloud access.
docker run --rm -i --network none --entrypoint python \
  -e "EXPECTED_GIT_SHA=$EXPECTED_GIT_SHA" -e LITELLM_LOCAL_MODEL_COST_MAP=True "$IMG" - <<'PY'
import asyncio
import importlib.util
import json
import os
from importlib.metadata import version
from pathlib import Path

from onolys_api.auth.idtoken import InvalidToken
from onolys_engine_core.errors import ConfigError
from onolys_eval_backend.app import create_app
from onolys_eval_backend.config import EvalConfig
from onolys_eval_backend.runs import _git_sha

assert os.environ['GIT_SHA'] == os.environ['EXPECTED_GIT_SHA']
assert _git_sha() == os.environ['EXPECTED_GIT_SHA']
print('ok image GIT_SHA=' + os.environ['GIT_SHA'])
for package in ['onolys-eval-backend', 'onolys-eval', 'onolys-api',
                'onolys-engine-core', 'onolys-miti', 'onolys-oneshot']:
    print(f'ok installed {package}={version(package)}')
assert importlib.util.find_spec('onolys_admin_backend') is None
# Third-party SDKs legitimately contain modules named uploads/runs (e.g. openai.types).
# Audit application content and every installed Onolys package, not SDK module names.
site = Path('/opt/venv/lib/python3.12/site-packages')
assert not Path('/src').exists()
for base in [Path('/app'), *site.glob('onolys_*')]:
    for path in base.rglob('*'):
        assert not {'datasets', 'uploads', 'runs', 'node_modules', '.git', '.worktrees',
                    'fixtures'}.intersection(path.parts), str(path)
        assert path.suffix not in {'.jsonl', '.vtt', '.srt', '.wav', '.mp3', '.mp4'}, str(path)
print('ok no admin backend, datasets, uploads, runs, fixtures or recordings in image')

env = dict(ENV='staging', EVAL_ALLOWED_EMAILS='test@example.com',
           AUTH_PROJECT='demo-project', DATASETS_BUCKET='synthetic-test', EVAL_MODE='true',
           UID_HMAC_KEY='ci-hmac-key', REGION='us-central1', WORKER_URL='https://worker.test.run.app',
           TASKS_QUEUE='projects/demo-project/locations/us-central1/queues/eval-runs',
           TASKS_SA='tasks@demo-project.iam.gserviceaccount.com',
           SERVICE_URL='https://test.run.app', PROD_ENGINE='miti', DEFAULT_PRESET='default',
           ROUTES_FILE='/app/config/staging/routes.yaml')
class Verifier:
    def verify_claims(self, token):
        if token == 'invalid':
            raise InvalidToken
        return {'email': 'test@example.com' if token == 'allowed' else 'other@example.com',
                'email_verified': True}
    verify = verify_claims
app = create_app(env, verifier=Verifier(), task_verifier=Verifier())
services = app.state.catalog
infos = services.registry.engines()
assert {info.name for info in infos} == {'miti', 'oneshot'}
assert all(info.version for info in infos)
assert services.engine('miti').output_schema()
assert services.engine('oneshot:miti').output_schema()
assert services.routes and services.prices
print('ok installed engine versions, MITI schemas/pack, prices and staging routes load')

async def request(path, token=None):
    messages = []
    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}
    async def send(message):
        messages.append(message)
    headers = [] if token is None else [(b'authorization', f'Bearer {token}'.encode())]
    await app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
               'method': 'GET', 'scheme': 'https', 'path': path, 'raw_path': path.encode(),
               'query_string': b'', 'headers': headers, 'server': ('test',443),
               'client': ('127.0.0.1',1234)}, receive, send)
    status = next(m['status'] for m in messages if m['type'] == 'http.response.start')
    return status, b''.join(m.get('body', b'') for m in messages)
async def checks():
    for token, expected in [(None,401), ('invalid',401), ('other',403), ('allowed',200)]:
        status, _ = await request('/v1/me', token)
        assert status == expected, (token,status)
    status, body = await request('/v1/options', 'allowed')
    assert status == 200, body
    assert {e['id'] for e in json.loads(body)['engines']} == {'human', 'miti', 'oneshot:miti'}
asyncio.run(checks())
print('ok offline real-package mock-verifier auth 401/403/200 and options 200')
for changed in [{'EVAL_ALLOWED_EMAILS':''}, {'AUTH_MODE':'off'}, {'EVAL_AUTH':'on'}]:
    try:
        EvalConfig.from_env({**env, **changed})
    except ConfigError:
        pass
    else:
        raise AssertionError('unsafe auth configuration accepted')
print('ok empty allowlist, disabled auth and removed settings fail closed')
PY

# Actual server process and HTTP anonymous gate, with dummy non-secret configuration.
docker run -d --name "$NAME" -p "127.0.0.1:$PORT:8080" \
  -e EVAL_ALLOWED_EMAILS=test@example.com -e AUTH_PROJECT=demo-project \
  -e DATASETS_BUCKET=synthetic-test -e EVAL_MODE=true -e UID_HMAC_KEY=ci-hmac-key -e REGION=us-central1 -e WORKER_URL=https://worker.test.run.app \
  -e TASKS_QUEUE=projects/demo-project/locations/us-central1/queues/eval-runs \
  -e TASKS_SA=tasks@demo-project.iam.gserviceaccount.com \
  -e SERVICE_URL=https://test.run.app -e PROD_ENGINE=miti -e DEFAULT_PRESET=default \
  -e ROUTES_FILE=/app/config/staging/routes.yaml -e LITELLM_LOCAL_MODEL_COST_MAP=True \
  "$IMG" >/dev/null
code=000
for _ in $(seq 1 40); do
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://127.0.0.1:$PORT/v1/me" || true)"
  [[ "$code" == 401 ]] && break
  sleep 1
done
if [[ "$code" != 401 ]]; then
  docker logs "$NAME" >&2
  echo "FAIL anonymous /v1/me -> $code (want 401)" >&2; exit 1
fi
echo 'ok actual server anonymous /v1/me -> 401'
docker image inspect "$IMG" --format 'image={{.Id}}'
