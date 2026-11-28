// Runs before any cloud authentication in the serialized app release.
// Checking current main also rejects a stale workflow_run/manual run queued after a newer release.
module.exports = async function verifyStagingRelease({ github, context, sha }) {
  if (!['workflow_run', 'workflow_dispatch'].includes(context.eventName) || context.ref !== 'refs/heads/main') {
    throw new Error('Releases must run on this repository main.');
  }
  if (!/^[0-9a-f]{40}$/.test(sha || '')) {
    throw new Error('Release SHA must be a full commit SHA.');
  }
  const { owner, repo } = context.repo;
  const { data: main } = await github.rest.git.getRef({ owner, repo, ref: 'heads/main' });
  if (main.object.sha !== sha) {
    throw new Error('Release SHA is no longer current main; dispatch the release workflow on current main after CI succeeds.');
  }
  const { data } = await github.rest.actions.listWorkflowRuns({
    owner, repo, workflow_id: 'ci.yml', head_sha: sha, branch: 'main', event: 'push', status: 'completed', per_page: 100,
  });
  const tested = data.workflow_runs.some(run =>
    run.head_sha === sha && run.head_branch === 'main' && run.event === 'push' &&
    run.conclusion === 'success' && run.head_repository?.full_name === `${owner}/${repo}`);
  if (!tested) {
    throw new Error('Release requires successful push CI for the exact SHA on this repository main.');
  }
};
