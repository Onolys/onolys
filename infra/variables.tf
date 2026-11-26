variable "project" {
  type    = string
  default = "onolys"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "resend_secret_wired" {
  description = "Wire auth-email settings and RESEND_API_KEY on the prod api and worker (prod rollout deferred; default false)."
  type        = map(bool)
  default = {
    prod = false
  }

  validation {
    condition     = toset(keys(var.resend_secret_wired)) == toset(["prod"])
    error_message = "resend_secret_wired needs exactly the key prod."
  }
}

variable "alert_email" {
  description = "Owner email for failure alerts (Monitoring channel needs a verification click)."
  type        = string
  default     = "tejitpabari99@gmail.com"
}

variable "llm_secrets" {
  description = "Map of env-var name to base secret id for LLM provider keys; each environment gets `<base>-<env>`."
  type        = map(string)
  default = {
    GEMINI_API_KEY    = "gemini-api-key"
    ANTHROPIC_API_KEY = "anthropic-api-key"
    OPENAI_API_KEY    = "openai-api-key" # live: openai-api-key-prod shell, version and worker accessor exist
  }
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

# Only feeds the authorized sign-in domains (the old staging site was removed).
variable "app_staging_site_id" {
  type    = string
  default = "onolys-app-staging"
}

variable "github_repository" {
  description = "GitHub repo (owner/name) allowed to impersonate the deployer SAs via WIF."
  type        = string
  default     = "Onolys/onolys"
}

variable "git_sha" {
  description = "Initial/current GIT_SHA env value for prod. CI overwrites it at deploy; pass the live value on apply to keep plan quiet."
  type        = map(string)
  default = {
    prod = "unset"
  }

  validation {
    condition     = toset(keys(var.git_sha)) == toset(["prod"])
    error_message = "git_sha needs exactly the key prod."
  }
}

variable "llm_provider" {
  description = "Live prod LLM_PROVIDER on api and worker (deploy-prod sets it from PROD_LLM_PROVIDER; blank = no override). Pass the live value to keep plan quiet."
  type        = string
  default     = ""
}

variable "llm_model" {
  description = "Live prod LLM_MODEL (deploy-prod PROD_LLM_MODEL; blank = no override)."
  type        = string
  default     = ""
}

variable "llm_effort" {
  description = "Live prod LLM_EFFORT (deploy-prod PROD_LLM_EFFORT; blank = no override)."
  type        = string
  default     = ""
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

