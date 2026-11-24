# Cloud Run shells (PRD R8/R14). The image is owned by CI after first create (ignore_changes).
# GIT_SHA: provider v6 models `env` as a SET, so a single entry cannot be ignored (env[0] is rejected)
# and ignoring all of env would also hide secret-ref changes. GIT_SHA is therefore a variable;
# after a CI deploy, plan shows it as drift until applied with -var 'git_sha={staging="<sha>",prod="<sha>"}' (see docs/reference/infra.md).

locals {
  worker_url = "https://onolys-worker-${var.env}-${data.google_project.this.number}.${var.region}.run.app"
  routes_env = [
    { name = "ROUTES_FILE", value = "config/${var.env}/routes.yaml" },
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
  platform_env = concat(local.interview_env, [
    { name = "ENV", value = var.env },
    { name = "GCP_PROJECT", value = var.project },
    { name = "REGION", value = var.region },
    { name = "FIRESTORE_DATABASE", value = var.database_id },
    { name = "AUTH_PROJECT", value = var.project },
    { name = "AUDIO_BUCKET", value = google_storage_bucket.audio.name },
    { name = "EVAL_CAP_DAY", value = tostring(var.eval_cap_day) },
    { name = "ADAPTERS", value = "real" },
    { name = "TASKS_QUEUE", value = google_cloud_tasks_queue.steps.name },
    { name = "TASKS_SA", value = google_service_account.tasks_invoker.email },
    { name = "WORKER_URL", value = local.worker_url },
  ])
}

resource "google_cloud_run_v2_service" "api" {
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
        # Only the api builds auth-email links; unset elsewhere is fine (Settings treats it as optional).
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
  ]
}

resource "google_cloud_run_v2_service" "admin_backend" {
  count               = var.admin_enabled ? 1 : 0
  project             = var.project
  location            = var.region
  name                = "onolys-admin-backend-${var.env}"
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account                  = google_service_account.admin_backend[0].email
    timeout                          = "130s"
    max_instance_request_concurrency = 20

    scaling {
      min_instance_count = 0
      max_instance_count = var.admin_max_instances
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
        name  = "ENV"
        value = var.env
      }
      env {
        name  = "ADMIN_AUTH"
        value = "on"
      }
      env {
        name  = "ADMIN_AUTH_PROJECT"
        value = var.project
      }
      env {
        name  = "ADMIN_CORS_ORIGINS"
        value = join(",", var.admin_cors_origins)
      }
      env {
        name = "ADMIN_ALLOWED_EMAILS"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.admin_allowed_emails[0].secret_id
            version = "latest"
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
    google_secret_manager_secret_iam_member.admin_emails,
  ]
}

# --- invokers (PRD R8) ---
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  project  = var.project
  location = var.region
  name     = google_cloud_run_v2_service.api.name
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

resource "google_cloud_run_v2_service_iam_member" "admin_public" {
  count    = var.admin_enabled ? 1 : 0
  project  = var.project
  location = var.region
  name     = google_cloud_run_v2_service.admin_backend[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
