# Terraform automation identities for this environment's project (staging or eval). PRs plan with terraform-plan@<project>
# (terraform.yml); deploy-<environment>.yml plans with it and applies as terraform-apply@<project> only from that workflow on
# refs/heads/main (after CI via workflow_run, or by dispatch), through the module's own `github-apply` pool (the deployer
# `github` pool above is untouched). Pipeline: docs/reference/infra-pipeline.md. Bootstrap needs a targeted apply first
# (module.terraform_ci), see that page.

module "terraform_ci" {
  source = "../modules/terraform-ci"

  project           = var.project
  project_number    = data.google_project.this.number
  github_repository = var.github_repository
  state_bucket      = "${var.project}-tfstate"
  deploy_workflow   = "deploy-${var.environment}.yml"
  deploy_events     = ["workflow_run", "workflow_dispatch"]

  depends_on = [google_project_service.api]
}

output "terraform_ci" {
  description = "Provider and service account names used by terraform.yml and deploy-<environment>.yml (derived there from <ENV>_WIF_PROVIDER; no repo variables needed)."
  value = {
    plan_wif_provider     = module.terraform_ci.plan_wif_provider
    plan_service_account  = module.terraform_ci.plan_service_account
    apply_wif_provider    = module.terraform_ci.apply_wif_provider
    apply_service_account = module.terraform_ci.apply_service_account
  }
}
