# Evaluation reference data is staging-only; uploads/ is reserved for SP5.
# No public IAM bindings: ADC callers require existing project/bucket permissions.
resource "google_storage_bucket" "eval_staging" {
  project                     = var.project
  name                        = "onolys-eval-data-staging"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = false
  }
}
