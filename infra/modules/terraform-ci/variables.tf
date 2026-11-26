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

variable "apply_principal_set" {
  description = "Full principalSet:// member allowed to impersonate the apply service account. Callers pass a main-only (ref) or production-environment (environment) selector inside their existing, repository-pinned WIF pool."
  type        = string

  validation {
    condition     = startswith(var.apply_principal_set, "principalSet://iam.googleapis.com/") && !strcontains(var.apply_principal_set, "/attribute.repository/")
    error_message = "The apply identity must be bound to a ref or environment selector, never to the whole repository."
  }
}

variable "apply_roles" {
  description = "Project roles for the apply identity. It is effectively project admin (it manages IAM, WIF, Cloud Run, Firestore, secrets, Hosting); the controls are the main-only/production-approval binding, not the role list."
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
  ]
}

variable "plan_roles" {
  description = "Project roles for the plan identity: metadata-only readers. Deliberately NOT roles/viewer or roles/datastore.viewer (they read Firestore documents and bucket objects, which hold user audio and session data); the plan identity is reachable from any same-repo pull_request workflow."
  type        = set(string)
  default = [
    "roles/run.viewer",
    "roles/secretmanager.viewer",
    "roles/cloudtasks.viewer",
    "roles/cloudscheduler.viewer",
    "roles/monitoring.viewer",
    "roles/iam.securityReviewer",
    "roles/serviceusage.serviceUsageViewer",
    "roles/serviceusage.serviceUsageConsumer",
    "roles/firebasehosting.viewer",
    "roles/firebaseauth.viewer",
    "roles/artifactregistry.reader",
  ]
}

variable "plan_extra_roles" {
  description = "Additional read-only roles when a plan reports a missing permission."
  type        = set(string)
  default     = []
}
