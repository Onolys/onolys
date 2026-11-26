output "plan_wif_provider" {
  description = "Repo variable value: workload_identity_provider for the plan identity."
  value       = google_iam_workload_identity_pool_provider.plan.name
}

output "plan_service_account" {
  description = "Repo variable value: service_account for plan jobs."
  value       = google_service_account.plan.email
}

output "apply_service_account" {
  description = "Repo variable value: service_account for apply jobs (provider is the root's existing deploy provider)."
  value       = google_service_account.apply.email
}

output "bindings" {
  description = "Resolved impersonation members and roles (asserted by tests)."
  value = {
    apply_member     = google_service_account_iam_member.apply_wif.member
    plan_member      = google_service_account_iam_member.plan_wif.member
    plan_roles       = sort(setunion(var.plan_roles, var.plan_extra_roles))
    apply_roles      = sort(var.apply_roles)
    state_bucket     = google_storage_bucket_iam_member.apply_state.bucket
    plan_upload_role = google_storage_bucket_iam_member.plan_upload.role
  }
}
