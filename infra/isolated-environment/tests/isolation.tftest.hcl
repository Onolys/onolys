# Offline plans only: mocked provider responses never contact GCP or a backend.
mock_provider "google" {}
mock_provider "google-beta" {}

override_data {
  target = module.environment.data.google_project.this
  values = { number = "904020682480" }
}

variables {
  environment     = "staging"
  project         = "onolys-staging"
  hosting_site_id = "onolys-staging-app"
}

run "staging_project_isolation" {
  command = plan
  assert {
    condition     = output.project == "onolys-staging" && output.auth_project == "onolys-staging"
    error_message = "Staging runtime and default identity must use the staging project."
  }
  assert {
    condition     = output.audio_bucket == "onolys-staging-audio" && output.database_id == "staging"
    error_message = "Storage/database must be owned by staging with a unique bucket name."
  }
  assert {
    condition     = output.api_service_name == "onolys-api-staging" && output.voice_service_name == "onolys-voice-staging" && output.eval_backend_service_name == null
    error_message = "Staging keeps the production-shaped API/worker/voice service topology."
  }
  assert {
    condition     = length(google_artifact_registry_repository_iam_member.reader) == 0
    error_message = "External image readers must be explicitly opted into."
  }
}

run "eval_project_with_existing_identity" {
  command = plan
  variables {
    environment     = "eval"
    project         = "onolys-eval"
    hosting_site_id = "onolys-eval-app"
  }
  assert {
    condition     = output.project == "onolys-eval" && output.auth_project == "onolys"
    error_message = "Eval billing/runtime must be separate from its existing identity issuer."
  }
  assert {
    condition     = output.api_service_name == null && output.voice_service_name == null && output.eval_backend_service_name == "onolys-eval-backend-eval"
    error_message = "Eval must create only its feature-scoped backend and worker."
  }
  assert {
    condition     = output.datasets_bucket == "onolys-eval-datasets"
    error_message = "Default eval datasets must use a newly owned bucket, not old live data."
  }
}

run "external_datasets_are_reference_only" {
  command = plan
  variables {
    environment            = "eval"
    project                = "onolys-eval"
    hosting_site_id        = "onolys-eval-app"
    datasets_source_bucket = "onolys-eval-data-staging"
  }
  assert {
    condition     = length(google_storage_bucket.datasets) == 0 && length(google_storage_bucket_iam_member.datasets_reader) == 0 && output.datasets_bucket == "onolys-eval-data-staging"
    error_message = "External dataset ownership/IAM must stay outside this state."
  }
}

run "promotion_readers_are_explicit" {
  command = plan
  variables {
    cloud_run_reader_members = ["serviceAccount:deployer-staging@onolys.iam.gserviceaccount.com"]
    artifact_registry_reader_members = [
      "serviceAccount:deployer-staging@onolys.iam.gserviceaccount.com",
      "serviceAccount:deployer-prod@onolys.iam.gserviceaccount.com",
      "serviceAccount:service-1054076260967@serverless-robot-prod.iam.gserviceaccount.com",
    ]
  }
  assert {
    condition     = length(google_cloud_run_v2_service_iam_member.provenance_reader) == 3 && length(google_artifact_registry_repository_iam_member.reader) == 3
    error_message = "Resolver reads must be explicitly scoped to the three stage services and this image repository."
  }
}

run "reject_production_project" {
  command = plan
  variables {
    project = "onolys"
  }
  expect_failures = [var.project]
}

run "never_manage_external_identity" {
  command = plan
  variables {
    environment     = "eval"
    project         = "onolys-eval"
    manage_identity = true
  }
  expect_failures = [var.manage_identity]
}

run "previews_disabled_by_default" {
  command = plan
  assert {
    condition     = length(google_service_account.pr_preview) == 0 && length(google_iam_workload_identity_pool_provider.github_pr) == 0 && output.pr_preview_service_account == null && output.pr_preview_wif_provider == null
    error_message = "Preview identity must be opt-in."
  }
}

run "staging_previews_limited_identity" {
  command = plan
  variables {
    enable_pr_previews = true
  }
  assert {
    condition     = length(google_service_account.pr_preview) == 1 && google_service_account.pr_preview[0].account_id == "pr-preview-staging"
    error_message = "Enabled staging creates the dedicated preview service account."
  }
  assert {
    condition     = google_iam_workload_identity_pool_provider.github_pr[0].attribute_condition == "assertion.repository == 'Onolys/onolys' && assertion.event_name == 'pull_request'"
    error_message = "Preview provider must admit only same-repo pull_request events."
  }
  assert {
    condition     = google_iam_workload_identity_pool_provider.github.attribute_condition == "assertion.repository=='Onolys/onolys' && assertion.ref=='refs/heads/main'"
    error_message = "The deployer provider must stay main-only."
  }
  assert {
    condition     = google_cloud_run_v2_service_iam_member.pr_preview_api[0].name == "onolys-api-staging" && google_cloud_run_v2_service_iam_member.pr_preview_api[0].role == "roles/run.developer" && google_service_account_iam_member.pr_preview_runtime[0].role == "roles/iam.serviceAccountUser"
    error_message = "Run developer only on the api service; actAs only the api runtime SA."
  }
  assert {
    condition     = toset(keys(google_project_iam_member.pr_preview)) == toset(["roles/serviceusage.serviceUsageConsumer", "roles/firebasehosting.admin"])
    error_message = "Project-level preview roles are limited to Hosting and API usage."
  }
}

run "eval_never_gets_previews" {
  command = plan
  variables {
    environment        = "eval"
    project            = "onolys-eval"
    hosting_site_id    = "onolys-eval-app"
    enable_pr_previews = true
  }
  assert {
    condition     = length(google_service_account.pr_preview) == 0 && length(google_iam_workload_identity_pool_provider.github_pr) == 0 && length(google_project_iam_member.pr_preview) == 0 && output.pr_preview_wif_provider == null
    error_message = "Eval must not get a preview identity."
  }
}
