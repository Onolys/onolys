# Keyless Terraform automation identities (GitHub OIDC -> Workload Identity Federation), one pair per project.
#
#   terraform-plan   metadata-only read + create-only upload of saved plans. Reachable from same-repo pull_request AND main
#                    pushes (own WIF pool, see below). Cannot change infrastructure or read user data.
#   terraform-apply  effectively project admin. Reachable only through the caller-supplied selector: refs/heads/main, or
#                    the `production` GitHub Environment (required reviewers) for the legacy prod root.
#
# No service account keys exist anywhere. See docs/reference/infra-pipeline.md.

locals {
  pool_root = "projects/${var.project_number}/locations/global/workloadIdentityPools"
}

resource "google_service_account" "apply" {
  project      = var.project
  account_id   = "terraform-apply"
  display_name = "Terraform apply (GitHub Actions, main / production approval only)"
}

resource "google_service_account" "plan" {
  project      = var.project
  account_id   = "terraform-plan"
  display_name = "Terraform plan (GitHub Actions, metadata read-only)"
}

resource "google_service_account_iam_member" "apply_wif" {
  service_account_id = google_service_account.apply.name
  role               = "roles/iam.workloadIdentityUser"
  member             = var.apply_principal_set
}

# Separate pool: a principalSet binds every provider of its pool, and the deploy pools either admit only main or are
# shared with deployers. This pool admits same-repo pull_request events (plan) and main pushes (plan before apply).
resource "google_iam_workload_identity_pool" "plan" {
  project                   = var.project
  workload_identity_pool_id = "github-plan"
  display_name              = "GitHub Terraform plan"
}

resource "google_iam_workload_identity_pool_provider" "plan" {
  project                            = var.project
  workload_identity_pool_id          = google_iam_workload_identity_pool.plan.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-plan"
  display_name                       = "GitHub Terraform plan"
  attribute_condition                = "assertion.repository=='${var.github_repository}' && (assertion.event_name=='pull_request' || assertion.ref=='refs/heads/main')"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
    "attribute.event_name" = "assertion.event_name"
  }
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "plan_wif" {
  service_account_id = google_service_account.plan.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${local.pool_root}/${google_iam_workload_identity_pool.plan.workload_identity_pool_id}/attribute.repository/${var.github_repository}"
}

# Metadata the predefined readers above do not cover (buckets, Firestore databases/indexes, project IAM). No object or
# document read permissions.
resource "google_project_iam_custom_role" "plan_metadata" {
  project     = var.project
  role_id     = "terraformPlanMetadata"
  title       = "Terraform plan metadata reader"
  description = "Read bucket/Firestore/project metadata for terraform plan; no data access."
  permissions = [
    "storage.buckets.get",
    "storage.buckets.getIamPolicy",
    "storage.buckets.list",
    "datastore.databases.get",
    "datastore.databases.getMetadata",
    "datastore.databases.list",
    "datastore.indexes.get",
    "datastore.indexes.list",
    "resourcemanager.projects.get",
    "resourcemanager.projects.getIamPolicy",
    "firebase.projects.get",
    "firebase.clients.get",
    "firebase.clients.list",
  ]
}

resource "google_project_iam_member" "apply" {
  for_each = var.apply_roles
  project  = var.project
  role     = each.value
  member   = "serviceAccount:${google_service_account.apply.email}"
}

resource "google_project_iam_member" "plan" {
  for_each = var.plan_roles
  project  = var.project
  role     = each.value
  member   = "serviceAccount:${google_service_account.plan.email}"
}

resource "google_project_iam_member" "plan_extra" {
  for_each = var.plan_extra_roles
  project  = var.project
  role     = each.value
  member   = "serviceAccount:${google_service_account.plan.email}"
}

resource "google_project_iam_member" "plan_metadata" {
  project = var.project
  role    = google_project_iam_custom_role.plan_metadata.name
  member  = "serviceAccount:${google_service_account.plan.email}"
}

# State: apply reads/writes state, locks and its saved plans. Plan reads state (plans run with -lock=false; the bucket holds
# only state and plans, and the gcs backend lists objects so the read grant is unconditional) and may only CREATE objects
# under plans/ (saved plans for the later apply job; it cannot overwrite or delete them).
resource "google_storage_bucket_iam_member" "apply_state" {
  bucket = var.state_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.apply.email}"
}

resource "google_storage_bucket_iam_member" "plan_state_read" {
  bucket = var.state_bucket
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.plan.email}"
}

resource "google_storage_bucket_iam_member" "plan_upload" {
  bucket = var.state_bucket
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.plan.email}"

  condition {
    title       = "saved-plans-create-only"
    description = "Create saved plan objects under plans/ only"
    expression  = "resource.name.startsWith('projects/_/buckets/${var.state_bucket}/objects/plans/')"
  }
}
