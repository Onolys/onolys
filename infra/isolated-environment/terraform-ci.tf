# Terraform automation identities for this environment's project (staging or eval). PRs and main pushes plan with
# terraform-plan@<project>; apply runs as terraform-apply@<project> only for refs/heads/main, inside the existing main-only
# `github` pool/provider above. Pipeline: docs/reference/infra-pipeline.md. Bootstrap needs a targeted apply first
# (module.terraform_ci), see that page.

module "terraform_ci" {
  source = "../modules/terraform-ci"

  project             = var.project
  project_number      = data.google_project.this.number
  github_repository   = var.github_repository
  state_bucket        = "${var.project}-tfstate"
  apply_principal_set = "principalSet://iam.googleapis.com/${local.wif_pool_root}/${google_iam_workload_identity_pool.github.workload_identity_pool_id}/attribute.ref/refs/heads/main"

  depends_on = [google_project_service.api]
}

output "terraform_ci" {
  description = "Repo variables for .github/workflows/terraform.yml (TF_<ENV>_*): plan provider + SA, apply SA (apply uses the deploy provider `wif_provider`)."
  value = {
    plan_wif_provider     = module.terraform_ci.plan_wif_provider
    plan_service_account  = module.terraform_ci.plan_service_account
    apply_wif_provider    = google_iam_workload_identity_pool_provider.github.name
    apply_service_account = module.terraform_ci.apply_service_account
  }
}
