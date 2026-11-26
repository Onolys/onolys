# Infrastructure runbook

**Audience:** the owner and agents who operate, deploy and debug Onolys on GCP.

Everything here was checked on 2026-11-20 against `terraform output`, `terraform show` (state), the Cloud Run API and Cloud Logging (`entries:list`). Terraform is the source of truth: if this page and `infra/` disagree, `infra/` wins, then fix this page. Why the choices were made: [ADR 0022](../decisions/0022-infra-gcp-terraform-two-environments.md).

## Overview

One GCP project (`onolys`, number `1054076260967`), region `us-central1`, two environments (`staging`, `prod`) in one Terraform root (`infra/`, state in `gs://onolys-tfstate`, prefix `infra`, Terraform `1.9.8`). Staging and prod are isolated by Firestore database, bucket, queue, service accounts and secrets. One Identity Platform user pool serves both.

> **Per-environment projects.** Production stays in `onolys` and in this legacy root. Staging (`onolys-staging`, `904020682480`) and eval (`onolys-eval`, `976672392004`) live in their own projects through the separate `infra/isolated-environment/` root. Staging is activated by the GitHub var `STAGING_GCP_PROJECT`; eval has no legacy target and always runs in `onolys-eval` (`EVAL_GCP_PROJECT` must be `onolys-eval`). Until staging activation, and for everything this page describes about `*-staging` resources in `onolys`, the legacy layout applies; the old `*-staging` / `*-eval` secrets in `onolys` have been deleted by the owner. See [isolated environments](../implementation/isolated-environments.md).

> **Legacy staging and eval removed from this root.** `module "staging"`, `module "eval"`, `eval.tf`, the `onolys-app-staging` and `onolys-eval-staging` sites and the staging/eval deployer grants are no longer declared in `infra/`. A reviewed `terraform apply` here destroys the old `staging`/`eval` Firestore databases, `*-staging`/`*-eval` Cloud Run services, buckets (incl. `onolys-eval-data-staging`), queues, schedulers, service accounts, IAM and secret shells in `onolys`, and changes nothing in prod. Kept: `deployer-staging` (+ WIF binding, pool/provider, `serviceUsageConsumer`) for deploy-prod `resolve`, the `onolys` registry, prod, and the Identity Platform config (eval hosts are retired from it: eval signs in through `onolys-eval`). `onolys-eval-staging` and `eval.onolys.com` moved to the isolated eval root. Parts of this page that describe the old staging/eval resources are historical; staging and eval now live in `onolys-staging` / `onolys-eval`.

```
Browser -> Hosting site (onolys-app) -> /v1/** rewrite -> Cloud Run onolys-api-prod -> Firestore (default), GCS, Cloud Tasks
Cloud Tasks steps-prod -(OIDC)-> onolys-worker-prod -> STT (location us) + Gemini API (Anthropic API for the `claude` preset)
staging: same shape, site onolys-app-staging, Firestore DB `staging`, *-staging services
```

## Resource names

| Resource | staging | prod |
|---|---|---|
| Cloud Run api | `onolys-api-staging` | `onolys-api-prod` |
| Cloud Run worker | `onolys-worker-staging` | `onolys-worker-prod` |
| Firestore database (Native, `us-central1`) | `staging` | `(default)` (delete-protection on) |
| GCS bucket (private) | `onolys-audio-staging` | `onolys-audio-prod` |
| Cloud Tasks queue | `steps-staging` | `steps-prod` |
| Service accounts (`@onolys.iam.gserviceaccount.com`) | `api-staging`, `worker-staging`, `tasks-invoker-staging`, `deployer-staging` | `api-prod`, `worker-prod`, `tasks-invoker-prod`, `deployer-prod` |
| Secret `uid-hmac-key-{env}` | `uid-hmac-key-staging` | `uid-hmac-key-prod` |
| Secret `resend-api-key-{env}` (shell; owner seeds the value) | `resend-api-key-staging` | `resend-api-key-prod` (shell only; not wired) |
| Secret `<base>-{env}` per `llm_secrets` / `stt_secrets` entry (default bases `gemini-api-key`, `anthropic-api-key`) | `gemini-api-key-staging`, `anthropic-api-key-staging` | `gemini-api-key-prod`, `anthropic-api-key-prod` |
| Log-based metric (5xx) | `onolys-api-5xx-staging` | `onolys-api-5xx-prod` |
| Alert policies | none while `staging_alerts=false` | `Onolys failed step/run (prod)`, `Onolys api 5xx rate (prod)` |
| Hosting site | `onolys-app-staging` (`https://onolys-app-staging.web.app`) | `onolys-app` (`https://onolys-app.web.app`, custom domain `app.onolys.com`) |

Shared (project level): Artifact Registry repo `onolys` (`us-central1-docker.pkg.dev/onolys/onolys`, no cleanup policy, so any earlier sha stays deployable), spend limits are not in Terraform (owner sets the Anthropic Console limit and a Google Cloud billing budget in the consoles; the former `google_billing_budget.monthly` was dropped from state with a `removed` block, `destroy = false`, so the existing budget is untouched), Monitoring channel `Onolys owner email`, Workload Identity pool `github` with provider `github` (condition `assertion.repository=='Onolys/onolys'`), Speech-to-Text service agent `service-1054076260967@gcp-sa-speech.iam.gserviceaccount.com` (`objectViewer` on both buckets), Identity Platform config (email+password, min length 8, open sign-up, no MFA). Email verify/reset links need `notification.sendEmail.callbackUri` = `https://app.onolys.com/auth/action` (set only by `python3 infra/scripts/identity-config.py`, a manual Terraform apply); `python3 infra/scripts/identity-config.py --check` is a read-only drift check (exit 1 and the remedy if it differs). Not in CI: the deployer SAs hold no Identity Platform read role (would need e.g. `roles/firebaseauth.viewer`).

Sizing (checked on the live services):

| Service | CPU / mem | Timeout | Concurrency | Max instances (staging / prod) |
|---|---|---|---|---|
| api | 1 / 1 GiB | 60 s | 80 | 3 / 10 |
| worker | 2 / 2 GiB | 900 s | 2 | 3 / 3 |

Queue `steps-{env}`: `max_attempts=2`, backoff 5 s to 30 s, `max_dispatches_per_second=5`, `max_concurrent_dispatches = worker_concurrency x worker_max_instances` (6 in both envs). Rule: never let dispatches exceed worker capacity, or Cloud Run answers 429 and burns a task's two attempts. To raise capacity, raise `worker_max_instances` (tfvar); the dispatch cap follows.

Bucket: uniform access, public access prevention enforced, no versioning, soft-delete 0, lifecycle deletes `uploads/` objects older than 1 day, CORS (PUT/HEAD) for the env's app origin (staging also `http://localhost:5173`).

Region note: STT v2 Chirp 3 is not offered in `us-central1`, so STT uses location `us` / endpoint `us-speech.googleapis.com`. That is a provider option in `config/{env}/stt_providers.yaml`, not infra.

## Environment variables (Cloud Run)

Set by Terraform (`infra/modules/environment/services.tf`). Base service values were checked with the Cloud Run API on 2026-11-20; auth-email rows describe the Terraform configuration and its activation gate.

| Var | api | worker | Value |
|---|---|---|---|
| `SERVICE_MODE` | yes | yes | `api` or `worker` |
| `ENV` | yes | yes | `staging` / `prod` |
| `GCP_PROJECT`, `AUTH_PROJECT` | yes | yes | `onolys` |
| `REGION` | yes | yes | `us-central1` |
| `FIRESTORE_DATABASE` | yes | yes | `staging` / `(default)` |
| `AUDIO_BUCKET` | yes | yes | `onolys-audio-{env}` |
| `TASKS_QUEUE` | yes | yes | `steps-{env}` |
| `TASKS_SA` | yes | yes | `tasks-invoker-{env}@onolys.iam.gserviceaccount.com` |
| `WORKER_URL` | yes | yes | `https://onolys-worker-{env}-1054076260967.us-central1.run.app` (also the OIDC audience) |
| `ADAPTERS` | yes | yes | `real` |
| `BLOB_SIGNER_EMAIL` | yes | no | `api-{env}@onolys.iam.gserviceaccount.com` (signs V4 upload/read URLs through IAM `signBlob`) |
| `EVAL_CAP_DAY` | yes | yes | `10` (per user evaluation runs per UTC day, app-side) |
| `AI_CAP_DAY` | yes | yes | `5` (per user AI interviews per UTC day, app-side) |
| `ROUTES_FILE` | yes | yes | `config/{env}/routes.yaml` (baked into the image; `stt_providers.yaml` sits next to it) |
| `DEFAULT_PRESET` | yes | yes | `default` |
| `CORS_ORIGINS` | yes | no | staging `https://onolys-app-staging.web.app,http://localhost:5173`; prod `https://app.onolys.com` |
| `UID_HMAC_KEY` | yes | yes | secret ref `uid-hmac-key-{env}` (keys the `uid_hash` log field) |
| `APP_BASE_URL` | yes | when activated | staging `https://onolys-app-staging.web.app`, prod `https://app.onolys.com` (module var `app_base_url`; `deploy-staging.yml` re-sets it on the api). The worker receives it only when `resend_secret_wired[env]` is true. Optional for `Settings`: when unset the service starts and `POST /v1/auth/email/verification` answers 503 `email_unavailable` (password reset stays 202 and logs `outcome=unconfigured`). When set it must be an HTTPS origin on a known app host or startup fails. The PR preview does not set it, so verification answers 503 and reset retains its generic 202 |
| `CLIENT_IP_TRUSTED_HOPS` | no | no | integer >= 0, default `1`. Number of proxy entries to skip from the right of `X-Forwarded-For` when picking the client IP for the password-reset per-IP cap (`parts[-(hops+1)]`, clamped to the leftmost; non-IP values fall back to the `unknown` bucket). See "Client IP and `X-Forwarded-For`" below |
| `EMAIL_FROM` | yes | when activated | `Onolys <no-reply@onolys.com>` (module var `email_from`; also in `deploy-staging.yml`) |
| `RESEND_API_KEY` | when activated | when activated | secret ref `resend-api-key-{env}`, only when root map var `resend_secret_wired[env]` is true (default false for both; a revision fails if the secret has no version). Without it verification answers 503 `email_unavailable`; reset still returns generic 202 and its delivery logs `outcome=unconfigured` |
| `GEMINI_API_KEY` (evaluation LLM) and `ANTHROPIC_API_KEY` (only for the `claude` preset) | no | yes | secret refs `gemini-api-key-{env}` and `anthropic-api-key-{env}` (one ref per `llm_secrets` / `stt_secrets` entry, always the env's own secret; staging and prod use separate provider keys) |
| `LLM_PROVIDER`, `LLM_MODEL`, `LLM_EFFORT` | yes | yes | runtime names shared by staging/prod; sourced independently from `LLM_*` / `PROD_LLM_*` repository variables and validated by each deploy workflow; not set by Terraform. Provider/model must be paired; effort is independent. Empty = preserve route defaults. See "LLM provider and model" |
| `GIT_SHA` | yes | yes | set by CI at deploy. `unset` until the first CI deploy (the services still run the placeholder image `us-docker.pkg.dev/cloudrun/container/hello`) |

There are no STT env vars. No model id appears in infra.

The two cap vars are integers >= 0 (0 disables that kind). There are no monthly caps: one daily limit per flow (evaluation, AI interview). The old single daily-run-cap var and the `EVAL_CAP_MONTH` / `AI_CAP_MONTH` vars were removed; a leftover value on a service is ignored. `MAX_ACTIVE_RUNS` (concurrent evaluation runs per user) defaults to `1`: one run at a time; `users/{uid}.max_active_runs` overrides per user.

## Client IP and `X-Forwarded-For`

Each Google front end appends the address it saw to whatever `X-Forwarded-For` the caller sent, so entries on the left are client-controlled and entries on the right are ours. The reset endpoint's per-IP cap (20/h) takes entry `parts[-(CLIENT_IP_TRUSTED_HOPS+1)]`.

- Default `1` is chosen for the Firebase Hosting `/v1/**` rewrite (the path the web uses). Third-party reports (not Google documentation) show that path arriving as `client, hosting-hop`, so one hop from the right is the client and any prefix the caller injects sits to its left and is ignored.
- Direct calls to the api's `run.app` URL (ingress is `ALL`) arrive as `<caller-supplied>, client`. With the default, such a caller can choose the bucket by sending a second entry, so the per-IP cap can be evaded on that path (set `0` to protect the direct path instead, at the cost of putting every Hosting user in one shared bucket). Per-email caps (1/min, 5/h) still apply either way.
- Not verified against live traffic. Before relying on it, check on staging: send one reset request through the Hosting URL and one directly to `run.app` with a forged `X-Forwarded-For`, and compare the chain lengths and the entry that lands in the bucket. Adjust `CLIENT_IP_TRUSTED_HOPS` if the Hosting chain length differs.

## Per-user limits (Firebase console)

Change one user's limits without a deploy. Defaults come from the env vars above (`EVAL_CAP_*`, `AI_CAP_*`).

1. Firebase console > Firestore. Database `(default)` for prod, `staging` for staging.
2. Find the uid: Authentication > Users, look up the email, copy User UID.
3. Collection `users`, document `users/{uid}` (the document id is the uid).
4. Add a map field `limits`, e.g. `limits.eval.day = 25`. Shape: `limits = {eval: {day}, interview: {day}}`; every leaf is optional.
5. Integers only. `0` disables that kind for the user. A leaf that is not an integer is ignored (the default applies, a warning is logged).
6. Delete a leaf to return to the default.
7. Takes effect on the next request; no deploy or restart.

The legacy field `daily_cap` is still honoured for the evaluation day cap only (deprecated; use `limits.eval.day`).

Usage counters live in collection `usage`: day doc `{uid}_{YYYY-MM-DD}` with `runs` and `interviews` (old month docs `{uid}_{YYYY-MM}` are no longer read or written). Edit them the same way (lower the number or set 0) to grant a one-off reset. Days are UTC. The first evaluation run of an AI-interview-linked session does not count toward the caps but still takes a concurrent-run slot.

`GET /v1/usage` shows what a user sees: used, effective cap (overrides included) and reset time. `used` can exceed `cap` after a cap is lowered.

## Terraform outputs

Run `cd infra && terraform output` (needs ADC; see Operating Terraform).

| Output | Use |
|---|---|
| `wif_provider` | GitHub var `WIF_PROVIDER`. Now: `projects/1054076260967/locations/global/workloadIdentityPools/github/providers/github` |
| `deployer_staging_email` | GitHub var `DEPLOYER_STAGING_SA`. Now: `deployer-staging@onolys.iam.gserviceaccount.com` |
| `deployer_prod_email` | GitHub var `DEPLOYER_PROD_SA`. Now: `deployer-prod@onolys.iam.gserviceaccount.com` |
| `web_env_prod` | same keys; `VITE_FIRESTORE_DATABASE` = `(default)` |
| `required_dns_updates` | DNS records the owner adds (next section) |
| `custom_domain_status` | Hosting verification state per custom domain |

`VITE_FIRESTORE_DATABASE` is a per-build value: the web app passes it to `getFirestore`. The deploy workflows set it themselves (`staging` in `deploy-staging.yml`, `(default)` in `deploy-prod.yml`), so it is not a GitHub variable; it appears in `web_env_*` for local builds.

The browser API key is public by design (a Firebase web key); it is not restricted yet (After launch).

## DNS records (owner)

Copied verbatim from `terraform output required_dns_updates` on 2026-11-20 (domain `app.onolys.com`, action `ADD` for both):

| Type | Host | Value |
|---|---|---|
| `CNAME` | `app.onolys.com` | `onolys-app.web.app` |
| `TXT` | `_acme-challenge.app.onolys.com` | `oN6Ib3nIZxSzD2DNyT0R_WP254oUKl4wi-cNxyAVPdg` |

Status then (`terraform output custom_domain_status`): `ownership OWNERSHIP_MISSING`, `host HOST_UNHOSTED`, `cert CERT_VALIDATING`. After the records exist, expect `OWNERSHIP_ACTIVE`, `HOST_ACTIVE`, `CERT_ACTIVE` (minutes to hours).

Re-run the output before adding records: the values change if Hosting changes its desired state, and the TXT value is per-certificate. Remove any conflicting `A`/`AAAA` record on `app.onolys.com` (a `CNAME` cannot coexist with other records on the same host).

No other staging custom domain (`onolys-app-staging.web.app` only).

## GitHub settings the owner must set

Repo `Onolys/onolys` > Settings > Secrets and variables > Actions > Variables (repository level), and Settings > Environments.

Environments: create `production` with Tejit as required reviewer (all prod jobs use it; the prod deployer trusts only that environment). `staging` is created on first use by `_deploy-cloudrun.yml`; no reviewer needed.

| Variable | Used by | Value (Terraform output) |
|---|---|---|
| `WIF_PROVIDER` | deploy-staging, deploy-prod, deploy-eval, `_deploy-cloudrun` | `wif_provider` |
| `DEPLOYER_STAGING_SA` | same (and the read-only `resolve` step of deploy-prod) | `deployer_staging_email` |
| `DEPLOYER_PROD_SA` | deploy-prod, `_deploy-cloudrun` | `deployer_prod_email` |
| `GCP_PROJECT`, `GCP_REGION` | optional; default `onolys`, `us-central1` | leave unset |
| `STAGING_VITE_FIREBASE_API_KEY`, `_AUTH_DOMAIN`, `_APP_ID`, `_STORAGE_BUCKET`, `_MESSAGING_SENDER_ID` | deploy-staging (web build) | `web_env_staging` keys `VITE_FIREBASE_*` (same names without the `STAGING_` prefix) |
| `PROD_VITE_FIREBASE_API_KEY`, `_AUTH_DOMAIN`, `_APP_ID`, `_STORAGE_BUCKET`, `_MESSAGING_SENDER_ID` | deploy-prod (web build) | `web_env_prod` keys |
| `STAGING_VITE_CONTACT_EMAIL`, `PROD_VITE_CONTACT_EMAIL` | optional, web build | owner's contact address |
| `LLM_PROVIDER`, `LLM_MODEL`, `LLM_EFFORT` | deploy-staging, API and worker | optional staging text-route selection; provider/model paired; model is a catalog tier ID |
| `PROD_LLM_PROVIDER`, `PROD_LLM_MODEL`, `PROD_LLM_EFFORT` | deploy-prod, API and worker | optional independent production selection; all blank restores the promoted image's prod route defaults |
| `EVAL_VITE_FIREBASE_API_KEY`, `_AUTH_DOMAIN`, `_APP_ID` | deploy-eval (web build) | isolated eval root's `web_env` output (`VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN` = `onolys-eval.firebaseapp.com`, `VITE_FIREBASE_APP_ID`). Eval never uses the `PROD_VITE_*` values. Any leftover legacy admin-app GitHub variables are unused and can be deleted |

`VITE_FIREBASE_PROJECT_ID` is taken from `GCP_PROJECT`/`onolys` in the prod/staging workflows (`EVAL_GCP_PROJECT` in deploy-eval); `VITE_FIRESTORE_DATABASE` is hard-coded per workflow (see Terraform outputs).

### Owner step: `RELEASE_TAG_TOKEN` (prod tag job)

The `tag` job of `deploy-prod` pushes `prod-<date>.<n>`. When the promoted commit (staging's, or a rollback target) is older than `main` and `.github/workflows/*` differ, `GITHUB_TOKEN` is refused ("refusing to allow a GitHub App to create or update workflow ... without `workflows` permission") and cannot be granted that permission. The job runs in its own GitHub environment `release-tag` (not `production`: a later gated job would need a second approval) and uses `RELEASE_TAG_TOKEN` from it; unset falls back to `GITHUB_TOKEN`, which works only when workflow files match `main`.

1. Settings > Environments > New environment `release-tag`: deployment branches = `main` only, no required reviewers.
2. Create a fine-grained PAT (resource owner `Onolys`, repository `Onolys/onolys` only, Repository permissions: Contents Read and write, Workflows Read and write, short expiry you will renew). The org may need to allow fine-grained PATs, or an owner must approve the token request.
3. Save it as an **environment secret** `RELEASE_TAG_TOKEN` in `release-tag` (not a repo secret).
4. Renew before expiry. An expired PAT fails the checkout; prod is already deployed by then, only the tag is lost.

Re-running a failed `tag` job (`gh run rerun <run> --failed`) works for future runs whose workflow file already has the token line. It does not work for run 45737922265 (commit `ce261570a3d31bd529bcdc5adfbe6300ae887894`): re-runs use the original commit's workflow file, which lacks it. Tag that one manually (next `prod-<date>.<n>` is numbered from origin): push over SSH, or run `gh auth refresh -s workflow` first (gh's default HTTPS scopes lack `workflow`):

```
git tag -a prod-<date>.<n> ce261570a3d31bd529bcdc5adfbe6300ae887894 -m "prod deploy prod-<date>.<n>" -m "commit: ce261570a3d31bd529bcdc5adfbe6300ae887894" -m "image: <image>" -m "run: https://github.com/Onolys/onolys/actions/runs/45737922265"
git push origin refs/tags/prod-<date>.<n>
```

Possible later alternative: a GitHub App token via `actions/create-github-app-token` instead of a PAT.

### Isolated staging and eval release targets (opt in)

The current production project is **`onolys`**. The additive isolated targets are **`onolys-staging`** and **`onolys-eval`**; their billing and infrastructure are provisioned separately. These workflow changes create no resources and change no live variables or domains. With `STAGING_GCP_PROJECT` unset, staging releases use the existing project, identities, sites and Firebase apps. Eval has no legacy target any more: `deploy-eval` always requires the `EVAL_*` bundle (it fails before authentication otherwise).

Prepare each bundle at repository level, keeping its project variable unset until the infrastructure, IAM, secrets and Firebase settings have been reviewed and provisioned:

| Variable | Staging value | Eval value |
|---|---|---|
| `STAGING_GCP_PROJECT` / `EVAL_GCP_PROJECT` | `onolys-staging` (set last to activate) | `onolys-eval` (set last to activate) |
| `STAGING_WIF_PROVIDER` / `EVAL_WIF_PROVIDER` | isolated staging root's `wif_provider` | isolated eval root's `wif_provider` |
| `STAGING_DEPLOYER_SA` / `EVAL_DEPLOYER_SA` | isolated staging root's `deployer_email` in `onolys-staging` | isolated eval root's `deployer_email` in `onolys-eval` |
| `STAGING_HOSTING_SITE` / `EVAL_HOSTING_SITE` | `onolys-staging-app` (`hosting_site_id`; supported email callback origin) | isolated eval root's `hosting_site_id`, a new site distinct from the legacy sites |
| `STAGING_PREVIEW_WIF_PROVIDER` / `STAGING_PREVIEW_SA` | isolated staging root's `pr_preview_wif_provider` / `pr_preview_service_account` (needs `enable_pr_previews`; PR previews only) | unused |
| `STAGING_ISOLATED_VITE_FIREBASE_API_KEY` | new staging Firebase web app SDK API key | unused |
| `STAGING_ISOLATED_VITE_FIREBASE_AUTH_DOMAIN` | `onolys-staging.firebaseapp.com` | unused |
| `STAGING_ISOLATED_VITE_FIREBASE_APP_ID` | new staging Firebase web app SDK app ID | unused |
| `STAGING_ISOLATED_VITE_FIREBASE_STORAGE_BUCKET`, `STAGING_ISOLATED_VITE_FIREBASE_MESSAGING_SENDER_ID` | optional new staging SDK values; never fall back to the legacy app after activation | unused |
| `EVAL_VITE_FIREBASE_API_KEY` | unused | eval Firebase web app SDK API key (isolated eval root `web_env`) |
| `EVAL_VITE_FIREBASE_AUTH_DOMAIN` | unused | `onolys-eval.firebaseapp.com` |
| `EVAL_VITE_FIREBASE_APP_ID` | unused | eval Firebase web app SDK app ID |

The project variable is the activation switch. Preparing the identity, site and isolated Firebase variables alone has no effect. Once activated, an incomplete or invalid bundle fails before cloud authentication, image publication or deployment; the workflow never silently redirects an incomplete active bundle to the old project. Stage the new Firebase values under `STAGING_ISOLATED_VITE_FIREBASE_*`; retain `STAGING_VITE_FIREBASE_*` for the legacy app. `GCP_PROJECT`, `WIF_PROVIDER`, `DEPLOYER_STAGING_SA` and `DEPLOYER_PROD_SA` continue to describe the existing `onolys` project and identities. Keep them unchanged. Region continues to use `GCP_REGION` (default `us-central1`).

After staging activation, app images, Cloud Run, Firestore `staging` rules and Hosting target `app-staging` all use `onolys-staging`. CI creates a project-scoped `.firebaserc` mapping only in its disposable checkout, sets the selected site as the API CORS/email origin and `VITE_APP_HOSTS` email-action destination, and replaces the staging voice CSP origin with that project's provisioned voice URL. Smoke uses `https://onolys-staging-app.web.app`. The new staging runtime must include the admitted callback origin; activate only after these changes and the matching infrastructure are on `main`. PR previews, preview cleanup and preview sweeping follow `STAGING_GCP_PROJECT`: they run in `onolys-staging` (site `STAGING_HOSTING_SITE`) as the limited `pr-preview-staging` identity (`STAGING_PREVIEW_WIF_PROVIDER` / `STAGING_PREVIEW_SA`, pull_request-only provider in its own `github-pr` workload identity pool, separate from the main-only deployer pool `github`) and fail fast when those vars are missing. Existing preview resources in the old project are not touched after activation; finish any desired legacy cleanup before setting `STAGING_GCP_PROJECT`.

After eval activation, its worker/backend images, Cloud Run, Firestore `eval` rules and Hosting target `eval-staging` (mapped to site `onolys-eval-app`) use `onolys-eval` and its project-local deployer. Eval has its own sign-in: Identity Platform (email/password) and a Firebase web app in `onolys-eval`, created by the isolated eval root (`manage_identity = true`, `auth_project = onolys-eval`), so the backend runs with `AUTH_PROJECT=onolys-eval` and the web build uses the `EVAL_VITE_FIREBASE_*` variables above (auth domain `onolys-eval.firebaseapp.com`). The authorized domains in `onolys-eval` are `onolys-eval-app.web.app` and `eval.onolys.com`, declared in Terraform. Eval users are not migrated: the operator creates accounts with `infra/scripts/create-test-user.py` (eval has no self sign-up and sends no email). The `onolys` Firebase app and its authorized domains are no longer involved. See [isolated environments](../implementation/isolated-environments.md#eval-own-sign-in-and-eval-onolyscom) for the apply order and owner steps.

Production writes and the single production approval remain in `onolys`, with the existing production deployer and independent `PROD_LLM_*` settings. Promotion resolves the image and checks staging API/worker/voice revision provenance in the selected staging project. The preapproval resolver intentionally retains the **legacy** `WIF_PROVIDER` + `DEPLOYER_STAGING_SA`: this preserves both manual and `v*` tag promotion without broadening the new main-only staging WIF provider. Before activating staging, grant that legacy resolver read access in `onolys-staging`; production also needs to read the cross-project image:

| Principal | Resource in `onolys-staging` | Required role |
|---|---|---|
| existing `DEPLOYER_STAGING_SA` | staging Cloud Run services/project | `roles/run.viewer` (read staging revisions and service state) |
| existing `DEPLOYER_STAGING_SA` | Artifact Registry repository `onolys`, location `us-central1` (or configured region) | `roles/artifactregistry.reader` |
| existing `DEPLOYER_PROD_SA` | same Artifact Registry repository | `roles/artifactregistry.reader` |
| production Cloud Run service agent `service-<onolys-project-number>@serverless-robot-prod.iam.gserviceaccount.com` | same Artifact Registry repository | `roles/artifactregistry.reader` (pulls promoted images into production) |

Apply registry roles on the repository, rather than granting project-wide write access. No new staging/eval deployer receives production write permissions. The workflow still promotes the staging image by digest, validates production LLM settings against that image, and never rebuilds it. Historical promotions after staging activation must have provenance in the newly selected staging project; clearing the activation variable returns provenance lookup to the legacy project. The switch does not copy old registry images or revision history.

Before activation, review/apply the new roots, provision enabled secret versions, confirm all services/sites and cross-project reader grants, and stage the complete repository-variable bundle. Set only the corresponding project variable last, then perform a reviewed release and verify the new `.web.app` site before considering a custom-domain handoff. Clearing the project variable is no longer a rollback to legacy staging: the legacy staging/eval targets in `onolys` are being destroyed (see the legacy apply steps in [isolated environments](../implementation/isolated-environments.md)), so workflows would point at resources that no longer exist. It does not move data or reverse any resources already created in the new project. The live Gemini provider check was removed from Nightly (along with its `nightly-gemini` identity and `github-nightly` pool); run it manually with `api/tests/test_live_real_mode.py -m live`.

### Gemini key: Secret Manager is the source

The live Gemini provider check was removed from Nightly (along with its `nightly-gemini` identity and `github-nightly` pool); run it manually with `api/tests/test_live_real_mode.py -m live`. Runtime references stay `gemini-api-key-staging` and `gemini-api-key-prod` for their respective environments; the production key stays only in Secret Manager and is never copied into GitHub. Offline guard: `python3 -m pytest infra/scripts/test_nightly_gemini_secret.py -q` (asserts the removal), plus `python3 scripts/ci/check_no_llm_keys_in_pr_workflows.py` and Terraform `fmt -check` / `validate`. Applying this removal to a legacy root destroys the old `github-nightly` pool/provider and `nightly-gemini` account.

Workflows: `deploy-staging.yml` runs after the `CI` workflow succeeds on `main` (also manual). Before cloud authentication, automatic and manual releases verify that the SHA is still current `main` and has successful push CI in this repository. A stale queued run fails rather than rolling back a newer release. `deploy-prod.yml` is manual (`workflow_dispatch`, input `sha` or `version`) or on a `v*` tag. `nightly.yml` runs 06:17 UTC daily.

App staging and eval release independently. `deploy-staging.yml` builds and deploys only the staging app API, worker, voice service, rules and site; its `deploy-staging` lock and smoke checks cover that app release. App failures do not block starting an eval release, and eval infrastructure failures do not fail an app release. Production promotion remains `deploy-prod.yml`: it requires the app image to have run on staging API, worker and voice services, with no eval deployment requirement.

To release eval, dispatch **deploy-eval on `main` after its push CI succeeds**. It is manual only and has its own `deploy-eval` concurrency lock. Before cloud authentication it rejects non-main refs, stale SHAs and commits without successful exact-SHA push CI in this repository, using the same admission guard as staging. It does not wait for or trigger an app deployment. Its authenticated preflight checks that `onolys-worker-eval` and `onolys-eval-backend-eval` exist and are accessible before publishing images. A missing/inaccessible service stops the release with infrastructure guidance; it does not create services or widen IAM.

The eval workflow independently builds the worker from `api/Dockerfile` into the existing Artifact Registry repository's **`onolys/eval-worker` package**, and builds `eval/backend/Dockerfile` into `onolys/eval-backend`. It never writes an `onolys/api` image tag. Eval and app workers share runtime Dockerfile, dependency and engine inputs at a given commit, but have separately built image digests and environment settings; matching image digests or deployed app/eval versions are not required. The workflow validates source configuration and the eval worker image configuration by digest, and retains the eval backend image smoke test. Terraform owns the eval worker's mode, routes, secrets and queue settings; staging app LLM overrides are not copied into eval.

Within one eval release, the worker deploys first, then the backend; the site and `firestore:eval` rules/indexes use the same admitted SHA. Both runtime `GIT_SHA` values and all image build provenance use that SHA, replacing Terraform bootstrap values. The eval lock remains held through Hosting, rules and smoke checks. During the first transition, wait for or cancel runs using the old coupled definitions before dispatching either new release: a changed workflow cannot retroactively lock a historical run. Deployment remains sequential, so active eval runs can still fail strict code/configuration drift checks while revisions change. If a release fails between services, correct the failure and dispatch **deploy-eval** again on current CI-green `main` to restore the pair. The drift guard remains enabled.

Eval releases require the existing SP03 infrastructure to have been provisioned. If the dedicated services are absent, an infrastructure owner must follow [eval infrastructure activation](#eval-infrastructure-activation): create/import secret shells, seed enabled versions, then review and manually apply the full existing Terraform configuration, including eval runtime/deployer IAM. Confirm the dedicated services are healthy before dispatching eval. This is separate from splitting the release workflows; CI does not apply Terraform, and an existing legacy backend alone does not provision the dedicated eval worker/backend pair.

The eval backend's `api-eval` service account starts and polls Speech-to-Text operations for dataset audio. It receives `roles/speech.client` only when the eval backend is enabled in `env=eval`; staging/prod API grants remain unchanged. The existing worker Speech grants remain in place.

## Operating Terraform

```bash
bash infra/scripts/install-tools.sh          # pinned terraform to ~/.local/bin
bash infra/bootstrap.sh                      # state bucket onolys-tfstate (idempotent)
export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/application_default_credentials.json
cd infra && terraform init && terraform plan     # add -lock=false for a read-only look
terraform apply
```

The providers use `user_project_override` with billing project `onolys`, so Terraform itself needs no `gcloud` (only the optional read of live values below does). `terraform plan/apply` is manual (no CI apply). Cloud Run images belong to CI. `GIT_SHA` and `LLM_PROVIDER`/`LLM_MODEL`/`LLM_EFFORT` are set by the deploy workflows on every deploy; the provider models Cloud Run `env` as a set, so one entry cannot be ignored (and ignoring all of `env` would hide Resend/provider-key wiring changes). Terraform therefore owns them from variables: before any plan/apply set the live values in the ignored `infra/terraform.tfvars` (template: `infra/terraform.tfvars.example`; the legacy root is prod only, so `git_sha` and `resend_secret_wired` accept just the `prod` key). Read the live values with `gcloud run services describe onolys-api-prod --project onolys --region us-central1 --format='value(spec.template.spec.containers[0].env)'` (names and values only; prod has no secret values in env). `llm_*` default to blank (no override), matching deploy-prod with no `PROD_LLM_*` variables. After each CI deploy the next plan shows drift until these are refreshed. CI-set labels: `commit-sha`, `managed-by` (service + template) and `goog-terraform-provisioned` (template) are ignored via `lifecycle`.

After a CI pinned api deploy (`pin_traffic`, revision named `<service>-<sha7>-<run>-<attempt>`), the next plan shows a harmless `template.revision -> null` on the api (it is deliberately not in `ignore_changes`, otherwise apply fails with 409 "Revision ... with different configuration already exists"); Cloud Run then auto-names the new revision.

Seed secret values outside state (values never printed, never in tfvars):

```bash
set -a; . ~/.config/onolys/keys.env; set +a
python3 infra/scripts/seed-secrets.py --env staging     # also: --env prod
```

It creates `uid-hmac-key-{env}` (random, only if missing) and writes the key for each `--map ENVVAR=base-id` (default `GEMINI_API_KEY=gemini-api-key` and `ANTHROPIC_API_KEY=anthropic-api-key`; a key whose variable is unset keeps its existing version) into `<base-id>-{env}`, so `--env staging` and `--env prod` fill different secrets from the key in your shell. Re-running is a no-op unless a value changed.

### Eval infrastructure activation

> Historical: the staging/eval modules this section targets were removed from the legacy root; new staging/eval are managed by `infra/isolated-environment/`.

Cloud Run cannot start revisions whose `latest` secret references have no enabled version. Provision the existing SP03 configuration in this order, using the operator's existing backend, credentials and ignored tfvars; review each saved plan before applying it:

1. From `infra/`, create a targeted secret-shell plan, inspect it and apply only that reviewed plan. The resource names are existing configuration, not new infrastructure code:

   ```bash
   terraform plan \
     -target='module.eval.google_secret_manager_secret.uid_hmac' \
     -target='module.eval.google_secret_manager_secret.provider' \
     -target='module.eval.google_secret_manager_secret.eval_allowed_emails[0]' \
     -out=eval-secret-shells.tfplan
   terraform show eval-secret-shells.tfplan
   terraform apply eval-secret-shells.tfplan
   ```

   The one-time allowlist import was removed because its source secret in `onolys` was deleted; the plan creates a fresh `eval-allowed-emails-eval` shell. Seed the allowlist value separately (see seed-secrets `--allowlist`); isolated eval lives in `onolys-eval`.

2. From the repository root, securely load the configured eval provider keys into the environment, then run `python3 infra/scripts/seed-secrets.py --env eval`. The helper generates the eval UID HMAC value when missing and seeds the default Gemini/Anthropic mappings. Supply repeated `--map ENVVAR=base-id` flags instead when the operator's `eval_llm_secrets` or `stt_secrets` has additional or different configured keys (the flags replace the default map). Verify enabled version metadata for all referenced secrets, including the existing allowlist. Do not put secret values in command arguments, tfvars, plans or git.

3. From `infra/`, review a full saved plan before applying it. It provisions the dedicated eval Cloud Run worker/backend, database, queue, bucket and service-account/IAM bindings. Preserve currently deployed app SHAs and operator variables as described above, and inspect any staging/production drift before approving. After healthy dedicated services and their IAM are verified, dispatch `deploy-eval` on current CI-green `main`.

The release preflight checks service existence/access only; it does not validate every secret version, provision resources or replace the owner's infrastructure review.

### Auth-email staging activation (two phases)

> Historical: the staging/eval modules this section targets were removed from the legacy root; new staging/eval are managed by `infra/isolated-environment/`.

Verification is sent by the API; password-reset requests enqueue a durable `reset-email` task and the worker generates the action link and sends through Resend. The API can also send a reset as a fallback if enqueueing fails. Both therefore need the email settings and the same environment's Resend key. The shared Identity Platform user pool is project-wide.

Defaults remain `resend_secret_wired={staging=false,prod=false}`. The API has its public app origin and From header already, but no key until activation. Worker email settings, Resend accessor, and action-link IAM are all gated off by default. Activation grants the worker `roles/secretmanager.secretAccessor` on `resend-api-key-staging` only and a custom project role `workerAuthEmail_staging` containing only `firebaseauth.users.sendEmail`. The existing API `roles/firebaseauth.admin` grant is also gated. The worker generates reset links without user lookup or signing; [Google's `accounts.sendOobCode` reference](https://docs.cloud.google.com/identity-platform/docs/reference/rest/v1/accounts/sendOobCode) documents the action-link permission.

1. Create only the staging secret shell from `infra/` (no plaintext or secret versions enter Terraform):

   ```bash
   terraform plan -target='module.staging.google_secret_manager_secret.resend' -out=staging-resend-shell.tfplan
   terraform apply staging-resend-shell.tfplan
   ```

2. The owner verifies the Resend sending domain, creates a sending-only key, and adds an enabled version of `resend-api-key-staging` in Secret Manager. The seed helper can alternatively read the key from the environment with `python3 infra/scripts/seed-secrets.py --env staging --map RESEND_API_KEY=resend-api-key` (run from the repo root; supply the environment securely, never put the value in a command, tfvars, or a plan). Confirm version metadata only before proceeding. An empty shell cannot start a Cloud Run revision that references it.

> Legacy root note: it is prod only now, so its `resend_secret_wired` and `git_sha` accept only the `prod` key (`{ prod = false }`); a leftover `staging` key in `infra/terraform.tfvars` fails validation (remove it). Staging's equivalent lives in `infra/isolated-environment/`. The `staging` examples in this historical block no longer apply to the legacy root.

3. After the version exists, persist this non-secret setting in the operator's existing ignored `infra/terraform.tfvars` (or an existing `*.auto.tfvars` file), retaining every other operator variable and replacing any existing `resend_secret_wired` assignment rather than duplicating it:

   ```hcl
   resend_secret_wired = { staging = true, prod = false }
   ```

   Terraform automatically loads those filenames from its root, so a later ordinary plan/apply retains staging activation. Use the complete two-entry map; setting only `staging` fails validation. An explicitly named operator tfvars file instead needs `-var-file` on every plan. Carry the non-secret activation setting into every checkout used to operate this state; git deliberately excludes local tfvars. Then make a narrowly targeted activation plan from `infra/`. Supply the services' currently deployed commit SHAs to preserve `GIT_SHA`; `STAGING_SHA` and `PROD_SHA` below are operator variables, not secrets.

   ```bash
   terraform plan \
     -var 'resend_secret_wired={staging=true,prod=false}' \
     -var "git_sha={staging=\"${STAGING_SHA}\",prod=\"${PROD_SHA}\"}" \
     -target='module.staging.google_secret_manager_secret_iam_member.resend_api' \
     -target='module.staging.google_secret_manager_secret_iam_member.resend_worker[0]' \
     -target='module.staging.google_project_iam_member.api_firebaseauth_admin[0]' \
     -target='module.staging.google_project_iam_custom_role.worker_auth_email[0]' \
     -target='module.staging.google_project_iam_member.worker_auth_email[0]' \
     -target='module.staging.google_cloud_run_v2_service.api' \
     -target='module.staging.google_cloud_run_v2_service.worker' \
     -out=staging-resend-activate.tfplan
   terraform show staging-resend-activate.tfplan
   terraform apply staging-resend-activate.tfplan
   ```

Review the saved plan before applying: targets include dependencies, so confirm every planned change is intended and no production resource changes. Terraform preserves each service's CI-owned image, but rewrites its env, including any CI-only `LLM_PROVIDER`/`LLM_MODEL` overrides (see below). After activation, verify healthy API and worker revisions, effective traffic, verification delivery, and queued password-reset delivery with an owner-controlled account. Re-run the staging deploy if needed to restore CI overrides. `latest` secret env values resolve when a revision starts; rotate by deploying fresh revisions.

The explicit `-var 'resend_secret_wired={staging=true,prod=false}'` above also makes the initial activation plan self-contained. Retain the same map in the automatically loaded operator tfvars file for later plans/applies. Without either input, false defaults disable email wiring. Production activation remains a separate rollout; these commands neither create nor activate its Resend resources. Targeting is an exceptional staged rollout tool; review a subsequent full plan for unrelated drift without applying it automatically.

### Cutover: shared `anthropic-api-key` to per-env secrets (one-time, owner decision 2026-11-20)

> Historical: the staging/eval modules this section targets were removed from the legacy root; new staging/eval are managed by `infra/isolated-environment/`.

A Cloud Run revision that references a secret with no version fails to deploy, so the new secrets must have values before services switch. Terraform drops the old shared secret from state without deleting it (`removed` block, `destroy = false`), so live revisions keep working until you delete it. Order:

```bash
cd infra && terraform init
# (a) create only the empty per-env secrets; services still use the old secret
terraform apply -target='module.staging.google_secret_manager_secret.provider' -target='module.prod.google_secret_manager_secret.provider'
# (b) seed values: staging key, then a DIFFERENT prod key
cd .. && ANTHROPIC_API_KEY=<staging key> python3 infra/scripts/seed-secrets.py --env staging
ANTHROPIC_API_KEY=<prod key> python3 infra/scripts/seed-secrets.py --env prod
# (c) full apply: moves accessor grants and the worker env refs to the per-env secrets, forgets the old secret
cd infra && terraform plan && terraform apply
```

Then dispatch `deploy-staging` / `deploy-prod` (or just confirm the new worker revisions are healthy) and, once both envs work on the new keys, delete the orphaned shared secret `anthropic-api-key` in the console (or `gcloud secrets delete`). Rotate the old key since it was shared.

## Deploy workflow guard (fork safety)

`deploy-staging.yml` runs after CI via `workflow_run`. That trigger's `branches: [main]` filter matches the head branch name, so a fork PR from a branch named `main` would match, and the deploy job would check out fork code with WIF access. The `build` job therefore requires `workflow_run.event == 'push'`, `head_repository.full_name == github.repository` and `head_branch == 'main'`; every other job `needs` it. `scripts/ci/test_workflow_run_guard.py` (run in CI) enforces this for any `workflow_run` workflow and bans `pull_request_target`. The WIF `attribute_condition` in `infra/deployer.tf` only checks the repository; tightening it to a ref is a separate owner apply.

## Eval access

The eval backend allowlist is a comma-separated list of emails in Secret Manager `eval-allowed-emails-{env}` (case-insensitive, spaces around commas ignored). The service reads it as env `EVAL_ALLOWED_EMAILS` (secret ref, `latest`). Anyone signed in but not on the list gets 403; no token gets 401.

Edit in the console: Secret Manager, open `eval-allowed-emails-{env}`, **+ New version**, paste the FULL list (it replaces the old one), Add. A running revision keeps the old value, so deploy a new revision (Cloud Run, **Edit & deploy new revision**, **Deploy**).

Edit with the script (value never printed):

```bash
EVAL_ALLOWED_EMAILS="a@x.com,b@y.com" python3 infra/scripts/seed-secrets.py --env eval --allowlist
```

## LLM provider and model

Which provider, model and reasoning effort the text routes (evaluation LLM calls) use, and where to change them.

- **Default:** `config/{env}/routes.yaml` (baked into the image). Staging routes point at Claude (`anthropic/claude-sonnet-5-5`); prod is unchanged.
- **Override (staging):** set GitHub repo variables (Settings > Secrets and variables > Actions > Variables) `LLM_PROVIDER` (`anthropic`, `gemini`, or `openai`) and `LLM_MODEL` (a tier id listed in `config/models.yaml`, e.g. `claude-sonnet-5-5`, `gemini-4-neon`, `gpt-6.1-sol`), then re-run `deploy-staging` (or push to `main`). Set both or neither. Optionally set `LLM_EFFORT` to an exact lowercase effort supported by every effective text tier (`none`, `low`, `medium`, `high`, `xhigh`, or `max` where supported). Effort may be set independently of provider/model; empty values preserve the route defaults. `deploy-staging.yml` validates all three using the runtime loader before cloud authentication, image publishing or deployment, and passes only validated values to the api and worker services. Invalid pairs, unsupported efforts, whitespace and separators fail this preflight. Runtime loading also rejects invalid configuration (the api loads routes at startup but does not need provider keys). The voice relay does not load these routes.
- **Override (production):** set separate repository variables `PROD_LLM_PROVIDER`, `PROD_LLM_MODEL` and optional `PROD_LLM_EFFORT`, then dispatch `deploy-prod` and approve its single production deployment prompt. Provider/model must be paired; effort may be set alone if every effective prod text model supports it. The workflow still promotes the exact digest that ran on staging API, worker and voice; it does not rebuild. Before any production changes or approval, nonblank settings are checked by the promoted image's own runtime loader and `config/prod/routes.yaml`, using a trusted workflow-ref validator in an isolated container with no network, credentials or workspace mount. Unsupported pairs, efforts and older images that lack requested override support fail resolve. Only validated values reach prod API and worker, never voice. Staging's `LLM_*` repository variables do not control production.
- **Blank values and timing:** editing repository variables does not change running services; settings take effect on the next corresponding deployment. Clearing all three staging or production variables and deploying writes empty runtime overrides, restoring that image's checked-in route defaults. Production's all-blank LLM preflight avoids requiring the newer override API from historical images; all existing source/image configuration and staging-digest guards still apply, so sufficiently old releases missing `config/models.yaml` remain blocked. A prod version tag selects source/image provenance, not a snapshot of repository variables: a rollback uses the current `PROD_LLM_*` settings, so clear them to restore that image's defaults or choose values its catalog supports.
- **Provider, model and effort:** provider is the API vendor (`openai`, `anthropic`, `gemini`); model is the exact catalog tier ID within that provider (`gpt-6.1-sol`, for example); effort controls the model's supported reasoning effort. There is no fourth tier variable: `LLM_MODEL` / `PROD_LLM_MODEL` already contains the tier ID. For production OpenAI selection, use `PROD_LLM_PROVIDER=openai`, `PROD_LLM_MODEL=gpt-6.1-sol`, `PROD_LLM_EFFORT=medium`; keep staging's existing variable names for an independent staging selection. Provider credentials must be provisioned separately in each environment before selecting it; mounting a key does not change model selection.
- **Precedence (low to high):** `routes.yaml` < `MITI_MODEL_*` < `LLM_PROVIDER`/`LLM_MODEL` < `LLM_EFFORT` < preset overlay. Only concrete text routes are rewritten; aliases follow their target. Effort changes `extra_params.reasoning_effort`, preserving other extra parameters and token caps. Neither override changes `oneshot`; presets apply last.
- **models.yaml:** the override reads `config/models.yaml`, found at `<ROUTES_FILE dir>/../models.yaml` (`/app/config/models.yaml` in the images; `MODELS_FILE` overrides the path). It is shipped in the api/worker image (`COPY config /app/config`) and the eval backend image (whitelisted in `eval/backend/Dockerfile.dockerignore`). `scripts/ci/check_config.sh` fails the build if it is missing in the repo or image.
- **Secret names:** `anthropic-api-key-staging` mounted as `ANTHROPIC_API_KEY` and `gemini-api-key-staging` as `GEMINI_API_KEY` on the worker (Terraform `llm_secrets`; prod uses `-prod`). Nothing to add in Terraform to switch between the two. The worker fails at startup if the key for the selected provider is missing.
- **Rollback (back to Gemini):** set `LLM_PROVIDER=gemini` and `LLM_MODEL=gemini-4-neon`, clear `LLM_EFFORT` or select a supported Gemini effort, then re-run `deploy-staging`. To drop all overrides, clear all three variables and re-run the deploy; routes.yaml applies again.
- **Terraform drift:** runtime `LLM_PROVIDER`, `LLM_MODEL` and `LLM_EFFORT` are set by CI on every api/worker deploy and mirrored in Terraform by the `llm_provider`/`llm_model`/`llm_effort` variables (legacy root: blank defaults = `deploy-prod` with no `PROD_LLM_*`; isolated root: `null` omits them, set the live values in its tfvars for staging). If they differ from live, an apply rewrites the env to the Terraform values (the routes.yaml default applies until the next deploy), so refresh the variables from the live service first. After a deploy changes them, the next plan shows drift until the variables are updated. Same pattern as `GIT_SHA` above.
- **Durable operator tfvars:** on the ops machine, `/root/.cache/onolys-terraform/legacy.tfvars`, `staging.tfvars` and `eval.tfvars` (git-ignored, no secrets) hold each root's non-secret inputs; pass them with `-var-file`. `git_sha` (every root) and `llm_provider`/`llm_model`/`llm_effort` (staging; legacy prod keeps them blank) must be refreshed from the live Cloud Run env after each deploy (`gcloud run services describe ... --format=json`, non-secret env only). Isolated staging also needs no extra blocks for Identity Platform: `multi_tenant` and `sign_in.phone_number` are declared to match the API defaults.
- **Authorized sign-in domains (`onolys`):** `identity-config.py` adds the declared list and removes only `local.retired_authorized_domains` in `infra/identity.tf` (deleted sites: the old app staging site, the admin sites). Firebase defaults and unlisted hosts (preview channels, `onolys.com`) are never removed. To retire another host, add it to that list (and drop it from `authorized_domains`); use `--dry-run` to preview. Eval signs in through its own project, so `eval.onolys.com`, `onolys-eval-staging.web.app` and `onolys-eval-app.web.app` are in the retired list and are removed from `onolys`; `onolys-staging` and `onolys-eval` declare their own hosts in the isolated root.
- **Eval service:** eval selection remains per run in its UI, independently of both sets of app repository variables. There are no `EVAL_LLM_*` deployment selection variables. The per-run picker reads `models.yaml`; selecting OpenAI resolves `openai/<tier>` through the existing LiteLLM client. Runtime keys must be mounted before executing that provider. It does not require a GitHub Actions secret.

### OpenAI runtime opt-in

`config/models.yaml` includes `gpt-6.1-sol` (low, medium, high, xhigh, max),
`gpt-6.1-terra` and `gpt-6-luna` (none, low, medium, high, xhigh, max).
Their picker default is medium. The existing route defaults remain active until a
per-run selection or deployment override is made. For a staging override, use
`LLM_PROVIDER=openai`, `LLM_MODEL=gpt-6.1-sol`, `LLM_EFFORT=medium` (or another supported
combination). Empty `LLM_EFFORT` preserves the route's current effort, rather than
selecting the catalog default.

Owner setup before live OpenAI execution: provide an existing Secret Manager secret
version and extend the environment's runtime secret map with `OPENAI_API_KEY`.
For the eval instance, a local tfvars override is:

```hcl
eval_llm_secrets = {
  GEMINI_API_KEY    = "gemini-api-key"
  ANTHROPIC_API_KEY = "anthropic-api-key"
  OPENAI_API_KEY    = "openai-api-key"
}
```

The existing module adds the `-eval` suffix and mounts the value on the eval worker;
use `llm_secrets` for staging/prod (`-staging`/`-prod`). Keep the existing entries.
Follow the secret-shell, seed and deployment sequence below. Supply secret values
through the secure runtime provisioning process; do not put them in tfvars, Git,
CI variables, logs or examples. The committed maps deliberately retain their current
defaults so deployment does not depend on a new, unpopulated secret.


## Adding an LLM or STT provider

1. **tfvars line.** The committed default already holds the two shipped providers (`GEMINI_API_KEY = "gemini-api-key"` for the evaluation routes, `ANTHROPIC_API_KEY = "anthropic-api-key"` for the `claude` preset). For a further provider, in a `terraform.tfvars` (local, not committed) extend the map, keeping the default entries (shown here with the optional `OPENAI_API_KEY`):
   ```hcl
   llm_secrets = {
     GEMINI_API_KEY    = "gemini-api-key"
     ANTHROPIC_API_KEY = "anthropic-api-key"
     OPENAI_API_KEY    = "openai-api-key"
   }
   ```
   STT keys go in `stt_secrets` (empty by default; Google STT uses the worker service account, not a key). The tfvars value is the BASE id; the module creates `<base>-staging` and `<base>-prod`. `terraform plan` must show exactly two new secret shells (one per env), their accessor bindings (that env's worker only) and one env ref per worker; existing resources unchanged. As in the cutover above, create the shells first with a `-target` apply, seed, then do the full apply, otherwise the new revision references a secret with no version.
2. **Seed the value** per env, with that env's own key: `GEMINI_API_KEY=<staging key> python3 infra/scripts/seed-secrets.py --env staging` (the default map covers Gemini and Anthropic; for another provider add `--map ENVVAR=base-id` and pass every `--map` you want checked), then the same with the prod key and `--env prod`. Pass every `--map` you want checked; unset variables keep their existing version.
3. **Route.** Add a route (or preset) in `config/{staging,prod}/routes.yaml` with `litellm_id: <provider>/<model>` and `api_key_env: <ENVVAR>` (the map key; shipped routes use `GEMINI_API_KEY`). For STT, add a provider under `providers:` in `config/{env}/stt_providers.yaml`, then point `default`, `by_language` or a preset's `stt` at it.
4. **Ship.** PR, merge to `main` (deploys staging), then dispatch `deploy-prod`. The new secret is only mounted on a new revision, which the deploy creates. CI fails if a config file is missing for an env.

## Runbook: a user reports a failed session

The failed session card shows the **session id** as its Reference. All app logs are one JSON line per event on Cloud Run stdout (Cloud Logging `jsonPayload.*`); lines carry ids and codes, never content. Fields, the link template and the `error_code` details are in [logging.md](logging.md).

1. **Open the session trail** (Logs Explorer, project `onolys`; both envs share it): `jsonPayload.session_id="<session id>"`, or the link template in [logging.md](logging.md#reference). Add `resource.labels.service_name=("onolys-api-prod" OR "onolys-worker-prod")` to pick the env. Sort ascending to read in order; for one run add `jsonPayload.run_id="<rid>"`.
2. **Find the failure:** add `jsonPayload.status="failed"`. Read `error_code`, `exc_class`, `step`, `code_version` (deployed sha). For a provider error read the `llm_provider_error` line just before it (`http_status`, `error_type`, `provider_error`).
3. **Errors with no session** (Settings cards, API-only calls) show a `request_id` instead: `jsonPayload.request_id="<id>"`.
4. **Match the `error_code`** below, fix or advise, then tell the user what the code says: Try again (transient), start a new session (`permanent_internal`) or upload a different file (`user_file`).

Verified 2026-11-20 against the task-10 test lines (staging, `error_code t10_test`, written for the alert check) through the REST API `POST https://logging.googleapis.com/v2/entries:list` with body `{"resourceNames":["projects/onolys"],"filter":"jsonPayload.request_id=\"t10b-1795181702\"","orderBy":"timestamp desc"}`: it returned the one `onolys-worker-staging` line (`status failed`, `session_id synthetic`, `step test`); the filter `jsonPayload.session_id="synthetic"` returned that line plus the `onolys-api-staging` one (`request_id t10-1795181472`); the alert filter (`resource.type="cloud_run_revision"`, service name in the two staging services, `jsonPayload.status="failed"`) matched both.

Alerts (prod always on; staging only with `staging_alerts=true`): an email for each `status="failed"` line (at most one per 5 min) and for more than 5 api 5xx responses in 5 min. The email channel needs its verification click.

### Slow or stuck transcription

`transcribe` logs `stt_started` (`stt_operation` = the Chirp operation name, `stt_started`) and every poll logs `stt_poll` (`poll_n`, `elapsed_s`, `stt_operation`, `outcome` pending|ready). Trail: `jsonPayload.session_id="<sid>" jsonPayload.event=("stt_started" OR "stt_poll")`; look the operation name up in the Speech-to-Text v2 operations API to see Chirp's own state.

Limits: the poll cap is `clamp(STT_CAP_FACTOR x audio seconds, STT_CAP_MIN_S, STT_TIME_LIMIT_S)` (defaults 3, 300 s, 1200 s; stored on the step as `stt_limit_s`), then `transcription_failed`. Each poll queues the next poll before it asks Chirp, so a poll that dies cannot stop the chain; a failed enqueue answers 5xx (Cloud Tasks retries the same poll) and, on the last attempt, fails the session. There is no scheduler. If a chain still stops, the session is failed on the next `GET /v1/sessions/{id}` or list call once `updated_at` is older than cap + 60 s (`session_stale` log line, `status=failed`, `exc_class=StaleSession`); the web app does not poll, so the session shows `transcribing` until something reads it through the API.

### `error_code` table

The code in the failed log line is the public code `to_public` (`api/src/onolys_api/adapters/error_map.py`) gives; the same code is in the session status and the error card. All codes: `api/src/onolys_api/errors.py`, schema `docs/contracts/public/public-error-response.schema.json`.

| `error_code` | Meaning | Usual fix |
|---|---|---|
| `upstream_unavailable` | LLM or STT provider failed or timed out (retryable; one retry is automatic) | Check Google (Gemini) / Anthropic status; check the worker has its secret ref and a valid key (`GEMINI_API_KEY`); user presses Try again shortly (at most 3 times) |
| `transcription_failed` | A non-transient STT error (a transient one stays `upstream_unavailable`) | Ask for a different file; look at `exc_class` (`SttProviderError`); check `config/{env}/stt_providers.yaml` and the STT service agent's bucket access |
| `no_speech` | No usable speech found | Nothing to fix; user uploads another recording |
| `speakers_not_separated` | Diarization could not separate speakers | Nothing to fix; another recording |
| `deadline_exceeded` | Run exceeded its time limit (retryable) | Run again; if repeated check the provider's latency and worker timeout (900 s) |
| `rate_limited` | Provider or API rate limit | Wait; if frequent lower load or raise the provider tier, then `worker_max_instances` |
| `invalid_parameters` | Engine rejected the input (`InputError`) | Not an outage; see the session input; fix the request |
| `internal_error` | Anything else (pack error, unexpected exception, test fixture miss) | Read `exc_class`, then the trail; likely a bug or bad config (routes file, missing secret); roll back if it started with a deploy |
| `daily_cap_reached` | Per-user evaluation day cap (`EVAL_CAP_DAY`, 10) or concurrent-run limit (HTTP 429, `period=day`) | Expected; raise the cap for one user in the console (Per-user limits) or the default via `EVAL_CAP_DAY` |
| `interview_cap_reached` | Per-user AI interview day cap (`AI_CAP_DAY`, 5) (HTTP 429, `period=day`) | Expected; raise for one user in the console or the default via `AI_CAP_DAY` |

Other public codes (`unauthenticated`, `not_found`, `invalid_state`, `conflict`, `unsupported_audio`, `audio_too_large`, `audio_too_long`, `audio_unreadable`, `rating_invalid`, ...) are returned to the client as 4xx and are not `status=failed` lines. A rise in 5xx without `failed` lines: filter `httpRequest.status>=500` on `onolys-api-{env}`.

### Rollback

Release = dispatch `deploy-prod` with `sha` empty (promotes the commit staging runs now) or a specific `sha`. Every successful deploy is tagged `prod-<UTC date>.<n>` (annotated tag on the promoted commit, message has sha, image digest, run URL) by the final `tag` job; rollbacks are tagged too, and only after the healthz smoke passes. The newest `prod-*` tag = last fully successful deploy; to undo a bad release, roll back to the tag before it. After a failed run prod may be mixed (check `/v1/healthz` `code_version` or the revisions' `GIT_SHA`). Rollback = dispatch `deploy-prod` with `version=<prod tag>`; it redeploys api, worker, web and rules from that tag's commit. `v*` = optional human release trigger; `prod-*` = bot record of each successful deploy; roll back only by `prod-*` version or `sha`.

If a rollback deploy succeeds but its `tag` job fails, prod is on the new commit but untagged (the newest `prod-*` tag is then stale): check `/v1/healthz` `code_version` for what is really live.

List prod versions: `git ls-remote --tags --refs --sort=-v:refname origin 'prod-*' | head`.

Details (from `.github/workflows/deploy-prod.yml`): Actions > deploy-prod > Run workflow > `version` = e.g. `prod-2026-11-21.1` (or `sha` = the full 40-char commit; set one, not both; empty both promotes the commit staging api runs now). The commit must have been built by `deploy-staging` (image tagged with that sha in Artifact Registry), and that image (the tag's index digest or one of its platform digests) must have run on both staging api and staging worker with `GIT_SHA=<sha>`, otherwise `resolve` fails ("never ran on ... deploy it to staging first"). Approve the one `production` review prompt. After it finishes, the prod revisions carry `GIT_SHA=<sha>`, and `code_version` in new log lines shows it. The `prod-*` tags cannot trigger `deploy-prod` (they do not match `v*`, and tags pushed with `GITHUB_TOKEN` trigger nothing). Firestore data is not rolled back. The `resolve` job holds staging deployer credentials, so it never executes code from the target sha: the config guard (`check_config.sh`, source tree and `--image`) is the workflow ref's copy, taken before the checkout and run with an empty environment (`env -i`) against the target tree as data, and the matcher runs as `python3 -I`.

### Prod promotion + rollback drill (2026-11-21)

**(a) Promotion, run 44922391380.** Promoted `096e3edde31fe4134cb588c092201691bf774a83`; production review approved; all jobs passed (resolve, rules, web, deploy-api, deploy-worker, smoke, tag) in ~4.5 min.

- Prod api revision `-00003-brc`, worker `-00004-nh4`, `GIT_SHA` `096e3ed`.
- Prod api digest equals staging: `sha256:88045a94675bc4417eed09e22acf5647bc8d408b192a5750845f02e758580c9f`.
- Healthz `https://onolys-app.web.app/v1/healthz` returned 200, `code_version` `096e3ed`.
- Tag created: `prod-2026-11-21.1`.

**(b) Rollback, run 44922869893.** Rolled back to `205a03fa48aa2a43416d8be1dacd130a9a20d9a0`. Deploys and smoke passed:

- api `-00004-hjw`, worker `-00005-96t`, `GIT_SHA` `205a03f`.
- Digest `sha256:ff0fad588e301b216d548b2dcd0214da70f190ab5ced8149a75b16c0980f07c9`; healthz 200.
- The `tag` job FAILED: "refusing to allow a GitHub App to create or update workflow .github/workflows/ci.yml without workflows permission". Cause: the shallow checkout in the tag job made the push upload the old commit's objects (including the workflow file). Fix is in PR #42 (full history checkout).
- Prod currently runs `205a03f`, untagged.

**(c) Roll-forward by tag: not run.** Deferred by the owner (2026-11-21). To finish later: merge #42, dispatch `deploy-prod` with `version=prod-2026-11-21.1` (expect a new tag), then a blank dispatch for the main head.

**Earlier failed attempts** (nothing deployed by either): 44914754450 (checkout deleted the creds file, fixed in #40); 44918021819 (index digest vs platform digest mismatch, fixed in #41).

## Acceptance sweep (SP06, 2026-11-21)

Measured live on 2026-11-21 (about 16:50-17:05 UTC) with ADC REST calls (Cloud Run v2, Cloud Tasks, Storage, Firestore, Identity Toolkit admin/v2, Service Usage, Secret Manager, IAM, Monitoring, Logging, Billing Budgets), `curl`, `gh`, the Firestore emulator and `terraform plan` (read-only, `-lock=false`, no apply). PRD: `docs/agent_files/feat-miti-platform-20261120-0153/06-infra/PRD.md` AC1-AC10, R8, R13. Prod runs `205a03f` (rollback of `096e3ed`); staging api live traffic is `096e3ed`.

| AC | Result | Evidence |
|---|---|---|
| AC1 | MET | `terraform` 1.9.8 in `~/.local/bin`, ADC quota project still `juno-medical-clarity`, no `gcloud`. `terraform init` + `validate` ("configuration is valid") + `plan` succeed. `plan -target=module.prod` (with `staging_alerts=true` and the live `git_sha` map): **No changes**. Unscoped plan: see "Terraform plan results" below (staging drift only, not a gap in the sweep) |
| AC2 | MET | Per env: bucket `onolys-audio-{env}` public access prevention `enforced`, uniform access on, soft-delete `0s`, versioning off, `uploads/` delete lifecycle (age 1), CORS PUT/HEAD for the env origin. Queue `steps-{env}` `maxAttempts 2`, backoff 5-30 s. Cloud Run limits match R8 (table below). Firestore `(default)` and `staging`: `FIRESTORE_NATIVE`, `us-central1`, PITR disabled (`(default)` delete-protection on). All 21 APIs in `local.apis` enabled (Service Usage). Identity Platform: email sign-in enabled, sign-up not disabled, password policy `ENFORCE` with `minPasswordLength 8`, `mfa.state DISABLED`. Rules emulator tests (`firestore-rules-test`, `firebase-tools` 14.27.0 `emulators:exec`): 16 pass, 0 fail, including the 3 listener cases (owner listen after create ok, other user denied, missing doc denied). Live rules releases exist for `cloud.firestore` (prod, 16:16Z) and `cloud.firestore/staging` (16:01Z) |
| AC3 | MET | Bucket IAM: `storage.objectAdmin` only for that env's `api-{env}`/`worker-{env}` (plus Speech service agent `objectViewer`). `datastore.user` bindings are conditioned `resource.name == "projects/onolys/databases/staging"` (staging SAs) and `.../(default)` (prod SAs). Secret IAM: each env's secrets list only its own SAs. Anonymous `GET` on `onolys-worker-prod` and `onolys-worker-staging` returns 403; worker `run.invoker` is only `tasks-invoker-{env}`; api (`/v1/healthz` direct run.app URL) returns 200 and its invoker is `allUsers` |
| AC4 | MET | Worker env in both envs has `ANTHROPIC_API_KEY` (secret ref `anthropic-api-key-{env}`) and no other provider key; no `STT_*` var (full env list checked). `stt_secrets = {}`: no STT secret exists. Plan with an extra `llm_secrets` entry `GEMINI_API_KEY` (prod-targeted): creates exactly `provider["GEMINI_API_KEY"]` shell, and `worker_provider` accessor bindings, and updates the worker service (env refs); 3 to add, 2 to change, 0 to destroy; nothing else touched. Image carries `config/` (`api/Dockerfile` `COPY config /app/config`) and `deploy-staging.yml` runs `test -s /app/config/<env>/<file>.yaml` per file against the image digest before deploy; both envs run `ROUTES_FILE=config/{env}/routes.yaml` and serve `/v1/healthz` 200 |
| AC5 | MET | `deploy-staging` run 44922123760 (workflow_run after CI 44921577408 on `096e3ed`) succeeded. Repo secrets: only `ANTHROPIC_API_KEY` (nightly); no GCP JSON key; WIF vars only. `https://onolys-app-staging.web.app/v1/healthz` 200 with `code_version 096e3ed`. Signed PUT CORS: preflight `OPTIONS` to `onolys-audio-staging` with the staging origin returns 200 and `access-control-allow-origin: https://onolys-app-staging.web.app`; real signed-URL upload through that origin passed in SP09 (`staging-e2e.md`) |
| AC6 | MET | `deploy-prod` run 44922391380: `production` environment approved by Tejit, all jobs passed, api digest equal to staging (`sha256:88045a94...`). GitHub environment `production` has `required_reviewers` (tejitpabari99) and a branch policy. `deployer-prod` can be impersonated only by `principalSet .../attribute.environment/production`; the provider condition is `assertion.repository=='Onolys/onolys'` (state ACTIVE), so forks and other workflows cannot mint a token for it |
| AC7 | MET | Budget `onolys monthly` (USD 20; 50 %, 90 %, 100 % current, 100 % forecast) with channel `Onolys owner email` (id 749283734341274206), project-scoped. Note: a second, non-Terraform budget `onolys` (USD 20; 50/80/100 %, project-level recipients) also exists on the billing account; left untouched. Cloud Run: api max 10 prod / 3 staging, concurrency 80; worker concurrency 2, max 3 both envs. Queues: `maxConcurrentDispatches 6` in both (2 x 3), `maxDispatchesPerSecond 5` |
| AC8 | MET | This page: resource names, env var table, outputs (incl. `VITE_FIRESTORE_DATABASE`), DNS records, runbook (reference id query, `error_code` table, rollback). DNS section refreshed against `terraform output` today: `app.onolys.com` is now `OWNERSHIP_ACTIVE`, `HOST_ACTIVE`, `CERT_ACTIVE` (was missing on 2026-11-20) |
| AC9 | MET (drill partial) | Live revisions carry the deployed commit: staging api (traffic revision `onolys-api-staging-096e3ed-34-1`) and worker `GIT_SHA=096e3ed...`; prod api and worker `205a03f...` (healthz `code_version` agrees on `app.onolys.com`, `onolys-app.web.app` and the run.app URL). Rollback drill run 44922869893 (earlier sha `205a03f`) redeployed rules, web, api and worker and passed smoke; its `tag` job failed (fix in PR #42, unmerged). Roll-forward by tag deferred by the owner; see the drill section above |
| AC10 | MET (owner confirmed email arrived, 2026-11-21) | Test line written to prod at launch check: `request_id sp06-sweep-1795279972`, `status=failed`, `error_code sp06_sweep_test`, service `onolys-worker-prod`, 16:52:52Z. Alert `0.ofa4aj5s6bk0` on policy `Onolys failed step/run (prod)` opened 16:53:06Z (14 s later), state OPEN. Runbook query `jsonPayload.request_id="sp06-sweep-1795279972"` through `entries:list` returned that one line. Policies `Onolys api 5xx rate (prod|staging)` and metrics `onolys-api-5xx-{env}` exist and are enabled. The agent did not read the owner's inbox: owner to confirm one email "Onolys failed step/run (prod)" arrived. Staging precedent: 71 s incident, SP09 Task 10 |

Cloud Run limits as measured (R8): api 1 CPU / 1 GiB, 60 s, concurrency 80; worker 2 CPU / 2 GiB, 900 s, concurrency 2; R13: `deploy-staging.yml`, `deploy-prod.yml`, `_deploy-cloudrun.yml` exist; every deploy authenticates by WIF.

### Terraform plan results

Command: `cd infra && terraform plan -var staging_alerts=true -var 'git_sha={staging="096e3edde31fe4134cb588c092201691bf774a83",prod="205a03fa48aa2a43416d8be1dacd130a9a20d9a0"}' -lock=false`.

- `-target=module.prod`: **No changes** (prod has no drift).
- Unscoped: `Plan: 0 to add, 2 to change, 0 to destroy`, both on staging, both known and pre-existing, not a sweep failure:
  - `module.staging...google_cloud_run_v2_service.api`: its template is currently the no-traffic PR-42 preview revision (`onolys-api-staging-pr-42-fc89744-14-1`: `SERVICE_MODE=combined`, `ADAPTERS=stub`, preview `CORS_ORIGINS`, `GIT_SHA=fc89744`, `cpu_idle=false`) while 100 % of traffic stays on `onolys-api-staging-096e3ed-34-1`. A preview deploy replaces the service template. Plan would reset it to the real template.
  - Staging worker is not drifting (`GIT_SHA` already `096e3ed`).
  - Follow-up DONE (fix/ci-preview-and-prod-guard): `pr-preview.yml` now runs `scripts/ci/pr_preview.sh restore-template` right after the preview deploy (and `pr-preview-cleanup.yml` runs it again, no-op when already matching). It reads the revision that serves traffic and PATCHes the service `template` back to that revision's config (Cloud Run v2, `updateMask=template`, service etag; traffic and the `pr-<N>` tag are untouched), creating one 0 %-traffic revision `onolys-api-staging-pr-<N>-tpl-<epoch>` that cleanup / sweep delete like any preview revision. After a preview the staging template matches the main revision again (no drift, nothing inherits preview mode). The pr-42 drift above predates this fix; apply or the next staging deploy clears it.

### Open-until-measured items (Task 15)

**(a) Worker `max-instances`: KEEP 3 (prod and staging).** Evidence: the Anthropic rate tier (owner step 7a) is not recorded anywhere (`docs/implementation/infra-staging-first-apply.md`: "unknown, owner to confirm"). SP09 measured N=1 only: no back-off, every run 1 attempt, 42-68 s to `report_ready` (default preset, 8,486 in / 1,303 out tokens); N=6 parallel is not measured; no real prod runs exist yet. Worker memory is not a constraint (`validate` peak 0.23 of 2 GiB). Decision: `worker_max_instances` stays 3, so the queue cap stays 6 (2 x 3). To raise: once the tier is confirmed and an N>1 staging run shows no 429 / back-off, set `worker_max_instances` (tfvar); the dispatch cap follows as 2 x new max, then confirm `maxConcurrentDispatches` with the Cloud Tasks API.

**(b) Preview-channel authorised domain (vs SP00 task 9): wildcard REJECTED.** `onolys-app-staging--pr-*.web.app` returns `400 INVALID_AUTHORIZED_DOMAIN` (checked 2026-11-20, `testing.md` "Preview auth domains"); this is not retried. SP00 task 9 fallback (add each channel host through the Identity Toolkit API) exists as `infra/scripts/identity-config.py --domains-only --add-domain HOST` (add-only; Terraform ignores `authorized_domains` drift) but is not wired into the preview workflow. Owner decision 2026-11-21: Google sign-in on previews is not needed (email/password works there), so no workflow step and no `firebaseauth.admin` on the preview deployer. Live list today: `localhost`, `onolys.firebaseapp.com`, `onolys.web.app`, `app.onolys.com`, `onolys-app.web.app`, `onolys-app-staging.web.app`; no `pr-*` host. Closed (won't-fix, owner).

**(c) Hosting `/v1` pass-through: SP09's acceptance, referenced only.** `staging-e2e.md` Task 11(a): Hosting forwards `Authorization`, `/v1` not cached (`no-cache`, no `HIT`/`Age`), AC11 there. Spot check today: `/v1/healthz` returns 200 through `app.onolys.com`, `onolys-app.web.app` and `onolys-app-staging.web.app`.

### Owner confirmations (2026-11-21)

- AC10 prod alert email ARRIVED: "[ALERT - No severity] Onolys failed step/run (prod)" for `onolys-worker-prod` revision `onolys-worker-prod-00005-96t` (Google Cloud Alerting, 11:53 local). AC10 fully met.
- Worker `max-instances`: keep 3 (owner decision).
- Unmanaged budget `onolys`: keep (owner decision).

### Needs the owner

- Anthropic rate tier (step 7a) if `worker_max_instances` is ever raised (currently kept at 3).
- Merge PR #42 (tag job fix); then the deferred roll-forward-by-tag drill if wanted.
