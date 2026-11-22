# Warnings

Warning codes on a MITI result and report. A warning never blocks the report; the session still ends `report_ready`. Messages are fixed templates and never contain transcript text. Sources: `engines/miti/src/onolys_miti/result.py` and `report.py`, which own the code lists and the shape (`code`, `severity`, optional `item_id` and `detail`).

**Audience:** users.

## Engine warnings (result and report)

| Code | Emitted when |
|---|---|
| `short_session` | The session is shorter than the MITI minimum, or has too few clinician or client turns (the MITI `input_checks` with severity `warn`). |
| `quote_not_found` | A quote a model returned could not be found in the transcript, so that evidence line or code was dropped. |
| `overlap` | A coded utterance repeats text already coded earlier in the same volley. |
| `insufficient_evidence` | A global rating had fewer located quotes than required; it was reset to the scale default. |
| `capped` | A MITI cap lowered a global score (`source: capped`; the raw score is kept). |
| `span_ignored` | A coded span was requested but the transcript has no timestamps, so the whole transcript was used. |
| `coded_window` | The session is over 20 minutes, so a reproducible 20-minute window was coded. |
| `unknown_speaker` | A speaker could not be mapped to clinician or client and was treated as other. |
| `language_not_validated` | The session language is not English; MITI coding is validated for English only. |
| `run_failed` | One of several runs failed and was excluded from the result. |

## Report-only warnings

| Code | Emitted when |
|---|---|
| `tips_failed` | The tips call failed; the report ships with no tips. |
| `fewer_tips` | Fewer than three valid tips were produced. |
| `reason_withheld_tone` | A model-written reason for an item failed the tone check and was withheld; the evidence lines are kept (`item_id` set). |
| `reasons_audit_failed`, `reasons_audit_partial` | In the report schema for the written-reasons section. The engine does not emit them: a run does not compare a rating card, and that section is `skipped`. |

Packs (the MITI definition) may add codes of the form `[a-z][a-z0-9_]*`; for example `session_too_long` and `missing_param` come from the input checks. Input checks with severity `error` stop the run with `invalid_parameters` instead ([public-api.md](public-api.md#engine-errors)).
