# Terraform automation identities for this environment's project (staging or eval). PRs and main pushes plan with
# terraform-plan@<project>; apply runs as terraform-apply@<project> only from the terraform.yml workflow on refs/heads/main, through the module's own
# `github-apply` pool (the deployer `github` pool above is untouched). Pipeline: docs/reference/infra-pipeline.md. Bootstrap needs a targeted apply first
# (module.terraform_ci), see that page.

module "terraform_ci" {
  source = "../modules/terraform-ci"

  project           = var.project
  project_number    = data.google_project.this.number
  github_repository = var.github_repository
  state_bucket      = "${var.project}-tfstate"

  depends_on = [google_project_service.api]
}

output "terraform_ci" {
  description = "Provider and service account names used by .github/workflows/terraform.yml (derived there from <ENV>_WIF_PROVIDER; no repo variables needed)."
  value = {
    plan_wif_provider     = module.terraform_ci.plan_wif_provider
    plan_service_account  = module.terraform_ci.plan_service_account
    apply_wif_provider    = module.terraform_ci.apply_wif_provider
    apply_service_account = module.terraform_ci.apply_service_account
  }
}
