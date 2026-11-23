---
status: approved
summary: SP5 routine backend/frontend wire contract for options, inputs and new runs
date: 2026-11-23
---
# SP5 API/UI wire contract

These routine wire decisions implement the approved PRD; they add no new design scope. Backend validation is authoritative.

## Options

`GET /v1/options?mode=dataset|upload[&upload_id=id]`

```json
{
  "engines": [{"id": "string", "label": "string", "engine": "string", "config": "optional", "prod": true, "version": "optional"}],
  "presets": [{"name": "string", "prod": true, "models": {}}],
  "defaults": {
    "dataset": {"engines": ["ids"], "presets": ["names"]},
    "upload": {"engines": ["ids"], "presets": ["names"]}
  }
}
```

`config` and `version` are optional fields. Engine IDs are `human`, `miti`, and `oneshot:miti`. SP5 binds the selected immutable one-shot config variant.

Human is offered for upload only when the actual saved upload has `has_gold=true`. An upload-mode query alone hides Human; query parameters cannot grant Human eligibility. The backend always validates actual gold, engine/preset selection and coded span.

## Datasets

- `GET /v1/datasets` returns `{"datasets": [manifestmetadata]}`.
- `GET /v1/datasets/{dataset_id}` returns the manifest with sessions.

## Uploads

`POST /v1/uploads` uses multipart fields: `file`, optional `gold`, `change_goal`, `language`, and optional `coded_span` encoded as JSON.

Response:

```json
{
  "upload_id": "id",
  "status": "ready",
  "has_gold": false,
  "speakers": [{"speaker": "label", "samples": ["strings"]}]
}
```

Status is `ready`, `awaiting_speakers`, `transcribing`, or `failed`. A failed response may include `"error": {"code": "string", "message": "string"}`.

Authenticated, allowlisted `GET /v1/uploads/{upload_id}` returns the same upload-response shape. The UI polls while `transcribing` and stops on a terminal state or unmount.

`POST /v1/uploads/{id}/speakers` accepts `{"clinician_speaker": "label"}` and returns the same upload-response shape.

## Start run

`POST /v1/runs` accepts:

```json
{
  "input": {"dataset_id": "id", "session_ids": ["ids"]},
  "engines": ["engineIDs"],
  "presets": ["names"],
  "repeats": 1
}
```

The alternate `input` shape is `{"upload_id": "id"}`. Optional top-level fields are `change_goal`, `language`, and `coded_span`. `repeats` is 1 or 3. Response: `{"run_id": "id", "status": "status"}`.

Human contributes one unit per session with no preset/repeat axes. Remaining units count as `sessions × non-Human engines × presets × repeats`.

## Later coordination

Task 6 defines history, detail and comparison contracts later and coordinates them with frontend Task 9. Do not invent those contracts here.
