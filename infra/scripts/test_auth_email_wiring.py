"""Auth email delivery spans the public API and the durable reset-email worker."""
from pathlib import Path
import re

INFRA = Path(__file__).parent.parent
MOD = INFRA / "modules" / "environment"


def block(filename, kind, name):
    text = (MOD / filename).read_text()
    match = re.search(r'resource "%s" "%s" \{(.*?)\n\}' % (kind, name), text, re.S)
    assert match, (kind, name)
    return match.group(1)


def test_api_and_worker_have_email_settings_and_gated_secret():
    for service in ("api", "worker"):
        body = block("services.tf", "google_cloud_run_v2_service", service)
        for key, value in (("APP_BASE_URL", "app_base_url"), ("EMAIL_FROM", "email_from")):
            if service == "api":
                assert re.search(r'name\s*=\s*"%s"\s+value\s*=\s*var\.%s\b' % (key, value), body), service
            else:
                assert re.search(r'%s\s*=\s*var\.%s\b' % (key, value), body)
                assert re.search(r'for_each\s*=\s*var\.resend_secret_wired\s*\?\s*\{.*?APP_BASE_URL.*?EMAIL_FROM.*?\}\s*:\s*\{\}', body, re.S)
                assert re.search(r'name\s*=\s*env\.key\s+value\s*=\s*env\.value', body)
        assert re.search(r'for_each\s*=\s*var\.resend_secret_wired\s*\?\s*\[1\]\s*:\s*\[\]\s+content\s*\{\s*name\s*=\s*"RESEND_API_KEY"', body), service
        assert re.search(r'secret\s*=\s*google_secret_manager_secret\.resend\.secret_id\s+version\s*=\s*"latest"', body), service
        assert f"google_secret_manager_secret_iam_member.resend_{service}" in body


def test_worker_email_access_is_gated_and_limited_to_resend_and_link_generation():
    accessor = block("secrets.tf", "google_secret_manager_secret_iam_member", "resend_worker")
    assert re.search(r'count\s*=\s*var\.resend_secret_wired\s*\?\s*1\s*:\s*0', accessor)
    assert "google_secret_manager_secret.resend.secret_id" in accessor
    assert 'role      = "roles/secretmanager.secretAccessor"' in accessor
    assert "google_service_account.worker.email" in accessor
    role = block("main.tf", "google_project_iam_custom_role", "worker_auth_email")
    assert re.search(r'count\s*=\s*var\.resend_secret_wired\s*\?\s*1\s*:\s*0', role)
    assert re.search(r'permissions\s*=\s*\["firebaseauth.users.sendEmail"\]', role)
    grant = block("main.tf", "google_project_iam_member", "worker_auth_email")
    assert re.search(r'count\s*=\s*var\.resend_secret_wired\s*\?\s*1\s*:\s*0', grant)
    assert "google_project_iam_custom_role.worker_auth_email[0].name" in grant
    assert "google_service_account.worker.email" in grant
    worker = block("services.tf", "google_cloud_run_v2_service", "worker")
    assert "google_project_iam_member.worker_auth_email" in worker


def test_email_activation_defaults_remain_off_for_prod():
    root = (INFRA / "variables.tf").read_text()
    var = re.search(r'variable "resend_secret_wired" \{(.*?)\n\}', root, re.S).group(1)
    assert re.search(r'prod\s*=\s*false', var)
    wiring = (INFRA / "main.tf").read_text()
    assert 'var.resend_secret_wired["prod"]' in wiring
    assert "staging" not in var
