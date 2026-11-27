output "plan_wif_provider" {
  description = "workload_identity_provider for the plan identity (the workflow derives it from the existing *WIF_PROVIDER variable)."
  value       = google_iam_workload_identity_pool_provider.plan.name
}

output "plan_service_account" {
  description = "service_account for plan jobs (the workflow derives it: terraform-plan@<project>)."
  value       = google_service_account.plan.email
}

output "apply_wif_provider" {
  description = "workload_identity_provider for the apply identity (the workflow derives it from the existing *WIF_PROVIDER variable)."
  value       = google_iam_workload_identity_pool_provider.apply.name
}

output "apply_service_account" {
  description = "service_account for apply jobs (the workflow derives it: terraform-apply@<project>)."
  value       = google_service_account.apply.email
}

output "bindings" {
  description = "Resolved impersonation members and roles (asserted by tests)."
  value = {
    apply_member     = google_service_account_iam_member.apply_wif.member
    apply_condition  = google_iam_workload_identity_pool_provider.apply.attribute_condition
    plan_condition   = google_iam_workload_identity_pool_provider.plan.attribute_condition
    plan_member      = google_service_account_iam_member.plan_wif.member
    plan_roles       = sort(setunion(var.plan_roles, var.plan_extra_roles))
    apply_roles      = sort(var.apply_roles)
    state_bucket     = google_storage_bucket_iam_member.apply_state.bucket
    plan_upload_role = google_storage_bucket_iam_member.plan_upload.role
  }
}
