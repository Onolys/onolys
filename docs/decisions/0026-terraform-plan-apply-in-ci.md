# 0026. Terraform plan on PRs and apply in CI after merge

**Audience:** contributors.

**Status:** accepted 2026-11-26. Amends [0022](0022-infra-gcp-terraform-two-environments.md) D1 ("run locally with ADC") and D5 (deploy auth only), and realizes the D18 `infra-plan.yml` item. Operating detail: [reference/infra-pipeline.md](../reference/infra-pipeline.md).

**Context.** Infrastructure was planned and applied by hand from one operator machine with git-ignored tfvars. That left drift between merged code and real infrastructure, no review of what a change does to the cloud, and a single machine as the only applier. The repository and its Actions logs are public, and pull requests from the same repository can run arbitrary workflow code.

**Decision.**

- **Plan on every PR, apply on merge.** `terraform.yml` plans prod (legacy root), staging and eval on PRs and posts one comment of resource addresses and actions (never values). After merge the same saved plan is applied. Manual apply remains for bootstrap and break-glass only.
- **Keyless identities, two per project.** Plan: `terraform-plan`, metadata-only (a custom role of get/list permissions plus verified read-only predefined roles; no data-read permission, enforced by a test), reachable by same-repo PRs through its own WIF pool. Apply: `terraform-apply`, project-admin-like, reachable only by the `terraform.yml` workflow on `main` through its own WIF pool; prod additionally requires the dedicated GitHub Environment `terraform-prod` (required reviewers, main only), separate from `production` so deploy approvals and infrastructure approvals do not authorize each other. No service account keys.
- **Saved plans stay private.** The plan goes to the private state bucket (`plans/`, expired after 7 days); only hashes travel in artifacts. The apply verifies the plan hash and the hash of the live deploy-managed inputs, and refuses to roll back a deploy that landed in between.
- **Environments are independent.** Each apply gates on its own plan result; prod asks for approval only when it has changes.
- **Not required checks.** The path-filtered plan jobs are not branch-protection checks (a skipped required check blocks unrelated PRs); the offline `infra` and `infra-isolated` jobs in `ci.yml` are.

**Consequences.** Merging an infra change changes real infrastructure within minutes (staging and eval immediately, prod after approval). The apply identity is powerful, so its trust boundary is the reviewed workflow file on `main` and the `terraform-prod` approval. Secrets and operator-only inputs stay out of Terraform. A new resource type must be added to the permission table or CI tests fail.
