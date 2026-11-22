# Voice relay (SP10 R12, D2/D3): same image as the api with SERVICE_MODE=voice, in its own service so a 10-minute
# WebSocket fits (3600 s request timeout) and Vertex rights stay off the API SA. CI owns the image after create.

locals {
  # Deterministic like worker_url, so the api service can carry it without depending on the voice service.
  voice_host = "onolys-voice-${var.env}-${data.google_project.this.number}.${var.region}.run.app"
  voice_env = [
    { name = "ENV", value = var.env },
    { name = "GCP_PROJECT", value = var.project },
    { name = "GOOGLE_CLOUD_PROJECT", value = var.project },
    { name = "REGION", value = var.region },
    { name = "FIRESTORE_DATABASE", value = var.database_id },
    { name = "AUTH_PROJECT", value = var.project },
    { name = "CORS_ORIGINS", value = join(",", var.cors_origins) },
    { name = "VOICE_PROVIDERS_FILE", value = "config/${var.env}/voice_providers.yaml" },
    { name = "ADAPTERS", value = "real" },
    { name = "AI_CAP_DAY", value = tostring(var.ai_cap_day) },
    { name = "AI_MAX_SECONDS", value = tostring(var.ai_max_seconds) },
    { name = "AI_WARN_SECONDS", value = tostring(var.ai_warn_seconds) },
    { name = "AI_MIN_SECONDS", value = tostring(var.ai_min_seconds) },
    { name = "AI_TOLERANCE_SECONDS", value = tostring(var.ai_tolerance_seconds) },
    { name = "AI_ABANDON_COUNT_SECONDS", value = tostring(var.ai_abandon_count_seconds) },
    { name = "AI_RECONNECT_SECONDS", value = tostring(var.ai_reconnect_seconds) },
    { name = "AI_MIC_GATE", value = tostring(var.ai_mic_gate) },
  ]
}

resource "google_service_account" "voice" {
  project      = var.project
  account_id   = "voice-${var.env}"
  display_name = "Onolys voice relay (${var.env})"
}

# Only two grants: Vertex AI (Gemini Live) and Firestore, limited to this env's database (same condition as api/worker).
resource "google_project_iam_member" "voice_aiplatform_user" {
  project = var.project
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.voice.email}"
}

resource "google_project_iam_member" "voice_datastore_user" {
  project = var.project
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.voice.email}"

  condition {
    title       = "firestore-${var.env}-only"
    description = "Only the ${var.database_id} database"
    expression  = "resource.name == \"${local.firestore_db_resource}\""
  }

  depends_on = [google_firestore_database.db]
}

resource "google_secret_manager_secret_iam_member" "voice_hmac" {
  project   = var.project
  secret_id = google_secret_manager_secret.uid_hmac.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.voice.email}"
}

resource "google_cloud_run_v2_service" "voice" {
  project             = var.project
  location            = var.region
  name                = "onolys-voice-${var.env}"
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account                  = google_service_account.voice.email
    timeout                          = "3600s"
    max_instance_request_concurrency = 10
    session_affinity                 = true

    scaling {
      min_instance_count = 0
      max_instance_count = var.voice_max_instances
    }

    containers {
      image = var.placeholder_image

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        cpu_idle = false # CPU always allocated: the socket pumps audio between requests
      }

      env {
        name  = "GIT_SHA"
        value = var.git_sha
      }
      env {
        name  = "SERVICE_MODE"
        value = "voice"
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
        for_each = local.voice_env
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
    google_secret_manager_secret_iam_member.voice_hmac,
    google_project_iam_member.voice_aiplatform_user,
    google_project_iam_member.voice_datastore_user,
  ]
}

# Browsers connect directly; access is enforced by the first-frame ID-token auth, not by Cloud Run IAM.
resource "google_cloud_run_v2_service_iam_member" "voice_public" {
  project  = var.project
  location = var.region
  name     = google_cloud_run_v2_service.voice.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
