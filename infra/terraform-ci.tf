# Terraform automation identities for the legacy root (project `onolys` = PROD). PRs plan with terraform-plan@onolys;
# merges to main plan with it, and apply runs as terraform-apply@onolys only from the terraform.yml workflow on main in the
# GitHub Environment `terraform-prod` (required reviewers), through the module's own `github-apply` pool. Pipeline: docs/reference/infra-pipeline.md. Bootstrap needs a targeted apply
# first (module.terraform_ci), see that page.

module "terraform_ci" {
  source = "./modules/terraform-ci"

  project           = var.project
  project_number    = "1054076260967" # onolys (prod); a root-level google_project data source is deliberately not used here
  github_repository = var.github_repository
  state_bucket      = "onolys-tfstate"
  # Apply additionally requires the dedicated GitHub Environment `terraform-prod` (required reviewers, main only), enforced in the
  # apply provider condition. Owner step: docs/reference/infra-pipeline.md.
  apply_required_environment = "terraform-prod"

  depends_on = [google_project_service.api]
}

output "terraform_ci" {
  description = "Provider and service account names used by .github/workflows/terraform.yml (derived there from WIF_PROVIDER; no repo variables needed)."
  value = {
    plan_wif_provider     = module.terraform_ci.plan_wif_provider
    plan_service_account  = module.terraform_ci.plan_service_account
    apply_wif_provider    = module.terraform_ci.apply_wif_provider
    apply_service_account = module.terraform_ci.apply_service_account
  }
}
