#!/usr/bin/env python3
"""Contract tests for .github/workflows/terraform.yml and scripts/ci/tf_*.py (docs/reference/infra-pipeline.md). Offline."""
import json
import re
import unittest
from pathlib import Path

import yaml

import tf_live_inputs
import tf_plan_summary

ROOT = Path(__file__).resolve().parents[2]
RAW = (ROOT / ".github" / "workflows" / "terraform.yml").read_text()
WF = yaml.safe_load(RAW)
ON = WF.get("on") or WF[True]
JOBS = WF["jobs"]
SHA_RE = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


class WorkflowTests(unittest.TestCase):
    def test_triggers(self):
        self.assertEqual(set(ON), {"pull_request", "push", "workflow_dispatch"})
        self.assertEqual(ON["push"]["branches"], ["main"])
        for ev in ("pull_request", "push"):
            self.assertIn("infra/**", ON[ev]["paths"])

    def test_every_action_pinned_to_a_commit_sha(self):
        for name, job in JOBS.items():
            for step in job["steps"]:
                if "uses" in step:
                    self.assertRegex(step["uses"], SHA_RE, f"{name}: {step['uses']}")

    def test_default_permissions_read_only_and_id_token_only_where_needed(self):
        self.assertEqual(WF["permissions"], {"contents": "read"})
        for name, job in JOBS.items():
            perms = job.get("permissions", {})
            uses_auth = any(s.get("uses", "").startswith("google-github-actions/auth@") for s in job["steps"])
            self.assertEqual(perms.get("id-token") == "write", uses_auth, name)
        self.assertEqual(JOBS["comment"]["permissions"].get("pull-requests"), "write")
        for name in ("plan", "apply-nonprod", "apply-prod"):
            self.assertNotIn("pull-requests", JOBS[name]["permissions"])
        # the PR-commenting job holds no cloud identity
        self.assertNotIn("id-token", JOBS["comment"]["permissions"])

    def test_prod_apply_requires_production_environment_and_main(self):
        job = JOBS["apply-prod"]
        self.assertEqual(job["environment"], "production")
        self.assertIn("refs/heads/main", job["if"])
        self.assertIn("pull_request", job["if"])
        for name in ("plan", "apply-nonprod", "comment"):
            self.assertNotIn("environment", JOBS[name])
        self.assertIn("apply-nonprod", job["needs"])

    def test_apply_concurrency_per_env_never_cancels(self):
        self.assertEqual(JOBS["apply-prod"]["concurrency"], {"group": "terraform-apply-prod", "cancel-in-progress": False})
        c = JOBS["apply-nonprod"]["concurrency"]
        self.assertEqual(c["group"], "terraform-apply-${{ matrix.env }}")
        self.assertIs(c["cancel-in-progress"], False)
        self.assertIn("matrix.env", JOBS["plan"]["concurrency"]["group"])

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
        self.assertGreaterEqual(RAW.count("-lockfile=readonly"), 3)
        self.assertIn("TF_PLUGIN_CACHE_DIR", RAW)

    def test_each_env_uses_its_own_backend_and_vars(self):
        m = {e["env"]: e for e in JOBS["plan"]["strategy"]["matrix"]["include"]}
        self.assertEqual((m["prod"]["root"], m["prod"]["bucket"]), ("infra", "onolys-tfstate"))
        self.assertEqual(m["staging"]["backend"], "examples/backend-staging.hcl.example")
        self.assertEqual(m["eval"]["backend"], "examples/backend-eval.hcl.example")
        self.assertEqual(m["staging"]["varfile"], "examples/environment-staging.tfvars.example")
        self.assertEqual(m["eval"]["varfile"], "examples/environment-eval.tfvars.example")
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
        self.assertNotRegex(RAW, r"name: tfplan|path: .*tfplan")
        # apply refuses a plan whose hash differs from the one planned in this run
        self.assertIn("saved plan hash mismatch", RAW)
        self.assertIn("sed '/^Outputs:/,$d'", RAW)

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
                if u.startswith("google-github-actions/auth@"):
                    seen_auth = True
                self.assertFalse(u.startswith("actions/checkout@") and seen_auth, name)

    def test_gated_by_ci_workflow_offline_checks(self):
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn("terraform -chdir=isolated-environment test", ci)
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

    def test_cloud_run_v2_shape(self):
        v2 = {"template": {"containers": [{"env": [{"name": "GIT_SHA", "value": "z"}]}]}}
        self.assertEqual(tf_live_inputs.env_values(v2), {"GIT_SHA": "z"})


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

    def test_unconfigured(self):
        self.assertIn("Not configured", tf_plan_summary.render("staging", "unconfigured", None, "", 80))


if __name__ == "__main__":
    unittest.main()
