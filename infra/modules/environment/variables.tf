variable "project" {
  type = string
}

variable "region" {
  type = string
}

variable "env" {
  description = "Environment name: staging, prod or eval."
  type        = string
  validation {
    condition     = contains(["staging", "prod", "eval"], var.env)
    error_message = "env must be staging, prod or eval."
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

variable "placeholder_image" {
  description = "Public image used until CI deploys the real one (image is ignored after create)."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "api_max_instances" {
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

variable "eval_mode" {
  description = "Adds EVAL_MODE=true to the api and worker env (eval instance only); omitted entirely when false."
  type        = bool
  default     = false
}

variable "runtime_env" {
  description = "Value of the ENV env var and the config/<runtime_env>/ directory. null = var.env. Eval runs as `staging`."
  type        = string
  default     = null
}

variable "eval_backend_enabled" {
  description = "Creates the allowlisted eval-backend service, its grants and the allowlist secret (eval instance only)."
  type        = bool
  default     = false
}

variable "eval_cors_origins" {
  description = "Browser origins for the eval-backend service (emitted as CORS_ORIGINS, the api Settings name)."
  type        = list(string)
  default     = []
}

variable "public_api_enabled" {
  description = "Gates the public api and voice Cloud Run services, their allUsers invokers and the voice SA/IAM (off for eval)."
  type        = bool
  default     = true
}

variable "max_active_runs" {
  description = "MAX_ACTIVE_RUNS env on api and worker; emitted only when non-null."
  type        = number
  default     = null
}

variable "datasets_bucket" {
  description = "Datasets bucket name emitted as DATASETS_BUCKET on the eval-backend service (read-only use by the backend)."
  type        = string
  default     = ""
}

variable "eval_max_per_provider" {
  description = "EVAL_MAX_PER_PROVIDER on the eval-backend service: max interviews in parallel per AI provider (enforced by the backend scheduler, not Terraform)."
  type        = number
  default     = 2
}

variable "eval_owner_uid" {
  description = "EVAL_OWNER_UID on the eval-backend service: the single uid every allowlisted eval user acts as."
  type        = string
  default     = "eval"
}

variable "audio_bucket_name" {
  description = "Optional globally unique audio bucket name; null preserves the legacy environment name."
  type        = string
  default     = null
}

variable "auth_project" {
  description = "Firebase identity project for ID-token verification; null preserves the runtime project. Auth-email IAM remains local to the runtime project."
  type        = string
  default     = null
}

variable "speech_object_prefix" {
  description = "Optional audio-object prefix readable by the Speech service agent; null preserves legacy whole-bucket access."
  type        = string
  default     = null
}
