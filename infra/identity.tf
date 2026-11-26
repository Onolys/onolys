# Identity Platform (PRD R4): one user pool for both envs; data isolation is by Firestore DB/bucket.
# Google sign-in is an owner console step (OAuth client cannot be created by API). The email action URL
# (verify/reset links -> https://app.onolys.com/auth/action, our in-app handler) is set by identity-config.py;
# email template wording is still edited in the console.

locals {
  # Firebase project defaults (kept: the project was created with them) + PRD R4 hosts.
  authorized_domains = distinct(concat(
    [
      "localhost",
      "${var.project}.firebaseapp.com",
      "${var.project}.web.app",
      "app.onolys.com",
      "${var.app_site_id}.web.app",
      "${var.app_staging_site_id}.web.app",
    ],
    ["eval.onolys.com", "onolys-eval-staging.web.app"],
  ))
}

resource "google_identity_platform_config" "default" {
  project            = var.project
  authorized_domains = local.authorized_domains

  # Domains are only ever added after creation (scripts/identity-config.py, incl. preview channel
  # hosts the SP00 workflow adds); Terraform must not prune them.
  lifecycle {
    ignore_changes = [authorized_domains]
  }

  sign_in {
    allow_duplicate_emails = false

    email {
      enabled           = true
      password_required = true
    }

    phone_number {
      enabled = false
    }
  }

  multi_tenant {
    allow_tenants = false
  }

  client {
    permissions {
      disabled_user_signup   = false # open sign-up
      disabled_user_deletion = false
    }
  }

  mfa {
    state = "DISABLED"
  }

  depends_on = [google_project_service.api]
}

# The provider has no password policy / email-enumeration-protection / email action URL fields: REST-patch them.
resource "terraform_data" "identity_policy" {
  triggers_replace = [
    filesha256("${path.module}/scripts/identity-config.py"),
    google_identity_platform_config.default.id,
    join(",", local.authorized_domains),
  ]

  provisioner "local-exec" {
    command = "python3 ${path.module}/scripts/identity-config.py ${join(" ", [for d in local.authorized_domains : "--add-domain ${d}"])}"
  }
}

# Firebase web app for the prod host.
resource "google_firebase_web_app" "app" {
  provider        = google-beta
  project         = var.project
  display_name    = "onolys-app"
  deletion_policy = "DELETE"

  depends_on = [google_project_service.api]
}

data "google_firebase_web_app_config" "app" {
  provider   = google-beta
  project    = var.project
  web_app_id = google_firebase_web_app.app.app_id
}

# Public web config per build (Firebase web apiKey is a public identifier; access is enforced by Identity Platform + rules).
output "web_env_prod" {
  description = "VITE_* build vars for the prod web app (site onolys-app). Firestore DB is (default)."
  value = {
    VITE_FIREBASE_API_KEY             = data.google_firebase_web_app_config.app.api_key
    VITE_FIREBASE_AUTH_DOMAIN         = data.google_firebase_web_app_config.app.auth_domain
    VITE_FIREBASE_PROJECT_ID          = var.project
    VITE_FIREBASE_APP_ID              = google_firebase_web_app.app.app_id
    VITE_FIREBASE_STORAGE_BUCKET      = data.google_firebase_web_app_config.app.storage_bucket
    VITE_FIREBASE_MESSAGING_SENDER_ID = data.google_firebase_web_app_config.app.messaging_sender_id
    VITE_FIRESTORE_DATABASE           = "(default)"
    VITE_VOICE_URL                    = replace(module.prod.voice_url, "https://", "wss://")
  }
}

output "web_env_eval" {
  description = "VITE_* build vars for eval/web (docs only): prod Firebase web app values, auth domain eval.onolys.com."
  value = {
    VITE_FIREBASE_API_KEY             = data.google_firebase_web_app_config.app.api_key
    VITE_FIREBASE_AUTH_DOMAIN         = "eval.onolys.com"
    VITE_FIREBASE_PROJECT_ID          = var.project
    VITE_FIREBASE_APP_ID              = google_firebase_web_app.app.app_id
    VITE_FIREBASE_STORAGE_BUCKET      = data.google_firebase_web_app_config.app.storage_bucket
    VITE_FIREBASE_MESSAGING_SENDER_ID = data.google_firebase_web_app_config.app.messaging_sender_id
  }
}

output "voice_url_prod" {
  description = "Voice relay URL (prod); https, use wss:// from the browser."
  value       = module.prod.voice_url
}
