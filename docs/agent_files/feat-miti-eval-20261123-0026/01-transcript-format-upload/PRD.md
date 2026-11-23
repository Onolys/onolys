---
status: draft
summary: transcript.v1 as the one transcript format, transcript upload (.json/.txt) in API + web, caller-chosen coded_span (full transcript by default)
date: 2026-11-23
---
# PRD: Transcript format, transcript upload, coded_span (SP1)

**Repo/branch:** Onolys/onolys · `feat/miti-eval` · **Depends on:** nothing (Phase 1) · **Owns:** `engines/miti/src/onolys_miti/{transcript.py,transcript_v1.py (new),transcript_txt.py (new),span.py,prepare.py,run.py,result.py,run_info.py}`, `engines/miti/src/onolys_miti/data/{transcript.v1.schema.json (new),miti-result.schema.json,report.schema.json}`, `api/src/onolys_api/routes/{transcript.py (new),sessions.py,runs.py,speakers.py}`, `api/src/onolys_api/jobs/{transcribe.py,machine.py,first_run.py}`, `api/src/onolys_api/{errors.py,adapters/*}`, `web/src/features/upload/*`, `web/src/features/session/SessionPage.tsx`, `docs/contracts/public/*` (regenerated), `docs/reference/transcript-format.md` (new), `docs/mission.md` (full-session wording)

## TL;DR
One transcript shape (`transcript.v1`, = the engine `Turn` shape) used by STT output, uploads, and the engine. Users can submit a `.json` or `.txt` transcript instead of audio, in the app and API; it counts as one session like audio. Callers can pass `coded_span`; absent means the engine codes the whole transcript. No migration: no real data, no users, breaking changes OK.

## Problem
- The app only accepts audio [verified: `routes/audio.py`, `UploadSlot.tsx` accept `.mp3,.wav,.m4a,.webm,.ogg`]. Public coded datasets (CASAA, SP2) are transcripts only.
- The engine picks the coded span itself: whole session up to 20 min, else a seeded random 20-min window [verified: `span.py` `select_coded_span`, `run.py:64,274`]. Callers cannot choose, so engine output cannot be compared with human coding of a stated segment.
- The format is implicit: `Transcript`/`Turn` in the engine, a separate `TranscriptTurn` view in the API [verified: `transcript.py`, `docs/contracts/public/transcript-view.schema.json`], with `speaker` optional and `stt_run` mixed in.

## Goals / Non-Goals
| Goals | Non-Goals |
|---|---|
| Documented, JSON-schema'd `transcript.v1`; STT writes it | Migrating stored data |
| Upload `.json`/`.txt` in web + API, one session of usage | PDF/DOCX/SRT/VTT input |
| `coded_span` (time or turn range) API → engine; default = full transcript | Moving types to `engines/core` (SP3) |
| Clear errors: empty, malformed, too long, too many speakers | Storing the original uploaded file |
| | Eval-site features, dataset files (repo is public: never commit data) |

## Requirements
**R1 Format.** `transcript.v1` = `{language?, duration_ms?, turns:[{id, speaker, role?: clinician|client, text, start_ms?, end_ms?}]}`. Rules: `id` unique non-empty; `speaker` non-empty string; `text` non-empty after trim; `role` null until the gate or supplied; `start_ms<=end_ms`; turn order = array order. `stt_run` and per-turn `language` are not part of v1 (provenance stays on the session).
**R2 Single source.** Pydantic model `TranscriptV1` in a self-contained module (imports only pydantic) plus generated `transcript.v1.schema.json`; engine `Transcript`, API `TranscriptView` and the STT adapters use it. Prose spec in `docs/reference/transcript-format.md`.
**R3 Upload API.** `PUT /v1/sessions/{id}/transcript` on a `created` session; body is the file content (`Content-Type: application/json` or `text/plain`), max 1 MB. Server validates/converts, stores via `put_transcript`, sets `transcript_ready`, and calls the first-run gate as the STT poll does. No signed-URL/validate/transcribe steps.
**R4 `.txt` parser.** UTF-8 (BOM stripped, CRLF normalised). A line `Label: text` starts a turn when `Label` is 1-40 chars, no colon, at line start. `T`/`C` (case-insensitive) → speaker `T`/`C`, role clinician/client. Any other label → speaker = label, role null (speaker gate decides). Non-label lines append to the previous turn; blank lines ignored; text before the first label is an error. Ids `t1..tn`. No timestamps in v1 of the parser [DEFERRED: `[mm:ss]` prefixes].
**R5 Speaker gate.** If every turn has a role, the clinician label is set and `speaker_confirmed` is true (gate skipped). Otherwise normal gate (`awaiting_input`, `speaker_confirmed=false`). If roles are present but more than one distinct speaker is `clinician`, reject (`transcript_invalid`) because the engine `speaker_map` takes one label.
**R6 Usage.** No new accounting: usage is counted when the run starts (`decide_start`, kind `eval`, units = `n_runs`) [verified: `repo/limits.py`], which the transcript path reaches via the same first-run gate. Daily-cap hold works unchanged.
**R7 `coded_span`.** Accepted on `POST /sessions` (stored, used by the first run) and `POST /sessions/{id}/runs` (overrides). Shape: `{start_ms,end_ms}` xor `{start_turn,end_turn}`. Both ranges are half-open and 0-based for turns (`[start,end)`), matching the existing overlap rule in `prepare.select_turns`. Absent = whole transcript. Time spans on a transcript without timestamps, or turn ranges past the end, are 422 `invalid_coded_span` (not the silent `span_ignored` warning for explicit spans).
**R8 Engine.** `run_miti` honours `params["coded_span"]`; `_ENGINE_ONLY_PARAMS` and the "ignored (R7)" docstring go. `select_coded_span`'s random-window logic stays as a helper (`default_window`), never applied automatically (main app included, owner D3). Also in scope: update `docs/mission.md` to say the full session is coded when no `coded_span` is given. Result/report `coded_span` and `run_info.span.mode` (`whole|explicit|random_window`) are extended to carry both span forms.
**R9 Limits.** Request body 1 MB; max 5,000 turns, 20,000 chars per turn, 8 distinct speakers; at least 50 words (reuse `no_speech`/`empty_transcript`). Coded portion over the engine's `duration_max` (25 min, `pack.yaml`) or a new word cap (default 6,000 words) fails `session_too_long` with a clear message asking the caller for a narrower `coded_span` (main app and eval alike; no automatic 20-min window).
**R10 Web.** New-session page gets an "Audio | Transcript" choice; transcript accepts `.json,.txt`, 1 MB precheck, same error cards. Session page shows the speaker gate when roles are missing. Copy for the usage note is the same as audio.

## Architecture
```
audio  → validate → STT ─┐
.json/.txt → PUT /transcript → parse+validate ─┴→ TranscriptV1 → put_transcript → [gate] → first-run gate (usage) → run_miti(coded_span?)
```
```jsonc
// coded_span (API == engine == report)
{"start_ms": 0, "end_ms": 1200000}   // or
{"start_turn": 0, "end_turn": 120}
```
Session state: transcript sessions go `created → awaiting_input` directly (new transition in `jobs/machine.py`), with `stt` null.

## Decisions
| # | Decision | Choice | Alternatives | Why |
|---|---|---|---|---|
| 1 | Upload transport | Direct `PUT` of the file body, 1 MB cap | Signed GCS URL like audio | Transcripts are ~20 KB; no validate/transcode steps needed |
| 2 | Original file | Not stored, only normalised v1 | Keep original | PHI minimisation; v1 is lossless for our use |
| 3 | `role` | Optional in v1, null until gate | Required | `.txt` with names has none; gate exists |
| 4 | Turn range semantics | 0-based, half-open | Inclusive; by turn id | Same as ms overlap rule; no id lookup |
| 5 | Explicit bad span | 422 | Warn and code everything | Silent fallback corrupts comparisons |
| 6 | `coded_span` on session create and run | Both | Run only | First run auto-starts, so create needs it |
| 7 | Schema generation | Pydantic → `transcript.v1.schema.json` in engine `data/` | Hand-written | One source; file moves with module in SP3 |
| 8 | Usage | Existing run-start accounting | Count at upload | Already 1 session per run for audio |

## Manual steps
- None for deploy (no infra change). Owner: confirm product copy for the transcript option.

## Risks / Open Questions
- [RESOLVED: full session everywhere (owner D3)] Absent `coded_span` = whole transcript in the main app and eval; the API does not apply `default_window`. `docs/mission.md` wording ("whole session if <=20 min, else 20-min window") is updated in this SP (code task, in scope). Sessions longer than the engine `duration_max` get a clear error asking for a `coded_span`.
- [RESOLVED: keep 25-min `duration_max` and 6,000-word cap] Over-limit sessions fail `session_too_long` with a message asking for a `coded_span` (same for eval). SP2 measures CASAA lengths; if they exceed the caps, the dataset manifest sets `coded_span` rather than raising limits.
- [RESOLVED: 8-speaker cap + speaker gate is enough] The gate shows the detected labels for the user to confirm; no extra heuristics in v1.
- [RESOLVED: default `en` when the file omits `language`] No UI question.
- [RESOLVED: verify at implementation] `test_golden.py`/`test_span.py` are updated as part of SP1 (fixtures untimed or <=20 min; random-window tests target `default_window`, which is kept as an unused-by-default helper).
- [RESOLVED: no comparison code change expected] Rating card `from_s/to_s` stays; SP1 adds a mapper if the new span form reaches it, verified at implementation.
- [RESOLVED: no migration] stored transcripts with `stt_run`/per-turn `language` need no handling.
- [DEFERRED] `[mm:ss]` timestamps in `.txt`; SRT/VTT; engine `Turn.language` removal check outside SP1 callers.

## Acceptance Criteria
- `transcript.v1.schema.json` is generated, validates STT output and uploaded `.json`, and CI fails if it drifts from the model.
- `PUT /transcript`: valid `.json` and `.txt` reach `awaiting_input` or the first run; empty → `empty_transcript`, malformed → `transcript_invalid` with `field`/`issue`, >1 MB or over limits → `transcript_too_large`/`transcript_invalid`; contracts in `docs/contracts/public` regenerated.
- `T:`/`C:` `.txt` skips the gate; `Name:` `.txt` shows it; two clinician labels rejected.
- A transcript session consumes exactly `n_runs` usage units at run start; a capped user gets `daily_cap_reached`.
- `coded_span` in both forms changes the coded turns and is echoed in the report; absent codes all turns; invalid spans return `invalid_coded_span`.
- Existing golden and span tests pass (updated only where default behaviour changed); web tests cover the transcript tab, precheck and errors.
