# Transcript format: transcript.v1

`transcript.v1` is the JSON shape for a session transcript. Its source of truth is
`TranscriptV1` in `engines/miti/src/onolys_miti/transcript_v1.py`. The generated JSON
Schema ships at `engines/miti/src/onolys_miti/data/transcript.v1.schema.json`.
The format name is not a field in the JSON object.

| Transcript field | Type | Required | Meaning |
|---|---|---|---|
| `turns` | array of turn objects | Yes | Turns in transcript order; array order is authoritative |
| `language` | string or null | No | Transcript language; omitted means null in the model |
| `duration_ms` | integer or null | No | Session duration in milliseconds; omitted means null |

| Turn field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | Yes | Unique within this transcript and containing a non-whitespace character |
| `speaker` | string | Yes | Speaker label containing a non-whitespace character |
| `role` | `"clinician"`, `"client"`, or null | No | Supplied role, or null until speaker confirmation; omitted means null |
| `text` | string | Yes | Speech text containing a non-whitespace character |
| `start_ms` | integer or null | No | Turn start in milliseconds; omitted means null |
| `end_ms` | integer or null | No | Turn end in milliseconds; omitted means null |

When both turn times are present, `start_ms` must be less than or equal to `end_ms`.
Either time can be absent. Turns are never sorted by time or ID. Strings are preserved
as supplied, including surrounding whitespace; validation does not rewrite speech,
speaker labels, or IDs. Roles are case-sensitive. An unknown role is an error.

Only the listed fields are supported. Session provenance such as `stt_run` and per-turn
`language` are outside this format. The core shape permits an empty `turns` array;
upload and coding input checks impose their own content and size requirements. Upload
handling supplies `en` when the language is omitted.

This synthetic example shows the shape; the text and labels are not from a real session:

```json
{
  "language": "en",
  "turns": [
    {"id": "t1", "speaker": "T", "role": "clinician", "text": "Example text."},
    {"id": "t2", "speaker": "C", "role": null, "text": "Another example."}
  ]
}
```

The JSON Schema checks field types, nonblank strings, allowed roles, and unknown fields.
Pydantic additionally checks unique turn IDs and start/end ordering, which standard
JSON Schema cannot express here. Validate through `TranscriptV1.model_validate(...)`
for the complete contract.

Regenerate the schema from the repository root after changing the model:

```bash
uv run --package onolys-miti python - <<'PY'
import json
from pathlib import Path
from onolys_miti.transcript_v1 import TranscriptV1
path = Path("engines/miti/src/onolys_miti/data/transcript.v1.schema.json")
path.write_text(
    json.dumps(TranscriptV1.model_json_schema(), indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
PY
```

`engines/miti/tests/test_transcript_v1.py` regenerates and compares the exact file content,
so the engine tests fail when the committed schema drifts from the model.
