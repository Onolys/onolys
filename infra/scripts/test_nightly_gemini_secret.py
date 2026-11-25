"""Offline security contracts for Nightly's staging-only Gemini secret source.

Use only the standard library so this runs in the minimal infra CI environment.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def workflow():
    return (ROOT / ".github/workflows/nightly.yml").read_text()


def live_job():
    return re.search(r"^  api-real-mode:\n(.*?)(?=^  [\w-]+:|\Z)", workflow(), re.M | re.S)[1]


def steps():
    return re.split(r"^      - ", live_job(), flags=re.M)[1:]


def terraform():
    return (ROOT / "infra/nightly.tf").read_text()


def block(kind, name):
    match = re.search(r'resource "%s" "%s" \{(.*?)\n\}' % (kind, name), terraform(), re.S)
    assert match, f"missing isolated Nightly resource: {kind}.{name}"
    return match[1]


def test_only_trusted_main_runs_receive_oidc_permission():
    triggers = re.search(r"^on:\n(.*?)(?=^\S)", workflow(), re.M | re.S)[1]
    assert re.findall(r"^  (\w+):", triggers, re.M) == ["schedule", "workflow_dispatch"]
    permissions = re.search(r"^permissions:\n(.*?)(?=^\S)", workflow(), re.M | re.S)[1]
    assert "id-token" not in permissions
    job = live_job()
    assert "github.ref == 'refs/heads/main'" in job
    assert "github.event_name == 'schedule'" in job
    assert "github.event_name == 'workflow_dispatch'" in job
    assert "    permissions:\n      contents: read\n      id-token: write\n" in job


def test_key_is_masked_and_only_injected_into_live_test_step():
    assert "secrets.GEMINI_API_KEY" not in workflow()
    assert "GEMINI_API_KEY" not in live_job().split("    steps:")[0]
    job_steps = steps()
    auth = next(s for s in job_steps if "google-github-actions/auth@" in s)
    assert "workload_identity_provider: ${{ vars.NIGHTLY_WIF_PROVIDER }}" in auth
    assert "service_account: ${{ vars.NIGHTLY_GEMINI_SA }}" in auth
    secret = next(s for s in job_steps if "google-github-actions/get-secretmanager-secrets@" in s)
    assert "secrets: gemini:${{ vars.GCP_PROJECT || 'onolys' }}/gemini-api-key-staging" in secret
    assert "min_mask_length: 1\n" in secret
    assert "export_to_environment: false\n" in secret
    live = next(s for s in job_steps if "test_live_real_mode.py" in s)
    assert "GEMINI_API_KEY: ${{ steps.gemini.outputs.gemini }}" in live
    assert 'test -n "$GEMINI_API_KEY"' in live, "an empty key must fail rather than skip the live test"
    assert job_steps.index(auth) < job_steps.index(secret) < job_steps.index(live)
    assert all("gemini.outputs" not in s for s in job_steps if s != live)


def test_no_other_workflow_consumes_nightly_identity():
    for path in (ROOT / ".github/workflows").glob("*.y*ml"):
        if path.name == "nightly.yml":
            continue
        text = path.read_text()
        assert "NIGHTLY_WIF_PROVIDER" not in text, path
        assert "NIGHTLY_GEMINI_SA" not in text, path


def test_provider_trust_pins_repo_main_workflow_and_events_in_separate_pool():
    provider = block("google_iam_workload_identity_pool_provider", "nightly")
    assert "google_iam_workload_identity_pool.nightly.workload_identity_pool_id" in provider
    condition = re.search(r'attribute_condition\s*=\s*"([^"]+)"', provider)[1]
    for clause in (
        "assertion.repository=='${var.github_repository}'",
        "assertion.ref=='refs/heads/main'",
        "assertion.workflow_ref=='${var.github_repository}/.github/workflows/nightly.yml@refs/heads/main'",
        "(assertion.event_name=='schedule' || assertion.event_name=='workflow_dispatch')",
    ):
        assert clause in condition
    assert condition.count("&&") == 3
    assert 'issuer_uri = "https://token.actions.githubusercontent.com"' in provider
    pool = block("google_iam_workload_identity_pool", "nightly")
    assert 'workload_identity_pool_id = "github-nightly"' in pool


def test_impersonation_uses_exact_main_subject_from_isolated_pool():
    binding = block("google_service_account_iam_member", "nightly_gemini_wif")
    assert "google_service_account.nightly_gemini.name" in binding
    assert 'role               = "roles/iam.workloadIdentityUser"' in binding
    assert 'principal://iam.googleapis.com/${google_iam_workload_identity_pool.nightly.name}/subject/repo:${var.github_repository}:ref:refs/heads/main' in binding
    assert "principalSet" not in binding


def test_service_account_can_access_only_exact_staging_secret():
    binding = block("google_secret_manager_secret_iam_member", "nightly_gemini")
    assert 'secret_id = "gemini-api-key-staging"' in binding
    assert 'role      = "roles/secretmanager.secretAccessor"' in binding
    assert 'member    = "serviceAccount:${google_service_account.nightly_gemini.email}"' in binding
    assert "gemini-api-key-prod" not in terraform()
    assert "deployer" not in terraform()
    # No project-wide grant or extra resource grants can hide next to the narrow binding.
    assert len(re.findall(r'resource "google_secret_manager_secret_iam_member"', terraform())) == 1
    assert 'resource "google_project_iam_' not in terraform()


def test_isolated_staging_pauses_only_the_legacy_paid_job():
    job = live_job()
    condition = re.search(r'^    if: >-\n(.*?)(?=^    \S)', job, re.M | re.S)[1]
    assert "vars.STAGING_GCP_PROJECT == '' &&" in condition
    # The activation switch must not pause offline coverage or create a skipped-job dependency.
    paused = re.search(r"^  api-real-mode-paused:\n(.*?)(?=^  [\w-]+:|\Z)", workflow(), re.M | re.S)[1]
    other_jobs = workflow().replace('  api-real-mode:\n' + job, '').replace('  api-real-mode-paused:\n' + paused, '')
    assert 'STAGING_GCP_PROJECT' not in other_jobs
    assert 'needs: api-real-mode' not in other_jobs
    assert '  full-offline:\n' in other_jobs


def test_legacy_live_job_is_opt_in_and_pause_is_announced():
    """Legacy secret was deleted: unset vars must skip with a notice, never fail."""
    job = live_job()
    assert "vars.NIGHTLY_LEGACY_GEMINI == 'true' &&" in job
    paused = re.search(r"^  api-real-mode-paused:\n(.*?)(?=^  [\w-]+:|\Z)", workflow(), re.M | re.S)[1]
    assert "vars.STAGING_GCP_PROJECT != '' ||" in paused
    assert "vars.NIGHTLY_LEGACY_GEMINI != 'true'" in paused
    assert "::notice" in paused
    assert "id-token" not in paused and "secrets" not in paused.replace("secret was deleted", "")
