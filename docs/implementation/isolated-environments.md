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

Eval uses the same module with the public API and voice disabled, and enables the eval backend, worker and eval mode. Runtime config remains `ENV=staging`; Firestore database is `eval`. Its smoke site is `onolys-eval-app`. `auth_project` defaults to `onolys` for eval, retaining the existing token issuer without moving users. The root never manages an external identity project. `manage_identity=true` is available for staging validation only when the issuer is that runtime project; it creates local email/password Identity Platform configuration and a Firebase web app. OAuth-provider setup, email template policy and existing-project authorized-domain additions remain separate reviewed identity operations.

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

Activating `STAGING_GCP_PROJECT` pauses only Nightly's paid `api-real-mode` job: its legacy `onolys` Gemini key would otherwise keep billing production. Offline Nightly coverage continues; a dedicated isolated Nightly identity/key and explicit workflow update are deferred. No budgets or live workflow settings are changed by this guard.

Do not cut over live domains, delete old environments, change GitHub configuration, migrate user data or populate datasets as part of provisioning this foundation. Those operations need their own verified rollout. Check application health, login, isolated Firestore/audio/Tasks paths, provider calls and report behavior on the new smoke sites first; offline validation does not establish those live results.

## Offline validation

Use the pinned Terraform version and providers. `terraform init -backend=false` plus `validate` for this root and `bootstrap/` contacts no state backend; reuse the existing provider installation or an approved plugin mirror for offline initialization. Run `terraform test` in this root for mocked staging/eval/external-dataset plans; mock providers make no GCP calls. Python regressions live in `infra/scripts/test_isolated_environment.py`, and the narrow app-origin cases are in `api/tests/test_config.py`.
