# Architecture

High-level design: how the system fits together.

**Audience:** everyone.

Onolys has a web app, a public API with a background worker, one MITI engine on a shared engine core, and an internal evaluation site.

```
web app --/v1--> api (+ worker) --registry--> MitiEngine (onolys_miti)
                    |                           |-- onolys_engine_core (LLM, transcript, context)
                    |                           |-- speech-to-text
                    |                           `-- voice (Gemini Live)
                    `-- Firestore, Cloud Storage, Cloud Tasks
eval site --/v1--> eval backend --onolys_api.auth + eval allowlist--> Identity Platform + allowlist
```

## Shared engine core: `onolys_engine_core`

[`engines/core/`](../engines/core/pyproject.toml) holds transcript types and parsing,
`RunContext`, LLM clients and route presets, safe logging, output validation, and the
`Engine` interface and registry. It imports no MITI code; an AST boundary test enforces
that separation. API and eval import these shared types directly from
`onolys_engine_core`, without compatibility re-exports in `onolys_miti`.

Each engine declares its output schema and runs asynchronously, returning an
`EngineResult` with output, artifacts and usage metadata. The API explicitly registers
MITI in `onolys_api.engines`; `PROD_ENGINE` selects the engine (default `miti`). Engine
and preset listings mark the configured production choices; `DEFAULT_PRESET` selects
the production route preset.

## Engine: `onolys_miti`

[`engines/miti/`](../engines/miti/README.md) is a Python package with MITI 4.2.1 built in. It holds the MITI definition, prompts, fixtures and report schema (`src/onolys_miti/data/`), the coding and tips passes, and audio adapters used by the api:

| Part | Job |
|---|---|
| `run_miti(...)` | Transcript in, no-rating report out. Passes: `code`, `tips`, `assemble`. |
| `MitiEngine` | Adapts `run_miti` to the core `Engine` interface and declares the report schema. |
| `stt/` | Speech-to-text providers (Google Chirp, fixture). |
| `voice/` | The Gemini Live adapter for the AI practice interview. |

Models propose; code checks quotes against the transcript and computes the scores.

## API and worker: `onolys_api`

[`api/`](../api/README.md) serves the public `/v1` API ([reference](reference/public-api.md), [schemas](contracts/)). One image runs as `api`, `worker` or `combined` (`SERVICE_MODE`). A session goes: create, upload audio, validate, transcribe, confirm speakers, run, report. The run resolves `MitiEngine` through the registry and calls its `run` method. The api also relays the AI practice interview ([ADR 0024](decisions/0024-ai-practice-interview-gemini-live-relay.md)). Auth is Identity Platform ID tokens or API keys; data is in Firestore and Cloud Storage.

The API image includes core and MITI wheels. It copies the eval workspace manifest for
frozen dependency resolution, without installing eval or shipping datasets. CI has a
separate core job for lint, offline tests and the import boundary. A core change also
runs MITI, API and eval checks through workspace dependency flags.

## Web app: `web/`

A React + TypeScript app. It talks to the api on the same origin (`/v1`), listens to session status in Firestore, and renders the report. Hosting and CSP: [ADR 0021](decisions/0021-web-app-hosting-and-sharing.md). It validates nothing about MITI itself; the api and engine own the report shape.

## Evaluation auth and retained admin frontend

The evaluation backend reuses the prod api auth (`onolys_api.auth` `IdTokenVerifier` / `verify_claims`) to verify Identity Platform tokens, plus an eval email allowlist (`EVAL_ALLOWED_EMAILS`, `eval/backend` `allowlist.py`). See [shared auth](reference/backend-api.md). The former admin backend source and deployment workflow have been retired. `frontend/` remains the legacy sign-in shell; its existing cloud resources and `admin.onolys.com` auth domain are retained. [ADR 0023](decisions/0023-admin-deployment-and-auth.md) records the original deployment design.

## Infrastructure

GCP with Terraform, staging and prod: [reference/infra.md](reference/infra.md), [ADR 0022](decisions/0022-infra-gcp-terraform-two-environments.md). Terraform is planned on PRs and applied by each environment's deploy pipeline, before the app: [reference/infra-pipeline.md](reference/infra-pipeline.md), [ADR 0026](decisions/0026-terraform-plan-apply-in-ci.md).

More: [implementation/](implementation/), [decisions/](decisions/), [testing/](testing/).
