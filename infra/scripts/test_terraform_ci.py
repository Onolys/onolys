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


def test_apply_has_its_own_pool_and_admits_only_the_deploy_workflow():
    assert 'workload_identity_pool_id = "github-apply"' in MODULE
    assert 'deploy_workflow_path = "${var.github_repository}/.github/workflows/${var.deploy_workflow}"' in MODULE
    # exact workflow_ref binding where the ref is fixed (main); repository binding in the dedicated pool only when release tags
    # are allowed (prod), the provider condition being the gate
    member = re.search(r'resource "google_service_account_iam_member" "apply_wif".*?\n}', MODULE, re.S).group(0)
    assert "attribute.workflow_ref/${local.deploy_workflow_path}@refs/heads/main" in member
    assert 'var.apply_tag_prefix == ""' in member
    cond = re.search(r"apply_condition = join\(\" && \", compact\(\[(.*?)\]\)\)", MODULE, re.S).group(1)
    for part in ("assertion.repository=='${var.github_repository}'", "assertion.ref=='refs/heads/main'",
                 "assertion.event_name in [${local.deploy_events}]",
                 "assertion.job_workflow_ref=='${local.deploy_workflow_path}@refs/heads/main'",
                 "assertion.ref.startsWith('${var.apply_tag_prefix}')",
                 "assertion.job_workflow_ref.startsWith('${local.deploy_workflow_path}@${var.apply_tag_prefix}')",
                 "assertion.environment=='${var.apply_required_environment}'"):
        assert part in cond, part
    assert "terraform.yml" not in cond  # the PR workflow never reaches the apply identity
    # legacy prod: deploy-prod.yml (tag pushes v* and dispatch on main), shared `production` approval
    assert re.search(r'deploy_workflow\s*=\s*"deploy-prod.yml"', LEGACY)
    assert re.search(r'deploy_events\s*=\s*\["push", "workflow_dispatch"\]', LEGACY)
    assert re.search(r'apply_tag_prefix\s*=\s*"refs/tags/v"', LEGACY)
    assert re.search(r'apply_required_environment\s*=\s*"production"', LEGACY)
    assert "terraform-prod" not in LEGACY + MODULE
    # staging/eval: their own deploy workflow, after CI (workflow_run) or manual dispatch, main only, no environment
    assert re.search(r'deploy_workflow\s*=\s*"deploy-\$\{var.environment\}.yml"', ISOLATED)
    assert re.search(r'deploy_events\s*=\s*\["workflow_run", "workflow_dispatch"\]', ISOLATED)
    assert "apply_tag_prefix" not in ISOLATED and "apply_required_environment" not in ISOLATED


def test_plan_pool_is_separate_and_admits_only_pr_plans_and_the_deploy_workflow():
    assert 'workload_identity_pool_id = "github-plan"' in MODULE
    cond = re.search(r'plan_condition = "(.*?)"\n', MODULE).group(1)
    assert cond.startswith("assertion.repository=='${var.github_repository}' && (")
    assert "(assertion.event_name in ['pull_request','workflow_dispatch'] && assertion.job_workflow_ref.startsWith('${local.workflow_path}@'))" in cond
    assert "(assertion.event_name in [${local.deploy_events}] && assertion.job_workflow_ref.startsWith('${local.deploy_workflow_path}@'))" in cond
    assert "'push'" not in cond  # terraform.yml no longer runs on push
    assert "refs/heads/main" not in cond  # no blanket "any event on main"


def test_deploy_inputs_are_validated():
    for var in ("deploy_workflow", "deploy_events", "apply_tag_prefix"):
        block = re.search(rf'variable "{var}" \{{(.*?)\n}}', MODULE, re.S).group(1)
        assert "validation" in block, var


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
