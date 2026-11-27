# Terraform automation identities for the legacy root (project `onolys` = PROD). PRs plan with terraform-plan@onolys
# (terraform.yml). deploy-prod.yml plans with it at the commit being released, and applies as terraform-apply@onolys only from
# deploy-prod.yml (dispatch on main, or a pushed v* release tag) in the GitHub Environment `production` (required reviewer, the
# same approval that releases the app), through the module's own `github-apply` pool. Pipeline: docs/reference/infra-pipeline.md.
# Bootstrap needs a targeted apply first (module.terraform_ci), see that page.

module "terraform_ci" {
  source = "./modules/terraform-ci"

  project           = var.project
  project_number    = "1054076260967" # onolys (prod); a root-level google_project data source is deliberately not used here
  github_repository = var.github_repository
  state_bucket      = "onolys-tfstate"
  deploy_workflow   = "deploy-prod.yml"
  deploy_events     = ["push", "workflow_dispatch"]
  # deploy-prod.yml also runs on pushed release tags v* (the `production` environment admits main and v* tags).
  apply_tag_prefix = "refs/tags/v"
  # Apply additionally requires the GitHub Environment `production` (required reviewer), enforced in the apply provider condition.
  apply_required_environment = "production"

  depends_on = [google_project_service.api]
}

output "terraform_ci" {
  description = "Provider and service account names used by terraform.yml and deploy-prod.yml (derived there from WIF_PROVIDER; no repo variables needed)."
  value = {
    plan_wif_provider     = module.terraform_ci.plan_wif_provider
    plan_service_account  = module.terraform_ci.plan_service_account
    apply_wif_provider    = module.terraform_ci.apply_wif_provider
    apply_service_account = module.terraform_ci.apply_service_account
  }
}
