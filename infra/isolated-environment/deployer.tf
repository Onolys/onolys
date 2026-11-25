resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  depends_on                = [google_project_service.api]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  attribute_condition                = "assertion.repository=='${var.github_repository}' && assertion.ref=='refs/heads/main'"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer" {
  project      = var.project
  account_id   = "deployer-${var.environment}"
  display_name = "Onolys ${var.environment} deployer"
  depends_on   = [google_project_service.api]
}

resource "google_service_account_iam_member" "deployer_wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

locals {
  deployer_member = "serviceAccount:${google_service_account.deployer.email}"
  services = var.environment == "staging" ? {
    api    = module.environment.api_service_name
    worker = module.environment.worker_service_name
    voice  = module.environment.voice_service_name
    } : {
    worker  = module.environment.worker_service_name
    backend = module.environment.eval_backend_service_name
  }
  runtime_sas = merge({
    api    = module.environment.api_sa_email
    worker = module.environment.worker_sa_email
  }, var.environment == "staging" ? { voice = module.environment.voice_sa_email } : {})
}

resource "google_cloud_run_v2_service_iam_member" "deployer" {
  for_each = local.services
  project  = var.project
  location = var.region
  name     = each.value
  role     = "roles/run.developer"
  member   = local.deployer_member
}

resource "google_service_account_iam_member" "deployer_runtime" {
  for_each           = local.runtime_sas
  service_account_id = "projects/${var.project}/serviceAccounts/${each.value}"
  role               = "roles/iam.serviceAccountUser"
  member             = local.deployer_member
}

resource "google_artifact_registry_repository_iam_member" "writer" {
  project    = var.project
  location   = var.region
  repository = google_artifact_registry_repository.onolys.repository_id
  role       = "roles/artifactregistry.writer"
  member     = local.deployer_member
}

resource "google_artifact_registry_repository_iam_member" "reader" {
  for_each   = var.artifact_registry_reader_members
  project    = var.project
  location   = var.region
  repository = google_artifact_registry_repository.onolys.repository_id
  role       = "roles/artifactregistry.reader"
  member     = each.value
}

resource "google_project_iam_custom_role" "firebase_project_get" {
  project     = var.project
  role_id     = "firebaseProjectGet"
  title       = "Firebase project get (deployer)"
  permissions = ["firebase.projects.get"]
  depends_on  = [google_project_service.api]
}

resource "google_project_iam_member" "deployer_firebase_project_get" {
  project = var.project
  role    = google_project_iam_custom_role.firebase_project_get.name
  member  = local.deployer_member
}

resource "google_project_iam_member" "deployer" {
  for_each = toset([
    "roles/serviceusage.serviceUsageConsumer",
    "roles/firebasehosting.admin",
    "roles/firebaserules.admin",
  ])
  project = var.project
  role    = each.value
  member  = local.deployer_member
}

resource "google_project_iam_member" "deployer_indexes" {
  project = var.project
  role    = "roles/datastore.indexAdmin"
  member  = local.deployer_member
  condition {
    title       = "environment-database-only"
    description = "Only this isolated environment database"
    expression  = "resource.name.startsWith('${module.environment.firestore_db_resource}')"
  }
}

locals {
  service_readers = {
    for pair in setproduct(keys(local.services), var.cloud_run_reader_members) :
    "${pair[0]}:${pair[1]}" => { service = local.services[pair[0]], member = pair[1] }
  }
}

resource "google_cloud_run_v2_service_iam_member" "provenance_reader" {
  for_each = local.service_readers
  project  = var.project
  location = var.region
  name     = each.value.service
  role     = "roles/run.viewer"
  member   = each.value.member
}
