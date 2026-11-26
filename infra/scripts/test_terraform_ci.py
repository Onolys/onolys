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


def test_apply_is_gated_by_ref_or_environment_never_whole_repo():
    assert 'startswith(var.apply_principal_set, "principalSet://iam.googleapis.com/")' in MODULE
    assert '!strcontains(var.apply_principal_set, "/attribute.repository/")' in MODULE
    # legacy prod: only jobs in the `production` GitHub Environment (required reviewers)
    assert re.search(r"apply_principal_set\s*=.*github\.name\}/attribute\.environment/production\"", LEGACY)
    # isolated staging/eval: only refs/heads/main inside the main-only pool
    assert re.search(r"apply_principal_set\s*=.*attribute\.ref/refs/heads/main\"", ISOLATED)


def test_plan_pool_is_separate_and_admits_only_pr_and_main_of_this_repo():
    assert 'workload_identity_pool_id = "github-plan"' in MODULE
    m = re.search(r"attribute_condition\s*=\s*\"(.*)\"", MODULE)
    assert m
    cond = m.group(1)
    assert "assertion.repository=='${var.github_repository}'" in cond
    assert "assertion.event_name=='pull_request'" in cond and "assertion.ref=='refs/heads/main'" in cond


def test_plan_identity_cannot_read_user_data_or_change_infrastructure():
    plan_roles = re.search(r'variable "plan_roles".*?default\s*=\s*\[(.*?)\]', MODULE, re.S).group(1)
    for banned in ("roles/viewer", "roles/editor", "roles/owner", "roles/datastore.viewer", "roles/storage.objectViewer",
                   "Admin", "roles/secretmanager.secretAccessor"):
        assert banned not in plan_roles, banned
    custom = re.search(r"permissions\s*=\s*\[(.*?)\]", MODULE, re.S).group(1)
    for perm in re.findall(r'"([^"]+)"', custom):
        assert perm.split(".")[-1] in {"get", "list", "getIamPolicy", "getMetadata"}, perm
        assert "objects" not in perm and "entities" not in perm
    # saved plans: create-only under plans/, no overwrite/delete
    assert 'role   = "roles/storage.objectCreator"' in MODULE
    assert "objects/plans/" in MODULE


def test_apply_has_no_owner_or_editor_basic_roles():
    apply_roles = re.search(r'variable "apply_roles".*?default\s*=\s*\[(.*?)\]', MODULE, re.S).group(1)
    for banned in ("roles/owner", "roles/editor", "roles/viewer"):
        assert banned not in apply_roles


def test_roots_use_their_own_state_bucket():
    assert 'state_bucket        = "onolys-tfstate"' in LEGACY
    assert 'state_bucket        = "${var.project}-tfstate"' in ISOLATED
