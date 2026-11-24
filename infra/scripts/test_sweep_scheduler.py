"""Static check: the server sweep is scheduled against the worker with the tasks-invoker OIDC."""
import pathlib
import re

ENV = pathlib.Path(__file__).parent.parent / "modules" / "environment"
ROOT = pathlib.Path(__file__).parent.parent


def test_scheduler_job_hits_the_worker_sweep_with_oidc():
    text = (ENV / "main.tf").read_text()
    m = re.search(r'resource "google_cloud_scheduler_job" "sweep" \{(.*?)\n\}\n', text, re.S)
    assert m
    b = m.group(1)
    assert 'schedule         = "*/15 * * * *"' in b
    assert 'uri         = "${local.worker_url}/tasks/sweep"' in b
    assert "service_account_email = google_service_account.tasks_invoker.email" in b
    assert "audience              = local.worker_url" in b


def test_scheduler_api_is_enabled():
    assert '"cloudscheduler.googleapis.com"' in (ROOT / "main.tf").read_text()
