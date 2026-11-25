variable "project" {
  type    = string
  default = "onolys"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "admin_enabled" {
  description = "Gates the admin (SP07) resources per environment: staging is the ONLY admin environment (serves admin.onolys.com, owner decision 2026-11-21); prod admin is off."
  type        = map(bool)
  default = {
    staging = true
    prod    = false
  }

  validation {
    condition     = toset(keys(var.admin_enabled)) == toset(["staging", "prod"])
    error_message = "admin_enabled needs exactly the keys staging and prod."
  }
}

variable "resend_secret_wired" {
  description = "Per environment: wire auth-email settings and RESEND_API_KEY on the api and worker. Set staging true only after the owner seeds resend-api-key-staging; prod stays false (prod rollout deferred)."
  type        = map(bool)
  default = {
    staging = false
    prod    = false
  }

  validation {
    condition     = toset(keys(var.resend_secret_wired)) == toset(["staging", "prod"])
    error_message = "resend_secret_wired needs exactly the keys staging and prod."
  }
}

variable "staging_alerts" {
  description = "Enable the failure alerts on staging (prod is always on)."
  type        = bool
  default     = false
}

variable "alert_email" {
  description = "Owner email for failure alerts (Monitoring channel needs a verification click)."
  type        = string
  default     = "tejitpabari99@gmail.com"
}

variable "llm_secrets" {
  description = "Map of env-var name to base secret id for LLM provider keys; each environment gets `<base>-<env>`."
  type        = map(string)
  default     = { GEMINI_API_KEY = "gemini-api-key", ANTHROPIC_API_KEY = "anthropic-api-key" }
}

variable "stt_secrets" {
  description = "Map of env-var name to base secret id for STT provider keys, per environment `<base>-<env>` (empty: Google STT uses ADC)."
  type        = map(string)
  default     = {}
}

variable "worker_concurrency" {
  type    = number
  default = 2
}

variable "worker_max_instances" {
  description = "Cloud Tasks max_concurrent_dispatches = worker_concurrency x worker_max_instances."
  type        = number
  default     = 3
}

# Hosting site ids are globally unique across Firebase. If one is taken, use the
# `onolys-miti-app*` fallbacks (PRD R11) and record which in docs/reference/infra.md.
variable "app_site_id" {
  type    = string
  default = "onolys-app"
}

variable "app_staging_site_id" {
  type    = string
  default = "onolys-app-staging"
}

variable "admin_site_id" {
  type    = string
  default = "onolys-admin"
}

variable "admin_staging_site_id" {
  type    = string
  default = "onolys-admin-staging"
}

variable "github_repository" {
  description = "GitHub repo (owner/name) allowed to impersonate the deployer SAs via WIF."
  type        = string
  default     = "Onolys/onolys"
}

variable "git_sha" {
  description = "Initial/current GIT_SHA env value per environment. CI overwrites it at deploy; pass the live values on apply to keep plan quiet."
  type        = map(string)
  default = {
    staging = "unset"
    prod    = "unset"
  }

  validation {
    condition     = toset(keys(var.git_sha)) == toset(["staging", "prod"])
    error_message = "git_sha needs exactly the keys staging and prod."
  }
}

variable "default_preset" {
  description = "Production default preset, shared with evaluation prod labels."
  type        = string
  default     = "default"
}

variable "prod_engine" {
  description = "Production engine key, shared with evaluation prod labels."
  type        = string
  default     = "miti"
}

variable "eval_worker_concurrency" {
  description = "Eval worker request concurrency (eval module instance)."
  type        = number
  default     = 2
}

variable "eval_worker_max_instances" {
  description = "Eval queue max_concurrent_dispatches = eval_worker_concurrency x eval_worker_max_instances."
  type        = number
  default     = 4
}

variable "eval_llm_secrets" {
  description = "Env-var name to base secret id for the eval instance's LLM keys (`<base>-eval`); same default as llm_secrets."
  type        = map(string)
  default     = { GEMINI_API_KEY = "gemini-api-key", ANTHROPIC_API_KEY = "anthropic-api-key" }
}

variable "eval_git_sha" {
  description = "Initial/current GIT_SHA env value for the eval instance; CI overwrites it at deploy."
  type        = string
  default     = "unset"
}
