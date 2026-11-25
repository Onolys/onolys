# Evaluation datasets bucket (kept from the legacy staging eval; address unchanged so it is not recreated).
# Read-only for the eval API SA; no public IAM bindings.
resource "google_storage_bucket" "eval_staging" {
  project                     = var.project
  name                        = "onolys-eval-data-staging"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  # V4 signed browser PUTs: exact deployment and default Vite origins only.
  cors {
    origin = [
      "https://onolys-eval-staging.web.app", "https://eval.onolys.com",
      "http://localhost:5173", "http://127.0.0.1:5173",
    ]
    method          = ["PUT"]
    response_header = ["Content-Type", "x-goog-content-length-range", "x-goog-if-generation-match"]
    max_age_seconds = 3600
  }

  versioning {
    enabled = false
  }
}

# Datasets are read-only for the eval backend (module `eval` api SA); no write grant.
resource "google_storage_bucket_iam_member" "eval_datasets_viewer" {
  bucket = google_storage_bucket.eval_staging.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${module.eval.api_sa_email}"
}

# Speech service agent reads eval uploads only (prefix-conditioned) from the eval audio bucket.
resource "google_storage_bucket_iam_member" "eval_speech_uploads" {
  bucket = module.eval.bucket_name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${module.eval.stt_service_agent_email}"
  condition {
    title       = "eval-uploads-only"
    description = "Speech may read evaluation uploads only"
    expression  = "resource.name.startsWith(\"projects/_/buckets/${module.eval.bucket_name}/objects/eval-uploads/\")"
  }
}

# Eval web hosting site (R10): kept, no longer gated by a feature flag.
resource "google_firebase_hosting_site" "eval_staging" {
  provider   = google-beta
  project    = var.project
  site_id    = "onolys-eval-staging"
  depends_on = [google_project_service.api]
}

moved {
  from = google_firebase_hosting_site.eval_staging[0]
  to   = google_firebase_hosting_site.eval_staging
}

moved {
  from = google_firebase_hosting_custom_domain.eval_staging[0]
  to   = google_firebase_hosting_custom_domain.eval_staging
}
