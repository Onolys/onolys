# Per-project identity (staging and eval each sign in through their own project; manage_identity = true).
# An external issuer is only referenced in AUTH_PROJECT and never changed by this root.
# Google sign-in (OAuth client) cannot be created by API: owner console step, see docs/implementation/isolated-environments.md.
locals {
  # Eval also serves its web app on the custom domain eval.onolys.com (see google_firebase_hosting_custom_domain.eval).
  authorized_domains = concat(
    ["localhost", "${var.project}.firebaseapp.com", "${var.project}.web.app", "${var.hosting_site_id}.web.app"],
    var.environment == "eval" ? [local.eval_custom_domain] : [],
  )
  eval_custom_domain = "eval.onolys.com"
}

resource "google_identity_platform_config" "this" {
  count              = var.manage_identity ? 1 : 0
  project            = var.project
  authorized_domains = local.authorized_domains
  sign_in {
    allow_duplicate_emails = false
    email {
      enabled           = true
      password_required = true
    }
    # Declared to match the API's defaults, otherwise every plan wants to remove them.
    phone_number {
      enabled = false
    }
  }
  multi_tenant {
    allow_tenants = false
  }
  # Eval has no self sign-up: accounts are created by the operator script (infra/scripts/create-test-user.py) through the
  # admin API, which is not subject to this switch. Staging keeps open sign-up.
  dynamic "client" {
    for_each = var.environment == "eval" ? [1] : []
    content {
      permissions {
        disabled_user_signup = true
      }
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

# eval.onolys.com (owner repoints DNS at the registrar from required_dns_updates after apply; do not block on it).
# A Firebase custom domain belongs to one site only: apply the legacy root (which no longer declares it) first.
resource "google_firebase_hosting_custom_domain" "eval" {
  count                 = var.environment == "eval" ? 1 : 0
  provider              = google-beta
  project               = var.project
  site_id               = google_firebase_hosting_site.this.site_id
  custom_domain         = local.eval_custom_domain
  wait_dns_verification = false
}
