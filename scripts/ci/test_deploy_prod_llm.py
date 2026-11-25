"""Production overrides use promoted-image validation before the single approval."""
import os
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
workflow = yaml.safe_load((ROOT / '.github/workflows/deploy-prod.yml').read_text())
jobs = workflow['jobs']
resolve = jobs['resolve']
steps = resolve['steps']
llm = next(step for step in steps if step.get('id') == 'llm')
assert 'environment' not in resolve, 'validation must precede the production approval'
for key in ('provider', 'model', 'effort'):
    assert llm['env'][f'LLM_{key.upper()}'] == '${{ vars.PROD_LLM_' + key.upper() + ' }}'
    assert resolve['outputs'][f'llm_{key}'] == '${{ steps.llm.outputs.' + key + ' }}'
    for name in ('deploy-api', 'deploy-worker'):
        assert f'LLM_{key.upper()}=${{{{ needs.resolve.outputs.llm_{key} }}}}' in jobs[name]['with']['env_vars']
assert 'LLM_' not in jobs['deploy-voice']['with']['env_vars']
assert llm['env']['IMAGE'] == '${{ steps.digest.outputs.image }}'
move = next(step['run'] for step in steps if 'git checkout --detach' in step.get('run', ''))
assert move.index('cp scripts/ci/validate_staging_llm.py') < move.index('git checkout --detach')
run = llm['run']
assert '${{' not in run, 'configuration crosses env only'
for flag in ('--network none', '--read-only', '--entrypoint python', '--cap-drop ALL', '--security-opt no-new-privileges'):
    assert flag in run
assert run.count('--mount ') == 1 and 'readonly' in run
assert '-e LLM_PROVIDER -e LLM_MODEL -e LLM_EFFORT' in run
assert run.count('-e ') == 3 and '--env-file' not in run
assert 'GITHUB_WORKSPACE' not in run and 'GOOGLE_' not in run
assert '--environment prod --config-root /app/config --stdout' in run
assert all(jobs[name]['needs'] == 'resolve' for name in ('deploy-api', 'deploy-worker', 'deploy-voice', 'rules', 'web'))

# Run the actual workflow command with a fake Docker executable. Blank variables must
# support historical images without starting any container or importing a newer loader.
with tempfile.TemporaryDirectory() as tmp:
    docker = Path(tmp, 'docker')
    docker.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$DOCKER_LOG"\nprintf "provider=openai\\nmodel=gpt-6.1-sol\\neffort=medium\\n"\nexit "${DOCKER_EXIT:-0}"\n')
    docker.chmod(0o755)
    output = Path(tmp, 'output')
    log = Path(tmp, 'docker-log')
    env = {**os.environ, 'PATH': tmp + os.pathsep + os.environ['PATH'], 'RUNNER_TEMP': tmp,
           'GITHUB_OUTPUT': str(output), 'DOCKER_LOG': str(log), 'IMAGE': 'registry/image@sha256:' + 'a' * 64,
           'LLM_PROVIDER': '', 'LLM_MODEL': '', 'LLM_EFFORT': ''}
    result = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', run], env=env, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert output.read_text() == 'provider=\nmodel=\neffort=\n' and not log.exists()
    output.unlink()
    env.update(LLM_PROVIDER='openai', LLM_MODEL='gpt-6.1-sol', LLM_EFFORT='medium')
    result = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', run], env=env, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert output.read_text() == 'provider=openai\nmodel=gpt-6.1-sol\neffort=medium\n'
    args = log.read_text()
    assert env['IMAGE'] in args and f'src={tmp}/validate_staging_llm.py' in args
    result = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', run], env={**env, 'DOCKER_EXIT': '1'}, check=False, capture_output=True, text=True)
    assert result.returncode != 0, 'image validation failure must fail resolve'

# The CI smoke must use the very same docker invocation shape as the production step.
smoke = (ROOT / 'scripts/ci/smoke_prod_llm_validator.sh').read_text()
for flag in ('--rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges',
             '--entrypoint python -e LLM_PROVIDER -e LLM_MODEL -e LLM_EFFORT',
             'dst=/tmp/validate_llm.py,readonly',
             '/tmp/validate_llm.py --environment prod --config-root /app/config --stdout'):
    assert flag in smoke, flag
ci = (ROOT / '.github/workflows/ci.yml').read_text()
assert 'bash scripts/ci/smoke_prod_llm_validator.sh onolys-api:ci' in ci.split('  api-image:', 1)[1].split('\n  frontend:', 1)[0]

print('ok   independent production variables, isolated promoted-image preflight and blank historical rollback')
