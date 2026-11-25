#!/usr/bin/env python3
"""The staging guard must precede side effects and supply both runtime services."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
workflow = yaml.safe_load((ROOT / ".github/workflows/deploy-staging.yml").read_text())
jobs = workflow["jobs"]
build = jobs["build"]
steps = build["steps"]
guard_index = next(i for i, step in enumerate(steps) if step.get("id") == "llm")
auth_index = next(i for i, step in enumerate(steps) if "google-github-actions/auth@" in step.get("uses", ""))
assert guard_index < auth_index, "validate before cloud authentication or build/push"
guard = steps[guard_index]
assert "validate_staging_llm.py" in guard["run"]
assert "${{" not in guard["run"], "raw configuration must enter via env, never shell source"
for key in ("PROVIDER", "MODEL", "EFFORT"):
    assert guard["env"][f"LLM_{key}"] == "${{ vars.LLM_" + key + " }}"
    assert build["outputs"][f"llm_{key.lower()}"] == "${{ steps.llm.outputs." + key.lower() + " }}"
    for service in ("deploy-api", "deploy-worker"):
        env_vars = jobs[service]["with"]["env_vars"]
        assert f"LLM_{key}=${{{{ needs.build.outputs.llm_{key.lower()} }}}}" in env_vars
        assert "vars.LLM_" not in env_vars, "only validated outputs may reach Cloud Run"
# Every other job must transitively depend on the guarded build; no always() bypass.
def depends_on_build(name):
    if name == "build":
        return True
    job = jobs[name]
    assert "always()" not in job.get("if", "")
    needs = job.get("needs", [])
    needs = [needs] if isinstance(needs, str) else needs
    return any(depends_on_build(dep) for dep in needs)

for name in jobs:
    assert depends_on_build(name), f"{name} can run before configuration validation"
# App staging owns only app services; eval has a separate release and lock.
assert "deploy-worker-eval" not in jobs and "deploy-eval" not in jobs
assert "onolys-worker-eval" not in str(jobs) and "deploy-eval.yml" not in str(jobs)
assert workflow["concurrency"] == {"group": "deploy-staging", "cancel-in-progress": False}
print("ok   staging LLM guard precedes app side effects and supplies API/worker")

verify_index = next(i for i, step in enumerate(steps) if step.get("id") == "release")
checkout_index = next(i for i, step in enumerate(steps) if step.get("uses", "").startswith("actions/checkout@"))
assert checkout_index < verify_index < auth_index
assert build["permissions"]["actions"] == "read"
assert steps[verify_index]["uses"] == "actions/github-script@v7"
assert "verify_staging_release.cjs" in steps[verify_index]["with"]["script"]
assert steps[verify_index]["env"]["RELEASE_SHA"] == "${{ steps.vars.outputs.sha }}"
print("ok   staging release admission remains before cloud authentication")
