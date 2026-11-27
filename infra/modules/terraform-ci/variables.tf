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

variable "deploy_workflow" {
  description = "File name of this project's deploy workflow, which plans and applies its infrastructure before the app deploy (deploy-prod.yml, deploy-staging.yml or deploy-eval.yml). The only workflow the apply identity admits."
  type        = string

  validation {
    condition     = contains(["deploy-prod.yml", "deploy-staging.yml", "deploy-eval.yml"], var.deploy_workflow)
    error_message = "deploy_workflow must be deploy-prod.yml, deploy-staging.yml or deploy-eval.yml."
  }
}

variable "deploy_events" {
  description = "GitHub events that trigger the deploy workflow (prod: push of a release tag, workflow_dispatch; staging/eval: workflow_run after CI, workflow_dispatch)."
  type        = list(string)

  validation {
    condition     = length(var.deploy_events) > 0 && alltrue([for e in var.deploy_events : contains(["push", "workflow_dispatch", "workflow_run"], e)])
    error_message = "deploy_events accepts push, workflow_dispatch and workflow_run only (never pull_request)."
  }
}

variable "apply_tag_prefix" {
  description = "Besides refs/heads/main, also admit the deploy workflow on tag refs with this prefix (prod: refs/tags/v, the release tags that trigger deploy-prod.yml). Empty = main only."
  type        = string
  default     = ""

  validation {
    condition     = var.apply_tag_prefix == "" || can(regex("^refs/tags/[A-Za-z0-9._-]+$", var.apply_tag_prefix))
    error_message = "apply_tag_prefix must be empty or refs/tags/<prefix>."
  }
}

variable "apply_required_environment" {
  description = "GitHub Environment the apply job must run in (prod: `production`, required reviewer; deployment refs main and v* tags). Empty for the nonprod roots."
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
  description = "Additional read-only permissions (get/list only) for the plan custom role when a plan reports a missing permission. Never data-read permissions: the shared deny list plan-deny.json is enforced here and in tests; review any addition by hand."
  type        = set(string)
  default     = []

  validation {
    condition     = alltrue([for p in var.plan_extra_permissions : can(regex("\\.(get|list|getIamPolicy|getMetadata)$", p))])
    error_message = "plan_extra_permissions accepts get/list/getIamPolicy/getMetadata permissions only."
  }

  validation {
    condition = alltrue([for p in var.plan_extra_permissions :
      !contains(jsondecode(file("${path.module}/plan-deny.json")).permissions_exact, p) &&
      alltrue([for prefix in jsondecode(file("${path.module}/plan-deny.json")).permission_prefixes : !startswith(p, prefix)])
    ])
    error_message = "plan_extra_permissions contains a data-read permission (plan-deny.json); the plan identity is reachable from pull requests."
  }
}

variable "plan_extra_roles" {
  description = "Additional read-only predefined roles when a plan reports a missing permission: `*.viewer` / `*Viewer` roles only, never one in plan-deny.json (they read data). Check the role with `gcloud iam roles describe` first."
  type        = set(string)
  default     = []

  validation {
    condition = alltrue([for r in var.plan_extra_roles :
      can(regex("^roles/[A-Za-z0-9_]+\\.([A-Za-z0-9_]*Viewer|viewer)$", r)) &&
      !contains(jsondecode(file("${path.module}/plan-deny.json")).roles, r)
    ])
    error_message = "plan_extra_roles accepts metadata viewer roles only (roles/<service>.viewer or ...Viewer), never a role in plan-deny.json."
  }
}
