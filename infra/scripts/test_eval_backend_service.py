"""Static checks for the eval-backend service, worker sizing and secrets (PRD 03-eval-environment R4-R6, D4/D13/D14)."""
import pathlib
import re

INFRA = pathlib.Path(__file__).parent.parent
MOD = INFRA / "modules" / "environment"
SERVICES = (MOD / "services.tf").read_text()
SECRETS = (MOD / "secrets.tf").read_text()
MODMAIN = (MOD / "main.tf").read_text()
OUTPUTS = (MOD / "outputs.tf").read_text()
MAIN = (INFRA / "main.tf").read_text()
ROOT_VARS = (INFRA / "variables.tf").read_text()


def block(text, rtype, name):
    m = re.search(r'resource "%s" "%s" \{\n(.*?)\n\}\n' % (rtype, name), text, re.S)
    assert m, f"{rtype}.{name} missing"
    return m.group(1)


def eval_module():
    return re.search(r'module "eval" \{(.*?)\n\}', MAIN, re.S).group(1)


def backend():
    return block(SERVICES, "google_cloud_run_v2_service", "eval_backend")


def test_backend_service_shape():
    b = backend()
    assert re.search(r"count\s*=\s*var\.eval_backend_enabled \? 1 : 0", b)
    assert 'name                = "onolys-eval-backend-${var.env}"' in b
    assert "service_account                  = google_service_account.api.email" in b
    assert "min_instance_count = 0" in b
    assert "image = var.placeholder_image" in b and "template[0].containers[0].image" in b


def test_backend_env_names():
    b = backend()
    for needle in (
        'name  = "CORS_ORIGINS"', "join(\",\", var.eval_cors_origins)", 'name  = "SERVICE_URL"',
        'name  = "TASKS_OIDC_AUDIENCE"', 'name  = "DATASETS_BUCKET"', 'name  = "EVAL_MAX_PER_PROVIDER"',
        'name  = "EVAL_OWNER_UID"', 'name = "EVAL_ALLOWED_EMAILS"', "google_secret_manager_secret.eval_allowed_emails[0].secret_id",
        "local.platform_env",
    ):
        assert needle in b, needle
    assert "EVAL_MAX_SESSIONS_IN_FLIGHT" not in SERVICES + MODMAIN


def test_backend_env_has_no_removed_names():
    b = backend()
    assert not re.search(r"EVAL_AUTH|EVAL_CORS_ORIGINS", b)
    assert not re.search(r"EVAL_AUTH|EVAL_CORS_ORIGINS", re.search(r"platform_env = .*?\n  \)\n", SERVICES, re.S).group(0))


def test_backend_reads_no_provider_keys():
    assert "worker_provider_secrets" not in backend() and "provider[" not in backend()


def test_public_invoker_gated_on_backend():
    b = block(SERVICES, "google_cloud_run_v2_service_iam_member", "eval_backend_public")
    assert "allUsers" in b and "var.eval_backend_enabled" in b and "eval_backend[0].name" in b


def test_worker_eval_mode_env():
    assert "var.eval_mode" in SERVICES and '"EVAL_MODE"' in SERVICES
    assert "eval_mode                = true" in eval_module()
    assert "eval_backend_enabled     = true" in eval_module()


def test_allowlist_secret_shell_and_iam():
    s = block(SECRETS, "google_secret_manager_secret", "eval_allowed_emails")
    assert "var.eval_backend_enabled" in s and 'secret_id = "eval-allowed-emails-${var.env}"' in s
    i = block(SECRETS, "google_secret_manager_secret_iam_member", "eval_allowed_emails")
    assert "google_service_account.api.email" in i


def test_dispatch_cap_covers_providers_plus_headroom():
    dflt = lambda n: int(re.search(r'variable "%s" \{.*?default\s*=\s*(\d+)' % n, ROOT_VARS, re.S).group(1))
    cap = dflt("eval_worker_concurrency") * dflt("eval_worker_max_instances")
    llm = re.search(r'variable "eval_llm_secrets" \{.*?default\s*=\s*\{(.*?)\}', ROOT_VARS, re.S).group(1)
    n = len(re.findall(r"\w+\s*=\s*\"", llm))
    assert n == 2 and cap >= 2 * n + 2
    assert "max_concurrent_dispatches = var.worker_concurrency * var.worker_max_instances" in MODMAIN


def test_secret_shells_cover_eval_needs():
    assert 'secret_id = "uid-hmac-key-${var.env}"' in SECRETS
    assert 'secret_id = "resend-api-key-${var.env}"' in SECRETS
    assert 'secret_id = "${each.value}-${var.env}"' in SECRETS  # llm/stt shells


def test_outputs():
    assert "one(google_cloud_run_v2_service.eval_backend[*].name)" in OUTPUTS
    assert "one(google_cloud_run_v2_service.eval_backend[*].uri)" in OUTPUTS


def test_backend_can_transcribe_audio_only_in_eval():
    grant = block(MODMAIN, "google_project_iam_member", "eval_backend_speech_client")
    assert re.search(r"count\s*=\s*var\.eval_backend_enabled && var\.env == \"eval\" \? 1 : 0", grant)
    assert 'role    = "roles/speech.client"' in grant
    assert 'member  = "serviceAccount:${google_service_account.api.email}"' in grant
    assert 'project = var.project' in grant
    for name in ("staging", "prod"):
        instance = re.search(r'module "%s" \{(.*?)\n\}' % name, MAIN, re.S).group(1)
        assert "eval_backend_enabled" not in instance
