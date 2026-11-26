#!/usr/bin/env python3
"""Contract tests for the Terraform pipeline (docs/reference/infra-pipeline.md). Offline.

terraform.yml plans on PRs only. Each deploy workflow (deploy-staging.yml, deploy-eval.yml, deploy-prod.yml) plans its
environment at the commit being deployed, applies only when the plan has changes, then deploys the app. The job `if:`
expressions are not substring-checked: they are parsed and evaluated against simulated job results (see `simulate`).
"""
import json
import re
import unittest
from pathlib import Path

import yaml

import tf_identity
import tf_live_inputs
import tf_plan_summary

ROOT = Path(__file__).resolve().parents[2]
WFDIR = ROOT / ".github" / "workflows"


def load(path):
    raw = path.read_text()
    return raw, yaml.safe_load(raw)


RAW, WF = load(WFDIR / "terraform.yml")
ON = WF.get("on") or WF[True]
JOBS = WF["jobs"]
PLAN_ACTION_RAW, PLAN_ACTION = load(ROOT / ".github" / "actions" / "terraform-plan" / "action.yml")
APPLY_ACTION_RAW, APPLY_ACTION = load(ROOT / ".github" / "actions" / "terraform-apply" / "action.yml")
CLOUDRUN_RAW, CLOUDRUN = load(WFDIR / "_deploy-cloudrun.yml")
PLAN_USES = "./.github/actions/terraform-plan"
APPLY_USES = "./.github/actions/terraform-apply"
SHA_RE = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")

# env -> (workflow file, job that admits/builds the release and outputs `sha`, enable flag, WIF variable, plan inputs)
DEPLOY = {
    "staging": ("deploy-staging.yml", "build", "TF_STAGING_ENABLED", "STAGING_WIF_PROVIDER",
                {"root": "target/infra/isolated-environment", "tfroot": "isolated", "project": "onolys-staging",
                 "bucket": "onolys-staging-tfstate", "backend": "examples/backend-staging.hcl.example",
                 "varfile": "examples/environment-staging.tfvars.example"}),
    "eval": ("deploy-eval.yml", "build", "TF_EVAL_ENABLED", "EVAL_WIF_PROVIDER",
             {"root": "target/infra/isolated-environment", "tfroot": "isolated", "project": "onolys-eval",
              "bucket": "onolys-eval-tfstate", "backend": "examples/backend-eval.hcl.example",
              "varfile": "examples/environment-eval.tfvars.example"}),
    "prod": ("deploy-prod.yml", "resolve", "TF_PROD_ENABLED", "WIF_PROVIDER",
             {"root": "target/infra", "tfroot": "legacy", "project": "onolys", "bucket": "onolys-tfstate"}),
}
# App jobs and their needs on main before this pipeline existed: ordering among them must be preserved.
APP_NEEDS = {
    "staging": {"deploy-api": {"build"}, "sweep-previews": {"build", "deploy-api"}, "deploy-worker": {"build", "deploy-api"},
                "deploy-voice": {"build", "deploy-api"}, "rules": {"build"}, "web": {"build", "deploy-api"},
                "smoke": {"build", "deploy-api", "deploy-worker", "deploy-voice", "rules", "web"}},
    "eval": {"deploy-worker": {"build"}, "deploy-backend": {"build", "deploy-worker"}, "site": {"build", "deploy-backend"},
             "firestore": {"build"}, "smoke": {"deploy-backend", "site", "firestore"}},
    "prod": {"deploy-api": {"resolve"}, "deploy-worker": {"resolve"}, "deploy-voice": {"resolve"}, "rules": {"resolve"},
             "web": {"resolve"}, "smoke": {"resolve", "deploy-api", "deploy-worker", "deploy-voice", "rules", "web"},
             "tag": {"resolve", "deploy-api", "deploy-worker", "deploy-voice", "rules", "web", "smoke"}},
}
INFRA = ("infra-plan", "infra-apply")


def deploy_wf(env):
    return load(WFDIR / DEPLOY[env][0])


def needs_of(job):
    n = job.get("needs", [])
    return {n} if isinstance(n, str) else set(n)


# --- a tiny evaluator for the `if:` subset these workflows use -------------------------------------------------------------
TOKEN = re.compile(r"\s*(\$\{\{|\}\}|!cancelled\(\)|&&|\|\||==|!=|\(|\)|'[^']*'|[A-Za-z_][\w.-]*)")


def to_python(expr):
    """Translate a GitHub expression (subset) to a Python expression over R(job), O(job, key), V(name), G(path)."""
    out, pos = [], 0
    expr = expr.strip()
    while pos < len(expr):
        m = TOKEN.match(expr, pos)
        if not m:
            raise ValueError(f"unsupported expression near: {expr[pos:]!r}")
        tok = m.group(1)
        pos = m.end()
        if tok in ("${{", "}}"):
            continue
        if tok == "!cancelled()":
            out.append("(not CANCELLED)")
        elif tok == "&&":
            out.append(" and ")
        elif tok == "||":
            out.append(" or ")
        elif tok in ("==", "!=", "(", ")") or tok.startswith("'"):
            out.append(f" {tok} ")
        elif tok.startswith("needs."):
            parts = tok.split(".")
            if parts[2] == "result":
                out.append(f"R({parts[1]!r})")
            elif parts[2] == "outputs":
                out.append(f"O({parts[1]!r}, {parts[3]!r})")
            else:
                raise ValueError(tok)
        elif tok.startswith("vars."):
            out.append(f"V({tok[5:]!r})")
        elif tok.startswith("github."):
            out.append(f"G({tok[7:]!r})")
        else:
            raise ValueError(f"unsupported token {tok!r} (always(), success(), failure() are not allowed here)")
    return "".join(out)


def simulate(jobs, variables, fail=(), outputs=None, github=None):
    """Run the job graph: which jobs run, and with what result. `fail` = jobs whose own steps fail when they run."""
    outputs = outputs or {}
    github = github or {}
    results, order = {}, list(jobs)
    while order:
        progressed = False
        for name in list(order):
            job = jobs[name]
            if not needs_of(job) <= set(results):
                continue
            cond = job.get("if")
            if cond is None:  # GitHub default: success() over the needs
                runs = all(results[n] == "success" for n in needs_of(job))
            else:
                env = {"R": lambda j: results[j], "O": lambda j, k: outputs.get(j, {}).get(k, "") if results[j] == "success" else "",
                       "V": lambda v: variables.get(v, ""), "G": lambda p: github.get(p, ""), "CANCELLED": False}
                runs = bool(eval(to_python(str(cond)), {"__builtins__": {}}, env))  # noqa: S307 (test-only, own files)
            results[name] = ("failure" if name in fail else "success") if runs else "skipped"
            order.remove(name)
            progressed = True
        assert progressed, f"cycle or unknown need among {order}"
    return results


def result_checks(cond):
    checks = {}
    for job, value in re.findall(r"needs\.([\w-]+)\.result == '(\w+)'", cond):
        checks.setdefault(job, set()).add(value)
    return checks


class TerraformWorkflowTests(unittest.TestCase):
    def test_pr_plan_and_manual_plan_only(self):
        self.assertEqual(set(ON), {"pull_request", "workflow_dispatch"})
        for path in ("infra/**", ".github/actions/terraform-plan/**", ".github/actions/terraform-apply/**", "scripts/ci/tf_*.py"):
            self.assertIn(path, ON["pull_request"]["paths"])
        self.assertEqual(set(JOBS), {"plan", "comment"})
        steps = [s for j in JOBS.values() for s in j["steps"]]
        self.assertFalse(any("terraform apply" in s.get("run", "") or s.get("uses") == APPLY_USES for s in steps))
        self.assertNotIn("environment", JOBS["plan"])
        self.assertNotIn("terraform-prod", RAW)
        self.assertIn("github.event_name != 'workflow_dispatch' || github.ref == 'refs/heads/main'", JOBS["plan"]["if"])

    def test_plan_uses_shared_action_without_saving(self):
        steps = JOBS["plan"]["steps"]
        plan = [s for s in steps if s.get("uses") == PLAN_USES]
        self.assertEqual(len(plan), 1)
        self.assertEqual(str(plan[0]["with"].get("save", "false")), "false")
        self.assertIn("steps.cfg.outputs.ok == 'true'", plan[0]["if"])
        self.assertNotIn("gcloud storage cp", RAW)

    def test_permissions_and_fork_guard(self):
        self.assertEqual(WF["permissions"], {"contents": "read"})
        self.assertEqual(JOBS["plan"]["permissions"], {"contents": "read", "id-token": "write"})
        self.assertEqual(JOBS["comment"]["permissions"], {"contents": "read", "pull-requests": "write"})
        guard = "github.event.pull_request.head.repo.full_name == github.repository"
        self.assertIn(guard, JOBS["plan"]["if"])
        self.assertIn(guard, JOBS["comment"]["if"])

    def test_matrix_backends_vars_and_budget(self):
        m = {e["env"]: e for e in JOBS["plan"]["strategy"]["matrix"]["include"]}
        self.assertEqual(list(m), ["prod", "staging", "eval"])
        self.assertEqual(JOBS["plan"]["timeout-minutes"], 5)
        self.assertEqual(JOBS["comment"]["timeout-minutes"], 5)
        self.assertEqual({k: e["wif_var"] for k, e in m.items()}, {"prod": "WIF_PROVIDER", "staging": "STAGING_WIF_PROVIDER", "eval": "EVAL_WIF_PROVIDER"})
        for env, e in m.items():
            if env == "prod":
                self.assertEqual((e["root"], e["bucket"], e["backend"], e["varfile"]), ("infra", "onolys-tfstate", "", ""))
                continue
            want = DEPLOY[env][4]
            self.assertEqual(e["root"], "infra/isolated-environment")
            self.assertEqual((e["backend"], e["varfile"], e["project"]), (want["backend"], want["varfile"], want["project"]))
            self.assertTrue((ROOT / e["root"] / e["backend"]).is_file())
            self.assertTrue((ROOT / e["root"] / e["varfile"]).is_file())
        flags = set(re.findall(r"vars\[format\('(TF_\{0\}_[A-Z]+)'", RAW))
        self.assertEqual(flags, {"TF_{0}_ENABLED"})

    def test_summary_artifacts_kept_7_days(self):
        uploads = [s for s in JOBS["plan"]["steps"] if s.get("uses", "").startswith("actions/upload-artifact@")]
        self.assertTrue(uploads)
        for s in uploads:
            self.assertEqual(s["with"]["retention-days"], 7)
        self.assertNotIn("tf-meta", RAW + APPLY_ACTION_RAW + PLAN_ACTION_RAW)

    def test_comment_is_updated_in_place_and_explains_the_deploy_pipelines(self):
        script = next(s["with"]["script"] for s in JOBS["comment"]["steps"] if "script" in s.get("with", {}))
        self.assertIn("terraform-plan-comment", script)
        self.assertIn("updateComment", script)
        self.assertIn("createComment", script)
        self.assertIn("deploy pipeline", script)
        self.assertNotIn("terraform-prod", script)


class ActionTests(unittest.TestCase):
    def test_every_external_action_pinned_to_a_commit_sha(self):
        steps = [("terraform.yml", s) for j in JOBS.values() for s in j["steps"]]
        steps += [("plan action", s) for s in PLAN_ACTION["runs"]["steps"]] + [("apply action", s) for s in APPLY_ACTION["runs"]["steps"]]
        for env in DEPLOY:
            _, wf = deploy_wf(env)
            steps += [(f"{env}:{n}", s) for n in INFRA for s in wf["jobs"][n]["steps"]]
        for where, step in steps:
            if "uses" in step and not step["uses"].startswith("./"):
                self.assertRegex(step["uses"], SHA_RE, f"{where}: {step['uses']}")

    def test_plan_action_is_readonly_private_and_guarded(self):
        steps = PLAN_ACTION["runs"]["steps"]
        names = [s.get("id", s.get("name", s.get("uses", ""))) for s in steps]
        idx = {n: i for i, n in enumerate(names)}
        auth = next(i for i, s in enumerate(steps) if s.get("uses", "").startswith("google-github-actions/auth@"))
        self.assertLess(idx["ident"], auth)
        self.assertIn("--kind plan", steps[idx["ident"]]["run"])
        self.assertLess(auth, idx["live"])
        self.assertLess(idx["live"], idx["plan"])
        run = steps[idx["plan"]]["run"]
        for flag in ("-lock=false", "-lockfile=readonly", "-detailed-exitcode", "-out=tfplan", "terraform show -json tfplan >",
                     "--protect module.terraform_ci"):
            self.assertIn(flag, run)
        self.assertNotIn("exit 0", run)
        self.assertIn("set -e", run.split("terraform plan")[-1])  # a failing summary fails the step
        self.assertIn("GITHUB_STEP_SUMMARY", PLAN_ACTION_RAW)  # the approver sees the per-resource summary in the run
        save = steps[idx["save"]]
        self.assertEqual(save["if"], "inputs.save == 'true' && steps.plan.outputs.status == 'ok'")
        self.assertIn('gs://${BUCKET}/${object}', save["run"])
        self.assertIn("plans/", save["run"])
        self.assertIn("live_sha256", save["run"])
        self.assertEqual(set(PLAN_ACTION["outputs"]), {"status", "changes", "sha256", "object", "live_sha256", "summary_file"})
        self.assertEqual(steps[-1]["if"], "steps.plan.outputs.status != 'ok'")  # fail the job on a failed/blocked plan
        self.assertNotRegex(PLAN_ACTION_RAW, r"terraform show -no-color|upload-artifact|credentials_json")
        for s in steps:
            if s.get("uses", "").startswith("hashicorp/setup-terraform@"):
                self.assertEqual(str(s["with"]["terraform_version"]), "1.9.8")

    def test_apply_action_applies_exactly_the_saved_plan(self):
        self.assertEqual({"plan_sha256", "plan_object", "live_sha256", "wif_provider"} - set(APPLY_ACTION["inputs"]), set())
        self.assertNotIn("download-artifact", APPLY_ACTION_RAW)
        steps = APPLY_ACTION["runs"]["steps"]
        pip = next(i for i, s in enumerate(steps) if "pip install" in s.get("run", ""))
        auth = next(i for i, s in enumerate(steps) if s.get("uses", "").startswith("google-github-actions/auth@"))
        self.assertLess(pip, auth)
        self.assertIn("--require-hashes", steps[pip]["run"])
        self.assertTrue(any("--kind apply" in s.get("run", "") for s in steps[:auth]))
        for text in ("--expect-sha256", "saved plan hash mismatch", "sed '/^Outputs:/,$d'", "Re-run all jobs", "-lockfile=readonly"):
            self.assertIn(text, APPLY_ACTION_RAW)
        reqs = (ROOT / "scripts" / "ci" / "tf-apply-requirements.txt").read_text()
        for line in reqs.splitlines():
            if re.match(r"^[A-Za-z0-9_.-]+", line):
                self.assertRegex(line, r"^[A-Za-z0-9_.-]+==\S+ \\$")

    def test_actions_are_composite_so_job_workflow_ref_is_the_calling_workflow(self):
        for action in (PLAN_ACTION, APPLY_ACTION):
            self.assertEqual(action["runs"]["using"], "composite")

    def test_pinned_terraform_matches_versions_tf(self):
        for p in ("infra/versions.tf", "infra/isolated-environment/versions.tf"):
            self.assertIn('required_version = "~> 1.9.8"', (ROOT / p).read_text())


class DeployPipelineTests(unittest.TestCase):
    def test_infra_plan_job_plans_the_deployed_commit_read_only(self):
        for env, (_, first, flag, wif, inputs) in DEPLOY.items():
            _, wf = deploy_wf(env)
            job = wf["jobs"]["infra-plan"]
            self.assertEqual(needs_of(job), {first}, env)
            self.assertEqual(result_checks(job["if"]), {first: {"success"}}, env)
            self.assertIn(f"vars.{flag} == 'true'", job["if"])
            self.assertEqual(job["timeout-minutes"], 5)
            self.assertEqual(job["permissions"], {"contents": "read", "id-token": "write"})
            self.assertNotIn("environment", job, f"{env}: the plan runs before any approval so the approver can read it")
            checkouts = [s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout@")]
            self.assertEqual(len(checkouts), 2, env)
            self.assertNotIn("ref", checkouts[0].get("with", {}))  # workflow ref: helper scripts and actions
            self.assertEqual(checkouts[1]["with"]["ref"], f"${{{{ needs.{first}.outputs.sha }}}}")
            self.assertEqual(checkouts[1]["with"]["path"], "target")
            plan = next(s for s in job["steps"] if s.get("uses") == PLAN_USES)
            self.assertEqual(plan["id"], "plan")
            self.assertEqual(str(plan["with"]["save"]), "true")
            self.assertEqual(plan["with"]["env"], env)
            self.assertEqual(plan["with"]["wif_provider"], f"${{{{ vars.{wif} }}}}")
            for k, v in inputs.items():
                self.assertEqual(plan["with"][k], v, f"{env}: {k}")
            for out in ("changes", "sha256", "object", "live_sha256"):
                self.assertEqual(job["outputs"][out], f"${{{{ steps.plan.outputs.{out} }}}}")

    def test_infra_apply_only_on_changes_with_the_saved_plan(self):
        for env, (_, first, _, wif, inputs) in DEPLOY.items():
            _, wf = deploy_wf(env)
            job = wf["jobs"]["infra-apply"]
            self.assertEqual(needs_of(job), {first, "infra-plan"})
            self.assertEqual(result_checks(job["if"]), {first: {"success"}, "infra-plan": {"success"}}, env)
            self.assertIn("needs.infra-plan.outputs.changes == 'true'", job["if"])
            self.assertEqual(job["timeout-minutes"], 20)
            self.assertEqual(job["permissions"], {"contents": "read", "id-token": "write"})
            if env == "prod":
                self.assertEqual(job["environment"], "production")
                self.assertEqual(job["name"], "infra-apply")
            else:
                self.assertNotIn("environment", job)
            apply = next(s for s in job["steps"] if s.get("uses") == APPLY_USES)
            w = apply["with"]
            self.assertEqual(w["plan_sha256"], "${{ needs.infra-plan.outputs.sha256 }}")
            self.assertEqual(w["plan_object"], "${{ needs.infra-plan.outputs.object }}")
            self.assertEqual(w["live_sha256"], "${{ needs.infra-plan.outputs.live_sha256 }}")
            self.assertEqual(w["wif_provider"], f"${{{{ vars.{wif} }}}}")
            self.assertEqual(w["root"], inputs["root"])
            self.assertEqual(str(w.get("python_deps", "false")), "true" if env == "prod" else "false")
            checkout = [s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout@")]
            self.assertEqual(checkout[1]["with"], {"ref": f"${{{{ needs.{first}.outputs.sha }}}}", "path": "target", "persist-credentials": False})

    def test_every_job_after_infra_uses_not_cancelled_and_explicit_results(self):
        for env in DEPLOY:
            _, wf = deploy_wf(env)
            jobs = wf["jobs"]
            for name, want_needs in APP_NEEDS[env].items():
                job = jobs[name]
                self.assertLessEqual(want_needs, needs_of(job), f"{env}:{name} lost an ordering need")
                cond = str(job.get("if", ""))
                self.assertTrue(cond.startswith("${{ !cancelled() && "), f"{env}:{name}: {cond!r}")
                self.assertNotRegex(cond, r"always\(\)|success\(\)|failure\(\)")
                checks = result_checks(cond)
                for need in needs_of(job):
                    want = {"success", "skipped"} if need in INFRA else {"success"}
                    self.assertEqual(checks.get(need), want, f"{env}:{name} needs.{need}.result")

    def test_app_waits_for_infra_in_staging_and_eval_through_needs(self):
        for env in ("staging", "eval"):
            _, wf = deploy_wf(env)
            for name in ("deploy-api", "rules") if env == "staging" else ("deploy-worker", "firestore"):
                self.assertLessEqual(set(INFRA), needs_of(wf["jobs"][name]), f"{env}:{name}")

    def test_scenarios(self):
        """Disabled = today's pipeline; no changes = app only; failed plan or apply = no app deploy."""
        for env, (_, first, flag, _, _) in DEPLOY.items():
            _, wf = deploy_wf(env)
            jobs = wf["jobs"]
            app = set(APP_NEEDS[env])
            gh = {"ref": "refs/heads/main", "event_name": "workflow_dispatch"}
            wait = (lambda r: {j for j in app if j not in ("smoke", "tag")}) if env == "prod" else (lambda r: set())

            r = simulate(jobs, {}, github=gh)
            self.assertEqual((r["infra-plan"], r["infra-apply"]), ("skipped", "skipped"), env)
            self.assertTrue(all(r[j] == "success" for j in app), (env, r))

            on = {flag: "true"}
            r = simulate(jobs, on, outputs={"infra-plan": {"changes": "false"}}, github=gh)
            self.assertEqual(r["infra-apply"], "skipped")
            self.assertTrue(all(r[j] == "success" for j in app), (env, r))

            r = simulate(jobs, on, outputs={"infra-plan": {"changes": "true"}}, github=gh)
            self.assertEqual(r["infra-apply"], "success")
            self.assertTrue(all(r[j] == "success" for j in app), (env, r))

            r = simulate(jobs, on, fail={"infra-plan"}, github=gh)
            self.assertEqual(r["infra-apply"], "skipped")
            self.assertTrue(all(r[j] == "skipped" for j in app), (env, r))

            # apply fails: staging/eval app jobs are skipped by `needs`; prod app jobs (approved together with the apply) fail
            # in their wait step, so smoke and tag never run
            r = simulate(jobs, on, fail={"infra-apply"} | wait(None), outputs={"infra-plan": {"changes": "true"}}, github=gh)
            self.assertEqual(r["infra-apply"], "failure")
            self.assertFalse(any(r[j] == "success" for j in app), (env, r))

            r = simulate(jobs, on, fail={first}, github=gh)
            self.assertTrue(all(r[j] == "skipped" for j in app | set(INFRA)), (env, r))

    def test_prod_one_approval_infra_and_app_start_together(self):
        _, wf = deploy_wf("prod")
        jobs = wf["jobs"]
        gated = {n for n, j in jobs.items() if j.get("environment") == "production"}
        self.assertEqual(gated, {"infra-apply", "rules", "web"})
        callers = {n for n, j in jobs.items() if j.get("uses") == "./.github/workflows/_deploy-cloudrun.yml"}
        self.assertEqual(callers, {"deploy-api", "deploy-worker", "deploy-voice"})
        # every production job becomes ready at the same moment (same needs) -> one review prompt, one click
        for n in gated | callers:
            self.assertEqual(needs_of(jobs[n]), {"resolve", "infra-plan"}, n)
        wait_expr = "${{ needs.infra-plan.outputs.changes == 'true' && 'infra-apply' || '' }}"
        for n in callers:
            self.assertEqual(jobs[n]["with"]["wait_for_job"], wait_expr)
            self.assertEqual(jobs[n]["permissions"].get("actions"), "read")
        for n in ("rules", "web"):
            steps = jobs[n]["steps"]
            self.assertEqual(steps[0]["name"], WAIT_NAME)
            self.assertEqual(steps[0]["env"]["WAIT_JOB"], wait_expr)
            self.assertEqual(steps[0]["run"], cloudrun_wait()["run"], f"{n}: wait snippet must match _deploy-cloudrun.yml")
            self.assertEqual(jobs[n]["permissions"].get("actions"), "read")
        self.assertNotIn("terraform-prod", deploy_wf("prod")[0])

    def test_concurrency_serializes_each_env(self):
        for env in DEPLOY:
            _, wf = deploy_wf(env)
            self.assertEqual(wf["concurrency"], {"group": f"deploy-{env}", "cancel-in-progress": False})

    def test_no_keys_and_checkout_before_auth(self):
        for env in DEPLOY:
            raw, wf = deploy_wf(env)
            self.assertNotRegex(raw, r"credentials_json|GOOGLE_CREDENTIALS|service_account_key")
            for n in INFRA:
                steps = wf["jobs"][n]["steps"]
                local = max(i for i, s in enumerate(steps) if s.get("uses", "").startswith("./"))
                last_checkout = max(i for i, s in enumerate(steps) if s.get("uses", "").startswith("actions/checkout@"))
                self.assertLess(last_checkout, local)


WAIT_NAME = "Wait for infra-apply (approved together with this job; app deploys only after infrastructure)"


def cloudrun_wait():
    return next(s for s in CLOUDRUN["jobs"]["deploy"]["steps"] if s.get("name") == WAIT_NAME)


class CloudRunWaitTests(unittest.TestCase):
    def test_reusable_deploy_waits_for_the_named_job(self):
        on = CLOUDRUN.get("on") or CLOUDRUN[True]
        self.assertEqual(on["workflow_call"]["inputs"]["wait_for_job"]["default"], "")
        self.assertEqual(CLOUDRUN["permissions"], {"contents": "read", "id-token": "write", "actions": "read"})
        job = CLOUDRUN["jobs"]["deploy"]
        self.assertEqual(job["timeout-minutes"], "${{ inputs.wait_for_job != '' && 40 || 15 }}")
        step = cloudrun_wait()
        self.assertEqual(job["steps"].index(step), 0)  # before auth and deploy
        self.assertEqual(step["if"], "inputs.wait_for_job != ''")
        self.assertEqual(step["env"], {"GH_TOKEN": "${{ github.token }}", "WAIT_JOB": "${{ inputs.wait_for_job }}"})
        run = step["run"]
        self.assertIn("actions/runs/${GITHUB_RUN_ID}/jobs?filter=latest&per_page=100", run)
        self.assertIn('"completed success")', run)
        self.assertIn("exit 1", run)
        self.assertNotIn("${{", run)

    def test_wait_snippet_behaviour(self):
        import os, subprocess, tempfile
        run = cloudrun_wait()["run"].replace("sleep 15", "sleep 0")
        with tempfile.TemporaryDirectory() as tmp:
            gh = Path(tmp, "gh")
            gh.write_text('#!/bin/bash\nn=$(cat "$STATE_DIR/n" 2>/dev/null || echo 0); echo $((n+1)) > "$STATE_DIR/n"\n'
                          'sed -n "$((n+1))p" "$STATE_DIR/seq"\n')
            gh.chmod(0o755)
            base = {**os.environ, "PATH": tmp + os.pathsep + os.environ["PATH"], "STATE_DIR": tmp, "WAIT_JOB": "infra-apply",
                    "GITHUB_REPOSITORY": "o/r", "GITHUB_RUN_ID": "1"}
            for seq, code in ((["missing", "queued ", "in_progress ", "completed success"], 0),
                              (["in_progress ", "completed failure"], 1), (["completed cancelled"], 1)):
                Path(tmp, "n").write_text("0")
                Path(tmp, "seq").write_text("\n".join(seq) + "\n")
                p = subprocess.run(["bash", "-c", run], env=base, capture_output=True, text=True)
                self.assertEqual(p.returncode, code, (seq, p.stdout, p.stderr))


def knative(env):
    return {"spec": {"template": {"spec": {"containers": [{"env": env}]}}}}


class LiveInputsTests(unittest.TestCase):
    def test_legacy_shape_is_a_prod_map(self):
        worker = knative([{"name": "GIT_SHA", "value": "abc"}])
        api = knative([{"name": "GIT_SHA", "value": "abc"}, {"name": "LLM_PROVIDER"}, {"name": "LLM_MODEL", "value": ""}])
        out, warns = tf_live_inputs.build("legacy", worker, api)
        self.assertEqual(out, {"git_sha": {"prod": "abc"}, "llm_provider": "", "llm_model": ""})
        self.assertEqual(warns, [])

    def test_isolated_shape_and_secret_refs_never_emitted(self):
        worker = knative([{"name": "GIT_SHA", "value": "abc"}])
        api = knative([{"name": "LLM_EFFORT", "value": "high"}, {"name": "X", "valueFrom": {"secretKeyRef": {}}}])
        out, _ = tf_live_inputs.build("isolated", worker, api)
        self.assertEqual(out, {"git_sha": "abc", "llm_effort": "high"})
        self.assertNotIn("X", json.dumps(out))

    def test_missing_services_use_terraform_defaults_and_mismatch_warns(self):
        self.assertEqual(tf_live_inputs.build("isolated", None, None)[0], {})
        _, warns = tf_live_inputs.build("isolated", knative([{"name": "GIT_SHA", "value": "a"}]),
                                        knative([{"name": "GIT_SHA", "value": "b"}]))
        self.assertTrue(warns)

    def test_digest_is_stable_and_detects_a_deploy(self):
        a = {"git_sha": "abc", "llm_model": "m"}
        self.assertEqual(tf_live_inputs.digest(a), tf_live_inputs.digest(dict(reversed(list(a.items())))))
        self.assertNotEqual(tf_live_inputs.digest(a), tf_live_inputs.digest({**a, "git_sha": "def"}))

    def test_expect_sha256_mismatch_aborts_with_rerun_message(self):
        import io, contextlib, tempfile
        from unittest import mock
        svc = knative([{"name": "GIT_SHA", "value": "new"}])
        out = Path(tempfile.mkdtemp()) / "live.json"
        argv = ["x", "--root", "isolated", "--env", "staging", "--project", "p", "--out", str(out)]
        err = io.StringIO()
        with mock.patch.object(tf_live_inputs, "describe", return_value=svc), mock.patch("sys.argv", argv + ["--expect-sha256", "0" * 64]), \
                contextlib.redirect_stderr(err):
            self.assertEqual(tf_live_inputs.main(), 1)
        self.assertIn("Re-run all jobs to re-plan", err.getvalue())
        ok = tf_live_inputs.digest({"git_sha": "new"})
        with mock.patch.object(tf_live_inputs, "describe", return_value=svc), mock.patch("sys.argv", argv + ["--expect-sha256", ok]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tf_live_inputs.main(), 0)
        self.assertEqual(__import__("hashlib").sha256(out.read_bytes()).hexdigest(), ok)  # file hash == digest (plan-time sha256sum)

    def test_cloud_run_v2_shape(self):
        v2 = {"template": {"containers": [{"env": [{"name": "GIT_SHA", "value": "z"}]}]}}
        self.assertEqual(tf_live_inputs.env_values(v2), {"GIT_SHA": "z"})


class IdentityTests(unittest.TestCase):
    WIF = "projects/123456789/locations/global/workloadIdentityPools/github/providers/github"

    def test_derives_plan_and_apply_names(self):
        self.assertEqual(tf_identity.derive(self.WIF, "onolys-eval", "plan"),
                         ("projects/123456789/locations/global/workloadIdentityPools/github-plan/providers/github-plan",
                          "terraform-plan@onolys-eval.iam.gserviceaccount.com"))
        self.assertEqual(tf_identity.derive(self.WIF, "onolys", "apply")[0].split("/")[-1], "github-apply")

    def test_rejects_unexpected_shapes(self):
        for bad in ("", "projects/1/locations/global/workloadIdentityPools/other/providers/github", self.WIF + "x"):
            with self.assertRaises(ValueError):
                tf_identity.derive(bad, "onolys", "plan")
        with self.assertRaises(ValueError):
            tf_identity.derive(self.WIF, "bad project", "plan")

    def test_matches_terraform_module_names(self):
        mod = (ROOT / "infra" / "modules" / "terraform-ci" / "main.tf").read_text()
        for kind in ("plan", "apply"):
            self.assertIn(f'= "github-{kind}"', mod)
            self.assertIn(f'account_id   = "terraform-{kind}"', mod)


class SummaryTests(unittest.TestCase):
    PLAN = {
        "resource_changes": [
            {"address": "a.keep", "change": {"actions": ["no-op"]}},
            {"address": "a.new", "change": {"actions": ["create"], "after": {"token": "SUPERSECRETVALUE123"}}},
            {"address": "a.gone", "change": {"actions": ["delete"]}},
            {"address": "a.swap", "change": {"actions": ["delete", "create"]}},
            {"address": "a.edit", "change": {"actions": ["update"]}},
        ],
        "output_changes": {"web_env": {"actions": ["update"], "after": {"key": "AIzaSyDUMMYDUMMYDUMMYDUMMYDUMMYDUMMY123"}}},
    }

    def test_counts_order_and_no_values(self):
        text = tf_plan_summary.render("prod", "ok", self.PLAN, "", 80)
        self.assertIn("1 to add, 1 to change, 1 to replace, 1 to destroy", text)
        self.assertLess(text.index("a.gone"), text.index("a.new"))
        self.assertNotIn("a.keep", text)
        self.assertIn("`web_env`", text)
        self.assertNotIn("SUPERSECRETVALUE123", text)
        self.assertNotIn("AIza", text)
        self.assertIn("Destructive", text)

    def test_truncation(self):
        plan = {"resource_changes": [{"address": f"r.{i}", "change": {"actions": ["create"]}} for i in range(200)]}
        text = tf_plan_summary.render("eval", "ok", plan, "", 10)
        self.assertIn("and 190 more", text)
        self.assertLessEqual(len(text), tf_plan_summary.MAX_COMMENT_CHARS)

    def test_failure_excerpt_is_redacted(self):
        log = "init ok\nError: boom\napi_key = AIzaSyDUMMYDUMMYDUMMYDUMMYDUMMYDUMMY123\ntoken: ghp_abcdefghijklmnopqrstuvwxyz0123\n"
        text = tf_plan_summary.render("prod", "failed", None, log, 80)
        self.assertIn("Plan failed", text)
        self.assertIn("[redacted]", text)
        self.assertNotIn("AIza", text)
        self.assertNotIn("ghp_", text)

    def test_forget_and_unknown_actions_do_not_crash(self):
        plan = {"resource_changes": [
            {"address": "a.out", "change": {"actions": ["forget"]}},
            {"address": "a.swap", "change": {"actions": ["forget", "create"]}},
            {"address": "a.future", "change": {"actions": ["teleport"]}},
        ]}
        text = tf_plan_summary.render("prod", "ok", plan, "", 80)
        self.assertIn("1 to forget", text)
        self.assertIn("1 to replace", text)
        self.assertIn("1 teleport", text)
        self.assertIn("`teleport` a.future", text)

    def test_malformed_plan_exits_nonzero(self):
        import subprocess, sys, tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{not json")
        proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "ci" / "tf_plan_summary.py"), "--env", "prod",
                               "--status", "ok", "--plan-json", f.name], capture_output=True)
        self.assertNotEqual(proc.returncode, 0)

    def test_unconfigured(self):
        self.assertIn("Not configured", tf_plan_summary.render("staging", "unconfigured", None, "", 80))

    def test_protected_identities_block_destroy_and_forget_but_not_replace(self):
        import subprocess, sys, tempfile
        plan = {"resource_changes": [
            {"address": "module.terraform_ci.google_service_account.apply", "change": {"actions": ["delete"]}},
            {"address": 'module.terraform_ci.google_project_iam_member.plan["roles/run.viewer"]', "change": {"actions": ["forget"]}},
            {"address": "module.terraform_ci.google_service_account_iam_member.apply_wif", "change": {"actions": ["delete", "create"]}},
            {"address": "module.terraform_ci_other.x", "change": {"actions": ["delete"]}},
            {"address": "google_cloud_run_v2_service.api", "change": {"actions": ["delete"]}},
        ]}
        self.assertEqual(tf_plan_summary.protected_removals(plan, ["module.terraform_ci"]), [
            'module.terraform_ci.google_project_iam_member.plan["roles/run.viewer"]',
            "module.terraform_ci.google_service_account.apply"])
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(plan, f)
        cmd = [sys.executable, str(ROOT / "scripts" / "ci" / "tf_plan_summary.py"), "--env", "prod", "--status", "ok",
               "--plan-json", f.name]
        blocked = subprocess.run(cmd + ["--protect", "module.terraform_ci"], capture_output=True, text=True)
        self.assertEqual(blocked.returncode, 3)
        self.assertIn("BLOCKED", blocked.stdout)
        self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        safe = {"resource_changes": [plan["resource_changes"][2]]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as g:
            json.dump(safe, g)
        ok = subprocess.run(cmd[:-1] + [g.name, "--protect", "module.terraform_ci"], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0)


class EvaluatorSelfTests(unittest.TestCase):
    def test_translation_rejects_unknown_functions(self):
        with self.assertRaises(ValueError):
            to_python("${{ always() && needs.a.result == 'success' }}")
        self.assertEqual(simulate({"a": {}, "b": {"needs": "a", "if": "${{ !cancelled() && needs.a.result == 'skipped' }}"}},
                                  {}, fail={"a"}), {"a": "failure", "b": "skipped"})


if __name__ == "__main__":
    unittest.main()
