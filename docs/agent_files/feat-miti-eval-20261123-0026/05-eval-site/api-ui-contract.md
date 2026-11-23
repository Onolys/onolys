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

Status is `ready`, `awaiting_speakers`, `transcribing`, or `failed`. Failures include an `error: {code, message}` object with safe public details.

Authenticated, allowlisted `GET /v1/uploads/{upload_id}` returns the same upload-response shape. The UI polls while `transcribing` and stops on ready, awaiting speakers, failed, or unmount.

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

## History and detail (Tasks 6 and 9)

`GET /v1/runs` returns `{"runs": [RunSummary]}`.

RunSummary mirrors saved run fields: `run_id`, `status`, `created_at`, `input`, `engines`, `presets`, `repeats`, `change_goal`, `language`, `coded_span`, `total_units`, `completed_units`, `done_units`, `failed_units`, `cancelled_units`, `usage`, `cost_usd_est`, `unpriced_units`, `engine_versions`, `engine_git_sha`, and `resolved_presets`. Omit `input_ref` and raw snapshot paths from summaries.

`GET /v1/runs/{rid}` returns `{...RunSummary, "units": [{"unit_id": "id", ...unitrecord}], "compare": Compare}`. Unit output is inline when stored inline; spilled output is loaded lazily.

Authenticated `GET /v1/runs/{rid}/units/{uid}/output` returns the raw JSON object for the JSON view.

## Rerun

`POST /v1/runs/{rid}/rerun` accepts `{"engines": ["ids"], "presets": ["names"], "repeats": 1}` and returns `{"run_id": "id", "status": "status"}`. It calls internal `create_run(input_ref=saved_input_ref)` and preserves immutable inputs and session configuration. The request body cannot replace the input.

Frontend Task 9 prefills New Run with `rerunSourceID` and calls the rerun endpoint on Start, retaining original snapshots. The cancel endpoint already exists from Task 5.

## Compare

```text
Compare = {
  has_human: boolean,
  metrics: [{id, group: counts|globals|summaries, label}],
  sessions: [{
    session_id,
    human: Record<metric_id, number|null>|null,
    cells: [{
      engine, preset, n, failed, unit_ids: [ids],
      values: Record<metric_id, {mean, min, max, n}>,
      diff?: Record<metric_id, number|null>
    }]
  }],
  aggregates: [{engine, preset, metrics: EXACT onolys_eval.metrics.aggregate output}],
  notes: [strings]
}
```

The metric list has 16 rows: ten behavior counts, four globals, `reflection_question_ratio`, and `pct_cr`.

- Mean/min/max use successful unit values; nulls are skipped with a separate `n` per metric. Failed units are excluded from values.
- Per-session `diff` is the signed difference of the cell mean against its Human value.
- Compare and aggregate calculations use existing metrics for each successful unit against its session Human. Aggregate across sessions **and repeats**; `n` counts successful unit comparisons. Preserve the exact existing `onolys_eval.metrics.aggregate` result shape.
- MAE labels must explicitly say **over successful run units**; do not compute errors only from cell means.
- Without Human: `has_human=false`, with no error columns, `diff`, or MAE. Pending/failed Human has `human=null` and reference count `n=0`.

