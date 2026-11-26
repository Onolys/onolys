#!/usr/bin/env python3
"""Contract tests for .github/workflows/terraform.yml and scripts/ci/tf_*.py (docs/reference/infra-pipeline.md). Offline."""
import json
import re
import unittest
from pathlib import Path

import yaml

import tf_identity
import tf_live_inputs
import tf_plan_summary

ROOT = Path(__file__).resolve().parents[2]
RAW = (ROOT / ".github" / "workflows" / "terraform.yml").read_text()
WF = yaml.safe_load(RAW)
ON = WF.get("on") or WF[True]
JOBS = WF["jobs"]
ACTION_RAW = (ROOT / ".github" / "actions" / "terraform-apply" / "action.yml").read_text()
ACTION = yaml.safe_load(ACTION_RAW)
LOCAL_ACTION = "./.github/actions/terraform-apply"
APPLY_JOBS = ("apply-staging", "apply-eval", "apply-prod")
SHA_RE = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


class WorkflowTests(unittest.TestCase):
    def test_triggers(self):
        self.assertEqual(set(ON), {"pull_request", "push", "workflow_dispatch"})
        self.assertEqual(ON["push"]["branches"], ["main"])
        for ev in ("pull_request", "push"):
            self.assertIn("infra/**", ON[ev]["paths"])
            self.assertIn(".github/actions/terraform-apply/**", ON[ev]["paths"])

    def test_workflow_dispatch_only_from_main(self):
        self.assertIn("github.event_name != 'workflow_dispatch' || github.ref == 'refs/heads/main'", JOBS["plan"]["if"])

    def test_every_action_pinned_to_a_commit_sha(self):
        steps = [(n, st) for n, job in JOBS.items() for st in job["steps"]] + [("action", st) for st in ACTION["runs"]["steps"]]
        for name, step in steps:
            if "uses" in step and step["uses"] != LOCAL_ACTION:
                self.assertRegex(step["uses"], SHA_RE, f"{name}: {step['uses']}")

    def test_default_permissions_read_only_and_id_token_only_where_needed(self):
        self.assertEqual(WF["permissions"], {"contents": "read"})
        for name, job in JOBS.items():
            perms = job.get("permissions", {})
            uses_auth = any(s.get("uses", "").startswith("google-github-actions/auth@") or s.get("uses") == LOCAL_ACTION
                            for s in job["steps"])
            self.assertEqual(perms.get("id-token") == "write", uses_auth, name)
        self.assertEqual(JOBS["comment"]["permissions"].get("pull-requests"), "write")
        for name in ("plan", "gate") + APPLY_JOBS:
            self.assertNotIn("pull-requests", JOBS[name]["permissions"])
        # the PR-commenting job and the gate hold no cloud identity
        for name in ("comment", "gate"):
            self.assertNotIn("id-token", JOBS[name]["permissions"])

    def test_prod_apply_uses_dedicated_environment_main_and_only_when_changed(self):
        job = JOBS["apply-prod"]
        self.assertEqual(job["environment"], "terraform-prod")
        self.assertNotEqual(job["environment"], "production")
        self.assertIn("refs/heads/main", job["if"])
        self.assertIn("pull_request", job["if"])
        self.assertIn("needs.gate.outputs.prod_changes == 'true'", job["if"])
        for name in ("plan", "gate", "comment", "apply-staging", "apply-eval"):
            self.assertNotIn("environment", JOBS[name])

    def test_each_apply_gates_on_its_own_env_not_the_whole_plan_matrix(self):
        for name, env in zip(APPLY_JOBS, ("staging", "eval", "prod")):
            job = JOBS[name]
            self.assertEqual(job["needs"], "gate", name)
            self.assertIn(f"needs.gate.outputs.{env}_changes == 'true'", job["if"])
            self.assertNotIn("needs.plan.result", job["if"])
            self.assertIn("refs/heads/main", job["if"])
        # gate runs even if one environment's plan failed (!cancelled), reads artifacts, and has no cloud identity
        self.assertIn("!cancelled()", JOBS["gate"]["if"])
        self.assertEqual(set(JOBS["gate"]["outputs"]), {"prod_changes", "staging_changes", "eval_changes"})
        self.assertIn("-f \"tf-meta/${e}.json\"", RAW)

    def test_apply_jobs_use_shared_action_and_derived_identities(self):
        for name in APPLY_JOBS:
            steps = JOBS[name]["steps"]
            self.assertEqual(sum(1 for st in steps if st.get("uses") == LOCAL_ACTION), 1, name)
            self.assertEqual(steps[0]["uses"].split("@")[0], "actions/checkout")
            self.assertTrue(any("tf_identity.py" in st.get("run", "") and "--kind apply" in st["run"] for st in steps), name)
        self.assertIn("vars.WIF_PROVIDER", RAW)
        self.assertIn("vars.STAGING_WIF_PROVIDER", RAW)
        self.assertIn("vars.EVAL_WIF_PROVIDER", RAW)
        # new repo variables are only the enable flags; no per-env SA/provider variables
        flags = set(re.findall(r"vars\[format\('(TF_\{0\}_[A-Z]+)'", RAW))
        self.assertEqual(flags, {"TF_{0}_ENABLED"})
        self.assertNotIn("vars.TF_", RAW)
        self.assertNotRegex(RAW, r"TF_\w*_(PLAN|APPLY)_(SA|WIF_PROVIDER)")

    def test_apply_concurrency_per_env_never_cancels(self):
        for name, env in zip(APPLY_JOBS, ("staging", "eval", "prod")):
            self.assertEqual(JOBS[name]["concurrency"], {"group": f"terraform-apply-{env}", "cancel-in-progress": False})
        self.assertIn("matrix.env", JOBS["plan"]["concurrency"]["group"])

    def test_pip_install_is_hash_pinned_and_before_auth(self):
        steps = ACTION["runs"]["steps"]
        names = [st.get("name", st.get("uses", "")) for st in steps]
        pip = next(i for i, st in enumerate(steps) if "pip install" in st.get("run", ""))
        auth = next(i for i, st in enumerate(steps) if st.get("uses", "").startswith("google-github-actions/auth@"))
        self.assertLess(pip, auth, names)
        self.assertIn("--require-hashes", steps[pip]["run"])
        reqs = (ROOT / "scripts" / "ci" / "tf-apply-requirements.txt").read_text()
        self.assertIn("--hash=sha256:", reqs)
        for line in reqs.splitlines():
            if re.match(r"^[A-Za-z0-9_.-]+", line):
                self.assertRegex(line, r"^[A-Za-z0-9_.-]+==\S+ \\$")
        self.assertNotIn("pip install --quiet --user \"google-auth", RAW + ACTION_RAW)

    def test_apply_aborts_when_live_inputs_drifted_and_plan_records_them(self):
        self.assertIn("--expect-sha256", ACTION_RAW)
        self.assertIn("live_sha256", RAW)
        self.assertIn("live_sha256", ACTION_RAW)
        self.assertIn("Re-run all jobs", ACTION_RAW)

    def test_summary_failure_fails_the_plan_step(self):
        plan_step = next(st for st in JOBS["plan"]["steps"] if st.get("id") == "plan")
        run = plan_step["run"]
        self.assertNotIn("exit 0", run)
        self.assertIn("set -e", run.split("terraform plan")[-1])

    def test_pinned_terraform_matches_versions_tf(self):
        versions = (ROOT / "infra" / "versions.tf").read_text()
        self.assertIn('required_version = "~> 1.9.8"', versions)
        for name, job in JOBS.items():
            for step in job["steps"]:
                if step.get("uses", "").startswith("hashicorp/setup-terraform@"):
                    self.assertEqual(str(step["with"]["terraform_version"]), "1.9.8", name)
        iso = (ROOT / "infra" / "isolated-environment" / "versions.tf").read_text()
        self.assertIn('required_version = "~> 1.9.8"', iso)

    def test_plan_is_readonly_lockfile_readonly_and_parallel_per_env(self):
        self.assertEqual([m["env"] for m in JOBS["plan"]["strategy"]["matrix"]["include"]], ["prod", "staging", "eval"])
        self.assertEqual(JOBS["plan"]["timeout-minutes"], 5)
        self.assertEqual(JOBS["comment"]["timeout-minutes"], 5)
        self.assertIn("-lock=false", RAW)
        self.assertGreaterEqual(RAW.count("-lockfile=readonly") + ACTION_RAW.count("-lockfile=readonly"), 2)
        self.assertIn("TF_PLUGIN_CACHE_DIR", RAW)

    def test_each_env_uses_its_own_backend_and_vars(self):
        m = {e["env"]: e for e in JOBS["plan"]["strategy"]["matrix"]["include"]}
        self.assertEqual((m["prod"]["root"], m["prod"]["bucket"]), ("infra", "onolys-tfstate"))
        self.assertEqual(m["staging"]["backend"], "examples/backend-staging.hcl.example")
        self.assertEqual(m["eval"]["backend"], "examples/backend-eval.hcl.example")
        self.assertEqual(m["staging"]["varfile"], "examples/environment-staging.tfvars.example")
        self.assertEqual(m["eval"]["varfile"], "examples/environment-eval.tfvars.example")
        self.assertEqual({k: e["wif_var"] for k, e in m.items()}, {"prod": "WIF_PROVIDER", "staging": "STAGING_WIF_PROVIDER", "eval": "EVAL_WIF_PROVIDER"})
        for e in m.values():
            if e["backend"]:
                self.assertTrue((ROOT / e["root"] / e["backend"]).is_file())
            if e["varfile"]:
                self.assertTrue((ROOT / e["root"] / e["varfile"]).is_file())

    def test_no_keys_and_no_plan_text_in_public_output(self):
        self.assertNotRegex(RAW, r"credentials_json|GOOGLE_CREDENTIALS|service_account_key")
        self.assertNotIn("terraform show -no-color", RAW)
        self.assertIn("terraform show -json tfplan >", RAW)  # to a file; the summary script prints addresses only
        # the saved plan goes to the private bucket, not to an artifact
        self.assertIn("gcloud storage cp", RAW)
        self.assertNotRegex(RAW + ACTION_RAW, r"name: tfplan|path: .*tfplan")
        # apply refuses a plan whose hash differs from the one planned in this run
        self.assertIn("saved plan hash mismatch", ACTION_RAW)
        self.assertIn("sed '/^Outputs:/,$d'", ACTION_RAW)

    def test_fork_prs_never_reach_cloud_identities(self):
        guard = "github.event.pull_request.head.repo.full_name == github.repository"
        self.assertIn(guard, JOBS["plan"]["if"])
        self.assertIn(guard, JOBS["comment"]["if"])

    def test_comment_is_updated_in_place(self):
        script = next(s["with"]["script"] for s in JOBS["comment"]["steps"] if "script" in s.get("with", {}))
        self.assertIn("terraform-plan-comment", script)
        self.assertIn("updateComment", script)
        self.assertIn("createComment", script)

    def test_checkout_precedes_auth(self):
        for name, job in JOBS.items():
            seen_auth = False
            for step in job["steps"]:
                u = step.get("uses", "")
                if u.startswith("google-github-actions/auth@") or u == LOCAL_ACTION:
                    seen_auth = True
                self.assertFalse(u.startswith("actions/checkout@") and seen_auth, name)

    def test_gated_by_ci_workflow_offline_checks(self):
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn("terraform -chdir=isolated-environment test", ci)
        jobs = yaml.safe_load(ci)["jobs"]
        self.assertEqual(jobs["infra"]["timeout-minutes"], 5)
        self.assertEqual(jobs["infra-isolated"]["timeout-minutes"], 5)
        self.assertIn("infra-isolated", jobs["required"]["needs"])
        self.assertIn("test_terraform_pipeline.py", ci)


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


if __name__ == "__main__":
    unittest.main()
