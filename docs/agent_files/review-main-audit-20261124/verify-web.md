# Verification — web findings (C*) + Codex web items

| ID | Verdict | Sev | Evidence |
|---|---|---|---|
| C1 | CONFIRMED | High | InterviewPage.tsx:219-224 deps include `finish`; :191-193 onError resets finishing; timeUp stays true → re-fires on any real failure (/end 5xx, POST /sessions 429, prepareUpload). RTT-bound outside mock. blob cached → no recording loss. |
| C2 | CONFIRMED | High | runs.py:54 RERUN_STATES=("awaiting_input",); :164 → failed gets 409; slots.tsx:40,45-46 shows gate for every failed; :178-185 confirm then /runs; speakers.py:26 allows failed so confirm persists. |
| C3 | PLAUSIBLE | Med | orphan created → upload_incomplete only after ~16 min (lazy). |
| C4 | CONFIRMED (overstated) | Low-Med | stale.py:77-85 moves created/uploading → upload_incomplete lazily after UPLOAD_URL_TTL_S (900 s) + 60 s; dead end ≥16 min. Same root as Codex M10. |
| C5 | PLAUSIBLE | Low-Med | SpeakerGate finally setBusy(false) before doc update. |
| C6 | CONFIRMED | Low-Med | consequence of C2. |
| C7 | CONFIRMED | Low | SessionPage.tsx:29,138. |
| C8 | CONFIRMED | Low | engine.ts:100-102 double close → InvalidStateError. |
| C17 | CONFIRMED | Low | chips.ts:11,28; SessionsPage.tsx:74 — only on version skew. |
| C9-C16, C18-C21 | not verified | — | reviewer-observed only. |
| Codex H6 | CONFIRMED | High | firestoreListener.ts:46-59; errors.ts:100-115 falls to permanent internal. |
| Codex M6 | CONFIRMED | Low-Med | AuthAction.tsx:108; checkActionCode returns email but not used; code not burned. |
| Codex M7 | CONFIRMED | Med | engineRef set after await start. |
| Codex M8 | CONFIRMED | Low | copy vs pauseRecording. |
| Codex M9 | CONFIRMED | Low-Med | controller.ts:107 no catch. |
| Codex M10 | CONFIRMED | Med | merge with C4. |
| Codex M11 | CONFIRMED | Low-Med | xhr.timeout never set (uploader.ts:127). |
| Codex M12 | PLAUSIBLE | Low-Med | sessions.py:234. |
| Codex I2 | CONFIRMED | Low | Settings.tsx:~165-176. |

Merge: C4+M10 (one nudge for all lazily-settled states); C2+C6 one defect; H6 compounds C2; C1+M12 finish mutation semantics; C8+M7 engine lifecycle.
