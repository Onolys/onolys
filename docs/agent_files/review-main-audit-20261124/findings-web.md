# Stage 2C — web/ app findings (raw, pre-verification)

Commit 6ffbf63. vitest 76 files / 1175 passed; tsc + eslint clean. Playwright probes vs dev:mock (18601 rating off, 18602 rating on): transcript flow, audio upload/cancel/delete, failure injection (fail-transient, fail-code, fail-upload_failed, cap-held), rating card, settings API key, legal/404, practice interview with fake mic, mobile 375 px, dark mode. Not run: full e2e (disk), huge file, mic denied, reload mid-flow (mock auth signs out on reload). Mock mode can't show real Firebase/Firestore/STT/network behavior.

## High
- C1 InterviewPage.tsx:219-224 / :191-193 time_up auto-end retries unbounded when finish fails (onError resets finishing; effect deps on `finish` identity). Vitest probe: /end 500 → 1027 POSTs in 1.5 s. Fix: once-only ref.
- C2 slots.tsx:178-185, SpeakerGate.tsx:61-62 "Change clinician → Save and try again" on failed session posts /runs; API RERUN_STATES=("awaiting_input",) → 409. Confirm persists, nothing reruns. Mock stateMachine.ts:799-805 wrongly allows failed → tests pass. Also shown for permanent_internal/user_file. Fix: use /retry; show only when action=retry.

## Medium
- C3 NewSessionPage.tsx:65-94 POST /sessions succeeds then PUT /transcript 422 or /audio fails → orphan `created` session shows "Uploading" forever; title/language change forces second session. Fix: validate first or DELETE on terminal prepare error.
- C4 UploadSlot.tsx:94,102-108 reload / second tab during upload: Resume only for upload_incomplete; created/uploading without in-memory job = dead end.
- C5 SpeakerGate.tsx:62-76 buttons re-enable after confirm before doc moves → conflicting second confirm 409/422.
- C6 SpeakerGate.tsx:61-63 confirm-then-run split: confirm persists when run errors (409 / cap 429), UI reads as unchanged.
- C7 SessionPage.tsx:29,138 not-found copy blames upload for any missing/mistyped session id.

## Low
- C8 engine.ts:100-102 close() not idempotent → unhandled "Cannot close a closed AudioContext" pageerror after every interview (observed).
- C9 SpeakerGate.tsx:~93 shows raw "Speaker spk_0".
- C10 NewSessionPage.tsx:181-191 language selector shown for transcript upload but ignored (pairs with A7).
- C11 RatingCard.tsx:176-190 editable after submit; "Draft saved" shown next to "Rating submitted".
- C12 uploader.ts:312,330 complete() error body dropped → generic "upload didn't finish".
- C13 uploader.ts:303-320 3 auto-retries back-to-back, no backoff.
- C14 ReportPage.tsx:111 vs ReportView.tsx:90-98 inconsistent date formats/timezones (local vs UTC en-GB).
- C15 ReportView.tsx:~300-312 missing onolys_count → 0 (no data looks like zero).
- C16 document.title never changes.
- C17 SessionsPage.tsx:60 / chips.ts STATUS_CHIP no default → unknown status crashes dashboard into RouteError.
- (extends Codex M10) useSessionStatus.ts drop() returns early while `quiet`; after failed DELETE held updates not replayed.

## Improvements
- C18 mobile coded-transcript dialog: Why column cut off.
- C19 NewSessionPage.tsx:173 hard-coded "300 MB, 10 to 20 minutes" vs served /upload-limits.
- C20 errors.ts session_too_long copy "Use a narrower coded_span in the API" in web UI.
- C21 "Rate session" step vs "Your rating" card labels confusing.

## Security/contract notes
No contract mismatch (audio, rating, upload-limits, api-key). No dangerouslySetInnerHTML. `next` handling sound (same-origin continueUrl not checked against blocked list — minor loop risk). CSP clean. Token: bearer per request, one forced refresh on 401.

## Flows OK
Signup→verify→transcript session; 422 mappings; speaker confirm→run→report; evidence→coded dialog + focus return; retry countdown; permanent_internal card; upload_failed view; cap-held; cancel→delete; rating validation; API key create/regenerate/revoke; legal/sample/404; logout/next; interview mic test→end→upload; mobile 375 no h-scroll; dark mode.
