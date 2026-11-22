# Configuration

Environment variables for the api and the MITI engine. Sources: `api/src/onolys_api/config.py` (`Settings.from_env`), `api/.env.example`, `engines/miti/src/onolys_miti/llm/routes.py`. The admin backend has its own list in [backend-api.md](backend-api.md#environment-variables).

**Audience:** users.

Provider keys are the standard variables LiteLLM reads, for example `GEMINI_API_KEY`. They are never logged. A route whose `api_key_env` is unset stops startup with an error naming the variable.

## Api and worker

| Variable | Default | Meaning |
|---|---|---|
| `ENV` | none (required) | `local`, `test`, `staging` or `prod`. `local` and `test` are refused on Cloud Run. |
| `SERVICE_MODE` | `combined` locally, else `api` | `api`, `worker`, `combined` or `voice`. |
| `AUTH_MODE` | `fake` locally, else `idp` | `fake` (`Bearer test:<uid>`, only `local`/`test`) or `idp` (Identity Platform). |
| `ADAPTERS` | `stub` locally, else `real` | `stub` or `real` STT and LLM adapters. |
| `GCP_PROJECT`, `REGION`, `AUTH_PROJECT` | empty | Project, region, and the project whose ID tokens are accepted. |
| `FIRESTORE_DATABASE` | `(default)` | Database name (`staging` in staging). |
| `AUDIO_BUCKET` | empty | Cloud Storage bucket for audio. |
| `CORS_ORIGINS` | empty | Comma-separated exact origins. |
| `TASKS_QUEUE`, `TASKS_SA`, `WORKER_URL` | empty | Cloud Tasks queue, its service account, and the worker URL. |
| `ROUTES_FILE`, `DEFAULT_PRESET` | empty | Model routes file and preset; see [llm-client.md](../implementation/llm-client.md). |
| `ENABLED_EXTRA_PRESETS` | empty | Presets besides the default that users may pick. |
| `MAX_ACTIVE_RUNS` | `1` | Runs in flight per user. |
| `EVAL_CAP_DAY`, `AI_CAP_DAY` | `10`, `5` | Daily run and AI-interview caps per user. |
| `STT_CAP_FACTOR`, `STT_CAP_MIN_S`, `STT_TIME_LIMIT_S` | `3`, `300`, `1200` | STT poll cap is the factor times the audio seconds, clamped to the min and max. |
| `GIT_SHA` | `dev` | Version stamp. |
| `UID_HMAC_KEY` | empty | Keys the `uid_hash` log field. Required in staging and prod (Secret Manager `uid-hmac-key-{env}`). |
| `VOICE_URL` | `ws://localhost:8081` locally, else empty | Voice relay base URL. |
| `AI_MAX_SECONDS`, `AI_WARN_SECONDS`, `AI_MIN_SECONDS` | `600`, `480`, `300` | AI interview hard cap, user warning time, shortest recording sent on. |
| `AI_TOLERANCE_SECONDS`, `AI_ABANDON_COUNT_SECONDS`, `AI_REFUNDS_PER_DAY` | `30`, `30`, `3` | Interview timing tolerance, the abandon threshold for a refund, and refunds per day. |
| `AI_RECONNECT_SECONDS`, `AI_MIC_GATE` | `60`, `false` | Relay wait for a dropped client; mic gate. |
| `AI_MAX_FRAME_BYTES`, `AI_MAX_AUDIO_BYTES_PER_S`, `AI_MAX_CONNECTS` | `65536`, `128000`, `30` | Relay abuse caps. |

STT and voice providers come from `config/{env}/stt_providers.yaml` and `voice_providers.yaml` in the image, not from environment variables.

## MITI engine

| Variable | Default | Meaning |
|---|---|---|
| `MITI_MODEL_CHEAP`, `MITI_MODEL_MID`, `MITI_MODEL_STRONG` | from the routes file | LiteLLM model id for that route. Applied before a preset's overrides. |
| `MITI_LLM_RESPONSE_FORMAT` | from the routes file | `json_object` or `json_schema`, set on every full route. |
| `MITI_LLM_RECORD` | unset | `1` wraps the live client and writes fixtures for replay. |
| `MITI_LIVE_PRESET` | unset | Route preset for the live checks. |

Routes used by the engine: `miti_code`, `miti_globals`, `tips`. Details: [engines/miti/README.md](../../engines/miti/README.md).
