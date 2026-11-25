"""Static checks for the third module instance `eval` (PRD 03-eval-environment R1-R3, Decisions 1-6).

No terraform plan (takes the remote state lock): asserts on the .tf text that the new module variables default to
current behaviour, the gated resources carry `moved` blocks, and the eval instance is isolated and not public.
"""
import pathlib
import re

INFRA = pathlib.Path(__file__).parent.parent
MOD = INFRA / "modules" / "environment"
MAIN = (INFRA / "main.tf").read_text()
ROOT_VARS = (INFRA / "variables.tf").read_text()
VARS = (MOD / "variables.tf").read_text()
SERVICES = (MOD / "services.tf").read_text()
VOICE = (MOD / "voice.tf").read_text()
OUTPUTS = (MOD / "outputs.tf").read_text()
MODMAIN = (MOD / "main.tf").read_text()


def var_block(text, name):
    m = re.search(r'variable "%s" \{(.*?)\n\}' % name, text, re.S)
    assert m, f"variable {name} missing"
    return m.group(1)


def module_block(name):
    m = re.search(r'module "%s" \{(.*?)\n\}' % name, MAIN, re.S)
    assert m, f"module {name} missing"
    return m.group(1)


def test_module_var_defaults_keep_current_behaviour():
    expected = {
        "eval_mode": "false",
        "eval_backend_enabled": "false",
        "eval_cors_origins": "[]",
        "public_api_enabled": "true",
        "max_active_runs": "null",
        "runtime_env": "null",
    }
    for name, default in expected.items():
        body = var_block(VARS, name)
        assert re.search(r"default\s*=\s*%s(?!\w)" % re.escape(default), body), (name, body)


def test_env_validation_allows_eval():
    body = var_block(VARS, "env")
    assert '["staging", "prod", "eval"]' in body


def test_runtime_env_drives_env_and_config_dir():
    assert "runtime_env = coalesce(var.runtime_env, var.env)" in SERVICES
    assert '{ name = "ENV", value = local.runtime_env }' in SERVICES
    assert 'value = "config/${local.runtime_env}/routes.yaml"' in SERVICES
    assert '{ name = "ENV", value = local.runtime_env }' in VOICE
    assert "config/${local.runtime_env}/voice_providers.yaml" in VOICE


def test_eval_mode_and_max_active_runs_are_conditional_env():
    assert re.search(r'var\.eval_mode \? \[\{ name = "EVAL_MODE", value = "true" \}\] : \[\]', SERVICES)
    assert re.search(r'var\.max_active_runs != null \? \[\{ name = "MAX_ACTIVE_RUNS"', SERVICES)


GATED = {
    "services.tf": ("google_cloud_run_v2_service.api", "google_cloud_run_v2_service_iam_member.api_public"),
    "voice.tf": (
        "google_cloud_run_v2_service.voice",
        "google_cloud_run_v2_service_iam_member.voice_public",
        "google_service_account.voice",
        "google_project_iam_member.voice_aiplatform_user",
        "google_project_iam_member.voice_datastore_user",
        "google_secret_manager_secret_iam_member.voice_hmac",
    ),
}


def test_gated_resources_have_count_and_moved_blocks():
    for fname, addrs in GATED.items():
        text = (MOD / fname).read_text()
        for addr in addrs:
            rtype, name = addr.rsplit(".", 1)
            m = re.search(r'resource "%s" "%s" \{\n(.*?)\n\}' % (rtype, name), text, re.S)
            assert m, addr
            assert re.search(r"count\s*=\s*var\.public_api_enabled \? 1 : 0", m.group(1)), addr
            assert re.search(r"moved \{\s*from\s*=\s*%s\s*to\s*=\s*%s\[0\]\s*\}" % (re.escape(addr), re.escape(addr)), text), addr


def test_outputs_use_one_for_gated_resources():
    for expr in (
        "one(google_cloud_run_v2_service.api[*].uri)",
        "one(google_cloud_run_v2_service.api[*].name)",
        "one(google_cloud_run_v2_service.voice[*].uri)",
        "one(google_cloud_run_v2_service.voice[*].name)",
        "one(google_service_account.voice[*].email)",
    ):
        assert expr in OUTPUTS, expr
    assert "google_cloud_run_v2_service.api.uri" not in OUTPUTS


def test_api_sa_is_not_gated():
    m = re.search(r'resource "google_service_account" "api" \{(.*?)\n\}', MODMAIN, re.S)
    assert m and not re.search(r"\bcount\s*=", m.group(1))


def test_eval_instance_wiring():
    body = module_block("eval")
    for needle in (
        'env                      = "eval"',
        'database_id              = "eval"',
        "delete_protection        = true",
        "alerts_enabled           = false",
        'runtime_env              = "staging"',
        "public_api_enabled       = false",
        "eval_mode                = true",
        "eval_cap_day             = 1000000",
        "max_active_runs          = 1000",
        'app_base_url             = ""',
        "worker_concurrency       = var.eval_worker_concurrency",
        "worker_max_instances     = var.eval_worker_max_instances",
        "llm_secrets              = var.eval_llm_secrets",
        "git_sha                  = var.eval_git_sha",
    ):
        assert needle in body, needle
    assert "allUsers" not in body


def test_staging_prod_do_not_opt_in():
    for name in ("staging", "prod"):
        body = module_block(name)
        for key in ("eval_mode", "runtime_env", "public_api_enabled", "max_active_runs", "eval_cap_day"):
            assert key not in body, (name, key)


def test_root_eval_vars():
    assert re.search(r"default\s*=\s*2", var_block(ROOT_VARS, "eval_worker_concurrency"))
    assert re.search(r"default\s*=\s*4", var_block(ROOT_VARS, "eval_worker_max_instances"))
    assert "default     = var.llm_secrets" not in ROOT_VARS  # variable defaults cannot reference vars
    assert re.search(r'default\s*=\s*"unset"', var_block(ROOT_VARS, "eval_git_sha"))
    assert "GEMINI_API_KEY" in var_block(ROOT_VARS, "eval_llm_secrets")


def test_datastore_user_condition_names_instance_database():
    m = re.search(r'resource "google_project_iam_member" "datastore_user" \{(.*?)\n\}', MODMAIN, re.S)
    assert 'expression  = "resource.name == \\"${local.firestore_db_resource}\\""' in m.group(1)
    assert 'firestore_db_resource = "projects/${var.project}/databases/${var.database_id}"' in MODMAIN
    assert 'database_id              = "eval"' in module_block("eval")


def test_no_all_users_on_eval_worker():
    # The worker invoker is only the tasks-invoker SA; allUsers appears only on the (gated) api/voice invokers.
    m = re.search(r'resource "google_cloud_run_v2_service_iam_member" "worker_tasks_invoker" \{(.*?)\n\}', SERVICES, re.S)
    assert "allUsers" not in m.group(1)
    for text in (SERVICES, VOICE):
        for rm in re.finditer(r'resource "google_cloud_run_v2_service_iam_member" "(\w+)" \{(.*?)\n\}', text, re.S):
            if "allUsers" in rm.group(2):
                assert rm.group(1) in {"api_public", "voice_public", "admin_public", "eval_backend_public"}, rm.group(1)
                if rm.group(1) == "eval_backend_public":
                    assert "var.eval_backend_enabled" in rm.group(2)
                elif rm.group(1) != "admin_public":
                    assert "var.public_api_enabled" in rm.group(2)
