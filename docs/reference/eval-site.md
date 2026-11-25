# Evaluation site (staging)

The founders-only [evaluation site](https://onolys-eval-staging.web.app) compares MITI 4.2.1 coding across engines, presets and human reference data. Sign in with a verified, allowlisted Firebase account. `eval.onolys.com` is the intended custom domain; its DNS and certificate must be ready before using it.

Choose **Dataset** to select stored sessions, or **Upload** for one audio recording, `transcript.v1` JSON, or UTF-8 `.txt`. In text files, `T:` identifies the clinician and `C:` the client; other labels require an explicit clinician selection. Text has no invented timestamps. For Google transcription, the default English `en` is sent as supported locale `en-US`; explicit locales are preserved. Audio uses automatic transcription and then asks you to select the clinician from actual speaker labels and samples. Supply the session change goal and language. Browser audio uploads normally use an authenticated eval upload-start request, a signed PUT directly to private storage, then an authenticated completion request. This is the same transport pattern as the main application; eval keeps its own upload records, storage paths and access checks. JSON and TXT transcripts, with optional gold, continue through multipart upload. See [transcript format](transcript-format.md).

Select engines, then pick **models**, **tiers** and **efforts** (options come from `models.yaml` via `/v1/options`), plus one or three runs per cell. A model (e.g. `claude`) has its own tiers (e.g. `claude-sonnet-5-5`), and each tier lists the efforts it supports. A run covers every valid combination `model/tier/effort`: each selected tier belongs to a selected model, each selected effort must be supported by at least one selected tier, and a combination whose tier lacks the effort is dropped (the UI shows the count preview and the dropped combinations). An invalid selection returns 422 with a specific message (unknown model/tier/effort, model without a tier, tier whose model is not selected, or no valid combination). The production default is the resolved `mid` route; labels marked **(prod)** come from the configured production engine and selection and are defaults, not evidence of accuracy. Dataset defaults select Human and the production engine and combination. Uploads offer Human only when an actual `gold.v1` file is attached.

Human is locked on for datasets: the server adds it automatically (the UI shows it checked and disabled), and it ignores the model/tier/effort and repeat axes. Planned units equal `sessions x (1 if Human + non-Human engines x combos x repeats)`. A run is capped at **499 units**; above that the request fails with 422 `Run has N units; the maximum is 499. ...`. A Human unit for a session without gold is kept but marked skipped (`no_gold`).

**`gold.v1` supports partial human labels.** Every label is optional; a missing or `null` value means "not labeled", never zero. `counts` may hold any subset of the ten count ids (each nonnegative integer or `null`); `globals` may be `null` or hold any subset of the four globals (integer 1 to 5 or `null`); `summaries` is optional and, when present, must equal the pack formulas over the labeled inputs (a summary is `null` when an input is missing or a denominator is zero). Optional metadata: `quality_label` (`"high"`, `"low"` or `null`, a session-level quality tag), `label_source` (provenance note, e.g. "human MITI 4.2.1") and `label_scheme` (free text, e.g. "MISC 2.5 mapped to MITI"). `source.coded_url`, `source.uncoded_url` and `source.sha256` are optional; `source.retrieved_at` stays required. A gold with no labels at all is valid. Existing full CASAA gold files validate unchanged. Comparison compares only fields present on both the gold and the engine side: other fields show `—` (null), are excluded from MAE, bias and within-1, and each aggregate reports its own `n`. `quality_label` is passed through to `compare.v1` (and to each session in the compare view, which shows a Quality label column when any session has one) so engine scores can be related to high/low quality.

Each combination re-points every LLM route of the base routes at the chosen model, tier and effort. Effort sets `reasoning_effort` and caps output tokens: low 16000, medium 32000, high 48000, max 64000, each bounded by the model's own maximum. Combination routes use a 300 s request timeout. The old preset path is deprecated: new runs ignore presets, and `presets` in the API is only accepted for stored legacy runs.

Start opens persisted progress. Work runs through Cloud Tasks and continues after the browser closes. Reopen the run from History. Each cell runs through the production run pipeline (the scheduler tick starts it; the production worker executes it). Cancel stops pending work; an in-flight provider request may finish. History preserves inputs, timestamps, engine versions and Git SHA, resolved models, usage and estimated cost. Rerun creates a fresh execution snapshot using the selected current configuration. **Rerun with different engines/selection** creates a new run from the original saved input snapshot. Rerun preserves the input and records the new execution configuration.

**Legacy runs.** Runs stored before the matrix carry preset names instead of a selection. They stay readable: History and Compare label their columns `preset: <name> (legacy)`, run summaries set `legacy_selection`; they are never executed again.

Compare shows one column per combination (`model/tier/effort`), with metrics as rows (transposed table); a failed unit shows its per-session error. A **Summary** tab gives per-combination means of counts, globals, reflection-to-question ratio and percent complex reflections, plus MAE when Human is present. Compare shows ten behavior counts, four globals, reflection-to-question ratio and percent complex reflections. Repeats show mean and minimum–maximum range, with successful sample counts. Summaries are recomputed from counts. Human enables signed per-session differences and mean absolute error (MAE) over successful run units, including repeats; failed units are excluded and denominators remain visible. Without Human there are no error columns. Each unit's output JSON is available for inspection.

Token totals are input plus output tokens. `~$` is an estimate, using provider-reported cost when available or bundled model prices otherwise; unknown prices remain unpriced. Speech transcription cost is excluded. There is no evaluation usage limit or cost cap. Queue concurrency constrains simultaneous work, not total spend. Uploads and run artifacts are retained until manually removed.

## HTTP API

The API base is `https://onolys-eval-backend-eval-1054076260967.us-central1.run.app`. Public application endpoints require `Authorization: Bearer <Firebase ID token>`; anonymous requests return 401 and unverified or non-allowlisted identities return 403. Tokens must belong to Firebase project `onolys`. Browser access is restricted to the configured evaluation origins.

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/me` | Confirm access |
| GET | `/v1/options?mode=dataset` | Engines, models/tiers/efforts, defaults and production labels |
| GET | `/v1/options?mode=upload&upload_id=ID` | Upload-specific Human eligibility |
| GET | `/v1/datasets` | Available manifests with original-source metadata (`source_media`, `transcript_origin`, `labels_summary`, `miti_version`, `overlaps_with`) |
| GET | `/v1/datasets/{id}` | Sessions, gold availability and coded spans |
| POST | `/v1/uploads` | Multipart JSON/TXT `file`, optional `gold`, `change_goal`, `language`, JSON `coded_span`; legacy clients may still send audio up to 25 MiB |
| POST | `/v1/uploads/audio` | Start every new browser audio upload: JSON `filename`, `content_type`, `size`, optional `gold` object, `change_goal`, `language`, `coded_span`; returns upload ID and signed PUT target |
| PUT | Signed storage URL returned by upload-start | Send the audio bytes with the returned headers and no application bearer token or cookies |
| POST | `/v1/uploads/{id}/complete` | Verify the stored recording and queue transcription; retryable without uploading successful bytes again |
| GET | `/v1/uploads/{id}` | Transcription/speaker readiness |
| POST | `/v1/uploads/{id}/speakers` | Confirm `clinician_speaker` |
| POST | `/v1/runs` | Start a run |
| GET | `/v1/runs` | History |
| GET | `/v1/runs/{id}` | Progress, units, metadata and compare |
| GET | `/v1/runs/{id}/units/{unit}/output` | Unit output JSON |
| POST | `/v1/runs/{id}/cancel` | Cancel pending work |
| POST | `/v1/runs/{id}/rerun` | New run with engines, selection and repeats; input is preserved |

For example, a run request is:

```json
{"input":{"dataset_id":"casaa-miti421-video2013","session_ids":["rounder"]},"engines":["human","oneshot:miti"],"selection":{"models":["claude"],"tiers":["claude-sonnet-5-5"],"efforts":["low"]},"repeats":1}
```

For an upload, use `"input":{"upload_id":"ID"}`. Engine, model, tier and effort IDs must come from options. Repeats must be 1 or 3. Optional run fields are `change_goal`, `language`, and `coded_span`; dataset sessions use manifest configuration. Selected coding spans must fit the 25-minute/6,000-word limits. Transcript and gold files are capped at 1 MiB each; supported audio extensions are `.wav`, `.mp3`, `.m4a`, `.webm`, `.ogg`, capped at 300 MiB. These are validation limits; browser audio uploads normally use direct storage at every supported size. Optional gold accompanies audio as parsed JSON in upload-start, while JSON/TXT transcripts and gold use multipart. Content and schema validation also apply.

If completion fails after a successful PUT, retry sends completion only. If the PUT response is lost, retry uses the same write-once target; an existing-object response leads to server verification before completion. An expired or denied signed PUT prepares a new upload on retry. For deployment compatibility, recordings up to 25 MiB fall back to the authenticated multipart endpoint only when signed upload-start returns a server error (5xx) or the initial storage PUT cannot connect. The fallback clears the pending direct attempt and never calls its completion endpoint, so unused stored bytes may remain but no second transcription is queued. Validation/authentication failures, storage HTTP errors (including 403), and completion failures do not trigger fallback; a storage 412 still proceeds to completion verification. Larger recordings require the signed flow.

Enabling direct storage for all recordings requires the eval bucket PUT CORS policy and runtime IAM signing permission (`roles/iam.serviceAccountTokenCreator` on its own service account) introduced in #58. Verify the backend signed endpoints and those infrastructure settings during rollout; the small-recording fallback preserves the existing upload path while those settings become available. Verify both a small recording and a recording above 25 MiB after applying the infrastructure. The multipart endpoint also remains available for older clients.

`/internal/tasks/tick`, `/internal/tasks/delete` and `/internal/tasks/transcribe` accept only verified Google OIDC tokens for the configured task service account and audience; a Firebase user token cannot invoke them.

## Releases

Eval releases independently of the app. Dispatch `deploy-eval` on current CI-green `main` to release the eval worker, backend, site and rules together; deploying staging or promoting production does not release eval. The eval worker uses the app runtime Dockerfile and shared engine code, with its own image package, digest and runtime configuration. Both eval services must carry the same release commit for the code-drift checks to pass. Active runs may fail those checks during an update. Provisioning prerequisites and recovery steps are in [infra.md](infra.md).

## Storage and method limits

Only staging is supported. `eval/web` is the SPA; `eval/backend` authenticates users, schedules work and reads results. The backend calls shared registered engines in process rather than the main application API. Engine coding logic and the direct-to-storage transport pattern are shared; eval orchestration remains separate: authenticated eval uploads, clinician selection, dataset manifests, Cloud Tasks, run records and result artifacts use the eval backend and its storage paths. Firestore database `eval` stores `eval_uploads` and `eval_runs` (a grouping doc per eval run; per-cell runs and reports use the session collections in that database); browser clients have no direct database access. The private `onolys-eval-data-staging` bucket stores `datasets/<dataset>/manifest.json`, session `transcript.json`/`gold.json`, and `uploads/<id>/` input and transcript artifacts. Dataset source files are excluded from the deployment image.

These are transcript-based MITI 4.2.1 comparisons, not diagnosis or judgments of clinical correctness. Automatic speaker labels and times may be wrong. Utterance splitting and CASAA row coding rules can change counts. One consensus reference does not establish inter-rater reliability, validation or official MITI status. Review evidence with human judgment; this is not an official MITI product.

## Dataset manifest: original source fields

A dataset `manifest.yaml` records what the dataset ORIGINALLY provides (we always store `transcript.v1`). The Dataset picker shows it as `Original: Video + audio + transcript · Transcript: human · Labels: ... · MITI 4.2.1 · Scheme: ...`, or `Original: Transcript only (no audio)`.

| Field | Type / allowed values | Notes |
|---|---|---|
| `source_media` | required list, unique, any of `audio`, `video`, `transcript` | What the original source offers |
| `transcript_origin` | optional: `human`, `auto_captions`, `translated`, `stt_ours` | Where the transcript came from |
| `labels_summary` | optional non-empty string | Human labels available, e.g. `MITI 4.2.1 behavior counts + 4 global ratings` |
| `miti_version` | required key: `4.2.1`, `4.2`, `4.0` or `null` | `null` = labels are not MITI-coded; the picker then shows `Not MITI-coded` instead of `MITI x` |
| `label_scheme` | optional non-empty string | Shown as `Scheme: ...`, e.g. `MITI 4.2`, `MISC 2.5 mapped to MITI`, `AnnoMI codes mapped to MITI`, `none` |
| `source_format` | `pdf` (default) or `mitags_csv` | `pdf`: per-session `coded_url`/`uncoded_url`. `mitags_csv`: dataset-level `source_files` (CSV URLs) and no per-session URLs |
| `sessions_from_source` | `false` (default) or `true` | `true` (non-pdf formats only): the YAML lists no `sessions`; they are derived from the fetched source file at `convert`/`upload`/`run` time and only the bucket `manifest.json` carries the full list. Keeps thousand-session datasets under the 200,000-byte repo guard (`welivita-mi`) |
| `overlaps_with` | optional list of `{dataset_id, note}` | Datasets sharing interviews |
| `sessions[].source_media` | optional per-session override, same values | |

Per-dataset sources, mappings and gaps: [eval-datasets.md](eval-datasets.md).
