output "project" {
  value = var.project
}

output "region" {
  value = var.region
}

output "auth_project" {
  value = local.auth_project
}

output "wif_provider" {
  value = google_iam_workload_identity_pool_provider.github.name
}

output "pr_preview_wif_provider" {
  description = "Value for repo var STAGING_PREVIEW_WIF_PROVIDER; null unless enable_pr_previews on staging."
  value       = local.preview_enabled ? google_iam_workload_identity_pool_provider.github_pr[0].name : null
}

output "pr_preview_service_account" {
  description = "Value for repo var STAGING_PREVIEW_SA; null unless enable_pr_previews on staging."
  value       = local.preview_enabled ? google_service_account.pr_preview[0].email : null
}

output "deployer_email" {
  value = google_service_account.deployer.email
}

output "hosting_site_id" {
  value = google_firebase_hosting_site.this.site_id
}

output "artifact_registry_repository" {
  value = google_artifact_registry_repository.onolys.id
}

output "image_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project}/onolys"
}

output "audio_bucket" {
  value = module.environment.bucket_name
}

output "datasets_bucket" {
  value = local.datasets_bucket
}

output "database_id" {
  value = module.environment.database_id
}

output "api_service_name" {
  value = module.environment.api_service_name
}

output "worker_service_name" {
  value = module.environment.worker_service_name
}

output "voice_service_name" {
  value = module.environment.voice_service_name
}

output "eval_backend_service_name" {
  value = module.environment.eval_backend_service_name
}

output "api_url" {
  value = module.environment.api_url
}

output "worker_url" {
  value = module.environment.worker_url
}

output "voice_url" {
  value = module.environment.voice_url
}

output "eval_backend_url" {
  value = module.environment.eval_backend_url
}

output "firebase_web_config" {
  description = "Public local-auth web config, or null unless manage_identity."
  value = var.manage_identity ? {
    project_id          = var.project
    app_id              = google_firebase_web_app.this[0].app_id
    api_key             = data.google_firebase_web_app_config.this[0].api_key
    auth_domain         = data.google_firebase_web_app_config.this[0].auth_domain
    storage_bucket      = data.google_firebase_web_app_config.this[0].storage_bucket
    messaging_sender_id = data.google_firebase_web_app_config.this[0].messaging_sender_id
  } : null
}

output "web_env" {
  description = "Public SDK settings for isolated staging/eval builds (GitHub vars STAGING_ISOLATED_VITE_* / EVAL_VITE_*); null unless manage_identity."
  value = var.manage_identity ? {
    VITE_FIREBASE_API_KEY             = data.google_firebase_web_app_config.this[0].api_key
    VITE_FIREBASE_AUTH_DOMAIN         = data.google_firebase_web_app_config.this[0].auth_domain
    VITE_FIREBASE_PROJECT_ID          = var.project
    VITE_FIREBASE_APP_ID              = google_firebase_web_app.this[0].app_id
    VITE_FIREBASE_STORAGE_BUCKET      = data.google_firebase_web_app_config.this[0].storage_bucket
    VITE_FIREBASE_MESSAGING_SENDER_ID = data.google_firebase_web_app_config.this[0].messaging_sender_id
    VITE_FIRESTORE_DATABASE           = module.environment.database_id
  } : null
}

output "required_dns_updates" {
  description = "Eval only: DNS records for eval.onolys.com to set at the registrar (type, host, value); empty elsewhere or once Hosting needs nothing more."
  value = flatten([
    for d in google_firebase_hosting_custom_domain.eval : concat(
      flatten([
        for u in d.required_dns_updates : [
          for dd in u.desired : [
            for r in dd.records : {
              domain = d.custom_domain
              type   = r.type
              host   = r.domain_name
              value  = r.rdata
              action = r.required_action
            }
          ]
        ]
      ]),
      flatten([
        for c in d.cert : [
          for v in c.verification : [
            for dn in v.dns : [
              for dd in dn.desired : [
                for r in dd.records : {
                  domain = d.custom_domain
                  type   = r.type
                  host   = r.domain_name
                  value  = r.rdata
                  action = r.required_action
                }
              ]
            ]
          ]
        ]
      ]),
    )
  ])
}

output "custom_domain_status" {
  description = "Eval only: Hosting verification state of eval.onolys.com (expect ownership OWNERSHIP_ACTIVE, host HOST_ACTIVE, cert CERT_ACTIVE after DNS)."
  value = {
    for d in google_firebase_hosting_custom_domain.eval : d.custom_domain => {
      ownership = d.ownership_state
      host      = d.host_state
      cert      = try(d.cert[0].state, null)
    }
  }
}

output "eval_cors_origins" {
  description = "Browser origins the eval backend accepts (empty outside eval): the Hosting site, the eval custom domain and local dev."
  value       = local.eval_cors_origins
}
