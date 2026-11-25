data "google_project" "this" {
  project_id = var.project
}

locals {
  firestore_db_resource = "projects/${var.project}/databases/${var.database_id}"
}

# --- Firestore (native, location is permanent; PITR off, no backups: PRD R5/D7) ---
resource "google_firestore_database" "db" {
  project                           = var.project
  name                              = var.database_id
  location_id                       = var.region
  type                              = "FIRESTORE_NATIVE"
  point_in_time_recovery_enablement = "POINT_IN_TIME_RECOVERY_DISABLED"
  delete_protection_state           = var.delete_protection ? "DELETE_PROTECTION_ENABLED" : "DELETE_PROTECTION_DISABLED"
  deletion_policy                   = var.delete_protection ? "ABANDON" : "DELETE"
}

# --- Audio bucket (PRD R6) ---
resource "google_storage_bucket" "audio" {
  project                     = var.project
  name                        = "onolys-audio-${var.env}"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = false
  }

  soft_delete_policy {
    retention_duration_seconds = 0
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age            = 1
      matches_prefix = ["uploads/"]
    }
  }

  cors {
    origin          = var.cors_origins
    method          = ["PUT", "HEAD"]
    response_header = ["Content-Type", "x-goog-content-length-range"]
    max_age_seconds = 3600
  }
}

# --- Cloud Tasks queue (PRD R7) ---
resource "google_cloud_tasks_queue" "steps" {
  project  = var.project
  location = var.region
  name     = "steps-${var.env}"

  rate_limits {
    max_dispatches_per_second = 5
    max_concurrent_dispatches = var.worker_concurrency * var.worker_max_instances
  }

  retry_config {
    max_attempts = 2
    min_backoff  = "5s"
    max_backoff  = "30s"
  }
}

# --- Server sweep (M-1, M-2, M-3) ---
# Settles stale sessions, resumes stuck deletions and repairs leaked run slots without anyone
# reading the page. Same OIDC as Cloud Tasks (tasks-invoker SA, audience = worker URL); the SA
# already holds run.invoker on the worker. Idempotent and bounded: a missed or doubled tick is
# harmless. Needs cloudscheduler.googleapis.com (infra/main.tf).
resource "google_cloud_scheduler_job" "sweep" {
  project          = var.project
  region           = var.region
  name             = "sweep-${var.env}"
  description      = "Onolys server sweep: stale sessions, stuck deletes, leaked run slots"
  schedule         = "*/15 * * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${local.worker_url}/tasks/sweep"

    oidc_token {
      service_account_email = google_service_account.tasks_invoker.email
      audience              = local.worker_url
    }
  }

  depends_on = [google_cloud_run_v2_service_iam_member.worker_tasks_invoker]
}

# --- Service accounts (PRD R9) ---
resource "google_service_account" "api" {
  project      = var.project
  account_id   = "api-${var.env}"
  display_name = "Onolys api (${var.env})"
}

resource "google_service_account" "worker" {
  project      = var.project
  account_id   = "worker-${var.env}"
  display_name = "Onolys worker (${var.env})"
}

resource "google_service_account" "tasks_invoker" {
  project      = var.project
  account_id   = "tasks-invoker-${var.env}"
  display_name = "Onolys Cloud Tasks invoker (${var.env})"
}

locals {
  runtime_sas = {
    api    = google_service_account.api.email
    worker = google_service_account.worker.email
  }
}

# datastore.user limited to this env's database by IAM condition on the resource name.
resource "google_project_iam_member" "datastore_user" {
  for_each = local.runtime_sas
  project  = var.project
  role     = "roles/datastore.user"
  member   = "serviceAccount:${each.value}"

  condition {
    title       = "firestore-${var.env}-only"
    description = "Only the ${var.database_id} database"
    expression  = "resource.name == \"${local.firestore_db_resource}\""
  }

  depends_on = [google_firestore_database.db]
}

resource "google_storage_bucket_iam_member" "object_admin" {
  for_each = local.runtime_sas
  bucket   = google_storage_bucket.audio.name
  role     = "roles/storage.objectAdmin"
  member   = "serviceAccount:${each.value}"
}

resource "google_cloud_tasks_queue_iam_member" "enqueuer" {
  for_each = local.runtime_sas
  project  = var.project
  location = var.region
  name     = google_cloud_tasks_queue.steps.name
  role     = "roles/cloudtasks.enqueuer"
  member   = "serviceAccount:${each.value}"
}

resource "google_service_account_iam_member" "tasks_invoker_user" {
  for_each           = local.runtime_sas
  service_account_id = google_service_account.tasks_invoker.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${each.value}"
}

# api signs V4 URLs as itself.
resource "google_service_account_iam_member" "api_self_token_creator" {
  service_account_id = google_service_account.api.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.api.email}"
}

# api generates verify/reset links (SP07). Start broad, narrow after smoke (PRD 07 Open Questions).
# Gated with the Resend wiring so an environment without email gets no extra IAM.
resource "google_project_iam_member" "api_firebaseauth_admin" {
  count   = var.resend_secret_wired ? 1 : 0
  project = var.project
  role    = "roles/firebaseauth.admin"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# The worker only generates password-reset action links (accounts:sendOobCode);
# it does not need Firebase user/config management or service-account signing.
resource "google_project_iam_custom_role" "worker_auth_email" {
  count       = var.resend_secret_wired ? 1 : 0
  project     = var.project
  role_id     = "workerAuthEmail_${var.env}"
  title       = "Worker auth email links (${var.env})"
  description = "Generate Firebase password-reset action links for the email worker."
  permissions = ["firebaseauth.users.sendEmail"]
}

resource "google_project_iam_member" "worker_auth_email" {
  count   = var.resend_secret_wired ? 1 : 0
  project = var.project
  role    = google_project_iam_custom_role.worker_auth_email[0].name
  member  = "serviceAccount:${google_service_account.worker.email}"
}

# Auth-email rate counters (api/src/onolys_api/email/rate.py) expire via Firestore TTL on `expires_at`.
resource "google_firestore_field" "email_rate_ttl" {
  project    = var.project
  database   = google_firestore_database.db.name
  collection = "email_rate"
  field      = "expires_at"

  ttl_config {}
}

# Status stubs of discarded uploads (api/src/onolys_api/jobs/validate.py, upload_failed) expire
# 7 days after the failure via Firestore TTL on `expire_at`; other status docs never set it.
resource "google_firestore_field" "session_status_ttl" {
  project    = var.project
  database   = google_firestore_database.db.name
  collection = "session_status"
  field      = "expire_at"

  ttl_config {}
}

resource "google_project_iam_member" "worker_speech_client" {
  project = var.project
  role    = "roles/speech.client"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

# Eval backend starts and polls transcription before it schedules coding runs.
# Public staging/prod APIs continue to delegate Speech calls to their workers.
resource "google_project_iam_member" "eval_backend_speech_client" {
  count   = var.eval_backend_enabled && var.env == "eval" ? 1 : 0
  project = var.project
  role    = "roles/speech.client"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# Speech-to-Text service agent reads audio from the bucket (PRD R9, RESOLVED yes).
resource "google_project_service_identity" "speech" {
  provider = google-beta
  project  = var.project
  service  = "speech.googleapis.com"
}

resource "google_storage_bucket_iam_member" "stt_agent_viewer" {
  bucket = google_storage_bucket.audio.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_project_service_identity.speech.email}"
}
