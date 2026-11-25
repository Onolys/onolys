# Optional local validation identity; external issuers (notably onolys for eval)
# are only referenced in AUTH_PROJECT and never changed by this root.
resource "google_identity_platform_config" "this" {
  count   = var.manage_identity ? 1 : 0
  project = var.project
  authorized_domains = [
    "localhost", "${var.project}.firebaseapp.com", "${var.project}.web.app",
    "${var.hosting_site_id}.web.app",
  ]
  sign_in {
    allow_duplicate_emails = false
    email {
      enabled           = true
      password_required = true
    }
  }
  depends_on = [google_firebase_project.this]
}

resource "google_firebase_web_app" "this" {
  count           = var.manage_identity ? 1 : 0
  provider        = google-beta
  project         = var.project
  display_name    = "onolys-${var.environment}"
  deletion_policy = "DELETE"
  depends_on      = [google_firebase_project.this]
}

data "google_firebase_web_app_config" "this" {
  count      = var.manage_identity ? 1 : 0
  provider   = google-beta
  project    = var.project
  web_app_id = google_firebase_web_app.this[0].app_id
}
