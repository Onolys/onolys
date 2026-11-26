"""Plan/apply permission coverage for the Terraform CI identities (docs/reference/infra-pipeline.md). Offline.

Role contents come from checked-in `gcloud iam roles describe` snapshots; refresh them with the command in the module README
comment of main.tf when a role list changes.
"""
import json
import re
from pathlib import Path

INFRA = Path(__file__).resolve().parents[1]
MOD = INFRA / "modules" / "terraform-ci"
MAIN = (MOD / "main.tf").read_text()
VARS = (MOD / "variables.tf").read_text()
PLAN_SNAP = json.loads((MOD / "plan-role-permissions.snapshot.json").read_text())
APPLY_SNAP = json.loads((MOD / "apply-role-permissions.snapshot.json").read_text())
TABLE = json.loads((MOD / "resource-permissions.json").read_text())["types"]

# Permissions that read user data or secrets; the plan identity is reachable from any same-repo pull_request workflow.
DENY_EXACT = {
    "firebaseauth.users.get", "firebaseauth.users.create", "cloudtasks.tasks.get", "cloudtasks.tasks.list",
    "cloudtasks.tasks.fullView", "secretmanager.versions.access", "logging.logEntries.list", "logging.privateLogEntries.list",
    "monitoring.timeSeries.list", "artifactregistry.files.download", "artifactregistry.repositories.downloadArtifacts",
    "cloudscheduler.jobs.run", "run.jobs.run", "run.services.invoke", "iam.serviceAccounts.getAccessToken",
    "iam.serviceAccounts.signBlob", "iam.serviceAccounts.implicitDelegation", "firebaseauth.configs.getSecret",
}
DENY_PREFIX = ("datastore.entities.", "storage.objects.", "pubsub.", "bigquery.", "speech.", "aiplatform.", "cloudkms.")


def default_list(var):
    return set(re.findall(r'"(roles/[^"]+)"', re.search(rf'variable "{var}".*?default\s*=\s*\[(.*?)\]', VARS, re.S).group(1)))


def custom_plan_permissions():
    block = re.search(r"plan_metadata_permissions = \[(.*?)\]", MAIN, re.S).group(1)
    return set(re.findall(r'"([^"]+)"', block))


def plan_granted():
    perms = set(custom_plan_permissions())
    for role in default_list("plan_roles"):
        perms |= set(PLAN_SNAP[role])
    return perms


def test_snapshots_match_the_default_role_lists():
    assert set(PLAN_SNAP) == default_list("plan_roles")
    assert set(APPLY_SNAP) == default_list("apply_roles")


def test_plan_identity_holds_no_data_read_permission():
    granted = plan_granted()
    bad = {p for p in granted if p in DENY_EXACT or p.startswith(DENY_PREFIX)}
    assert not bad, sorted(bad)
    # the two earlier offenders by name
    assert "roles/firebaseauth.viewer" not in default_list("plan_roles")
    assert "roles/cloudtasks.viewer" not in default_list("plan_roles")
    assert "roles/iam.securityReviewer" not in default_list("plan_roles")


def test_plan_custom_role_is_read_only():
    for perm in custom_plan_permissions():
        assert perm.split(".")[-1] in {"get", "list", "getIamPolicy", "getMetadata"} or perm == "serviceusage.services.use", perm


def test_every_google_resource_and_data_type_is_mapped():
    found = set()
    for p in list(INFRA.glob("*.tf")) + list((INFRA / "isolated-environment").glob("*.tf")) + list((INFRA / "modules").rglob("*.tf")):
        for kind, typ in re.findall(r'^(resource|data) "(google[a-z_0-9]*)"', p.read_text(), re.M):
            found.add(typ if kind == "resource" else f"data.{typ}")
    assert found - set(TABLE) == set(), f"unmapped types: {sorted(found - set(TABLE))}"
    assert set(TABLE) - found == set(), f"stale mapping rows: {sorted(set(TABLE) - found)}"


def test_plan_permissions_cover_every_type():
    granted = plan_granted()
    for typ, row in TABLE.items():
        missing = set(row["plan_permissions"]) - granted
        assert not missing, f"{typ}: plan lacks {sorted(missing)}"


def test_apply_roles_cover_every_type():
    roles = default_list("apply_roles")
    union = set().union(*APPLY_SNAP.values())
    for typ, row in TABLE.items():
        assert set(row["apply_roles"]) <= roles, f"{typ}: apply role not granted"
        missing = set(row["apply_permissions"]) - union
        assert not missing, f"{typ}: apply roles lack {sorted(missing)}"


def test_logging_metric_is_covered_both_ways():
    assert "logging.logMetrics.get" in custom_plan_permissions()
    assert "roles/logging.configWriter" in default_list("apply_roles")


def test_plan_extra_permissions_variable_feeds_the_custom_role():
    assert 'variable "plan_extra_permissions"' in VARS
    assert "var.plan_extra_permissions" in MAIN
