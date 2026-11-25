// Offline trust-boundary cases for staging's admission guard (no GitHub/cloud calls).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const verify = require('./verify_staging_release.cjs');
const sha = 'a'.repeat(40);
const repo = 'Onolys/onolys';
const success = { head_sha: sha, head_branch: 'main', event: 'push', conclusion: 'success', head_repository: { full_name: repo } };

function fixture({ head = sha, runs = [success], eventName = 'workflow_run', ref = 'refs/heads/main' } = {}) {
  const calls = [];
  return {
    calls, sha,
    context: { repo: { owner: 'Onolys', repo: 'onolys' }, eventName, ref },
    github: { rest: {
      git: { getRef: async (args) => { calls.push(args); return { data: { object: { sha: head } } }; } },
      actions: { listWorkflowRuns: async (args) => { calls.push(args); return { data: { workflow_runs: runs } }; } },
    } },
  };
}

test('CI-green exact current main is admitted for automatic and manual releases', async () => {
  for (const eventName of ['workflow_run', 'workflow_dispatch']) {
    const input = fixture({ eventName });
    await verify(input);
    assert.equal(input.calls[0].ref, 'heads/main');
    assert.deepEqual(input.calls[1], { owner: 'Onolys', repo: 'onolys', workflow_id: 'ci.yml', head_sha: sha, branch: 'main', event: 'push', status: 'completed', per_page: 100 });
  }
});

test('queued older release cannot roll back a newer release', async () => {
  const input = fixture({ head: 'b'.repeat(40) });
  await assert.rejects(verify(input), /current main/);
  assert.equal(input.calls.length, 1);
});

test('manual release cannot bypass main ref or green push CI', async () => {
  await assert.rejects(verify(fixture({ eventName: 'workflow_dispatch', ref: 'refs/heads/feature' })), /main/);
  await assert.rejects(verify(fixture({ eventName: 'workflow_dispatch', runs: [] })), /CI/);
});

test('failed, foreign, PR, other branch and wrong SHA CI runs are rejected', async () => {
  for (const patch of [
    { conclusion: 'failure' }, { conclusion: 'cancelled' }, { head_repository: { full_name: 'fork/onolys' } },
    { event: 'pull_request' }, { head_branch: 'feature' }, { head_sha: 'b'.repeat(40) },
  ]) {
    await assert.rejects(verify(fixture({ runs: [{ ...success, ...patch }] })), /CI/);
  }
});

test('malformed SHA and unexpected trigger fail before API or credentials', async () => {
  for (const patch of [{ sha: 'main' }, { sha: '' }, { context: { eventName: 'pull_request', ref: 'refs/heads/main' } }]) {
    const input = { ...fixture(), ...patch };
    await assert.rejects(verify(input));
    assert.equal(input.calls.length, 0);
  }
});

test('API failure fails closed', async () => {
  const input = fixture();
  input.github.rest.git.getRef = async () => { throw new Error('unavailable'); };
  await assert.rejects(verify(input), /unavailable/);
});
