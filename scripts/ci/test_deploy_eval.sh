#!/usr/bin/env bash
# R11: staging workflow, isolated image inputs and strict Hosting origin substitution.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
python3 - <<'PY'
import json
import yaml
import os
import subprocess
import tempfile
from pathlib import Path

wf = Path('.github/workflows/deploy-eval.yml')
assert wf.is_file(), 'deploy-eval.yml missing'
s = wf.read_text()
for required in ['workflow_dispatch:', 'environment: staging',
                 'file: eval/backend/Dockerfile', 'steps.push.outputs.digest',
                 'GIT_SHA=${{ steps.sha.outputs.sha }}', 'google-github-actions/auth@v2',
                 'google-github-actions/deploy-cloudrun@v2', 'skip_default_labels: true', 'id-token: write',
                 'onolys-eval-backend-eval', 'eval-staging',
                 'VITE_EVAL_API_URL:', 'vars.EVAL_VITE_FIREBASE_API_KEY',
                 'vars.EVAL_VITE_FIREBASE_APP_ID', 'vars.EVAL_VITE_FIREBASE_AUTH_DOMAIN',
                 'firestore:eval', 'working-directory: web',
                 'set_eval_origin.sh', 'test_eval_image.sh', '/v1/me', '401',
                 'content-security-policy:',
                 'hosting:eval-staging']:
    assert required in s, f'missing workflow contract: {required}'
workflow = yaml.safe_load(s)
triggers = workflow.get('on', workflow.get(True))
assert set(triggers) == {'workflow_run', 'workflow_dispatch'}, 'eval auto-deploys after CI on main like staging; manual dispatch kept'
assert triggers['workflow_run'] == {'workflows': ['CI'], 'types': ['completed'], 'branches': ['main']}
assert workflow['concurrency'] == {'group': 'deploy-eval', 'cancel-in-progress': False}
jobs = workflow['jobs']
build = jobs['build']
cond = build['if']
assert "github.ref == 'refs/heads/main'" in cond, 'reject non-main before credentials'
for guard in ["github.event_name == 'workflow_dispatch'", "github.event.workflow_run.conclusion == 'success'",
              "github.event.workflow_run.event == 'push'",
              "github.event.workflow_run.head_repository.full_name == github.repository",
              "github.event.workflow_run.head_branch == 'main'"]:
    assert guard in cond, f'build if lacks {guard}'
assert build['permissions']['actions'] == 'read'
steps = build['steps']
release = next(i for i, step in enumerate(steps) if step.get('id') == 'release')
auth = next(i for i, step in enumerate(steps) if 'google-github-actions/auth@' in step.get('uses', ''))
assert release < auth, 'admit CI-green current main before cloud authentication'
assert 'verify_staging_release.cjs' in steps[release]['with']['script']
sha_step = steps[0]
assert sha_step['id'] == 'sha' and 'github.event.workflow_run.head_sha || github.sha' in sha_step['env']['RUN_SHA'], \
    'workflow_run must use the CI run head_sha, not default-branch HEAD'
SHA = '${{ steps.sha.outputs.sha }}'
assert steps[release]['env']['RELEASE_SHA'] == SHA
assert build['outputs']['sha'] == SHA
checkout0 = next(step for step in steps if step.get('uses', '').startswith('actions/checkout@'))
assert checkout0['with']['ref'] == SHA
assert steps.index(sha_step) < steps.index(checkout0)
assert any('check_config.sh' in step.get('run', '') for step in steps[:auth]), 'source config guard before auth'
worker_build = next(step for step in steps if step.get('id') == 'push-worker')
assert worker_build['with']['file'] == 'api/Dockerfile', 'same runtime build inputs as app worker'
assert worker_build['with']['build-args'] == 'GIT_SHA=' + SHA
assert 'github.sha' not in json.dumps(build['steps'][1:]), 'build job must not use default-branch github.sha'
assert 'onolys/eval-worker' in s and 'onolys/api' not in s, 'eval must never publish an app image tag'
preflight = next(step for step in steps if 'gcloud run services describe' in step.get('run', ''))
assert auth < steps.index(preflight) < steps.index(worker_build)
assert steps.index(preflight) < next(i for i, step in enumerate(steps) if step.get('id') == 'push')
# Execute the actual workflow preflight with an offline gcloud stub, including access/missing failures.
with tempfile.TemporaryDirectory() as tmp:
    command = Path(tmp, 'gcloud')
    command.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$CALL_LOG"\nexit "${STUB_EXIT:-0}"\n')
    command.chmod(0o755)
    env = {**os.environ, 'PATH': tmp + os.pathsep + os.environ['PATH'],
           'PROJECT': 'test-project', 'REGION': 'test-region', 'CALL_LOG': str(Path(tmp, 'calls'))}
    result = subprocess.run(['bash', '-e', '-c', preflight['run']], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    calls = Path(env['CALL_LOG']).read_text()
    assert 'onolys-worker-eval' in calls and 'onolys-eval-backend-eval' in calls
    assert calls.count('--project test-project --region test-region') == 2
    for code in ['1', '7']:
        result = subprocess.run(['bash', '-e', '-c', preflight['run']], env={**env, 'STUB_EXIT': code}, text=True, capture_output=True)
        assert result.returncode != 0 and 'SP03 Terraform' in result.stdout and 'secret versions' in result.stdout
assert build['outputs']['worker_image'] == '${{ steps.vars.outputs.worker_repo }}@${{ steps.push-worker.outputs.digest }}'
assert any('check_config.sh --image "$IMAGE"' in step.get('run', '') and
           step.get('env', {}).get('IMAGE') == build['outputs']['worker_image'] for step in steps), 'guard worker image by digest'
worker = jobs['deploy-worker']
assert worker['needs'] == 'build'
assert worker['uses'] == './.github/workflows/_deploy-cloudrun.yml'
assert worker['with']['env'] == 'eval' and worker['with']['service'] == 'onolys-worker-eval'
assert worker['with']['image'] == '${{ needs.build.outputs.worker_image }}'
assert worker['with']['git_sha'] == '${{ needs.build.outputs.sha }}'
assert 'env_vars' not in worker['with'], 'Terraform owns eval runtime settings'
assert set(jobs['deploy-backend']['needs']) == {'build', 'deploy-worker'}, 'worker must precede backend rollout'
assert 'env_vars: GIT_SHA=${{ needs.build.outputs.sha }}' in s, 'replace backend bootstrap SHA'
assert 'build' in jobs['site']['needs']
for name in ['site', 'firestore']:
    checkout = next(step for step in jobs[name]['steps'] if step.get('uses', '').startswith('actions/checkout@'))
    assert checkout['with']['ref'] == '${{ needs.build.outputs.sha }}', f'{name} must pin admitted SHA'
assert set(jobs['smoke']['needs']) == {'deploy-backend', 'site', 'firestore'}
assert 'inputs.sha' not in s and 'workflow_call:' not in s
for forbidden in ['DEPLOYER_PROD_SA', 'credentials_json', 'service_account_key', 'environment: production']:
    assert forbidden not in s, f'forbidden workflow config: {forbidden}'
img = Path('scripts/ci/test_eval_image.sh').read_text()
run = img[img.index('docker run -d'):]
for name in ['ENV=staging', 'FIRESTORE_DATABASE=', 'GCP_PROJECT=', 'AUDIO_BUCKET=']:
    assert f'-e {name}' in run, f'docker run in test_eval_image.sh must set {name} (fail-closed config)'
assert 'onolys_admin_auth' not in img and 'onolys-admin-auth' not in img and 'ADMIN_' not in img, 'stale admin auth names in test_eval_image.sh'
assert 'ADMIN_' not in s and 'onolys-eval-backend-staging' not in s, 'legacy admin/staging names remain'
assert 'PROD_VITE_' not in s and 'onolys-eval-staging' not in s, 'eval must not use the prod Firebase app or the legacy site'
fs = json.loads(Path('firebase.json').read_text())['firestore']
ev = [d for d in fs if d['database'] == 'eval']
assert len(ev) == 1 and ev[0]['rules'] == 'firestore.rules' and ev[0]['indexes'] == 'api/firestore.indexes.json'
dc = Path('.github/workflows/_deploy-cloudrun.yml').read_text()
assert 'staging|prod|eval' in dc and "inputs.env == 'prod' && vars.DEPLOYER_PROD_SA || vars.DEPLOYER_STAGING_SA" in dc
assert "inputs.env == 'prod' && 'production' || 'staging'" in dc
print('ok staging-only WIF workflow, digest image, image provenance, independent SHA-coordinated eval release and smoke')
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
    targets = json.loads(Path(rc).read_text())['targets']
    assert targets['onolys-eval']['hosting']['eval-staging'] == ['onolys-eval-app'], rc
    assert 'eval-staging' not in targets.get('onolys', {}).get('hosting', {}), 'legacy eval site mapping removed'
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
