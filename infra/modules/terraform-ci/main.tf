# Keyless Terraform automation identities (GitHub OIDC -> Workload Identity Federation), one pair per project.
#
#   terraform-plan   metadata-only read + create-only upload of saved plans. Reachable from same-repo pull_request plans
#                    (terraform.yml) and from this project's deploy workflow (own WIF pool, see below). Cannot change
#                    infrastructure or read user data.
#   terraform-apply  effectively project admin. Reachable only through its OWN pool `github-apply` whose provider admits just
#                    this project's deploy workflow (deploy-<env>.yml) on refs/heads/main (prod also on release tags), with its
#                    trigger events, and for prod only jobs in the GitHub Environment `production` (required reviewer), the same
#                    approval that releases the app. The deployers' pools are untouched.
#
# No service account keys exist anywhere. See docs/reference/infra-pipeline.md.

locals {
  pool_root            = "projects/${var.project_number}/locations/global/workloadIdentityPools"
  workflow_path        = "${var.github_repository}/.github/workflows/terraform.yml" # PR plans (and manual read-only plans)
  deploy_workflow_path = "${var.github_repository}/.github/workflows/${var.deploy_workflow}"
  deploy_events        = join(",", [for e in var.deploy_events : "'${e}'"])

  # Apply: the deploy workflow file at the ref that runs it (a non-reusable workflow's job_workflow_ref is <path>@<github.ref>),
  # main only, or main plus release tags for prod; prod also requires the job's GitHub Environment.
  apply_condition = join(" && ", compact([
    "assertion.repository=='${var.github_repository}'",
    var.apply_tag_prefix == "" ? "assertion.ref=='refs/heads/main'" : "(assertion.ref=='refs/heads/main' || assertion.ref.startsWith('${var.apply_tag_prefix}'))",
    "assertion.event_name in [${local.deploy_events}]",
    var.apply_tag_prefix == "" ? "assertion.job_workflow_ref=='${local.deploy_workflow_path}@refs/heads/main'" : "(assertion.job_workflow_ref=='${local.deploy_workflow_path}@refs/heads/main' || assertion.job_workflow_ref.startsWith('${local.deploy_workflow_path}@${var.apply_tag_prefix}'))",
    var.apply_required_environment == "" ? "" : "assertion.environment=='${var.apply_required_environment}'",
  ]))
  # Plan: PR plans of terraform.yml, and the plan job of this project's deploy pipeline. Read-only identity, so any ref.
  plan_condition = "assertion.repository=='${var.github_repository}' && ((assertion.event_name in ['pull_request','workflow_dispatch'] && assertion.job_workflow_ref.startsWith('${local.workflow_path}@')) || (assertion.event_name in [${local.deploy_events}] && assertion.job_workflow_ref.startsWith('${local.deploy_workflow_path}@')))"

  # Read-only metadata for `terraform plan`, mapped resource by resource in resource-permissions.json (a test enforces the
  # table). No object, document, task, user, log-entry, secret-version or time-series reads.
  plan_metadata_permissions = [
    "storage.buckets.get",
    "storage.buckets.getIamPolicy",
    "storage.buckets.list",
    "datastore.databases.get",
    "datastore.databases.getMetadata",
    "datastore.databases.list",
    "datastore.indexes.get",
    "datastore.indexes.list",
    "datastore.schemas.get", # the predefined Firestore roles list index/field management under schemas.* (verified with gcloud)
    "datastore.schemas.list",
    "resourcemanager.projects.get",
    "resourcemanager.projects.getIamPolicy",
    "firebase.projects.get",
    "firebase.clients.get",
    "firebase.clients.list",
    "firebaseauth.configs.get",
    "cloudtasks.queues.get",
    "cloudtasks.queues.list",
    "cloudtasks.queues.getIamPolicy",
    "cloudtasks.locations.get",
    "cloudtasks.locations.list",
    "artifactregistry.repositories.get",
    "artifactregistry.repositories.list",
    "artifactregistry.repositories.getIamPolicy",
    "monitoring.alertPolicies.get",
    "monitoring.alertPolicies.list",
    "monitoring.notificationChannels.get",
    "monitoring.notificationChannels.list",
    "logging.logMetrics.get",
    "logging.logMetrics.list",
    "serviceusage.services.get",
    "serviceusage.services.list",
    "serviceusage.services.use",
  ]
}

resource "google_service_account" "apply" {
  project      = var.project
  account_id   = "terraform-apply"
  display_name = "Terraform apply (GitHub Actions, ${var.deploy_workflow} only)"
}

resource "google_service_account" "plan" {
  project      = var.project
  account_id   = "terraform-plan"
  display_name = "Terraform plan (GitHub Actions, metadata read-only)"
}

resource "google_service_account_iam_member" "apply_wif" {
  service_account_id = google_service_account.apply.name
  role               = "roles/iam.workloadIdentityUser"
  # Exact workflow ref where the ref is fixed (main). With release tags (prod) the ref varies, so the binding is the repository
  # within this dedicated single-provider pool and the provider condition (workflow, refs, events, environment) is the gate.
  member = var.apply_tag_prefix == "" ? "principalSet://iam.googleapis.com/${local.pool_root}/${google_iam_workload_identity_pool.apply.workload_identity_pool_id}/attribute.workflow_ref/${local.deploy_workflow_path}@refs/heads/main" : "principalSet://iam.googleapis.com/${local.pool_root}/${google_iam_workload_identity_pool.apply.workload_identity_pool_id}/attribute.repository/${var.github_repository}"
}

# Own pool for apply (not the deployers' `github` pool): its provider admits nothing but this project's deploy workflow, and
# for prod also requires the GitHub Environment (required reviewer) so the cloud token itself needs the approval.
resource "google_iam_workload_identity_pool" "apply" {
  project                   = var.project
  workload_identity_pool_id = "github-apply"
  display_name              = "GitHub Terraform apply"
}

resource "google_iam_workload_identity_pool_provider" "apply" {
  project                            = var.project
  workload_identity_pool_id          = google_iam_workload_identity_pool.apply.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-apply"
  display_name                       = "GitHub Terraform apply"
  attribute_condition                = local.apply_condition
  attribute_mapping = {
    "google.subject"         = "assertion.sub"
    "attribute.repository"   = "assertion.repository"
    "attribute.ref"          = "assertion.ref"
    "attribute.workflow_ref" = "assertion.job_workflow_ref"
  }
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Separate pool: a principalSet binds every provider of its pool, and the deploy pools either admit only main or are
# shared with deployers. This pool admits only jobs of terraform.yml (same-repo pull_request, manual dispatch) and of this
# project's deploy workflow (its trigger events). A PR can edit the workflow file, which is why the plan identity holds nothing
# but metadata reads.
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
  attribute_condition                = local.plan_condition
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

# Metadata the predefined readers do not cover (buckets, Firestore, Cloud Tasks queues, Artifact Registry repos, Monitoring,
# log-based metrics, Identity Platform config, Service Usage, project IAM). No object or document read permissions.
resource "google_project_iam_custom_role" "plan_metadata" {
  project     = var.project
  role_id     = "terraformPlanMetadata"
  title       = "Terraform plan metadata reader"
  description = "Read bucket/Firestore/project metadata for terraform plan; no data access."
  permissions = sort(setunion(local.plan_metadata_permissions, var.plan_extra_permissions))
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
