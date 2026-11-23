---
status: draft
summary: SP1 tasks - transcript.v1 model+schema, .txt parser, engine/API adoption, coded_span end to end, PUT /transcript upload, web transcript tab
date: 2026-11-23
---
# Tasks: SP1 Transcript format, transcript upload, coded_span

Source of truth: /root/projects/onolys/iaudit/.worktrees/feat/miti-eval/docs/agent_files/feat-miti-eval-20261123-0026/01-transcript-format-upload/PRD.md. Breaking changes are fine (no users, no migration). Never commit dataset files (public repo). Tests are written first in every task and run only for the touched areas. Existing CI already runs engine, api and web tests, so no CI task is needed; new tests land in existing test trees.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | `transcript.v1` model, schema, prose spec | - | done |
| 2 | `.txt` parser and input limits | 1 | done |
| 3 | Adopt v1 across engine, STT adapters, API view | 1 | done |
| 4 | Engine `coded_span` and full-session default | 3 | done |
| 5 | `PUT /transcript` upload and speaker gate | 2, 3 | done |
| 6 | `coded_span` in API and contract regeneration | 4, 5 | done |
| 7 | Web transcript option and speaker gate | 6 | done |

## Task 1 — `transcript.v1` model, schema, prose spec
What it is: The one documented transcript shape every other piece uses. (R1, R2, Decision 7)
What changes at a high level: Add a self-contained pydantic model (imports only pydantic) enforcing the R1 rules: unique non-empty ids, non-empty speaker, non-blank text, optional role, ordered start/end times. Generate the JSON schema into the engine data folder from the model. Write the prose spec in the reference docs.
Done when: Unit tests cover each rule (valid, duplicate id, blank text, bad role, start after end, role null). A drift test regenerates the schema and fails if the committed file differs from the model, so CI catches drift through the existing engine test run. The reference doc exists.

## Task 2 — `.txt` parser and input limits
What it is: Turn a plain-text transcript into v1, and enforce size rules on any uploaded transcript. (R4, R9)
What changes at a high level: A parser module following R4: `Label: text` lines start turns, `T`/`C` map to roles, other labels leave role null, continuation lines append, blank lines ignored, text before the first label is an error, BOM and CRLF normalised, ids `t1..tn`. A shared validation step applies the limits: 5,000 turns, 20,000 chars per turn, 8 speakers, at least 50 words (reusing the existing empty-transcript errors).
Done when: Tests cover T/C and named speakers, multi-line turns, BOM/CRLF, leading orphan text, malformed input, and each limit boundary, with the right error and field/issue detail.

## Task 3 — Adopt v1 across engine, STT adapters, API view
What it is: Make v1 the single source so STT output, uploads and the engine share one type. (R2)
What changes at a high level: The engine transcript type is built on the v1 model. STT adapters write v1 (no `stt_run` or per-turn language; provenance stays on the session). The API transcript view uses the same model, replacing the separate turn view. Language defaults to `en` when omitted.
Done when: Existing engine, adapter and API transcript tests pass, updated only where the shape changed. A test shows STT adapter output validates against the generated schema.

## Task 4 — Engine `coded_span` and full-session default
What it is: Let callers choose the coded portion; absent means the whole transcript. (R7 engine side, R8, R9 duration/word cap, Decisions 4, 5)
What changes at a high level: The engine honours an explicit span in either form (ms range or half-open 0-based turn range). The span-ignored engine-only handling is removed. The random-window logic is kept only as an unused-by-default helper. Result, report and run-info span records carry both forms and the mode. Bad explicit spans fail instead of warning. Coded portions over 25 minutes or 6,000 words fail `session_too_long` with a message asking for a narrower span. The mission doc wording is updated to full-session coding.
Done when: Tests cover both span forms, absent span, time span on untimed transcript, out-of-range turns, over-limit failure, and span echoed in report. Golden and span tests are updated and pass; random-window tests target the kept helper.

## Task 5 — `PUT /transcript` upload and speaker gate
What it is: Users submit a `.json` or `.txt` transcript instead of audio. (R3, R5, R6, R9, Decisions 1, 2, 3, 8)
What changes at a high level: A new route accepts the file body (JSON or plain text, 1 MB cap) on a `created` session, parses and validates, stores the normalised v1 only, and moves the session straight to the gate state. If every turn has a role, the clinician label is set and the gate is skipped; otherwise the normal gate shows. More than one clinician speaker is rejected. The first-run gate is reached as after STT, so usage counts at run start. New error codes for invalid, too-large and empty transcripts carry field and issue.
Done when: API tests cover valid JSON and txt reaching the gate or first run, `T:`/`C:` skipping the gate, `Name:` showing it, two clinician labels rejected, empty, malformed, over 1 MB, over limits, wrong state, exactly `n_runs` usage consumed, and `daily_cap_reached` for a capped user.

## Task 6 — `coded_span` in API and contract regeneration
What it is: Carry the span from the API into the first run and later runs. (R7 API side, Decision 6)
What changes at a high level: Accept an optional span on session creation (stored, used by the first run) and on run creation (overrides). Reject malformed or both-forms spans and engine span failures as 422 `invalid_coded_span`; surface `session_too_long` clearly. Regenerate the public contracts so they include the transcript route, span shapes and new errors.
Done when: API tests cover both forms on create and run, override behaviour, absent span coding all turns, invalid spans returning `invalid_coded_span`, and span echoed in the report. Contract drift check passes with regenerated files.

## Task 7 — Web transcript option and speaker gate
What it is: The app side of upload. (R10)
What changes at a high level: The new-session page gets an Audio or Transcript choice; transcript accepts `.json` and `.txt` with a 1 MB precheck, the same error cards, and the same usage note copy. The session page shows the speaker gate when roles are missing, listing detected labels.
Done when: Web tests cover the transcript tab, file-type and size precheck, API error cards (invalid, too large, empty, session too long), and the gate display for a transcript with unlabelled roles.

## Manual steps
None for deploy (no infra change). Owner: confirm product copy for the transcript option (Task 7 uses the audio copy until then).
