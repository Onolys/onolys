#!/usr/bin/env python3
"""Offline regression checks for required-job admission and tier routing."""
import datetime as dt
import re
import unittest
from pathlib import Path

from required_gate import JOB_FLAGS, elapsed_from_jobs, validate


class GateTests(unittest.TestCase):
    def needs(self, event="pull_request"):
        flags = dict.fromkeys(set(JOB_FLAGS.values()), "true")
        needs = {"changes": {"result": "success", "outputs": flags}, "guards": {"result": "success"}}
        for job in JOB_FLAGS:
            needs[job] = {"result": "success"}
        if event == "pull_request":
            for job in ("api-image", "api-flaky"):
                needs[job]["result"] = "skipped"
        return needs

    def test_complete_pr(self):
        self.assertEqual(validate(self.needs(), "pull_request", 148), [])

    def test_selected_missing_failed_or_skipped_never_passes(self):
        for result in (None, "failure", "cancelled", "skipped"):
            needs = self.needs()
            if result is None:
                del needs["api-emulator"]
            else:
                needs["api-emulator"]["result"] = result
            self.assertTrue(validate(needs, "pull_request", 148))

    def test_main_requires_images_and_contention(self):
        self.assertTrue(validate(self.needs(), "push", 148))
        self.assertEqual(validate(self.needs("push"), "push", 500), [])

    def test_unselected_may_skip_but_cannot_fail(self):
        needs = self.needs()
        needs["changes"]["outputs"]["api"] = "false"
        for job, flag in JOB_FLAGS.items():
            if flag == "api":
                needs[job]["result"] = "skipped"
        self.assertEqual(validate(needs, "pull_request", 148), [])
        needs["api-unit"]["result"] = "failure"
        self.assertTrue(validate(needs, "pull_request", 148))

    def test_routing_and_guards_fail_closed(self):
        for job in ("changes", "guards"):
            needs = self.needs()
            needs[job]["result"] = "skipped"
            self.assertTrue(validate(needs, "pull_request", 1))
        needs = self.needs()
        del needs["changes"]["outputs"]["web"]
        self.assertTrue(validate(needs, "pull_request", 1))

    def test_main_cannot_filter_out_a_package(self):
        needs = self.needs("push")
        needs["changes"]["outputs"]["web"] = "false"
        self.assertTrue(validate(needs, "push", 1))

    def test_pr_budget(self):
        self.assertTrue(validate(self.needs(), "pull_request", 301))

    def test_timing_ignores_initial_queue_and_includes_aggregate_work(self):
        jobs = [
            {"status": "completed", "conclusion": "success", "started_at": "2026-11-24T12:00:00Z"},
            {"status": "in_progress", "conclusion": None, "started_at": "2026-11-24T12:02:20Z"},
            {"status": "queued", "conclusion": None, "started_at": "2026-11-24T11:00:00Z"},
            {"status": "completed", "conclusion": "skipped", "started_at": "2026-11-24T11:00:00Z"},
        ]
        data = {"total_count": len(jobs), "jobs": jobs}
        now = dt.datetime(2026, 11, 24, 12, 2, 28, tzinfo=dt.UTC)
        self.assertEqual(elapsed_from_jobs(data, now), 148)
        with self.assertRaises(RuntimeError):
            elapsed_from_jobs({**data, "total_count": 101}, now)
        with self.assertRaises(KeyError):
            elapsed_from_jobs({}, now)
        with self.assertRaises(RuntimeError):
            elapsed_from_jobs({"total_count": 0, "jobs": []}, now)

    def test_every_workflow_job_is_aggregated(self):
        workflow = Path(".github/workflows/ci.yml").read_text()
        jobs = set(re.findall(r"^  ([\w-]+):$", workflow.split("jobs:\n", 1)[1], re.MULTILINE))
        self.assertEqual(jobs, set(JOB_FLAGS) | {"changes", "guards", "required"})
        aggregate = workflow.split("  required:\n", 1)[1]
        dependencies = re.search(r"needs: \[(.*)\]", aggregate).group(1).split(", ")
        self.assertEqual(set(dependencies), jobs - {"required"})

    def test_workflow_preserves_coverage_and_exact_main(self):
        workflow = Path(".github/workflows/ci.yml").read_text()
        self.assertIn("coverage report --fail-under=94", workflow)
        self.assertIn('if [ "$EVENT" != "pull_request" ]; then', workflow)
        self.assertIn("export FORCE_ALL=true", workflow)
        self.assertNotIn("continue-on-error:", workflow)
        for job in ("api-unit", "api-emulator", "api-coverage", "guards"):
            self.assertIn(job, workflow.split("  required:", 1)[1])
        nightly = Path(".github/workflows/nightly.yml").read_text()
        self.assertIn("uses: ./.github/workflows/ci.yml", nightly)
        caller = nightly.split("  full-offline:\n", 1)[1].split("\n  api-nightly:", 1)[0]
        self.assertIn("actions: read", caller)
        self.assertIn("contents: read", caller)


if __name__ == "__main__":
    unittest.main()
