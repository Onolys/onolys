"""Staging evaluation infrastructure contracts, separate from production services."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def text(name):
    return (ROOT / name).read_text()


def test_eval_flag_and_staging_boundary():
    assert 'variable "eval_enabled"' in text('variables.tf')
    assert 'var.eval_enabled ? 1 : 0' in text('eval-services.tf')
    assert 'onolys-eval-backend-staging' in text('eval-services.tf')
    assert 'onolys-eval-backend-prod' not in text('eval-services.tf')
    assert 'var.eval_enabled ? ["eval.onolys.com", "onolys-eval-staging.web.app"] : []' in text('identity.tf')
    assert 'google_firebase_web_app" "eval' not in text('identity.tf')


def test_eval_compute_and_task_limits():
    source = text('eval-services.tf')
    for pattern in [r'timeout\s*=\s*"900s"', r'max_instance_request_concurrency\s*=\s*4',
                    r'max_instance_count\s*=\s*5', r'cpu\s*=\s*"2"', r'memory\s*=\s*"2Gi"',
                    r'max_concurrent_dispatches\s*=\s*4', r'max_attempts\s*=\s*3']:
        assert re.search(pattern, source), pattern
    assert 'dispatch_deadline' not in source  # 900s belongs to each HTTP task, not its queue.
    assert re.search(r'TASKS_QUEUE\s*=\s*google_cloud_tasks_queue.eval_staging\[0\].id', source)


def test_eval_config_and_access():
    source = text('eval-services.tf')
    for name in ['ENV', 'ADMIN_AUTH', 'ADMIN_AUTH_PROJECT', 'ADMIN_CORS_ORIGINS', 'ADMIN_ALLOWED_EMAILS',
                 'EVAL_BUCKET', 'TASKS_QUEUE', 'TASKS_SA', 'SERVICE_URL', 'TASKS_OIDC_AUDIENCE',
                 'PROD_ENGINE', 'DEFAULT_PRESET', 'ROUTES_FILE', 'FIRESTORE_DATABASE']:
        assert name in source
    for role in ['roles/storage.objectUser', 'roles/storage.objectViewer', 'roles/datastore.user',
                 'roles/speech.client', 'roles/cloudtasks.enqueuer', 'roles/iam.serviceAccountUser',
                 'roles/run.invoker', 'roles/secretmanager.secretAccessor']:
        assert role in source
    assert 'objects/uploads/' in source
    assert 'resource.name == \\"projects/${var.project}/databases/staging\\"' in source
    assert 'https://onolys-eval-staging.web.app,https://eval.onolys.com' in source
    assert 'deployer_staging_eval_developer' in text('deployer.tf')
    assert 'deployer_staging_eval_runtime_user' in text('deployer.tf')
    assert 'custom_domain         = "eval.onolys.com"' in text('domains.tf')
