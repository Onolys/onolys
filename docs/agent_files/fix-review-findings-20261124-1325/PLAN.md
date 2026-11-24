---
status: done
summary: Fix all review findings (FINDINGS.md + Codex backlog); PR CI < 5 min, slow tests nightly
date: 2026-11-24
---

# Fix plan — light mode, orchestrator-owned status

Two tracks run in parallel (disjoint files): **S** = server (api/engines/eval backend/admin/infra), **W** = web/frontend/eval-web. CI task last.

| ID | Track | Scope (finding IDs) | Status | Commit |
|---|---|---|---|---|
| T01 | W | Live Firestore mapper: H-1 (H6/D12); timestamps; M13 UI elapsed if web-side | done | 8ebb1a1 |
| T02 | S | MITI report integrity: H-2 (code_pass completeness), H-3 (B1 per-run warnings), LM-6 (B2 tone lint reason/rationale) | done | e043c48 |
| T03 | W | Interview lifecycle: H-4 (C1), M-6 (M7+C8), LM-13 (M9), M8 copy | done | 3976329 |
| T04 | S | api state atomicity: M-10 (H3 advance txn + N3), M-11 (H4 publish), M-4 (A4+H5 discard txn), N1 transcript PUT atomic, LM-2 (A5 rating) | done (emulator verified b01ce75) | ce58176 |
| T05 | W | Speaker/session UX: H-5 (C2+C6 + mock), LM-16 (C5), C7, C9, LM-12 (M6), I2 | done | ade784f |
| T06 | S | api recovery: M-1 (A2 deleting sweep), M-2 (A1+N2 slot leak), M-3 server side (sweep stale), LM-1 (A3), A13 | done (bounded sweep fairness follow-up) | b01ce75, 93d0ec6, f8fbd90 |
| T07 | W | Upload UX: M-8 (C3), C4 resume, LM-14 (M11), C10, C12, C13, C19, M-3 web nudge all lazily-settled states, useSessionStatus drop() | done | e49995e |
| T08 | S | api routes misc: LM-3 (A6), LM-4 (A7), LM-5 (A8), M13 server, A15, A17, A18, LM-15 server (idempotent interview session create), A23 small items; + T03 follow-up: make POST /interviews/{id}/end idempotent (web retry re-sends it) | done (A23 partial: refund window, SpeechClient per poll, session-create cap, run_info verbatim left) | f2f93b0 |
| T09 | W | Report/UI polish: C11, C14, C15, C16, C17, C18, C20, C21; + T02 follow-up: WARNING_TEXT (ReportView.tsx:252) entries for quote_not_found, overlap, insufficient_evidence, capped, reason_withheld_tone; show unknown codes generically; + T05 follow-up: SessionPage first-mode speaker gate on failed session (speaker_confirmed=false) only confirms, never re-runs | done (RatingCard.test:59 regression → T11) | 9ff5090 |
| T10 | S | api async/durability: M-5 (M2 durable reset email), LM-10 (M4/B7 api part), LM-17 (M1+A14), A16, A19 | done (A16 partial: alert policies infra) | 2d43b82 |
| T11 | W | Admin + eval web: M-9 (D1), LM-11 UI (D2), D3, D6, D7, D8 UI, D9 UI, D13 copy, D14 (viewport, dates, accept), D5 CSP | done | 5070340, 3d13389 |
| T12 | S | Engines misc: LM-7 (B3 deadline), LM-9 (B6 txt parser), B8, B9, B11, B12, B17, B19 (label_for rounding, _clamp_ends no fabricated times, lang default), oneshot; + T02 follow-up: code_pass _OUTPUT_FORMAT prompt must say every volley id returned, empty list allowed (update prompt hashes/fixtures) | done (B12 partial: pack params/compare/source.url, eval prices; B17 partial: api/real.py metrics on failure → T15; B19 span dup/getsource left) | a4a3645 |
| T13 | S | Eval backend: H-6 (H2 lease), LM-18 (M3), B13/D9, B14, B15, D3 server, LM-11 server (D2), D8 server, B7 eval part, M-7 (D4 upload path); + T11 follow-ups: cancel_requested in SUMMARY_FIELDS, limit+cursor on GET /v1/runs | done (stale upload writers fenced) | 1ae5922, 8e2911d |
| T14 | S | Auth verifiers: LM-8 (B4+B5+M5), D13 server code (distinct 403 code for email_unverified vs not_allowlisted), D11 eval CORS localhost | done | f4955df |
| T15 | S | Config/infra/hygiene: A9, A10, A11, A21 dead code, A22 code-only bits, D10 openapi 403s; + T12 follow-up: B17 api/real.py keep usage metrics on failure (D11 moved to T14) | done (A21/A22/B17 partial; see T15.md) | 962c951 |
| R1 | S | Regressions: test_error_map 4 fails (attempt counter T06/T08); test_transcript_upload named upload 422 (T12 txt parser "Pat:") | done (owner: 3+ one-off names → 3rd treated as continuation) | fb4e7ce |
| T17 | W | Follow-ups after T13/T14: frontend/firebase.json frame-src authDomain gap + test; eval run 404 stops polling; D13 UI uses new 403 codes; D8 Load more using cursor | done (direct signed GCS upload, CSP/IAM, goldless UI included) | fe92b10 |
| T16 | S+W | CI: PR gate < 5 min, nightly tiers (emulator matrix, full browser matrix, mutation, property, image builds), flaky route test fix, keep coverage gate honest, no bloat | done (hosted/cold timing and nightly matrix unmeasured locally) | 8de7159 |

## Owner-only / product decisions (skipped, noted)
- A20 deployer IAM scope, shared Identity Platform pool staging/prod (cloud IAM).
- A21 audio/transcript retention policy, account-delete route (product decision).
- I1 privacy policy provider list (legal text).
- A12 make CI a required check (GitHub settings).
- B10 mean counts vs representative-run instances, B16 session weighting, B18 trumping rules in code (MITI scoring semantics — needs owner call).
- Dataset id typo `suspiscious-smoker` (baked into bucket paths; data migration).
- Terraform changes in this branch need `terraform apply` by owner.
- (T06) `terraform apply` for Cloud Scheduler sweep job (`*/15`, OIDC tasks-invoker) + enable cloudscheduler API; deployer may need Scheduler admin + actAs. Deploy new Firestore composite index sessions(state, stage_started_at).
- (T10) Worker service needs RESEND_API_KEY, APP_BASE_URL, Firebase Admin auth-link access (reset email now sent from worker). Add alert policies for worker/voice/queue failures (alerts.tf). Set `--ws-max-size` on voice service.

## Completion evidence

All implementation tasks are recorded with their documented partial scope and owner deferrals retained. Final branch review and verification are in [review-2026-11-24-1532.md](review-2026-11-24-1532.md). Broad-test assertion maintenance and API evidence were committed in `005c592`; sweep fairness runtime repair is `f8fbd90` ([details](T06-sweep-followup.md)). R1's accepted one-off-name behavior remains unchanged.

- T13: [backend results](T13-RESULTS.md), [upload fencing follow-up](T13-UPLOAD-FOLLOWUP.md).
- T14: [auth verification](T14-auth-verifiers.md).
- T15: [configuration and partial A21/A22/B17 scope](T15.md).
- T17: [signed GCS uploads, CSP/IAM and goldless UI](T17-RESULTS.md).
- T16: [CI tiers and local evidence](T16-CI.md). Required CI branch protection remains an owner setting if desired; candidate hosted/cold timing, Firefox/WebKit and Docker/nightly matrix have not run in this environment.

Owner must apply/deploy the Terraform changes and confirm staging signed upload, runtime signing and live CORS. Provider acceptance before handle persistence remains at-least-once. No push or cloud mutation was performed.
