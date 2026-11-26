# Decisions

Why is it like this? Architecture decision records. ADRs 0001-0016 (the old evidence-audit design) were removed; see [0025](0025-miti-only-lean-engine.md).

**Audience:** contributors.

| ADR | Decision |
|---|---|
| [0017](0017-workspace-routes-shared-core.md) | uv workspace, model routes and a shared `onolys_core` (superseded by 0025) |
| [0018](0018-protocol-pack-data-vs-code.md) | Protocol packs: data first, three code hooks, safe formulas (superseded by 0025) |
| [0019](0019-evaluation-engine-and-concern-suppression.md) | Evaluation engine: one in-process run, concern suppression before the decision table (superseded by 0025) |
| [0020](0020-public-api-contract.md) | Public `/v1` API contract: generated OpenAPI, stable names, vendored Redoc |
| [0021](0021-web-app-hosting-and-sharing.md) | Web app hosting: same-origin `/v1` rewrite, strict CSP, privacy checks as tests |
| [0022](0022-infra-gcp-terraform-two-environments.md) | Infrastructure: one GCP project, Terraform, staging and prod, STT in `us`, no residency claims |
| [0023](0023-admin-deployment-and-auth.md) | Admin deployment and auth: one Cloud Run service, direct calls, verified email plus allowlist, no MFA (superseded by 0025) |
| [0024](0024-ai-practice-interview-gemini-live-relay.md) | AI practice interview: Gemini Live via a server-side relay, separate Cloud Run service |
| [0025](0025-miti-only-lean-engine.md) | MITI-only lean engine; supersedes 0017, 0018, 0019, 0023; archive tag |
| [0026](0026-terraform-plan-apply-in-ci.md) | Terraform plan on PRs and apply in CI after merge; keyless WIF identities; amends 0022 D1 and D5 |
