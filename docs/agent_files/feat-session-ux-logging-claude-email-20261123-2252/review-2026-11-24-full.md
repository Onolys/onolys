---
status: done
summary: PASS after fix round 1 (7cc2c65, 95df1c6); first pass NEEDS_CHANGES — 2 must-fix
date: 2026-11-24
---
# Review — 2026-11-24 — full branch
Diff: origin/main...1a789f3   Personas: Bug Hunter, Security, Architect

## Verdict (first pass): NEEDS_CHANGES
Lane verdicts: Bug Hunter NEEDS_CHANGES, Security PASS, Architect NEEDS_CHANGES.

## Must-fix
- [Bug Hunter] web/src/features/session/useSessionStatus.ts:24 (`detailToDoc`), api/src/onolys_api/routes/sessions.py:120,399 — SessionDetail lacked error_kind/retries_left and web didn't map them or counted, so in fallback polling failed sessions lost Retry / "Upload a different file" and showed wrong charge text. Fixed 7cc2c65.
- [Architect] docs/reference/public-api.md, logging.md, infra.md contradicted the final error mapping (LLMBadOutput, D6 transient STT, invalid_parameters action, 401/403/400/404 → internal_error, user actions) and missed retry + upload-limits endpoints. Fixed 95df1c6.

## Notes (non-blocking)
- [Bug Hunter] Elapsed after a retry from failed includes idle time in failed (progress.py:92-96); report_ready→running reset branch is dead; SP05 PRD DEFERRED note out of date.
- [Bug Hunter] progress_cb writes can land on the status doc after a cancel (cosmetic; web hides progress when cancelled).
- [Architect] CANCELLABLE_STATES duplicated in repo/limits.py and machine.py TRANSITIONS; error_kind passed by hand at 5 sites though SessionError._fill_kind derives it; staging LLM override vs eval combo_routes map different model fields; no concepts page for failures/limits/cancel.
- [Security] validate.py interview_audio_check log includes client user_agent (capped, sanitized) next to session_id; optional to drop.

## Re-review — fix round 1 (95df1c6, 7cc2c65)
Verdict: PASS (Bug Hunter PASS, Architect PASS). Notes: live doc retries_left 0 vs fallback null can re-fire SessionPage reset effect (server rejects duplicates); upload_failed page shows not-found if listener drops (pre-existing); logging.md:92 "5xx" too broad (only 500/502/503/504/529, 408 transient); infra.md:288,290 wording "Run again"/"fix the request"; PUBLIC_MESSAGES[internal_error] says "Run again".

## CI
PR #56 all 19 checks green on f9fd503 after CI slimming (cached Playwright browser, cached static ffmpeg 7.0.2, nightly marker, preview paths filter, 10-min job caps, fast test clocks). web-e2e 493–634s → 145s; api-unit 88–103s → 72s.

## Next step
Owner review/merge of PR #56.
