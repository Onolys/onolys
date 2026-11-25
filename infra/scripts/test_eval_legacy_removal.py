"""Legacy staging eval removed; datasets bucket kept read-only (PRD 03-eval-environment R7, R9, R10)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(name):
    return (ROOT / name).read_text()


def all_tf():
    return "\n".join(p.read_text() for p in ROOT.glob("*.tf"))


def block(src, header):
    start = src.index(header)
    return src[start:src.index("\n}\n", start)]


def test_legacy_resources_absent():
    tf = all_tf()
    assert not (ROOT / "eval-services.tf").exists()
    for token in ["onolys-eval-backend-staging", "onolys-eval-runs-staging", "eval-backend-staging",
                  "eval-tasks-staging", "\"eval_datastore\"", "\"eval_speech\"", "\"eval_objects\"", "\"eval_stt_uploads\"",
                  "\"eval_provider\"", "\"eval_allowlist\"", "eval_service_url", "eval_env ", "eval_enabled",
                  "eval_backend_url_staging", "deployer_staging_eval_developer",
                  "deployer_staging_eval_runtime_user", "google_cloud_run_v2_service\" \"eval_staging",
                  "google_service_account\" \"eval_staging"]:
        assert token not in tf, token


def test_datasets_bucket_kept_private_with_cors():
    src = text("eval.tf")
    for pattern in [r'resource "google_storage_bucket" "eval_staging"', r'name\s*=\s*"onolys-eval-data-staging"',
                    r'uniform_bucket_level_access\s*=\s*true', r'public_access_prevention\s*=\s*"enforced"',
                    r'force_destroy\s*=\s*false']:
        assert re.search(pattern, src), pattern
    cors = re.search(r"cors\s*\{([^}]+)\}", src).group(1)
    for origin in ["https://onolys-eval-staging.web.app", "https://eval.onolys.com",
                   "http://localhost:5173", "http://127.0.0.1:5173"]:
        assert f'"{origin}"' in cors
    assert re.search(r'method\s*=\s*\["PUT"\]', cors)


def test_datasets_iam_is_object_viewer_only_for_eval_api_sa():
    src = text("eval.tf")
    grants = re.findall(r'resource "google_storage_bucket_iam_(?:member|binding)" "(\w+)"', src)
    datasets = [g for g in grants if "datasets" in g or "eval_data" in g]
    assert len(datasets) == 1, grants
    body = block(src, f'"{datasets[0]}"')
    assert 'bucket = google_storage_bucket.eval_staging.name' in body
    assert 'role   = "roles/storage.objectViewer"' in body
    assert 'member = "serviceAccount:${module.eval.api_sa_email}"' in body
    for bad in ["objectUser", "objectAdmin", "objectCreator", "storage.admin", "legacyBucket"]:
        assert bad not in src, bad
    assert "uploads/" not in block(src, f'"{datasets[0]}"')


def test_speech_agent_reads_eval_uploads_prefix_only():
    src = text("eval.tf")
    body = block(src, '"eval_speech_uploads"')
    assert "bucket = module.eval.bucket_name" in body
    assert 'role   = "roles/storage.objectViewer"' in body
    assert 'member = "serviceAccount:${module.eval.stt_service_agent_email}"' in body
    assert 'objects/eval-uploads/' in body and "startsWith" in body


def test_hosting_site_and_domain_ungated_with_moved_blocks():
    src = all_tf()
    site = block(src, 'resource "google_firebase_hosting_site" "eval_staging"')
    dom = block(src, 'resource "google_firebase_hosting_custom_domain" "eval_staging"')
    assert "count" not in site and "count" not in dom
    assert 'site_id    = "onolys-eval-staging"' in site
    assert "google_firebase_hosting_site.eval_staging.site_id" in dom
    assert 'custom_domain         = "eval.onolys.com"' in dom
    for kind in ["google_firebase_hosting_site", "google_firebase_hosting_custom_domain"]:
        assert re.search(rf"moved\s*\{{\s*from\s*=\s*{kind}\.eval_staging\[0\]\s*to\s*=\s*{kind}\.eval_staging\s*\}}", src), kind
    assert '"eval.onolys.com" = google_firebase_hosting_custom_domain.eval_staging' in text("domains.tf")


def test_authorized_domains_unconditional():
    src = text("identity.tf")
    assert '"eval.onolys.com", "onolys-eval-staging.web.app"' in src
    assert "eval_enabled" not in src
