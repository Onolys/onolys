# PR previews (staging only): a dedicated, limited identity for pull_request workflows (pr-preview*.yml). Separate from the
# main-only deployer: its own WIF POOL + provider admitting only same-repo pull_request events, and grants only what a preview
# needs (tagged no-traffic revision of the api service + template restore, image push, Hosting channels). No worker/voice/
# Firestore rules or indexes grants. The preview revision runs as the api runtime SA, so preview code CAN read the secrets that
# SA reads in staging (e.g. resend and uid-hmac); previews therefore only ever see staging data and staging-only secrets, and the
# workflows hold no LLM keys. It is a separate pool because a principalSet binds every provider in its pool: sharing the
# deployer pool would let any same-repo PR impersonate deployer-staging.
locals {
  preview_enabled = var.enable_pr_previews && var.environment == "staging"
  preview_member  = local.preview_enabled ? "serviceAccount:${google_service_account.pr_preview[0].email}" : null
}

resource "google_service_account" "pr_preview" {
  count        = local.preview_enabled ? 1 : 0
  project      = var.project
  account_id   = "pr-preview-${var.environment}"
  display_name = "Onolys ${var.environment} PR preview"
  depends_on   = [google_project_service.api]
}

resource "google_iam_workload_identity_pool" "github_pr" {
  count                     = local.preview_enabled ? 1 : 0
  project                   = var.project
  workload_identity_pool_id = "github-pr"
  display_name              = "GitHub PR previews"
  depends_on                = [google_project_service.api]
}

resource "google_iam_workload_identity_pool_provider" "github_pr" {
  count                              = local.preview_enabled ? 1 : 0
  project                            = var.project
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_pr[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "github-pr"
  display_name                       = "GitHub PR previews"
  attribute_condition                = "assertion.repository == '${var.github_repository}' && assertion.event_name == 'pull_request'"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.event_name" = "assertion.event_name"
    "attribute.ref"        = "assertion.ref"
  }
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# The principalSet matches the repository attribute of EVERY provider in the pool it names, so it names the preview pool, which
# holds only the pull_request provider. The deployer binding names the separate main-only pool, so neither can use the other.
resource "google_service_account_iam_member" "pr_preview_wif" {
  count              = local.preview_enabled ? 1 : 0
  service_account_id = google_service_account.pr_preview[0].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${local.wif_pool_root}/${google_iam_workload_identity_pool.github_pr[0].workload_identity_pool_id}/attribute.repository/${var.github_repository}"
}

# Tagged no-traffic revisions + service template PATCH/restore: only the api service.
resource "google_cloud_run_v2_service_iam_member" "pr_preview_api" {
  count    = local.preview_enabled ? 1 : 0
  project  = var.project
  location = var.region
  name     = module.environment.api_service_name
  role     = "roles/run.developer"
  member   = local.preview_member
}

# Deploying a revision requires actAs on its runtime identity: only the api runtime SA.
resource "google_service_account_iam_member" "pr_preview_runtime" {
  count              = local.preview_enabled ? 1 : 0
  service_account_id = "projects/${var.project}/serviceAccounts/${module.environment.api_sa_email}"
  role               = "roles/iam.serviceAccountUser"
  member             = local.preview_member
}

# The workflow pushes pr-<N>-<sha> images to the project repository.
resource "google_artifact_registry_repository_iam_member" "pr_preview_writer" {
  count      = local.preview_enabled ? 1 : 0
  project    = var.project
  location   = var.region
  repository = google_artifact_registry_repository.onolys.repository_id
  role       = "roles/artifactregistry.writer"
  member     = local.preview_member
}

# firebase-tools reads the project before deploying a channel.
resource "google_project_iam_member" "pr_preview_firebase_project_get" {
  count   = local.preview_enabled ? 1 : 0
  project = var.project
  role    = google_project_iam_custom_role.firebase_project_get.name
  member  = local.preview_member
}

# Hosting channel deploy/delete (project-level role: Hosting has no narrower role that covers channels) and API usage.
resource "google_project_iam_member" "pr_preview" {
  for_each = local.preview_enabled ? toset([
    "roles/serviceusage.serviceUsageConsumer",
    "roles/firebasehosting.admin",
  ]) : toset([])
  project = var.project
  role    = each.value
  member  = local.preview_member
}
