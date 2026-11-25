# Owner notification channel (R15/R16): needs a one-time verification click in the owner's mailbox.
resource "google_monitoring_notification_channel" "owner_email" {
  project      = var.project
  display_name = "Onolys owner email"
  type         = "email"

  labels = {
    email_address = var.alert_email
  }

  depends_on = [google_project_service.api]
}

# Budget (R15) is no longer Terraform-managed: the owner sets limits in the consoles.
# The existing budget is forgotten from state, not destroyed, so its alerts keep working.
removed {
  from = google_billing_budget.monthly

  lifecycle {
    destroy = false
  }
}
