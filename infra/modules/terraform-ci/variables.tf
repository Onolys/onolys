variable "project" {
  description = "GCP project the two Terraform identities live in and manage."
  type        = string
}

variable "project_number" {
  description = "Number of `project` (used to build WIF principal names from known values)."
  type        = string
}

variable "github_repository" {
  type    = string
  default = "Onolys/onolys"
}

variable "state_bucket" {
  description = "Private GCS bucket holding this root's Terraform state (must already exist; created by infra/bootstrap.sh or isolated-environment/bootstrap)."
  type        = string
}

variable "apply_required_environment" {
  description = "GitHub Environment the apply job must run in (prod: `terraform-prod`, required reviewers, main only). Empty for the main-only nonprod roots."
  type        = string
  default     = ""
}

variable "apply_roles" {
  description = "Project roles for the apply identity. It is effectively project admin (it manages IAM, WIF, Cloud Run, Firestore, secrets, Hosting); the controls are the apply pool's workflow/ref/environment conditions, not the role list."
  type        = set(string)
  default = [
    "roles/run.admin",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountUser",
    "roles/iam.roleAdmin",
    "roles/iam.workloadIdentityPoolAdmin",
    "roles/resourcemanager.projectIamAdmin",
    "roles/secretmanager.admin",
    "roles/datastore.owner",
    "roles/datastore.indexAdmin", # datastore.owner has no datastore.indexes.* (google_firestore_field needs indexes.update)
    "roles/storage.admin",
    "roles/cloudtasks.admin",
    "roles/cloudscheduler.admin",
    "roles/artifactregistry.admin",
    "roles/firebase.admin",
    "roles/firebasehosting.admin",
    "roles/firebaseauth.admin",
    "roles/firebaserules.admin",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/monitoring.admin",
    "roles/logging.configWriter",
  ]
}

variable "plan_roles" {
  description = "Predefined project roles for the plan identity: metadata-only readers, each verified with `gcloud iam roles describe` and snapshotted in plan-role-permissions.snapshot.json (a test fails if a data-read permission appears). Deliberately NOT roles/viewer, roles/datastore.viewer, roles/firebaseauth.viewer (users.get), roles/cloudtasks.viewer (tasks.get/list: task bodies hold uid/sid/email), roles/iam.securityReviewer (logging.logEntries.list, storage.objects.list, tasks.list), roles/monitoring.viewer (timeSeries.list) or roles/artifactregistry.reader (image download); the plan identity is reachable from any same-repo pull_request workflow. Everything else the plan needs is in the custom role (local.plan_metadata_permissions)."
  type        = set(string)
  default = [
    "roles/run.viewer",
    "roles/secretmanager.viewer",
    "roles/cloudscheduler.viewer",
    "roles/iam.serviceAccountViewer",
    "roles/iam.roleViewer",
    "roles/iam.workloadIdentityPoolViewer",
    "roles/firebasehosting.viewer",
  ]
}

variable "plan_extra_permissions" {
  description = "Additional read-only permissions (get/list only) for the plan custom role when a plan reports a missing permission. Never data-read permissions: a test denies them in the defaults, review any addition by hand."
  type        = set(string)
  default     = []

  validation {
    condition     = alltrue([for p in var.plan_extra_permissions : can(regex("\\.(get|list|getIamPolicy|getMetadata)$", p))])
    error_message = "plan_extra_permissions accepts get/list/getIamPolicy/getMetadata permissions only."
  }
}

variable "plan_extra_roles" {
  description = "Additional read-only roles when a plan reports a missing permission."
  type        = set(string)
  default     = []
}
