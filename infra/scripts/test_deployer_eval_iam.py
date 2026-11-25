"""Static check: deployer-staging deploys the eval services and the eval Firestore database (03-eval R8c)."""
import pathlib
import re

DEPLOYER = (pathlib.Path(__file__).parent.parent / "deployer.tf").read_text()


def block(kind, name):
    m = re.search(r'resource "%s" "%s" \{(.*?)\n\}' % (kind, name), DEPLOYER, re.S)
    assert m, name
    return m.group(1)


def test_eval_locals_cover_worker_and_backend():
    assert re.search(r"eval_services\s*=\s*\{", DEPLOYER)
    assert "module.eval.worker_service_name" in DEPLOYER
    assert "module.eval.eval_backend_service_name" in DEPLOYER
    assert re.search(r"eval_runtime_sas\s*=", DEPLOYER)
    assert "module.eval.worker_sa_email" in DEPLOYER and "module.eval.api_sa_email" in DEPLOYER


def test_staging_deployer_gets_run_developer_and_actas_on_eval():
    b = block("google_cloud_run_v2_service_iam_member", "deployer_eval_developer")
    assert "local.eval_services" in b and '"roles/run.developer"' in b and "local.deployer_staging_member" in b
    b = block("google_service_account_iam_member", "deployer_eval_runtime_user")
    assert "local.eval_runtime_sas" in b and '"roles/iam.serviceAccountUser"' in b and "local.deployer_staging_member" in b


def test_eval_index_admin_conditioned_on_eval_db():
    b = block("google_project_iam_member", "deployer_staging_eval_index_admin")
    assert '"roles/datastore.indexAdmin"' in b and "local.deployer_staging_member" in b
    assert "module.eval.firestore_db_resource" in b and "condition" in b
