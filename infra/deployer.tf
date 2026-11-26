# Keyless GitHub deploys (PRD R9, R13, D5): Workload Identity pool + provider `github`, and the
# `deployer-staging` service account (kept only so deploy-prod's read-only `resolve` job can impersonate it and read the isolated staging project;
# its rights over the old staging/eval resources were removed with them) and `deployer-prod` (production environment only).

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"

  depends_on = [google_project_service.api]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub OIDC"

  # Same repo only: fork PRs present a different `repository` claim and never match.
  attribute_condition = "assertion.repository=='${var.github_repository}'"

  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.repository"       = "assertion.repository"
    "attribute.ref"              = "assertion.ref"
    "attribute.environment"      = "assertion.environment"
    "attribute.workflow_ref"     = "assertion.job_workflow_ref"
    "attribute.repository_owner" = "assertion.repository_owner"
  }

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer_staging" {
  project      = var.project
  account_id   = "deployer-staging"
  display_name = "Onolys GitHub deployer (staging + PR previews)"
}

# Any workflow of the repo may impersonate (deploy-prod `resolve` runs on tags/dispatch).
resource "google_service_account_iam_member" "deployer_staging_wif" {
  service_account_id = google_service_account.deployer_staging.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

locals {
  deployer_staging_member = "serviceAccount:${google_service_account.deployer_staging.email}"
}

# firebase-tools reads the Firebase project (firebase.projects.get) before every deploy. That permission is
# project level, so the Hosting grant (conditioned on site resource names) never covers it. A single-permission
# custom role keeps it narrower than roles/firebase.viewer.
resource "google_project_iam_custom_role" "firebase_project_get" {
  project     = var.project
  role_id     = "firebaseProjectGet"
  title       = "Firebase project get (deployers)"
  description = "Read the Firebase project; required by firebase-tools deploy."
  permissions = ["firebase.projects.get"]
}

# API calls made with this identity (deploy-prod `resolve` against the isolated staging project) need serviceusage.
resource "google_project_iam_member" "deployer_staging_usage" {
  project = var.project
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = local.deployer_staging_member
}

output "wif_provider" {
  description = "Value for google-github-actions/auth `workload_identity_provider`."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "deployer_staging_email" {
  description = "Value for google-github-actions/auth `service_account` (staging + previews)."
  value       = google_service_account.deployer_staging.email
}

# --- deployer-prod (PRD R9, R13, D6) ---
resource "google_service_account" "deployer_prod" {
  project      = var.project
  account_id   = "deployer-prod"
  display_name = "Onolys GitHub deployer (prod)"
}

# Only jobs running in the GitHub `production` environment may impersonate. The provider condition
# already pins the repository; a staging job (environment `staging` or none) never matches this principal.
resource "google_service_account_iam_member" "deployer_prod_wif" {
  service_account_id = google_service_account.deployer_prod.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.environment/production"
}

locals {
  deployer_prod_member = "serviceAccount:${google_service_account.deployer_prod.email}"
  prod_services = merge(
    {
      api    = module.prod.api_service_name
      worker = module.prod.worker_service_name
      voice  = module.prod.voice_service_name
    },
  )
  prod_runtime_sas = merge(
    { api = module.prod.api_sa_email, worker = module.prod.worker_sa_email, voice = module.prod.voice_sa_email },
  )
}

resource "google_cloud_run_v2_service_iam_member" "deployer_prod_developer" {
  for_each = local.prod_services
  project  = var.project
  location = var.region
  name     = each.value
  role     = "roles/run.developer"
  member   = local.deployer_prod_member
}

resource "google_service_account_iam_member" "deployer_prod_runtime_user" {
  for_each           = local.prod_runtime_sas
  service_account_id = "projects/${var.project}/serviceAccounts/${each.value}"
  role               = "roles/iam.serviceAccountUser"
  member             = local.deployer_prod_member
}

# Prod pulls the image built by staging CI; it never pushes.
resource "google_artifact_registry_repository_iam_member" "deployer_prod_reader" {
  project    = var.project
  location   = var.region
  repository = google_artifact_registry_repository.onolys.repository_id
  role       = "roles/artifactregistry.reader"
  member     = local.deployer_prod_member
}

resource "google_project_iam_member" "deployer_prod_usage" {
  project = var.project
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = local.deployer_prod_member
}

resource "google_project_iam_member" "deployer_prod_firebase_project_get" {
  project = var.project
  role    = google_project_iam_custom_role.firebase_project_get.name
  member  = local.deployer_prod_member
}

# Project level on purpose: IAM conditions on Hosting resource names never matched what Hosting presents (ADR 0022 D5).
resource "google_project_iam_member" "deployer_prod_hosting" {
  project = var.project
  role    = "roles/firebasehosting.admin"
  member  = local.deployer_prod_member
}

resource "google_project_iam_member" "deployer_prod_index_admin" {
  project = var.project
  role    = "roles/datastore.indexAdmin"
  member  = local.deployer_prod_member

  condition {
    title       = "firestore-prod-only"
    description = "Only the (default) database"
    expression  = "resource.name.startsWith(\"${module.prod.firestore_db_resource}\")"
  }
}

resource "google_project_iam_member" "deployer_prod_rules_admin" {
  project = var.project
  role    = "roles/firebaserules.admin"
  member  = local.deployer_prod_member
}

output "deployer_prod_email" {
  description = "Value for google-github-actions/auth `service_account` (prod, `production` environment jobs only)."
  value       = google_service_account.deployer_prod.email
}
