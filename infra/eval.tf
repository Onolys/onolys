# Evaluation reference data is staging-only; uploads/ is reserved for SP5.
# No public IAM bindings: ADC callers require existing project/bucket permissions.
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
