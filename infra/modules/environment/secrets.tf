# Secret shells only; values are written by infra/scripts/seed-secrets.py (PRD D9) so they never enter state.
# Provider-key shells (llm_secrets/stt_secrets) are per environment: `<base>-<env>` (owner decision 2026-11-20).

resource "google_secret_manager_secret" "uid_hmac" {
  project   = var.project
  secret_id = "uid-hmac-key-${var.env}"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "admin_allowed_emails" {
  count     = var.admin_enabled ? 1 : 0
  project   = var.project
  secret_id = "admin-allowed-emails-${var.env}"

  replication {
    auto {}
  }
}

locals {
  # Keys are the env-var names (known at plan time); values the BASE secret ids (env suffix added below).
  worker_provider_secrets = merge(var.llm_secrets, var.stt_secrets)
}

resource "google_secret_manager_secret" "provider" {
  for_each  = local.worker_provider_secrets
  project   = var.project
  secret_id = "${each.value}-${var.env}"

  replication {
    auto {}
  }
}

# Resend API key shell (SP07 auth emails). The value is seeded by the owner (infra/scripts/seed-secrets.py or console).
resource "google_secret_manager_secret" "resend" {
  project   = var.project
  secret_id = "resend-api-key-${var.env}"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "resend_api" {
  project   = var.project
  secret_id = google_secret_manager_secret.resend.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

# The reset-email worker needs only this environment's Resend key, after activation.
resource "google_secret_manager_secret_iam_member" "resend_worker" {
  count     = var.resend_secret_wired ? 1 : 0
  project   = var.project
  secret_id = google_secret_manager_secret.resend.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_secret_manager_secret_iam_member" "hmac" {
  for_each  = local.runtime_sas
  project   = var.project
  secret_id = google_secret_manager_secret.uid_hmac.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${each.value}"
}

resource "google_secret_manager_secret_iam_member" "worker_provider" {
  for_each  = local.worker_provider_secrets
  project   = var.project
  secret_id = google_secret_manager_secret.provider[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.worker.email}"
}

# --- admin-backend (SP07, behind admin_enabled) ---
resource "google_service_account" "admin_backend" {
  count        = var.admin_enabled ? 1 : 0
  project      = var.project
  account_id   = "admin-backend-${var.env}"
  display_name = "Onolys admin-backend (${var.env})"
}

resource "google_secret_manager_secret_iam_member" "admin_emails" {
  count     = var.admin_enabled ? 1 : 0
  project   = var.project
  secret_id = google_secret_manager_secret.admin_allowed_emails[0].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.admin_backend[0].email}"
}
