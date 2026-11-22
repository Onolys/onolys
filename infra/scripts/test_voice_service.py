"""Static stand-in for the AC11 plan check (no `terraform plan`: it takes the remote state lock).

Asserts on the .tf text: the voice SA holds only roles/aiplatform.user + Firestore (datastore.user, env-DB
condition), the api/worker grants are untouched, and the voice service has the relay settings (SP10 R12).
A real `terraform plan` still runs in CI / by the owner.
"""
import pathlib
import re
import subprocess

import pytest

INFRA = pathlib.Path(__file__).parent.parent
MOD = INFRA / "modules" / "environment"
VOICE = (MOD / "voice.tf").read_text()
GRANT_TYPES = (
    "google_project_iam_member",
    "google_project_iam_binding",
    "google_storage_bucket_iam_member",
    "google_cloud_tasks_queue_iam_member",
    "google_service_account_iam_member",
    "google_secret_manager_secret_iam_member",
    "google_cloud_run_v2_service_iam_member",
)


def blocks(text, rtype):
    return {m.group(1): m.group(2) for m in re.finditer(r'resource "%s" "(\w+)" \{(.*?)\n\}' % rtype, text, re.S)}


def all_tf():
    return {p.relative_to(INFRA).as_posix(): p.read_text() for p in INFRA.rglob("*.tf") if ".terraform" not in p.parts}


def grants_naming_voice_sa():
    found = {}
    for path, text in all_tf().items():
        for rtype in GRANT_TYPES:
            for name, body in blocks(text, rtype).items():
                if "google_service_account.voice" in body or "voice_sa_email" in body:
                    found[(path, name)] = body
    return found


def test_voice_sa_holds_only_aiplatform_user_and_firestore():
    found = grants_naming_voice_sa()
    assert {k[1] for k in found} == {"voice_aiplatform_user", "voice_datastore_user"}, set(found)
    assert {k[0] for k in found} == {"modules/environment/voice.tf"}
    roles = {re.search(r'role\s*=\s*"([^"]+)"', b).group(1) for b in found.values()}
    assert roles == {"roles/aiplatform.user", "roles/datastore.user"}
    ds = found[("modules/environment/voice.tf", "voice_datastore_user")]
    assert "resource.name ==" in ds and "local.firestore_db_resource" in ds  # this env's database only
    assert "google_service_account_iam_member" not in VOICE  # no actAs/tokenCreator for the voice SA


def test_api_and_worker_grants_unchanged():
    main = (MOD / "main.tf").read_text()
    assert re.search(r"runtime_sas = \{\s*api\s*=\s*google_service_account\.api\.email\s*worker\s*=\s*google_service_account\.worker\.email\s*\}", main)
    assert "voice" not in main and "voice" not in (MOD / "secrets.tf").read_text()
    api_roles = sorted(
        re.search(r'role\s*=\s*"([^"]+)"', b).group(1)
        for t in GRANT_TYPES
        for b in blocks(main, t).values()
        if "runtime_sas" in b or "google_service_account.api.email" in b
    )
    assert api_roles == sorted(
        ["roles/datastore.user", "roles/storage.objectAdmin", "roles/cloudtasks.enqueuer",
         "roles/iam.serviceAccountUser", "roles/iam.serviceAccountTokenCreator"]
    )


def test_api_grants_identical_to_origin_main():
    def show(ref, rel):
        r = subprocess.run(["git", "show", f"{ref}:infra/modules/environment/{rel}"], cwd=INFRA, capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None

    for rel in ("main.tf", "secrets.tf"):
        old = show("origin/main", rel)
        if old is None:
            pytest.skip("origin/main not available")
        cur = (MOD / rel).read_text()
        for t in GRANT_TYPES:
            o, c = blocks(old, t), blocks(cur, t)
            o.pop("admin_llm", None)  # intentionally removed by 04-admin-shell Task 5 (admin uses no LLM)
            assert o == {k: c.get(k) for k in o}, f"{rel}: {t} grants changed vs origin/main"


def test_voice_service_settings():
    svc = blocks(VOICE, "google_cloud_run_v2_service")["voice"]
    assert 'name                = "onolys-voice-${var.env}"' in svc
    assert re.search(r'timeout\s*=\s*"3600s"', svc)
    assert re.search(r"max_instance_request_concurrency\s*=\s*10\b", svc)
    assert re.search(r"session_affinity\s*=\s*true", svc)
    assert re.search(r"cpu_idle\s*=\s*false", svc)  # CPU always allocated
    assert re.search(r"max_instance_count\s*=\s*var\.voice_max_instances", svc)
    assert re.search(r'name\s*=\s*"SERVICE_MODE"\s*value\s*=\s*"voice"', svc)
    assert "service_account                  = google_service_account.voice.email" in svc
    assert "template[0].containers[0].image" in svc  # CI owns the image
    inv = blocks(VOICE, "google_cloud_run_v2_service_iam_member")["voice_public"]
    assert '"allUsers"' in inv and '"roles/run.invoker"' in inv


def test_voice_env_and_defaults():
    names = set(re.findall(r'\{ name = "(\w+)"', VOICE))
    assert {"VOICE_PROVIDERS_FILE", "GOOGLE_CLOUD_PROJECT", "FIRESTORE_DATABASE", "AUTH_PROJECT", "CORS_ORIGINS", "ENV",
            "AI_CAP_DAY", "AI_MAX_SECONDS", "AI_WARN_SECONDS", "AI_MIN_SECONDS",
            "AI_TOLERANCE_SECONDS", "AI_ABANDON_COUNT_SECONDS", "AI_RECONNECT_SECONDS", "AI_MIC_GATE"} <= names
    variables = (MOD / "variables.tf").read_text()
    for var, default in {"ai_max_seconds": 600, "ai_warn_seconds": 480, "ai_min_seconds": 300, "ai_tolerance_seconds": 30,
                         "ai_abandon_count_seconds": 30, "ai_reconnect_seconds": 60, "voice_max_instances": 3}.items():
        assert re.search(r'variable "%s" \{.*?default\s*=\s*%d\n' % (var, default), variables, re.S), var
    assert re.search(r'variable "ai_mic_gate" \{.*?default\s*=\s*false', variables, re.S)


def test_api_gets_voice_url_and_vertex_api_enabled():
    assert 'name  = "VOICE_URL"' in (MOD / "services.tf").read_text()
    assert '"aiplatform.googleapis.com"' in (INFRA / "main.tf").read_text()
    assert "voice_url" in (MOD / "outputs.tf").read_text()
    ident = (INFRA / "identity.tf").read_text()
    assert 'output "voice_url_staging"' in ident and 'output "voice_url_prod"' in ident


def test_deployer_can_deploy_voice_service_and_act_as_its_sa():
    text = (INFRA / "deployer.tf").read_text()
    for env in ("staging", "prod"):
        assert f"voice  = module.{env}.voice_service_name" in text
        assert f"voice = module.{env}.voice_sa_email" in text


def test_api_service_does_not_ignore_template_revision():
    # CI pins api traffic to a named revision; ignoring template[0].revision makes Terraform send that name
    # back on any in-place update -> 409 "Revision ... with different configuration already exists".
    svc = blocks((MOD / "services.tf").read_text(), "google_cloud_run_v2_service")
    assert "template[0].revision" not in svc["api"]
    assert "template[0].containers[0].image" in svc["api"]  # image stays CI-owned
    for other in ("worker", "admin_backend"):
        assert "template[0].revision" in svc[other]
