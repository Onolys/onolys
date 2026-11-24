# Nightly reads the staging Gemini key through its own trust boundary. The shared GitHub
# pool also trusts PR deploys, so none of its principals may impersonate this account.
resource "google_iam_workload_identity_pool" "nightly" {
  project                   = var.project
  workload_identity_pool_id = "github-nightly"
  display_name              = "GitHub Nightly only"

  depends_on = [google_project_service.api]
}

resource "google_iam_workload_identity_pool_provider" "nightly" {
  project                            = var.project
  workload_identity_pool_id          = google_iam_workload_identity_pool.nightly.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-nightly"
  display_name                       = "Nightly main OIDC"

  # workflow_ref identifies this workflow (unlike job_workflow_ref, which is only
  # present for reusable workflows). Reject PRs, other workflows and dispatch refs.
  attribute_condition = "assertion.repository=='${var.github_repository}' && assertion.ref=='refs/heads/main' && assertion.workflow_ref=='${var.github_repository}/.github/workflows/nightly.yml@refs/heads/main' && (assertion.event_name=='schedule' || assertion.event_name=='workflow_dispatch')"

  attribute_mapping = {
    "google.subject" = "assertion.sub"
  }

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "nightly_gemini" {
  project      = var.project
  account_id   = "nightly-gemini"
  display_name = "Nightly staging Gemini secret reader"
}

resource "google_service_account_iam_member" "nightly_gemini_wif" {
  service_account_id = google_service_account.nightly_gemini.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principal://iam.googleapis.com/${google_iam_workload_identity_pool.nightly.name}/subject/repo:${var.github_repository}:ref:refs/heads/main"
}

resource "google_secret_manager_secret_iam_member" "nightly_gemini" {
  project   = var.project
  secret_id = "gemini-api-key-staging"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.nightly_gemini.email}"

  depends_on = [module.staging]
}

output "nightly_wif_provider" {
  description = "GitHub NIGHTLY_WIF_PROVIDER repository variable (Nightly main only)."
  value       = google_iam_workload_identity_pool_provider.nightly.name
}

output "nightly_gemini_email" {
  description = "GitHub NIGHTLY_GEMINI_SA repository variable (staging Gemini secret reader)."
  value       = google_service_account.nightly_gemini.email
}
