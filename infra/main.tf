locals {
  apis = [
    "serviceusage.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "firestore.googleapis.com",
    "storage.googleapis.com",
    "cloudtasks.googleapis.com",
    "cloudscheduler.googleapis.com",
    "secretmanager.googleapis.com",
    "identitytoolkit.googleapis.com",
    "firebase.googleapis.com",
    "firebasehosting.googleapis.com",
    "firebaserules.googleapis.com",
    "speech.googleapis.com",
    "aiplatform.googleapis.com",
    "cloudbilling.googleapis.com",
    "billingbudgets.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "policytroubleshooter.googleapis.com",
  ]
}

resource "google_project_service" "api" {
  for_each = toset(local.apis)

  project            = var.project
  service            = each.value
  disable_on_destroy = false
}

# Shared legacy image repo (prod images; staging/eval use their own projects). No cleanup policy in v1 (PRD D18).
resource "google_artifact_registry_repository" "onolys" {
  project       = var.project
  location      = var.region
  repository_id = "onolys"
  format        = "DOCKER"
  description   = "Onolys api/worker images"

  depends_on = [google_project_service.api]
}

# Prod Firebase Hosting site, alongside landing's `onolys` and `onolys-redirect` (not managed here).
resource "google_firebase_hosting_site" "app" {
  provider = google-beta
  project  = var.project
  site_id  = var.app_site_id

  depends_on = [google_project_service.api]
}

# Provider-key secrets are per environment (`<base>-<env>`, created inside the module; owner decision 2026-11-20).
# The old shared project-level shell (`anthropic-api-key`) is dropped from state WITHOUT deleting it, so live
# revisions keep working until the owner deletes it by hand after the cutover (docs/reference/infra.md).
removed {
  from = google_secret_manager_secret.provider

  lifecycle {
    destroy = false
  }
}

# Prod: the only environment in this root. Staging and eval live in their own projects (infra/isolated-environment).
module "prod" {
  source = "./modules/environment"

  project                  = var.project
  region                   = var.region
  env                      = "prod"
  database_id              = "(default)"
  delete_protection        = true
  default_preset           = var.default_preset
  worker_concurrency       = var.worker_concurrency
  worker_max_instances     = var.worker_max_instances
  api_max_instances        = 10
  llm_secrets              = var.llm_secrets
  stt_secrets              = var.stt_secrets
  git_sha                  = var.git_sha["prod"]
  app_base_url             = "https://app.onolys.com"
  resend_secret_wired      = var.resend_secret_wired["prod"]
  alerts_enabled           = true
  notification_channel_ids = [google_monitoring_notification_channel.owner_email.id]
  cors_origins             = ["https://app.onolys.com"]

  depends_on = [google_project_service.api]
}
