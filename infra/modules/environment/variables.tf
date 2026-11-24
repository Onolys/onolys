variable "project" {
  type = string
}

variable "region" {
  type = string
}

variable "env" {
  description = "Environment name: staging or prod."
  type        = string
  validation {
    condition     = contains(["staging", "prod"], var.env)
    error_message = "env must be staging or prod."
  }
}

variable "database_id" {
  description = "Firestore database id: `staging` for staging, `(default)` for prod."
  type        = string
}

variable "delete_protection" {
  description = "Firestore delete protection (on for prod)."
  type        = bool
  default     = false
}

variable "cors_origins" {
  description = "Browser origins allowed to PUT to the audio bucket via signed URLs."
  type        = list(string)
}

variable "worker_concurrency" {
  type = number
}

variable "worker_max_instances" {
  description = "Queue max_concurrent_dispatches = worker_concurrency x worker_max_instances."
  type        = number
}

variable "llm_secrets" {
  description = "Env-var name to BASE secret id for LLM provider keys; the module creates `<base>-<env>`."
  type        = map(string)
}

variable "stt_secrets" {
  description = "Env-var name to BASE secret id for STT provider keys (worker only); the module creates `<base>-<env>`."
  type        = map(string)
  default     = {}
}

variable "admin_enabled" {
  description = "Gates every admin-backend (SP07) resource."
  type        = bool
  default     = false
}

variable "admin_cors_origins" {
  description = "Browser origins the admin-backend answers CORS preflight for."
  type        = list(string)
  default     = []
}

variable "placeholder_image" {
  description = "Public image used until CI deploys the real one (image is ignored after create)."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "api_max_instances" {
  type    = number
  default = 3
}

variable "admin_max_instances" {
  type    = number
  default = 3
}

variable "eval_cap_day" {
  type    = number
  default = 10
}

variable "ai_cap_day" {
  type    = number
  default = 5
}

variable "default_preset" {
  description = "Default preset name in the routes file (SP01)."
  type        = string
  default     = "default"
}

variable "git_sha" {
  description = "Initial GIT_SHA env value; CI overwrites it at deploy (PRD R13/R14)."
  type        = string
  default     = "unset"
}

variable "alerts_enabled" {
  description = "Create the failure alert policies (prod true; staging via staging_alerts)."
  type        = bool
  default     = false
}

variable "notification_channel_ids" {
  description = "Monitoring notification channel ids for the failure alerts."
  type        = list(string)
  default     = []
}

variable "voice_max_instances" {
  description = "Voice relay max instances (concurrency 10 each)."
  type        = number
  default     = 3
}

variable "ai_max_seconds" {
  type    = number
  default = 600
}

variable "ai_warn_seconds" {
  type    = number
  default = 480
}

variable "ai_min_seconds" {
  type    = number
  default = 300
}

variable "ai_tolerance_seconds" {
  type    = number
  default = 30
}

variable "ai_mismatch_min_seconds" {
  description = "Relay/upload duration mismatch tolerated up to max(this, ai_mismatch_pct % of the relay duration); beyond it the session stops as our error."
  type        = number
  default     = 60
}

variable "ai_mismatch_pct" {
  type    = number
  default = 15
}

variable "ai_abandon_count_seconds" {
  type    = number
  default = 30
}

variable "ai_reconnect_seconds" {
  type    = number
  default = 60
}

variable "ai_mic_gate" {
  type    = bool
  default = false
}

variable "app_base_url" {
  description = "Public web app origin used in auth-email links by the api and activated reset-email worker."
  type        = string
}

variable "email_from" {
  description = "From header for auth emails (api and activated worker EMAIL_FROM)."
  type        = string
  default     = "Onolys <no-reply@onolys.com>"
}

variable "resend_secret_wired" {
  description = "Wire RESEND_API_KEY on the api and worker via secret_key_ref, plus worker email settings and IAM. Keep false until the owner has seeded a version of resend-api-key-<env> (a revision fails to start if the secret has no version)."
  type        = bool
  default     = false
}
