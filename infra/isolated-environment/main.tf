locals {
  auth_project = coalesce(var.auth_project, var.environment == "eval" ? "onolys" : var.project)
  site_origin  = "https://${var.hosting_site_id}.web.app"
  apis = toset(concat([
    "serviceusage.googleapis.com", "cloudresourcemanager.googleapis.com", "iam.googleapis.com",
    "iamcredentials.googleapis.com", "sts.googleapis.com", "run.googleapis.com",
    "artifactregistry.googleapis.com", "firestore.googleapis.com",
    "cloudtasks.googleapis.com", "cloudscheduler.googleapis.com", "secretmanager.googleapis.com",
    "identitytoolkit.googleapis.com", "firebase.googleapis.com", "firebasehosting.googleapis.com",
    "generativelanguage.googleapis.com",
    "firebaserules.googleapis.com", "speech.googleapis.com",
    "logging.googleapis.com", "monitoring.googleapis.com",
  ], var.environment == "staging" ? ["aiplatform.googleapis.com"] : []))
}

# Reusing an initialized state for another project/environment requires replacing this
# protected identity, so a mixed-up backend fails the plan rather than moving resources.
resource "terraform_data" "state_identity" {
  input            = { project = var.project, environment = var.environment }
  triggers_replace = [var.project, var.environment]
  lifecycle {
    prevent_destroy = true
  }
}

resource "google_project_service" "api" {
  for_each           = local.apis
  project            = var.project
  service            = each.value
  disable_on_destroy = false
}

resource "google_firebase_project" "this" {
  provider   = google-beta
  project    = var.project
  depends_on = [google_project_service.api]
}

resource "google_artifact_registry_repository" "onolys" {
  project       = var.project
  location      = var.region
  repository_id = "onolys"
  format        = "DOCKER"
  description   = "Onolys ${var.environment} images"
  depends_on    = [google_project_service.api]
}

resource "google_firebase_hosting_site" "this" {
  provider   = google-beta
  project    = var.project
  site_id    = var.hosting_site_id
  depends_on = [google_firebase_project.this]
}

resource "google_storage_bucket" "datasets" {
  count                       = var.environment == "eval" && var.datasets_source_bucket == "" ? 1 : 0
  project                     = var.project
  name                        = coalesce(var.datasets_bucket_name, "${var.project}-datasets")
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  depends_on                  = [google_project_service.api]
}

locals {
  datasets_bucket = var.environment == "eval" ? (var.datasets_source_bucket != "" ? var.datasets_source_bucket : google_storage_bucket.datasets[0].name) : ""
}

module "environment" {
  source = "../modules/environment"

  project              = var.project
  region               = var.region
  env                  = var.environment
  runtime_env          = "staging"
  database_id          = var.environment
  delete_protection    = true
  audio_bucket_name    = coalesce(var.audio_bucket_name, "${var.project}-audio")
  auth_project         = local.auth_project
  speech_object_prefix = var.environment == "eval" ? "eval-uploads/" : null
  cors_origins         = [local.site_origin, "http://localhost:5173"]
  app_base_url         = var.app_base_url
  worker_concurrency   = 2
  worker_max_instances = var.environment == "eval" ? 4 : 3
  llm_secrets          = var.llm_secrets
  stt_secrets          = var.stt_secrets
  git_sha              = var.git_sha
  llm_provider         = var.llm_provider
  llm_model            = var.llm_model
  llm_effort           = var.llm_effort
  placeholder_image    = var.placeholder_image
  public_api_enabled   = var.environment == "staging"
  eval_mode            = var.environment == "eval"
  eval_backend_enabled = var.environment == "eval"
  eval_cors_origins    = var.environment == "eval" ? [local.site_origin, "http://localhost:5173"] : []
  datasets_bucket      = local.datasets_bucket
  eval_cap_day         = var.environment == "eval" ? 1000000 : 10
  max_active_runs      = var.environment == "eval" ? 1000 : null
  # Auth email stays off: cross-project email permissions are not granted implicitly.
  resend_secret_wired = var.resend_secret_wired

  depends_on = [google_project_service.api, terraform_data.state_identity]
}

resource "google_storage_bucket_iam_member" "datasets_reader" {
  count  = var.environment == "eval" && var.datasets_source_bucket == "" ? 1 : 0
  bucket = google_storage_bucket.datasets[0].name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${module.environment.api_sa_email}"
}
