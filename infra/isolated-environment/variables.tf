variable "environment" {
  type = string
  validation {
    condition     = contains(["staging", "eval"], var.environment)
    error_message = "This root manages staging or eval only; production stays in the legacy root."
  }
}

variable "project" {
  description = "Existing, separately billed GCP project for this environment."
  type        = string
  validation {
    condition     = var.project == "onolys-${var.environment}"
    error_message = "Project must be onolys-staging for staging or onolys-eval for eval. Never point this root at onolys."
  }
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "hosting_site_id" {
  description = "New globally unique Firebase Hosting site; no custom domain is managed here."
  type        = string
}

variable "audio_bucket_name" {
  description = "Globally unique bucket override; null uses PROJECT-audio."
  type        = string
  default     = null
}

variable "auth_project" {
  description = "Firebase token issuer project; null uses the local project for staging and existing onolys identity for eval."
  type        = string
  default     = null
}

variable "manage_identity" {
  description = "Create local Identity Platform config and a web app for validation. Never manages an external auth project."
  type        = bool
  default     = false
  validation {
    condition     = !var.manage_identity || coalesce(var.auth_project, var.environment == "eval" ? "onolys" : var.project) == var.project
    error_message = "Identity management is allowed only when auth_project equals this runtime project."
  }
}

variable "datasets_source_bucket" {
  description = "External read-only eval dataset source; empty creates a new project-owned dataset bucket. External IAM and content migration are separate owner operations."
  type        = string
  default     = ""
}

variable "datasets_bucket_name" {
  description = "Globally unique new eval dataset bucket override; null uses PROJECT-datasets."
  type        = string
  default     = null
}

variable "llm_secrets" {
  description = "Env name to base secret id; import pre-created shells, seed values outside Terraform."
  type        = map(string)
  default = {
    GEMINI_API_KEY    = "gemini-api-key"
    ANTHROPIC_API_KEY = "anthropic-api-key"
    OPENAI_API_KEY    = "openai-api-key"
  }
}

variable "stt_secrets" {
  type    = map(string)
  default = {}
}

variable "git_sha" {
  description = "Bootstrap GIT_SHA; CI owns image updates after initial provisioning."
  type        = string
  default     = "unset"
}

variable "placeholder_image" {
  description = "Bootstrap image; application images and deployment are a separate rollout."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "github_repository" {
  type    = string
  default = "Onolys/onolys"
}

variable "artifact_registry_reader_members" {
  description = "Optional exact IAM principals for cross-project promotion, scoped only to this image repository. Empty grants no external access."
  type        = set(string)
  default     = []
}

variable "cloud_run_reader_members" {
  description = "Optional provenance-only principals; run.viewer is scoped to each environment service, with no deploy or actAs grant."
  type        = set(string)
  default     = []
}

variable "app_base_url" {
  description = "Auth-email link origin. Empty disables email until the application accepts the new Hosting host; no live domain is assumed."
  type        = string
  default     = ""
}

variable "resend_secret_wired" {
  description = "Enable the shared email capability only after seeding Resend and validating the link origin. Cross-project identity email requires a separate reviewed IAM design."
  type        = bool
  default     = false
  validation {
    condition     = !var.resend_secret_wired || (var.app_base_url != "" && coalesce(var.auth_project, var.environment == "eval" ? "onolys" : var.project) == var.project)
    error_message = "Auth email requires a nonempty supported app_base_url and identity in this runtime project."
  }
}
