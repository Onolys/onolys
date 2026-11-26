# Isolated staging and eval projects

The additive root at [`infra/isolated-environment/`](../../infra/isolated-environment/README.md) reuses the environment module with separate project billing and Terraform state. It does not migrate resources, data, users, secrets or live domains. Production continues to use the existing `infra/` root and state; do not clean-apply a production example or point the new root at its backend.

| Environment | GCP project ID | Project number | Terraform configuration/state |
|---|---|---|---|
| prod | `onolys` (display name `onolys-prod`) | `1054076260967` | Existing `infra/`, `gs://onolys-tfstate/infra` |
| staging | `onolys-staging` | `904020682480` | New common root, `gs://onolys-staging-tfstate/environment` |
| eval | `onolys-eval` | `976672392004` | New common root, `gs://onolys-eval-tfstate/environment` |

Project creation, billing linkage and the operator's permissions are prerequisites. Existing manually configured Cloud Billing budgets, caps and notifications remain owner-managed and unchanged; this foundation assigns no billing accounts and creates no budget or spend-control actions. The new root refuses production, enforces the project/environment pairing, and records a protected state identity: reusing one environment's initialized state for another requires destroying that protected identity and fails planning. Separate backend buckets and `TF_DATA_DIR` directories are still required; the protection complements operator review.

## Common template and differences

Staging and production use the same `modules/environment` implementation and API/worker/voice topology, with Firestore, audio storage, Tasks, Scheduler, per-service identities, secrets and IAM. Staging uses its own project, database `staging`, new smoke Hosting site `onolys-staging-app`, smaller service limits, staging routes and optionally its own Firebase users. Production retains its current project, `(default)` database, domains, state and operator settings. The new root does not change the legacy root or its defaults.

The legacy root no longer declares `module.staging` or `module.eval` (nor `eval.tf` or the old staging/eval hosting sites and deployer grants). Applying it destroys the old staging/eval resources in `onolys` (owner-approved, data included) and changes prod only by the pending items listed in the apply steps below; `deployer-staging`, its WIF binding and `serviceUsageConsumer` stay because deploy-prod `resolve` still impersonates it.

The eval Hosting site `onolys-eval-staging` and its custom domain `eval.onolys.com` are removed from the legacy root; the domain moves to the isolated eval root (see [Eval own sign-in and eval.onolys.com](#eval-own-sign-in-and-eval-onolyscom)).
Applying the legacy root therefore also deletes the `onolys-eval-staging` site in `onolys`.

Routine applies of every root run in CI, inside each environment's deploy pipeline once enabled ([infra pipeline](../reference/infra-pipeline.md), [ADR 0026](../decisions/0026-terraform-plan-apply-in-ci.md)); the manual steps below are bootstrap and break-glass only. The legacy destroy of the old staging/eval resources described here is complete (verified 2026-11-26: a read-only prod plan showed no change outside `module.terraform_ci`); confirm that again before the CI identities' first apply, otherwise the first CI prod apply would run it.

Owner steps for a manual legacy apply (do not run a plain `terraform apply` in `infra/`):

1. Empty the non-empty buckets first, they have `force_destroy=false`: `onolys-eval-data-staging` (datasets already copied to `gs://onolys-eval-datasets` and verified), `onolys-audio-staging`, `onolys-audio-eval`.

   ```
   gcloud storage rm --recursive --project=onolys 'gs://onolys-eval-data-staging/**' 'gs://onolys-audio-staging/**' 'gs://onolys-audio-eval/**'
   ```

   Do not touch `onolys-eval-datasets` or `onolys-eval-audio` (the new eval buckets in project `onolys-eval`).
2. The old eval Firestore database `projects/onolys/databases/eval` has delete protection, so Terraform only drops it from state (`deletion_policy` ABANDON). Disable delete protection and delete it manually:

   ```
   gcloud firestore databases update --project=onolys --database=eval --no-delete-protection
   gcloud firestore databases delete --project=onolys --database=eval
   ```

   Warning: project `onolys-eval` also has a database named `eval`; never run these without `--project=onolys`, and do not touch that one.
3. Apply with targeted addresses only (`-target=` for the reviewed destroy set). The legacy plan's former PROD drift is fixed in config (default `llm_secrets` now include `OPENAI_API_KEY`, matching live `openai-api-key-prod`; `GIT_SHA` and `LLM_*` are Terraform-owned from variables, so pass the live values, see `terraform.tfvars.example`). With the operator inputs set, the remaining prod changes are all intended and pending: Cloud Run env additions (`AI_*`, `APP_BASE_URL`, `EMAIL_FROM`, `PR_PREVIEW`, blank `LLM_*`, worker `OPENAI_API_KEY` mount), the `sweep-prod` scheduler job, two Firestore TTL fields, the Cloud Scheduler API, the Artifact Registry description, removal of the now-unused worker accessor grant on `resend-api-key-prod` (prod `resend_secret_wired = false`), and a replaced `terraform_data.identity_policy`. That replace re-runs `identity-config.py`, which now also REMOVES the explicit `retired_authorized_domains` list (`onolys-app-staging.web.app`, `admin.onolys.com`, `onolys-admin.web.app`, `onolys-admin-staging.web.app`); the eval hosts (`eval.onolys.com`, `onolys-eval-staging.web.app`, `onolys-eval-app.web.app`) are retired from prod and no longer added (eval signs in through its own project `onolys-eval`, see "Eval own sign-in and eval.onolys.com"). Firebase defaults and any unlisted domain (`onolys.com`, preview hosts) are untouched. Preview the PATCH first, read-only: `python3 infra/scripts/identity-config.py --dry-run --domains-only --add-domain ... --remove-domain ...`. Operator inputs: the durable, git-ignored tfvars live on the ops machine in `/root/.cache/onolys-terraform/{legacy,staging,eval}.tfvars` (legacy: `resend_secret_wired = { prod = false }`, `git_sha`, blank `llm_*`; staging: `git_sha` + `llm_*`; eval: `git_sha`, no `llm_*`). Always plan/apply with `-var-file` of the matching file, and refresh `git_sha` (and `llm_*` when changed) from the live services after every deploy, or the next plan shows drift and an apply would rewrite the env. After apply, expected plans: eval and legacy prod `No changes`; staging shows only the harmless api `template.revision`/container-name `-> null` after a CI-pinned deploy (see infra.md "Terraform drift"). Deploy prod (`deploy-prod`) with or right after the apply: the live prod image predates `POST /tasks/sweep`; its old `/tasks/{kind}` route rejects the sweep job's empty body, so the scheduler job gets 422s until then. The Cloud Scheduler API is enabled in the same apply, so the first create of the sweep job may fail while the API propagates; re-running apply fixes it. Full-plan check: `/root/.cache/onolys-terraform/legacy-drift-fix-plan.txt`.
4. Only after the apply is clearing `STAGING_GCP_PROJECT` meaningless as a rollback: the legacy staging target no longer exists.

Eval uses the same module with the public API and voice disabled, and enables the eval backend, worker and eval mode. Runtime config remains `ENV=staging`; Firestore database is `eval`. Its smoke site is `onolys-eval-app`. `auth_project` defaults to the runtime project for both environments: eval signs in through `onolys-eval`, never through prod `onolys`. The root never manages an external identity project (`manage_identity=true` requires `auth_project` = the runtime project); it creates email/password Identity Platform configuration and a Firebase web app in that project. OAuth-provider setup (Google sign-in) and email template policy remain separate reviewed owner operations.

The module's new `audio_bucket_name`, `auth_project` and `speech_object_prefix` inputs default to null, preserving legacy names, issuer and Speech access. New buckets default to `PROJECT-audio`. Eval grants its Speech service agent read access only under `eval-uploads/`; normal staging retains the existing module access. UID HMAC and provider keys remain environment-local secret references, with no values in Terraform. New provider-shell defaults include Gemini, Anthropic and OpenAI; mounting credentials does not select a provider.

Eval defaults to a new `onolys-eval-datasets` bucket with read-only access for its backend. It starts empty; dataset upload or copying is a separate validated operation. Alternatively set `datasets_source_bucket` to reference existing data. In that mode this root neither owns the source bucket nor changes its IAM; the source owner must separately grant the new eval API identity read access. No dataset objects or existing bucket policies are copied automatically.

## APIs and deploy identities

A successful reviewed apply enables required APIs through `google_project_service`; manual API enabling is not normally needed. Missing billing/operator permissions can prevent that apply and must be resolved before deployment.

| Capability | New staging | New eval | Existing prod |
|---|---|---|---|
| Cloud Run, Firestore, Storage, Tasks, Scheduler, Secrets, Artifact Registry, IAM/WIF, Firebase/Hosting/rules | Enabled by new root | Enabled by new root | Retains existing configuration |
| Gemini API (`generativelanguage.googleapis.com`) | Enabled by new root | Enabled by new root | This additive root makes no production changes; verify separately |
| Speech-to-Text (`speech.googleapis.com`) | Enabled by new root | Enabled by new root | Retains existing configuration |
| Vertex AI (`aiplatform.googleapis.com`) | Enabled for voice | Not enabled by this root | Existing voice uses it |
| Cloud Functions | Not used | Not used | Not used by this application |

Each project gets its own repository `onolys`, deployer service account and GitHub WIF provider. Trust requires repository `Onolys/onolys` and `refs/heads/main`; it grants no tag or PR-branch deployment access. The deployer has service-scoped Cloud Run revision rights and runtime actAs, its own repository writer, project-local Hosting/rules permissions, and index access conditioned on its database.

### PR previews (staging only)

Previews run in isolated staging when `STAGING_GCP_PROJECT` is set. Terraform input `enable_pr_previews` (true in the staging example; ignored for eval) adds service account `pr-preview-staging`, a separate WIF pool `github-pr` (not the deployer's pool `github`: a principalSet binding matches every provider of its pool, so sharing would let any same-repo PR impersonate `deployer-staging`) holding provider `github-pr` that admits only `Onolys/onolys` `pull_request` events, and these grants: `run.developer` on the api service only, `iam.serviceAccountUser` on the api runtime SA only, repository `artifactregistry.writer`, `firebasehosting.admin`, `serviceusage.serviceUsageConsumer` and the `firebase.projects.get` custom role. Nothing on worker, voice, Firestore or rules/indexes, and no secret grants to the preview identity itself; but the preview revision runs as the api runtime SA, so preview code can read the secrets that SA reads in staging (e.g. the Resend and uid-hmac secrets). The preview workflows hold no LLM keys. No `firebaseauth.admin`: firebase-tools may warn about channel domains in Firebase Auth, which is accepted (previews use email/password). Owner steps after the reviewed apply: set repo vars `STAGING_PREVIEW_WIF_PROVIDER` (output `pr_preview_wif_provider`, `projects/904020682480/locations/global/workloadIdentityPools/github-pr/providers/github-pr`) and `STAGING_PREVIEW_SA` (output `pr_preview_service_account`). Until set, previews fail fast with a clear message while `STAGING_GCP_PROJECT` is set.

Production promotion can retain its existing GitHub identity. The staging example explicitly opts the legacy staging resolver into service-scoped `roles/run.viewer` plus repository reader, and grants repository reader to the existing prod deployer and prod Cloud Run service agent. Those principals get no new staging deployment or actAs rights. The optional `cloud_run_reader_members` and `artifact_registry_reader_members` inputs default to empty; review example grants before applying. Production WIF and resources are unchanged.

## Initialize and import

Examples are versioned under `infra/isolated-environment/examples/`:

- `environment-staging.tfvars.example` and `backend-staging.hcl.example` target new staging.
- `environment-eval.tfvars.example` and `backend-eval.hcl.example` target new eval.
- `environment-prod.tfvars.example` and `backend-prod.hcl.example` are references to the existing legacy root/state only. They are not a fresh-production template or a migration command.

If state buckets do not exist, first use the separate `bootstrap/` root. It creates only the new projects' protected, versioned state buckets (and enables Storage), using independent administrative local state. Bootstrap is the sole Terraform owner of the Storage API enablement; the environment root requires the already-enabled API and does not duplicate its ownership across states. Review a saved bootstrap plan, apply it only with owner authorization, and securely retain its local state; never use the production backend or discard the bootstrap state. Import any already-created state bucket instead of recreating it. No bootstrap command is executed by validation or by the application CI.

Initialize one environment at a time with its own directory. From the repository root, for staging:

```bash
export TF_DATA_DIR="$HOME/.cache/onolys-terraform/staging"
terraform -chdir=infra/isolated-environment init \
  -backend-config=examples/backend-staging.hcl.example
```

For eval, change both the data directory to `.../eval` and the backend file to `backend-eval.hcl.example`. Never use `-migrate-state`, copy production state, or use Terraform workspaces to substitute for these distinct backends. Preserve non-secret operator variable choices in an ignored local tfvars file; use its absolute path consistently for imports and plans.

The three provider secret shells already created in each new project must be imported into their canonical addresses before planning their creation. With the correct backend initialized, run the following pattern separately for each environment (set `env_name` to `staging` or `eval` and use the matching tfvars file):

```bash
env_name=staging
project_id="onolys-${env_name}"
for entry in GEMINI_API_KEY:gemini ANTHROPIC_API_KEY:anthropic OPENAI_API_KEY:openai; do
  variable_name="${entry%%:*}"
  provider_name="${entry#*:}"
  terraform -chdir=infra/isolated-environment import \
    -var-file="examples/environment-${env_name}.tfvars.example" \
    "module.environment.google_secret_manager_secret.provider[\"${variable_name}\"]" \
    "projects/${project_id}/secrets/${provider_name}-api-key-${env_name}"
done
```

Import preserves existing versions; never place secret values in import arguments or Terraform variables. For any other already-created shell, verify its exact identity before importing: Firebase project uses `google_firebase_project.this` with `projects/PROJECT`; Hosting uses `google_firebase_hosting_site.this` with `projects/PROJECT/sites/SITE`; a pre-existing local identity configuration uses `google_identity_platform_config.this[0]` with `projects/PROJECT/config`. Resource existence and import addresses must match the reviewed plan; do not import legacy production resources into the new state.

## Secret-first provisioning and rollout

Cloud Run cannot start a revision whose referenced `latest` secret has no enabled version. After imports, review a targeted shell-only plan for `module.environment.google_secret_manager_secret.uid_hmac`, `.provider` and `.resend`; for eval also include `.eval_allowed_emails[0]`. Dependencies may enable APIs and create the state identity, so inspect every planned change. Apply only that reviewed saved plan before seeding missing values.

Use the existing seed helper with the explicit project and complete configured provider map, for example:

```bash
python3 infra/scripts/seed-secrets.py --project onolys-staging --env staging \
  --map GEMINI_API_KEY=gemini-api-key \
  --map ANTHROPIC_API_KEY=anthropic-api-key \
  --map OPENAI_API_KEY=openai-api-key
```

Load values securely into the environment outside git; do not put values in commands, tfvars, plans or logs. For eval use `--project onolys-eval --env eval`; seed its allowlist with the helper's `--allowlist` option only after the owner provides the intended value. Verify enabled version metadata for all references. Include any configured STT keys in the explicit map. The helper generates a missing HMAC value and leaves unchanged values alone. Resend activation is separate and remains opt-in.

Then review a full saved plan against the new project's backend, confirm there are no production resources and apply only with authorization. Bootstrap Cloud Run uses a public placeholder image: it proves resource provisioning, not app health. Deploy trusted application images before exercising app behavior. New deployments need the root's `project`, `region`, `wif_provider`, `deployer_email`, Hosting/service/database/bucket outputs. `image_repository` is `REGION-docker.pkg.dev/PROJECT/onolys`. `web_env` and `firebase_web_config` expose public local Firebase SDK settings; when retaining external eval identity they are null and existing issuer SDK settings are supplied separately.

The canonical isolated staging app origin is accepted by the backend's fixed host allowlist. Its web build must set `VITE_APP_HOSTS=onolys-staging-app.web.app` for email-action navigation. `APP_BASE_URL` does not itself enable email: seed Resend and set `resend_secret_wired=true` only after validating the sender and local identity permissions. Cross-project auth-email activation is rejected by this root pending a separate IAM review. Existing production mail, domains, users and route selections remain untouched.

The live Gemini provider check was removed from Nightly (along with its `nightly-gemini` identity and `github-nightly` pool); run it manually with `api/tests/test_live_real_mode.py -m live`. No budgets or live workflow settings are changed by this guard.

Do not cut over live domains, delete old environments, change GitHub configuration, migrate user data or populate datasets as part of provisioning this foundation. Those operations need their own verified rollout. Check application health, login, isolated Firestore/audio/Tasks paths, provider calls and report behavior on the new smoke sites first; offline validation does not establish those live results.

## Offline validation

Use the pinned Terraform version and providers. `terraform init -backend=false` plus `validate` for this root and `bootstrap/` contacts no state backend; reuse the existing provider installation or an approved plugin mirror for offline initialization. Run `terraform test` in this root for mocked staging/eval/external-dataset plans; mock providers make no GCP calls. Python regressions live in `infra/scripts/test_isolated_environment.py`, and the narrow app-origin cases are in `api/tests/test_config.py`.

## Eval own sign-in and eval.onolys.com

Eval signs in through its own project, like isolated staging: `environment-eval.tfvars.example` sets `auth_project = "onolys-eval"` and `manage_identity = true`. The root then creates, in `onolys-eval`: Identity Platform (email/password, authorized domains `localhost`, `onolys-eval.firebaseapp.com`, `onolys-eval.web.app`, `onolys-eval-app.web.app` and `eval.onolys.com`), a Firebase web app `onolys-eval`, and the Hosting custom domain `eval.onolys.com` on site `onolys-eval-app` (eval only; `count = 0` for staging). The eval backend and worker run with `AUTH_PROJECT=onolys-eval`. Eval has no sign-up: the operator creates users with `infra/scripts/create-test-user.py` (see [eval site](../reference/eval-site.md)); no users are migrated. The eval backend's CORS origins include `https://eval.onolys.com`, the Hosting site and localhost.

Prod (`onolys`) no longer authorizes eval hosts: `eval.onolys.com`, `onolys-eval-staging.web.app` and `onolys-eval-app.web.app` moved from `authorized_domains` to `local.retired_authorized_domains` in `infra/identity.tf`, and `identity-config.py` removes them on the legacy apply. Its `web_env_eval` output was removed; the eval web build values come from the eval root's `web_env` output.

Apply order (a Firebase custom domain belongs to one site only):

Note: Firebase Hosting custom domains are soft-deleted for about 30 days after the legacy destroy. If creating `eval.onolys.com` on `onolys-eval-app` in step 2 fails because the domain is still held, undelete it or wait, or add the domain once in the Hosting console of `onolys-eval` and import it (`google_firebase_hosting_custom_domain.eval[0]`).

1. Legacy root (`infra/`), reviewed targeted apply as described above. It destroys the `onolys-eval-staging` site and its `eval.onolys.com` custom domain and (via the replaced `terraform_data.identity_policy`) removes the three eval hosts from prod's authorized domains. Preview the identity PATCH first: `python3 infra/scripts/identity-config.py --dry-run --domains-only --remove-domain eval.onolys.com --remove-domain onolys-eval-staging.web.app --remove-domain onolys-eval-app.web.app`.
2. Eval root (`infra/isolated-environment/` with `backend-eval.hcl` and the updated `eval.tfvars`: `auth_project = "onolys-eval"`, `manage_identity = true`). It adds Identity Platform, the web app and the custom domain. Read `terraform output required_dns_updates` and `custom_domain_status`, and `terraform output -json web_env`.
3. Owner steps below, then dispatch `deploy-eval`.

Owner steps:

- Update the durable operator tfvars `/root/.cache/onolys-terraform/eval.tfvars` (`auth_project`, `manage_identity`) before the eval apply.
- Set GitHub variables (repo level, or the `staging` environment that deploy-eval uses): `EVAL_VITE_FIREBASE_API_KEY` (= `web_env.VITE_FIREBASE_API_KEY`), `EVAL_VITE_FIREBASE_AUTH_DOMAIN` (must be `onolys-eval.firebaseapp.com`), `EVAL_VITE_FIREBASE_APP_ID` (= `web_env.VITE_FIREBASE_APP_ID`). The existing `EVAL_GCP_PROJECT`, `EVAL_WIF_PROVIDER`, `EVAL_DEPLOYER_SA` and `EVAL_HOSTING_SITE` must be set; `deploy-eval` has no legacy fallback any more. The old `PROD_VITE_FIREBASE_*` values are no longer read by eval.
- DNS: at Namecheap, repoint `eval.onolys.com` to the records Firebase shows (`required_dns_updates` / Hosting console for `onolys-eval-app`), including the `_acme-challenge` TXT record if listed. Remove the old records for that host first. Expect `OWNERSHIP_ACTIVE`, `HOST_ACTIVE`, `CERT_ACTIVE` in `custom_domain_status`; until then eval is reachable at `https://onolys-eval-app.web.app`.
- Eval has no Google sign-in, no self sign-up (`disabled_user_signup = true`) and sends no email: the login page hides Google, and accounts are created verified by `infra/scripts/create-test-user.py` (admin API, not subject to the sign-up switch). Authorized domains need no manual step.
- Allowlisted eval emails (`eval-allowed-emails-eval`) must be addresses of accounts the operator created in `onolys-eval` with `create-test-user.py`.
