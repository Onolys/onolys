# Terraform automation identities for the legacy root (project `onolys` = PROD). PRs plan with terraform-plan@onolys;
# merges to main plan with it, and apply runs as terraform-apply@onolys only from a job in the GitHub `production`
# environment (required reviewers). The apply identity reuses the `github` pool/provider above (repository-pinned) and the
# same environment selector as deployer-prod. Pipeline: docs/reference/infra-pipeline.md. Bootstrap needs a targeted apply
# first (module.terraform_ci), see that page.

module "terraform_ci" {
  source = "./modules/terraform-ci"

  project             = var.project
  project_number      = "1054076260967" # onolys (prod); a root-level google_project data source is deliberately not used here
  github_repository   = var.github_repository
  state_bucket        = "onolys-tfstate"
  apply_principal_set = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.environment/production"

  depends_on = [google_project_service.api]
}

output "terraform_ci" {
  description = "Repo variables for .github/workflows/terraform.yml (TF_PROD_*): plan provider + SA, apply SA (apply uses the deploy provider `wif_provider`)."
  value = {
    plan_wif_provider     = module.terraform_ci.plan_wif_provider
    plan_service_account  = module.terraform_ci.plan_service_account
    apply_wif_provider    = google_iam_workload_identity_pool_provider.github.name
    apply_service_account = module.terraform_ci.apply_service_account
  }
}
