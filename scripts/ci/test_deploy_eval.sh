#!/usr/bin/env bash
# R11: staging workflow, isolated image inputs and strict Hosting origin substitution.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
python3 - <<'PY'
import json
from pathlib import Path

wf = Path('.github/workflows/deploy-eval.yml')
assert wf.is_file(), 'deploy-eval.yml missing'
s = wf.read_text()
for required in ['workflow_call:', 'environment: staging',
                 'file: eval/backend/Dockerfile', 'steps.push.outputs.digest',
                 'GIT_SHA=${{ inputs.sha }}', 'google-github-actions/auth@v2',
                 'google-github-actions/deploy-cloudrun@v2', 'skip_default_labels: true', 'id-token: write',
                 'onolys-eval-backend-eval', 'eval-staging', 'onolys-eval-staging',
                 'VITE_EVAL_API_URL:', 'vars.PROD_VITE_FIREBASE_API_KEY',
                 'vars.PROD_VITE_FIREBASE_APP_ID', 'VITE_FIREBASE_AUTH_DOMAIN: eval.onolys.com',
                 'firestore:eval', 'working-directory: web', 'VITE_APP_URL:',
                 'set_eval_origin.sh', 'test_eval_image.sh', '/v1/me', '401',
                 'content-security-policy:',
                 'hosting:eval-staging']:
    assert required in s, f'missing workflow contract: {required}'
assert 'workflow_dispatch:' not in s and '\n  push:' not in s, 'eval must release only inside the staging lock'
assert 'concurrency:' not in s, 'caller holds the release lock through the reusable workflow'
assert 'env_vars: GIT_SHA=${{ inputs.sha }}' in s, 'runtime env must replace Terraform bootstrap SHA'
assert s.count('ref: ${{ inputs.sha }}') == 3, 'build, site and Firestore checkout must pin the worker SHA'
assert 'github.sha' not in s, 'workflow_run default ref is not the tested commit'
for forbidden in ['DEPLOYER_PROD_SA', 'credentials_json', 'service_account_key',
                  'environment: production', '_deploy-cloudrun.yml']:
    assert forbidden not in s, f'forbidden workflow config: {forbidden}'
img = Path('scripts/ci/test_eval_image.sh').read_text()
run = img[img.index('docker run -d'):]
for name in ['ENV=staging', 'FIRESTORE_DATABASE=', 'GCP_PROJECT=', 'AUDIO_BUCKET=']:
    assert f'-e {name}' in run, f'docker run in test_eval_image.sh must set {name} (fail-closed config)'
assert 'onolys_admin_auth' not in img and 'onolys-admin-auth' not in img and 'ADMIN_' not in img, 'stale admin auth names in test_eval_image.sh'
assert 'ADMIN_' not in s and 'onolys-eval-backend-staging' not in s, 'legacy admin/staging names remain'
assert 'vars.PROD_VITE_FIREBASE_AUTH_DOMAIN' not in s, 'auth domain must be the literal eval.onolys.com'
fs = json.loads(Path('firebase.json').read_text())['firestore']
ev = [d for d in fs if d['database'] == 'eval']
assert len(ev) == 1 and ev[0]['rules'] == 'firestore.rules' and ev[0]['indexes'] == 'api/firestore.indexes.json'
dc = Path('.github/workflows/_deploy-cloudrun.yml').read_text()
assert 'staging|prod|eval' in dc and "inputs.env == 'prod' && vars.DEPLOYER_PROD_SA || vars.DEPLOYER_STAGING_SA" in dc
assert "inputs.env == 'prod' && 'production' || 'staging'" in dc
print('ok staging-only WIF workflow, digest image, image provenance, SHA-coordinated deploy and smoke')
docker = Path('eval/backend/Dockerfile').read_text()
for member in ['engines/core', 'engines/miti', 'engines/oneshot', 'api',
               'eval/core', 'eval/backend']:
    assert f'COPY {member}/pyproject.toml {member}/pyproject.toml' in docker, member
    assert Path(member, 'pyproject.toml').is_file(), member
for required in ['--frozen', '--no-editable', 'ARG GIT_SHA', 'GIT_SHA=${GIT_SHA}',
                 'COPY config /app/config', 'USER onolys']:
    assert required in docker, required
ignore = Path('eval/backend/Dockerfile.dockerignore').read_text()
assert ignore.splitlines()[0] == '**', 'image context must be opt-in'
assert '!config/models.yaml' in ignore.splitlines(), 'models.yaml must ship (LLM_PROVIDER/LLM_MODEL)'
assert 'eval/auth' not in docker and 'eval/auth' not in ignore, 'eval/auth was removed (R14)'
assert 'admin/' not in docker and 'admin/' not in ignore, 'retired image inputs remain'
for denied in ['**/node_modules', '**/.git', '**/.worktrees', '**/datasets', '**/uploads',
               '**/runs', '**/.env', '**/.env.*', '**/tests', '**/__pycache__']:
    assert denied in ignore, denied
print('ok frozen workspace metadata, runtime source allowlist and excluded data')
fb = json.loads(Path('eval/web/firebase.json').read_text())['hosting']
assert len(fb) == 1 and fb[0]['target'] == 'eval-staging'
assert fb[0]['public'] == 'dist'
csp = next(h['value'] for rule in fb[0]['headers'] for h in rule['headers']
           if h['key'] == 'Content-Security-Policy')
assert "connect-src 'self' __EVAL_BACKEND_ORIGIN__ " in csp
for origin in ['https://apis.google.com', 'https://identitytoolkit.googleapis.com',
               'https://securetoken.googleapis.com', 'https://accounts.google.com',
               'https://*.firebaseapp.com']:
    assert origin in csp, origin
for rc in ['.firebaserc', 'eval/web/.firebaserc']:
    assert json.loads(Path(rc).read_text())['targets']['onolys']['hosting']['eval-staging'] == ['onolys-eval-staging']
assert 'test_deploy_eval.sh' in Path('.github/workflows/ci.yml').read_text()
assert 'bash scripts/ci/test_eval_image.sh' in Path('.github/workflows/ci.yml').read_text()
assert 'eval/web' in Path('scripts/ci/test_hosting_targets.sh').read_text()
print('ok eval Hosting target and Firebase auth CSP')
PY
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
cp eval/web/firebase.json "$T/firebase.json"
bash scripts/ci/set_eval_origin.sh https://eval-test.run.app "$T/firebase.json"
python3 - "$T/firebase.json" <<'PY'
import json, sys
s = open(sys.argv[1]).read()
json.loads(s)
assert '__EVAL_BACKEND_ORIGIN__' not in s
assert "connect-src 'self' https://eval-test.run.app " in s
print('ok exact deployed origin substituted')
PY
for origin in '' http://x.run.app https://localhost https://127.0.0.1 https://x.run.app/path \
    https://x.run.app:443 'https://x.run.app;evil' javascript:alert 'https://x.run.app?x=y'; do
  cp eval/web/firebase.json "$T/bad.json"
  if bash scripts/ci/set_eval_origin.sh "$origin" "$T/bad.json" >/dev/null 2>&1; then
    echo "FAIL accepted invalid origin $origin" >&2; exit 1
  fi
done
printf '{}\n' > "$T/missing.json"
if bash scripts/ci/set_eval_origin.sh https://x.run.app "$T/missing.json" >/dev/null 2>&1; then
  echo 'FAIL accepted missing placeholder' >&2; exit 1
fi
echo 'ok malformed/local origins and missing placeholder rejected'
node --test scripts/ci/test_verify_staging_release.cjs
if command -v actionlint >/dev/null 2>&1; then
  actionlint .github/workflows/deploy-eval.yml
  echo 'ok actionlint'
fi
