"""The legacy root infra/ (project onolys = prod) declares prod only: old staging/eval environments were removed.

Staging and eval live in their own projects (infra/isolated-environment). Applying this root destroys the old
staging/eval resources in onolys. Offline text checks; no terraform plan.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TF = {p.name: p.read_text() for p in ROOT.glob("*.tf")}
ALL = "\n".join(TF.values())


def block(src, header):
    m = re.search(re.escape(header) + r" \{", src)
    assert m, f"missing {header}"
    i, depth = m.end(), 1
    while depth:
        depth += {"{": 1, "}": -1}.get(src[i], 0)
        i += 1
    return src[m.start():i]


def test_prod_still_declared():
    assert re.search(r'module\s+"prod"\s*\{[^}]*source\s*=\s*"\./modules/environment"', ALL, re.S)
    assert (ROOT / "modules" / "environment").is_dir()  # the isolated root uses it too
    for name in ("app",):
        assert f'resource "google_firebase_hosting_site" "{name}"' in ALL
    assert 'resource "google_firebase_hosting_custom_domain" "app"' in ALL
    assert 'resource "google_artifact_registry_repository" "onolys"' in ALL
    assert 'resource "google_identity_platform_config" "default"' in ALL
    for name in ("deployer_prod_developer", "deployer_prod_runtime_user", "deployer_prod_reader", "deployer_prod_usage",
                 "deployer_prod_hosting", "deployer_prod_index_admin", "deployer_prod_rules_admin",
                 "deployer_prod_firebase_project_get"):
        assert f'"{name}"' in TF["deployer.tf"], name


def test_identity_deploy_prod_resolve_needs_is_kept():
    # deploy-prod `resolve` auths with vars.WIF_PROVIDER + vars.DEPLOYER_STAGING_SA (deployer-staging@onolys) and reads
    # the isolated staging project; it needs the SA, the repo WIF binding, the pool/provider and serviceusage.
    d = TF["deployer.tf"]
    assert 'resource "google_service_account" "deployer_staging"' in d
    b = block(d, 'resource "google_service_account_iam_member" "deployer_staging_wif"')
    assert '"roles/iam.workloadIdentityUser"' in b and "attribute.repository/${var.github_repository}" in b
    assert 'resource "google_iam_workload_identity_pool" "github"' in d
    assert 'resource "google_iam_workload_identity_pool_provider" "github"' in d
    u = block(d, 'resource "google_project_iam_member" "deployer_staging_usage"')
    assert '"roles/serviceusage.serviceUsageConsumer"' in u and "local.deployer_staging_member" in u
    assert 'output "wif_provider"' in d and 'output "deployer_staging_email"' in d and 'output "deployer_prod_email"' in d


def test_deployer_staging_holds_no_onolys_project_rights_beyond_usage():
    d = TF["deployer.tf"]
    uses = re.findall(r'resource "(\w+)" "(\w+)" \{(.*?)\n\}', d, re.S)
    granted = [name for _, name, body in uses if "local.deployer_staging_member" in body]
    assert granted == ["deployer_staging_usage"], granted


def test_eval_signin_is_not_in_prod_identity():
    # eval signs in through its own project (onolys-eval); prod must not authorize its hosts any more.
    ident = TF["identity.tf"]
    block_src = re.search(r"authorized_domains = distinct\(concat\((.*?)\n  \)\)\n", ident, re.S).group(1)
    retired = re.search(r"retired_authorized_domains = \[(.*?)\]", ident, re.S).group(1)
    for host in ["eval.onolys.com", "onolys-eval-staging.web.app", "onolys-eval-app.web.app"]:
        assert host not in block_src, host
        assert f'"{host}"' in retired, host
    assert 'output "web_env_prod"' in ident and 'output "web_env_eval"' not in ident

