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
