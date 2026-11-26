"""Terraform automation identities (docs/reference/infra-pipeline.md): keyless, apply gated, plan read-only. Offline text checks."""
import re
from pathlib import Path

INFRA = Path(__file__).resolve().parents[1]
MODULE = "\n".join(p.read_text() for p in (INFRA / "modules" / "terraform-ci").glob("*.tf"))
LEGACY = (INFRA / "terraform-ci.tf").read_text()
ISOLATED = (INFRA / "isolated-environment" / "terraform-ci.tf").read_text()


def test_no_service_account_keys_anywhere():
    for p in INFRA.rglob("*.tf"):
        assert "google_service_account_key" not in p.read_text(), p


def test_apply_has_its_own_pool_workflow_and_ref_scoped_never_whole_repo():
    assert 'workload_identity_pool_id = "github-apply"' in MODULE
    assert "/attribute.workflow_ref/${local.workflow_path}@refs/heads/main" in MODULE
    assert "attribute.repository/" not in re.search(r'resource "google_service_account_iam_member" "apply_wif".*?\n}', MODULE, re.S).group(0)
    cond = re.search(r'attribute_condition\s*=\s*"(assertion\.repository==.*?ref==\'refs/heads/main\'.*?)"\n', MODULE).group(1)
    for part in ("assertion.ref=='refs/heads/main'", "assertion.event_name in ['push','workflow_dispatch']",
                 "assertion.job_workflow_ref=='${local.workflow_path}@refs/heads/main'", "var.apply_required_environment"):
        assert part in cond, part
    # legacy prod additionally requires the dedicated terraform-prod environment (enforced by the apply provider condition)
    assert 'apply_required_environment = "terraform-prod"' in LEGACY
    assert "apply_required_environment" not in ISOLATED


def test_plan_pool_is_separate_and_admits_only_terraform_workflow_events():
    assert 'workload_identity_pool_id = "github-plan"' in MODULE
    cond = re.search(r'attribute_condition\s*=\s*"(assertion\.repository==[^"]*startsWith[^"]*)"', MODULE).group(1)
    assert "assertion.repository=='${var.github_repository}'" in cond
    assert "assertion.event_name in ['pull_request','push','workflow_dispatch']" in cond
    assert "assertion.job_workflow_ref.startsWith('${local.workflow_path}@')" in cond
    assert "refs/heads/main" not in cond  # no blanket "any event on main"


def test_plan_identity_cannot_use_basic_or_admin_roles_and_uploads_create_only():
    plan_roles = re.search(r'variable "plan_roles".*?default\s*=\s*\[(.*?)\]', MODULE, re.S).group(1)
    for banned in ("roles/viewer", "roles/editor", "roles/owner", "roles/datastore.viewer", "roles/storage.objectViewer",
                   "Admin", "roles/secretmanager.secretAccessor"):
        assert banned not in plan_roles, banned
    # saved plans: create-only under plans/, no overwrite/delete
    assert 'role   = "roles/storage.objectCreator"' in MODULE
    assert "objects/plans/" in MODULE


def test_apply_has_no_owner_or_editor_basic_roles():
    apply_roles = re.search(r'variable "apply_roles".*?default\s*=\s*\[(.*?)\]', MODULE, re.S).group(1)
    for banned in ("roles/owner", "roles/editor", "roles/viewer"):
        assert banned not in apply_roles


def test_roots_use_their_own_state_bucket():
    assert re.search(r"state_bucket\s*= \"onolys-tfstate\"", LEGACY)
    assert re.search(r"state_bucket\s*= \"\$\{var.project\}-tfstate\"", ISOLATED)


def test_state_buckets_expire_saved_plans_after_7_days():
    tf = (INFRA / "isolated-environment" / "bootstrap" / "main.tf").read_text()
    sh = (INFRA / "bootstrap.sh").read_text()
    for text in (tf, sh):
        assert "plans/" in text
    assert "age            = 7" in tf and "days_since_noncurrent_time = 7" in tf
    assert '"age": 7' in sh and '"daysSinceNoncurrentTime": 7' in sh
