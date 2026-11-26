# Cloud Run shells (PRD R8/R14). The image is owned by CI after first create (ignore_changes).
# GIT_SHA and LLM_PROVIDER/LLM_MODEL/LLM_EFFORT are set by the deploy workflows on every deploy. Provider v6 models
# `env` as a SET, so a single entry cannot be ignored (env[0] is rejected) and ignoring all of env would also hide
# secret-ref (Resend/provider key) changes. They are therefore variables: pass the live values on plan/apply
# (git_sha, llm_provider, llm_model, llm_effort; see docs/reference/infra.md "Terraform drift").

locals {
  runtime_env = coalesce(var.runtime_env, var.env)
  worker_url  = "https://onolys-worker-${var.env}-${data.google_project.this.number}.${var.region}.run.app"
  # Deterministic run.app URL (same pattern as worker_url); the backend verifies Cloud Tasks OIDC against it.
  eval_backend_url = "https://onolys-eval-backend-${var.env}-${data.google_project.this.number}.${var.region}.run.app"
  routes_env = [
    { name = "ROUTES_FILE", value = "config/${local.runtime_env}/routes.yaml" },
    { name = "DEFAULT_PRESET", value = var.default_preset },
  ]
  interview_env = [
    { name = "AI_CAP_DAY", value = tostring(var.ai_cap_day) },
    { name = "AI_MAX_SECONDS", value = tostring(var.ai_max_seconds) },
    { name = "AI_WARN_SECONDS", value = tostring(var.ai_warn_seconds) },
    { name = "AI_MIN_SECONDS", value = tostring(var.ai_min_seconds) },
    { name = "AI_TOLERANCE_SECONDS", value = tostring(var.ai_tolerance_seconds) },
    { name = "AI_MISMATCH_MIN_SECONDS", value = tostring(var.ai_mismatch_min_seconds) },
    { name = "AI_MISMATCH_PCT", value = tostring(var.ai_mismatch_pct) },
    { name = "AI_ABANDON_COUNT_SECONDS", value = tostring(var.ai_abandon_count_seconds) },
    { name = "AI_RECONNECT_SECONDS", value = tostring(var.ai_reconnect_seconds) },
    { name = "AI_MIC_GATE", value = tostring(var.ai_mic_gate) },
  ]
  # Deploy-managed LLM overrides (api and worker only; the voice and eval-backend services do not take them). null omits.
  llm_env = [for e in [
    { name = "LLM_PROVIDER", value = var.llm_provider },
    { name = "LLM_MODEL", value = var.llm_model },
    { name = "LLM_EFFORT", value = var.llm_effort },
  ] : e if e.value != null]
  platform_env = concat(local.interview_env, [
    { name = "ENV", value = local.runtime_env },
    { name = "GCP_PROJECT", value = var.project },
    { name = "REGION", value = var.region },
    { name = "FIRESTORE_DATABASE", value = var.database_id },
    { name = "AUTH_PROJECT", value = coalesce(var.auth_project, var.project) },
    { name = "AUDIO_BUCKET", value = google_storage_bucket.audio.name },
    { name = "EVAL_CAP_DAY", value = tostring(var.eval_cap_day) },
    { name = "ADAPTERS", value = "real" },
    { name = "TASKS_QUEUE", value = google_cloud_tasks_queue.steps.name },
    { name = "TASKS_SA", value = google_service_account.tasks_invoker.email },
    { name = "WORKER_URL", value = local.worker_url },
    ],
    var.eval_mode ? [{ name = "EVAL_MODE", value = "true" }] : [],
    var.max_active_runs != null ? [{ name = "MAX_ACTIVE_RUNS", value = tostring(var.max_active_runs) }] : [],
  )
}

moved {
  from = google_cloud_run_v2_service.api
  to   = google_cloud_run_v2_service.api[0]
}

resource "google_cloud_run_v2_service" "api" {
  count               = var.public_api_enabled ? 1 : 0
  project             = var.project
  location            = var.region
  name                = "onolys-api-${var.env}"
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account                  = google_service_account.api.email
    timeout                          = "60s"
    max_instance_request_concurrency = 80

    scaling {
      min_instance_count = 0
      max_instance_count = var.api_max_instances
    }

    containers {
      image = var.placeholder_image

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        cpu_idle = true
      }

      env {
        name  = "GIT_SHA"
        value = var.git_sha
      }
      env {
        name  = "SERVICE_MODE"
        value = "api"
      }
      env {
        name  = "PR_PREVIEW"
        value = "false"
      }
      env {
        # V4 signed URLs on Cloud Run have no private key: GcsBlobStore signs through IAM signBlob as this SA
        # (api_self_token_creator grants it). Without it the upload-URL call fails with a 500.
        name  = "BLOB_SIGNER_EMAIL"
        value = google_service_account.api.email
      }
      env {
        name = "UID_HMAC_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.uid_hmac.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "CORS_ORIGINS"
        value = join(",", var.cors_origins)
      }
      env {
        # Verification links and the API reset fallback use the public app origin.
        name  = "APP_BASE_URL"
        value = var.app_base_url
      }
      env {
        name  = "EMAIL_FROM"
        value = var.email_from
      }
      dynamic "env" {
        # PRD 07 D2: only once the owner has seeded a secret version; otherwise the api runs and answers 503 email_unavailable.
        for_each = var.resend_secret_wired ? [1] : []
        content {
          name = "RESEND_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.resend.secret_id
              version = "latest"
            }
          }
        }
      }
      env {
        # Relay base the api hands to the browser in POST /interviews (voice.tf).
        name  = "VOICE_URL"
        value = "wss://${local.voice_host}"
      }
      dynamic "env" {
        for_each = local.llm_env
        content {
          name  = env.value.name
          value = env.value.value
        }
      }
      dynamic "env" {
        for_each = local.platform_env
        content {
          name  = env.value.name
          value = env.value.value
        }
      }
      dynamic "env" {
        for_each = local.routes_env
        content {
          name  = env.value.name
          value = env.value.value
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      # The template revision name is NOT ignored here: CI pins api traffic to a named revision, and ignoring it
      # makes Terraform send that name back on any template update (409 "different configuration already exists").
      client,
      scaling, # service-level block the API fills with zeros (perpetual diff); per-revision scaling is set in template
      client_version,
      labels["commit-sha"], # set by CI (google-github-actions/deploy-cloudrun)
      labels["managed-by"], # set by CI
      template[0].labels["commit-sha"],
      template[0].labels["managed-by"],
      template[0].labels["goog-terraform-provisioned"],
    ]
  }

  depends_on = [
    google_secret_manager_secret_iam_member.hmac,
    google_secret_manager_secret_iam_member.resend_api,
  ]
}

resource "google_cloud_run_v2_service" "worker" {
  project             = var.project
  location            = var.region
  name                = "onolys-worker-${var.env}"
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account                  = google_service_account.worker.email
    timeout                          = "900s"
    max_instance_request_concurrency = var.worker_concurrency

    scaling {
      min_instance_count = 0
      max_instance_count = var.worker_max_instances
    }

    containers {
      image = var.placeholder_image

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        cpu_idle = true
      }

      env {
        name  = "GIT_SHA"
        value = var.git_sha
      }
      env {
        name  = "SERVICE_MODE"
        value = "worker"
      }
      env {
        name = "UID_HMAC_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.uid_hmac.secret_id
            version = "latest"
          }
        }
      }
      # Durable password-reset jobs generate links and send mail in this service.
      # Keep the whole worker email configuration off until the secret has a version.
      dynamic "env" {
        for_each = var.resend_secret_wired ? {
          APP_BASE_URL = var.app_base_url
          EMAIL_FROM   = var.email_from
        } : {}
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = var.resend_secret_wired ? [1] : []
        content {
          name = "RESEND_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.resend.secret_id
              version = "latest"
            }
          }
        }
      }
      dynamic "env" {
        for_each = local.llm_env
        content {
          name  = env.value.name
          value = env.value.value
        }
      }
      dynamic "env" {
        for_each = local.platform_env
        content {
          name  = env.value.name
          value = env.value.value
        }
      }
      dynamic "env" {
        for_each = local.routes_env
        content {
          name  = env.value.name
          value = env.value.value
        }
      }
      dynamic "env" {
        for_each = local.worker_provider_secrets
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.provider[env.key].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      template[0].revision,
      client,
      scaling, # service-level block the API fills with zeros (perpetual diff); per-revision scaling is set in template
      client_version,
      labels["commit-sha"], # set by CI (google-github-actions/deploy-cloudrun)
      labels["managed-by"], # set by CI
      template[0].labels["commit-sha"],
      template[0].labels["managed-by"],
      template[0].labels["goog-terraform-provisioned"],
    ]
  }

  depends_on = [
    google_secret_manager_secret_iam_member.hmac,
    google_secret_manager_secret_iam_member.worker_provider,
    google_secret_manager_secret_iam_member.resend_worker,
    google_project_iam_member.worker_auth_email,
  ]
}

resource "google_cloud_run_v2_service" "eval_backend" {
  count               = var.eval_backend_enabled ? 1 : 0
  project             = var.project
  location            = var.region
  name                = "onolys-eval-backend-${var.env}"
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    # Same SA as the module's api (identical grants by construction, PRD 03 R4).
    service_account                  = google_service_account.api.email
    timeout                          = "60s"
    max_instance_request_concurrency = 20

    scaling {
      min_instance_count = var.eval_backend_min_instances # default 0: Cloud Tasks wakes it
      max_instance_count = var.api_max_instances
    }

    containers {
      image = var.placeholder_image

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        cpu_idle = true
      }

      env {
        name  = "GIT_SHA"
        value = var.git_sha
      }
      env {
        name  = "SERVICE_MODE"
        value = "api"
      }
      env {
        name = "UID_HMAC_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.uid_hmac.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "BLOB_SIGNER_EMAIL"
        value = google_service_account.api.email
      }
      env {
        name  = "CORS_ORIGINS"
        value = join(",", var.eval_cors_origins)
      }
      env {
        name  = "SERVICE_URL"
        value = local.eval_backend_url
      }
      env {
        name  = "TASKS_OIDC_AUDIENCE"
        value = local.eval_backend_url
      }
      env {
        name  = "DATASETS_BUCKET"
        value = var.datasets_bucket
      }
      env {
        name  = "EVAL_MAX_PER_PROVIDER"
        value = tostring(var.eval_max_per_provider)
      }
      env {
        name  = "EVAL_OWNER_UID"
        value = var.eval_owner_uid
      }
      env {
        name = "EVAL_ALLOWED_EMAILS"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.eval_allowed_emails[0].secret_id
            version = "latest"
          }
        }
      }
      dynamic "env" {
        for_each = local.platform_env
        content {
          name  = env.value.name
          value = env.value.value
        }
      }
      dynamic "env" {
        for_each = local.routes_env
        content {
          name  = env.value.name
          value = env.value.value
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      template[0].revision,
      client,
      scaling,
      client_version,
      labels["commit-sha"],
      labels["managed-by"],
      template[0].labels["commit-sha"],
      template[0].labels["managed-by"],
      template[0].labels["goog-terraform-provisioned"],
    ]
  }

  depends_on = [
    google_secret_manager_secret_iam_member.hmac,
    google_secret_manager_secret_iam_member.eval_allowed_emails,
  ]
}

# --- invokers (PRD R8) ---
moved {
  from = google_cloud_run_v2_service_iam_member.api_public
  to   = google_cloud_run_v2_service_iam_member.api_public[0]
}

resource "google_cloud_run_v2_service_iam_member" "api_public" {
  count    = var.public_api_enabled ? 1 : 0
  project  = var.project
  location = var.region
  name     = google_cloud_run_v2_service.api[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "worker_tasks_invoker" {
  project  = var.project
  location = var.region
  name     = google_cloud_run_v2_service.worker.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.tasks_invoker.email}"
}

# Auth is in-app (Firebase ID token + allowlist), same as the legacy eval service.
resource "google_cloud_run_v2_service_iam_member" "eval_backend_public" {
  count    = var.eval_backend_enabled ? 1 : 0
  project  = var.project
  location = var.region
  name     = google_cloud_run_v2_service.eval_backend[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
