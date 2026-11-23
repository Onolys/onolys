# Evaluation runtime is staging-only; SP2's existing private bucket remains independent.
# The admin-staging Firebase web app is reused (no second Firebase application).
data "google_project" "eval" {
  project_id = var.project
}

locals {
  eval_service_url      = "https://onolys-eval-backend-staging-${data.google_project.eval.number}.${var.region}.run.app"
  eval_provider_secrets = var.eval_enabled ? merge(var.llm_secrets, var.stt_secrets) : {}
  eval_env = var.eval_enabled ? {
    ENV                 = "staging"
    GCP_PROJECT         = var.project
    REGION              = var.region
    FIRESTORE_DATABASE  = "staging"
    ADMIN_AUTH          = "on"
    ADMIN_AUTH_PROJECT  = var.project
    ADMIN_CORS_ORIGINS  = "https://onolys-eval-staging.web.app,https://eval.onolys.com"
    EVAL_BUCKET         = google_storage_bucket.eval_staging.name
    TASKS_QUEUE         = google_cloud_tasks_queue.eval_staging[0].id
    TASKS_SA            = google_service_account.eval_tasks_staging[0].email
    SERVICE_URL         = local.eval_service_url
    TASKS_OIDC_AUDIENCE = local.eval_service_url
    PROD_ENGINE         = var.prod_engine
    DEFAULT_PRESET      = var.default_preset
    ROUTES_FILE         = "config/staging/routes.yaml"
  } : {}
}

resource "google_firebase_hosting_site" "eval_staging" {
  count      = var.eval_enabled ? 1 : 0
  provider   = google-beta
  project    = var.project
  site_id    = "onolys-eval-staging"
  depends_on = [google_project_service.api]
}

resource "google_service_account" "eval_staging" {
  count        = var.eval_enabled ? 1 : 0
  project      = var.project
  account_id   = "eval-backend-staging"
  display_name = "Onolys evaluation backend (staging)"
}

resource "google_service_account" "eval_tasks_staging" {
  count        = var.eval_enabled ? 1 : 0
  project      = var.project
  account_id   = "eval-tasks-staging"
  display_name = "Onolys evaluation task OIDC (staging)"
}

resource "google_cloud_tasks_queue" "eval_staging" {
  count    = var.eval_enabled ? 1 : 0
  project  = var.project
  location = var.region
  name     = "onolys-eval-runs-staging"
  rate_limits {
    max_dispatches_per_second = 4
    max_concurrent_dispatches = 4
  }
  retry_config {
    max_attempts = 3
    min_backoff  = "5s"
    max_backoff  = "30s"
  }
  depends_on = [google_project_service.api]
}

resource "google_cloud_tasks_queue_iam_member" "eval_enqueuer" {
  count    = var.eval_enabled ? 1 : 0
  project  = var.project
  location = var.region
  name     = google_cloud_tasks_queue.eval_staging[0].name
  role     = "roles/cloudtasks.enqueuer"
  member   = "serviceAccount:${google_service_account.eval_staging[0].email}"
}

resource "google_service_account_iam_member" "eval_tasks_user" {
  count              = var.eval_enabled ? 1 : 0
  service_account_id = google_service_account.eval_tasks_staging[0].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.eval_staging[0].email}"
}

resource "google_project_iam_member" "eval_datastore" {
  count   = var.eval_enabled ? 1 : 0
  project = var.project
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.eval_staging[0].email}"
  condition {
    title       = "firestore-staging-only"
    description = "Only the staging database"
    expression  = "resource.name == \"projects/${var.project}/databases/staging\""
  }
}

# Match worker-staging: Speech ADC and provider keys, no Vertex role (worker has none).
resource "google_project_iam_member" "eval_speech" {
  count   = var.eval_enabled ? 1 : 0
  project = var.project
  role    = "roles/speech.client"
  member  = "serviceAccount:${google_service_account.eval_staging[0].email}"
}

resource "google_storage_bucket_iam_member" "eval_objects" {
  count  = var.eval_enabled ? 1 : 0
  bucket = google_storage_bucket.eval_staging.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.eval_staging[0].email}"
}

resource "google_storage_bucket_iam_member" "eval_stt_uploads" {
  count  = var.eval_enabled ? 1 : 0
  bucket = google_storage_bucket.eval_staging.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${module.staging.stt_service_agent_email}"
  condition {
    title       = "eval-uploads-only"
    description = "Speech may read evaluation uploads only"
    expression  = "resource.name.startsWith(\"projects/_/buckets/${google_storage_bucket.eval_staging.name}/objects/uploads/\")"
  }
}

resource "google_secret_manager_secret_iam_member" "eval_provider" {
  for_each  = local.eval_provider_secrets
  project   = var.project
  secret_id = "${each.value}-staging"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.eval_staging[0].email}"
}

resource "google_secret_manager_secret_iam_member" "eval_allowlist" {
  count     = var.eval_enabled ? 1 : 0
  project   = var.project
  secret_id = "admin-allowed-emails-staging"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.eval_staging[0].email}"
}

resource "google_cloud_run_v2_service" "eval_staging" {
  count               = var.eval_enabled ? 1 : 0
  project             = var.project
  location            = var.region
  name                = "onolys-eval-backend-staging"
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false
  template {
    service_account                  = google_service_account.eval_staging[0].email
    timeout                          = "900s"
    max_instance_request_concurrency = 4
    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }
    containers {
      # Harmless bootstrap shell; Task 11 replaces this with the real authenticated backend.
      image = "us-docker.pkg.dev/cloudrun/container/hello"
      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        cpu_idle = true
      }
      dynamic "env" {
        for_each = local.eval_env
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name = "ADMIN_ALLOWED_EMAILS"
        value_source {
          secret_key_ref {
            secret  = "admin-allowed-emails-staging"
            version = "latest"
          }
        }
      }
      dynamic "env" {
        for_each = local.eval_provider_secrets
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = "${env.value}-staging"
              version = "latest"
            }
          }
        }
      }
    }
  }
  lifecycle {
    precondition {
      condition     = var.admin_enabled["staging"]
      error_message = "Evaluation reuses the enabled admin-staging Firebase app and allowlist."
    }
    ignore_changes = [
      template[0].containers[0].image, template[0].revision,
      client, scaling, client_version,
      labels["commit-sha"], labels["managed-by"],
      template[0].labels["commit-sha"], template[0].labels["managed-by"],
      template[0].labels["goog-terraform-provisioned"],
    ]
  }
  depends_on = [google_secret_manager_secret_iam_member.eval_provider, google_secret_manager_secret_iam_member.eval_allowlist]
}

resource "google_cloud_run_v2_service_iam_member" "eval_public" {
  count    = var.eval_enabled ? 1 : 0
  project  = var.project
  location = var.region
  name     = google_cloud_run_v2_service.eval_staging[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "eval_tasks_invoker" {
  count    = var.eval_enabled ? 1 : 0
  project  = var.project
  location = var.region
  name     = google_cloud_run_v2_service.eval_staging[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.eval_tasks_staging[0].email}"
}

output "eval_backend_url_staging" {
  value = var.eval_enabled ? local.eval_service_url : null
}
