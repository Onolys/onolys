# Evaluation site (staging)

The founders-only [evaluation site](https://onolys-eval-staging.web.app) compares MITI 4.2.1 coding across engines, presets and human reference data. Sign in with a verified, allowlisted Firebase account. `eval.onolys.com` is the intended custom domain; its DNS and certificate must be ready before using it.

Choose **Dataset** to select stored sessions, or **Upload** for one audio recording, `transcript.v1` JSON, or UTF-8 `.txt`. In text files, `T:` identifies the clinician and `C:` the client; other labels require an explicit clinician selection. Text has no invented timestamps. For Google transcription, the default English `en` is sent as supported locale `en-US`; explicit locales are preserved. Audio uses automatic transcription and then asks you to select the clinician from actual speaker labels and samples. Supply the session change goal and language. See [transcript format](transcript-format.md).

Select engines, presets, and one or three runs per cell. Labels marked **(prod)** come from the configured production engine and preset; they are defaults, not evidence of accuracy. Dataset defaults select Human and the production engine/preset. Uploads offer Human only when an actual `gold.v1` file is attached. Human ignores the preset and repeat axes. Planned units equal `sessions × non-Human engines × presets × repeats + sessions with Human`.

Start opens persisted progress. Work runs through Cloud Tasks and continues after the browser closes. Reopen the run from History. Cancel stops pending work; an in-flight provider request may finish. History preserves inputs, timestamps, engine versions and Git SHA, resolved models, usage and estimated cost. **Rerun with different engines/presets** creates a new run from the original saved input snapshot. If the queued AI execution configuration changes before execution (code SHA, engine version or resolved models), the unit fails with `execution_config_changed` before calling the provider. Rerun preserves the input and records the new execution configuration.

Compare shows ten behavior counts, four globals, reflection-to-question ratio and percent complex reflections. Repeats show mean and minimum–maximum range, with successful sample counts. Summaries are recomputed from counts. Human enables signed per-session differences and mean absolute error (MAE) over successful run units, including repeats; failed units are excluded and denominators remain visible. Without Human there are no error columns. Each unit's output JSON is available for inspection.

Token totals are input plus output tokens. `~$` is an estimate, using provider-reported cost when available or bundled model prices otherwise; unknown prices remain unpriced. Speech transcription cost is excluded. There is no evaluation usage limit or cost cap. Queue concurrency constrains simultaneous work, not total spend. Uploads and run artifacts are retained until manually removed.

## HTTP API

The API base is `https://onolys-eval-backend-staging-1054076260967.us-central1.run.app`. Public application endpoints require `Authorization: Bearer <Firebase ID token>`; anonymous requests return 401 and unverified or non-allowlisted identities return 403. Tokens must belong to Firebase project `onolys`. Browser access is restricted to the configured evaluation origins.

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/me` | Confirm access |
| GET | `/v1/options?mode=dataset` | Engines, presets, defaults and production labels |
| GET | `/v1/options?mode=upload&upload_id=ID` | Upload-specific Human eligibility |
| GET | `/v1/datasets` | Available manifests |
| GET | `/v1/datasets/{id}` | Sessions, gold availability and coded spans |
| POST | `/v1/uploads` | Multipart `file`, optional `gold`, `change_goal`, `language`, JSON `coded_span` |
| GET | `/v1/uploads/{id}` | Transcription/speaker readiness |
| POST | `/v1/uploads/{id}/speakers` | Confirm `clinician_speaker` |
| POST | `/v1/runs` | Start a run |
| GET | `/v1/runs` | History |
| GET | `/v1/runs/{id}` | Progress, units, metadata and compare |
| GET | `/v1/runs/{id}/units/{unit}/output` | Unit output JSON |
| POST | `/v1/runs/{id}/cancel` | Cancel pending work |
| POST | `/v1/runs/{id}/rerun` | New run with engines, presets and repeats; input is preserved |

For example, a run request is:

```json
{"input":{"dataset_id":"casaa-miti421-video2013","session_ids":["rounder"]},"engines":["human","oneshot:miti"],"presets":["claude"],"repeats":1}
```

For an upload, use `"input":{"upload_id":"ID"}`. Engine and preset IDs must come from options. Repeats must be 1 or 3. Optional run fields are `change_goal`, `language`, and `coded_span`; dataset sessions use manifest configuration. Selected coding spans must fit the 25-minute/6,000-word limits. Transcript and gold files are capped at 1 MiB each; supported audio extensions are `.wav`, `.mp3`, `.m4a`, `.webm`, `.ogg`, capped at 300 MiB. Content and schema validation also apply.

`/internal/tasks/unit` and `/internal/tasks/transcribe` accept only verified Google OIDC tokens for the configured task service account and audience; a Firebase user token cannot invoke them.

## Storage and method limits

Only staging is supported. `eval/web` is the SPA; `eval/backend` authenticates users, schedules work and reads results. The backend calls registered engines in process rather than the main application API. Firestore database `staging` stores `eval_uploads`, `eval_runs`, and run `units`; browser clients have no direct database access. The private `onolys-eval-data-staging` bucket stores `datasets/<dataset>/manifest.json`, session `transcript.json`/`gold.json`, `uploads/<id>/` input and transcript artifacts, and large `runs/<run>/<unit>.json` outputs. Dataset source files are excluded from the deployment image.

These are transcript-based MITI 4.2.1 comparisons, not diagnosis or judgments of clinical correctness. Automatic speaker labels and times may be wrong. Utterance splitting and CASAA row coding rules can change counts. One consensus reference does not establish inter-rater reliability, validation or official MITI status. Review evidence with human judgment; this is not an official MITI product.
