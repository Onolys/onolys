# Architecture

High-level design: how the system fits together.

**Audience:** everyone.

Onolys has a web app, a public API with a background worker, one MITI engine, and a small admin shell.

```
web app --/v1--> api (+ worker) --imports--> onolys_miti
                    |                           |-- LLM (LiteLLM routes)
                    |                           |-- speech-to-text
                    |                           `-- voice (Gemini Live)
                    `-- Firestore, Cloud Storage, Cloud Tasks
admin site --/v1/me--> admin backend (login check only)
```

## Engine: `onolys_miti`

[`engines/miti/`](../engines/miti/README.md) is a Python package with MITI 4.2.1 built in. It holds the MITI definition, prompts, fixtures and report schema (`src/onolys_miti/data/`), the coding and tips passes, and the infrastructure the api needs:

| Part | Job |
|---|---|
| `run_miti(...)` | Transcript in, no-rating report out. Passes: `code`, `tips`, `assemble`. |
| `llm/` | The one interface to every model call: routes (model choice as data), live, fixture and failing clients. |
| `stt/` | Speech-to-text providers (Google Chirp, fixture). |
| `voice/` | The Gemini Live adapter for the AI practice interview. |

Models propose; code checks quotes against the transcript and computes the scores.

## API and worker: `onolys_api`

[`api/`](../api/README.md) serves the public `/v1` API ([reference](reference/public-api.md), [schemas](contracts/)). One image runs as `api`, `worker` or `combined` (`SERVICE_MODE`). A session goes: create, upload audio, validate, transcribe, confirm speakers, run, report. The run calls `onolys_miti`. The api also relays the AI practice interview ([ADR 0024](decisions/0024-ai-practice-interview-gemini-live-relay.md)). Auth is Identity Platform ID tokens or API keys; data is in Firestore and Cloud Storage.

## Web app: `web/`

A React + TypeScript app. It talks to the api on the same origin (`/v1`), listens to session status in Firestore, and renders the report. Hosting and CSP: [ADR 0021](decisions/0021-web-app-hosting-and-sharing.md). It validates nothing about MITI itself; the api and engine own the report shape.

## Admin shell: `admin/` and `frontend/`

An internal site behind a login. The backend (`admin/backend`) serves only `GET /v1/me`; `admin/auth` verifies the token and the email allowlist. The frontend is sign-in plus an empty page. See [ADR 0023](decisions/0023-admin-deployment-and-auth.md) and [backend-api.md](reference/backend-api.md).

## Infrastructure

GCP with Terraform, staging and prod: [reference/infra.md](reference/infra.md), [ADR 0022](decisions/0022-infra-gcp-terraform-two-environments.md).

More: [implementation/](implementation/), [decisions/](decisions/), [testing/](testing/).
