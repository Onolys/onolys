# Offline tests of infra/modules/terraform-ci itself (prod and eval shapes the isolated root cannot express, and the
# plan_extra_* deny validations). Mocked provider; never contacts GCP. docs/reference/infra-pipeline.md.
mock_provider "google" {}

run "prod_apply_admits_deploy_prod_on_main_or_release_tags_in_production_only" {
  command = plan
  module {
    source = "../modules/terraform-ci"
  }
  variables {
    project                    = "onolys"
    project_number             = "1054076260967"
    state_bucket               = "onolys-tfstate"
    deploy_workflow            = "deploy-prod.yml"
    deploy_events              = ["push", "workflow_dispatch"]
    apply_tag_prefix           = "refs/tags/v"
    apply_required_environment = "production"
  }
  assert {
    condition     = output.bindings.apply_condition == "assertion.repository=='Onolys/onolys' && (assertion.ref=='refs/heads/main' || assertion.ref.startsWith('refs/tags/v')) && assertion.event_name in ['push','workflow_dispatch'] && (assertion.job_workflow_ref=='Onolys/onolys/.github/workflows/deploy-prod.yml@refs/heads/main' || assertion.job_workflow_ref.startsWith('Onolys/onolys/.github/workflows/deploy-prod.yml@refs/tags/v')) && assertion.environment=='production'"
    error_message = "Prod apply: deploy-prod.yml only, main dispatch or v* tag push, and only inside the production environment."
  }
  assert {
    condition     = output.bindings.apply_member == "principalSet://iam.googleapis.com/projects/1054076260967/locations/global/workloadIdentityPools/github-apply/attribute.repository/Onolys/onolys"
    error_message = "With release tags the ref varies, so the dedicated pool binds the repository and the provider condition is the gate."
  }
  assert {
    condition     = output.bindings.plan_condition == "assertion.repository=='Onolys/onolys' && ((assertion.event_name in ['pull_request','workflow_dispatch'] && assertion.job_workflow_ref.startsWith('Onolys/onolys/.github/workflows/terraform.yml@')) || (assertion.event_name in ['push','workflow_dispatch'] && assertion.job_workflow_ref.startsWith('Onolys/onolys/.github/workflows/deploy-prod.yml@')))"
    error_message = "Prod plan: PR plans from terraform.yml and the deploy-prod.yml pipeline only."
  }
}

run "eval_apply_admits_only_deploy_eval_on_main" {
  command = plan
  module {
    source = "../modules/terraform-ci"
  }
  variables {
    project         = "onolys-eval"
    project_number  = "976672392004"
    state_bucket    = "onolys-eval-tfstate"
    deploy_workflow = "deploy-eval.yml"
    deploy_events   = ["workflow_run", "workflow_dispatch"]
  }
  assert {
    condition     = output.bindings.apply_condition == "assertion.repository=='Onolys/onolys' && assertion.ref=='refs/heads/main' && assertion.event_name in ['workflow_run','workflow_dispatch'] && assertion.job_workflow_ref=='Onolys/onolys/.github/workflows/deploy-eval.yml@refs/heads/main'"
    error_message = "Eval apply: deploy-eval.yml on main only (after CI or by dispatch)."
  }
  assert {
    condition     = output.bindings.apply_member == "principalSet://iam.googleapis.com/projects/976672392004/locations/global/workloadIdentityPools/github-apply/attribute.workflow_ref/Onolys/onolys/.github/workflows/deploy-eval.yml@refs/heads/main"
    error_message = "Without release tags the binding is the exact workflow ref."
  }
}

run "data_read_permissions_are_rejected_as_plan_extras" {
  command = plan
  module {
    source = "../modules/terraform-ci"
  }
  variables {
    project                = "onolys-eval"
    project_number         = "976672392004"
    state_bucket           = "onolys-eval-tfstate"
    deploy_workflow        = "deploy-eval.yml"
    deploy_events          = ["workflow_run", "workflow_dispatch"]
    plan_extra_permissions = ["datastore.entities.list", "storage.objects.get", "firebaseauth.users.get", "cloudtasks.tasks.list", "logging.logEntries.list"]
    plan_extra_roles       = ["roles/datastore.viewer"]
  }
  expect_failures = [var.plan_extra_permissions, var.plan_extra_roles]
}

run "non_viewer_roles_are_rejected_as_plan_extras" {
  command = plan
  module {
    source = "../modules/terraform-ci"
  }
  variables {
    project          = "onolys-eval"
    project_number   = "976672392004"
    state_bucket     = "onolys-eval-tfstate"
    deploy_workflow  = "deploy-eval.yml"
    deploy_events    = ["workflow_run", "workflow_dispatch"]
    plan_extra_roles = ["roles/viewer"]
  }
  expect_failures = [var.plan_extra_roles]
}

run "metadata_extras_are_accepted" {
  command = plan
  module {
    source = "../modules/terraform-ci"
  }
  variables {
    project                = "onolys-eval"
    project_number         = "976672392004"
    state_bucket           = "onolys-eval-tfstate"
    deploy_workflow        = "deploy-eval.yml"
    deploy_events          = ["workflow_run", "workflow_dispatch"]
    plan_extra_permissions = ["compute.networks.get"]
    plan_extra_roles       = ["roles/compute.viewer"]
  }
  assert {
    condition     = contains(output.bindings.plan_roles, "roles/compute.viewer")
    error_message = "Metadata-only extras stay possible."
  }
}

run "unknown_deploy_workflow_or_event_is_rejected" {
  command = plan
  module {
    source = "../modules/terraform-ci"
  }
  variables {
    project         = "onolys-eval"
    project_number  = "976672392004"
    state_bucket    = "onolys-eval-tfstate"
    deploy_workflow = "terraform.yml"
    deploy_events   = ["pull_request"]
  }
  expect_failures = [var.deploy_workflow, var.deploy_events]
}
