---
status: done
summary: "Merged whole-project review @6ffbf63 — 6 high, 11 medium, 18 low-medium, ~50 low/improvement"
date: 2026-11-24
---

# Whole-project review — merged (Claude review/main-audit + Codex review/whole-project-main-20261124)

Commit reviewed: `6ffbf63` (origin/main). Code only; docs/PRDs/agent_files not used as basis. No fixes made.
Sources: Claude raw findings (`findings-backend-api.md` A*, `findings-engines-eval-admin.md` B*, `findings-web.md` C*, `findings-secondary-ui-contracts.md` D*), independent verification (`verify-web.md` + backend verification below), Codex report on branch `review/whole-project-main-20261124` (`docs/agent_files/review-whole-project-main-20261124-20261124-0529/review-2026-11-24-0529.md`, H*/M*/I*).
Tag: **[C]** Claude only · **[X]** Codex only · **[C+X]** both. Severity = post-verification (some corrected from original).
Verdict key: ✔ confirmed (code re-read, often probe) · ~ plausible (real path, impact/likelihood uncertain).

## Coverage (both reviews combined)
| Area | Result |
|---|---|
| api offline pytest | 1829 passed / 5 skipped (both) |
| api Firestore emulator | 357 passed (Codex only) |
| engines core / miti / oneshot | 315 / 491 / 66 passed |
| eval core / backend | 195(+1 env fail: console script not on PATH) / 193 passed |
| admin auth / backend | 25 / 47 passed |
| infra + CI scripts | 91 passed; terraform fmt, actionlint clean; Codex: terraform validate ok |
| web vitest / tsc / eslint | 1175 passed / clean / clean |
| web Playwright | Codex 91 e2e passed; Claude drove all flows in mock mode (transcript, audio, failure injection, rating, settings, interview w/ fake mic, mobile, dark) |
| frontend (admin) / eval/web vitest | 47 / 73 passed; Playwright probes of both UIs |
| Firestore rules | 16 passed (Codex); Claude static: consistent |
| OpenAPI / generated TS types | no drift (app.openapi() == openapi.json == schema.d.ts) |
| Known flaky | `web/src/routes/routes.flaky.test.tsx:12` asserts `/sample` before navigation settles |
| Not covered | real STT/LLM/voice/email, deployed cloud, load |

---

## HIGH (fix first)

| # | Src | Finding | Evidence | Impact / scenario | Fix |
|---|---|---|---|---|---|
| H-1 | C+X ✔ | Live Firestore status adapter drops failure/progress fields (Codex H6 = D12) | `web/src/api/firestoreListener.ts:46-59`; `errors.ts:100-115`; `SessionPage.tsx:166` | In prod every failed session renders "permanent internal": no Retry, no "replace file", wrong charged notice; elapsed 0; progress ceilings wrong. Mock bypasses adapter so tests pass. | Map all `SessionStatusDoc` fields; test real snapshots → failureView |
| H-2 | X ✔ | MITI code_pass accepts incomplete responses → silent undercounts (Codex H1) | `engines/miti/src/onolys_miti/code_pass.py:246-266,92,335` | `{"volleys":[]}` → zero counts, zero warnings, report published | Validate returned volley IDs vs requested; retry then fail |
| H-3 | C ✔ | Per-run engine warnings never reach report (B1) | `engines/miti/.../build.py:74-82`; `run.py:204` | All globals unsupported → default 3 shown "fair", `warnings: []`; quote_not_found / capped / dropped utterances invisible | Merge RunResult.warnings into report warnings |
| H-4 | C ✔ | Interview time-up auto-end retries unbounded on failure (C1) | `web/src/features/interview/InterviewPage.tsx:191-193,219-224` | Any `/end` 5xx, `/sessions` 429, prepare error → re-fires every render; probe 1027 POSTs/1.5 s (mock), RTT-bound in prod | Once-only ref for auto path |
| H-5 | C ✔ | "Change clinician → Save and try again" broken for failed sessions (C2+C6) | `web/src/features/session/slots.tsx:40-46,178-185`; `SpeakerGate.tsx:61-76`; `api/.../routes/runs.py:54,164`; `speakers.py:26`; mock `web/src/mocks/stateMachine.ts:799-805` | Confirm persists, then `/runs` 409 (only `awaiting_input` allowed); shown even for permanent failures; mock wrongly allows it | Use `/retry`; show only when action=retry; fix mock |
| H-6 | X ✔ | Eval units stranded after interrupted claim — no lease (Codex H2) | `eval/backend/src/onolys_eval_backend/runs.py:557-566,713-716` | CancelledError/crash after claim → unit `running` forever; redelivery no-ops; run never finishes | Lease + owner token, reclaim expired, fenced final write |

## MEDIUM

| # | Src | Finding | Evidence | Impact | Fix |
|---|---|---|---|---|---|
| M-1 | C ✔ | DELETE failing twice leaves hidden `deleting` session (A2) | `api/.../routes/sessions.py:547-580`; `queue.py:30`; `jobs/delete.py` | Task name dedupe + 2 attempts; hidden from list/get, no sweep → audio/PHI retained | Sweep `deleting`; longer retry |
| M-2 | C ✔ | `active_runs` slot leak → permanent 429 (A1 + N2) | `api/.../jobs/stale.py:94-98`; `jobs/run.py:76-89` | Release in separate txn / final-attempt release failure never retried; MAX_ACTIVE_RUNS=1 → user blocked (only DELETE repairs) | Release in same txn; repair on refused start |
| M-3 | C+X ✔ | Stale settlement only lazy; open page nudges only `transcribing` (Codex M10 + C4) | `web/src/features/session/useSessionStatus.ts:119,162`; `api/.../jobs/stale.py:31,64,77-85` | Upload/validate/run stuck states never settle while page open (≥16 min to ~1 h); reload/2nd tab during upload = dead end | Nudge all lazily-settled states or server sweep (combine with M-1/M-2 sweeper) |
| M-4 | C+X ✔ | `discard_failed_upload` races and orphans interview (A4 + Codex H5, H5 downgraded) | `api/.../repo/firestore.py:400-419`; `routes/audio.py:145`; `firestore.py:250` | Interview stays linked to deleted session → relink 409, unit lost; recursive delete outside txn can remove a just-cancelled session | One txn: tombstone + reset interview link, then cleanup |
| M-5 | X ✔ | Password reset sent via in-process BackgroundTask after 202 (Codex M2) | `api/.../routes/auth_email.py:92,123`; `infra/modules/environment/services.tf:36,54` (`cpu_idle=true`) | Reset emails silently lost | Durable enqueue + retry |
| M-6 | X ✔ | Leaving during mic startup orphans engine/socket (Codex M7; + C8) | `InterviewPage.tsx:110-116,136-155`; `audio/engine.ts:100-102` | Mic + relay socket live after navigation; double `close()` → unhandled InvalidStateError every interview | Store engine before await; cancel flag; idempotent close |
| M-7 | C ✔ | Eval audio upload limit 300 MiB > Cloud Run HTTP/1 32 MiB (D4) | `eval/backend/.../uploads.py:31`; `infra/eval-services.tf` | >32 MiB → GFE 413 non-JSON no CORS → "Failed to fetch"; whole file in memory, conc. 4 / 2 GiB → OOM risk | Signed-URL GCS upload |
| M-8 | C ~ | Orphan `created` session after transcript 422 / audio prepare failure (C3) | `web/src/features/upload/NewSessionPage.tsx:65-94` | List shows "Uploading" for ≥16 min; edit title/lang forces new session | Validate first or DELETE on terminal prepare error |
| M-9 | C ✔ | Eval UI drops most server error messages (D1) | `eval/web/src/api.ts:70-74`; backend emits `{"detail":…}` | Generic "Request failed (422)" instead of "Unknown model"/"Human requires gold" | Read `detail` too, or uniform error handler |
| M-10 | X ~ | `advance` read/check/write not atomic (Codex H3 + N3, downgraded) | `api/.../jobs/machine.py:123,170`; `repo/firestore.py:273`; `routes/sessions.py:~560` | Worker can overwrite `cancelled`/`deleting` (ms window, partly guarded) | Transactional transition with source-state guard |
| M-11 | X ~ | Report publication vs run/session bookkeeping separate (Codex H4, downgraded) | `api/.../jobs/run.py:109,197,209`; `routes/runs.py:151,281` | Final-attempt failure after report stored → contradictory state, retry blocked | One fenced publish txn + reconciler |

## LOW-MEDIUM

| # | Src | Finding | Evidence |
|---|---|---|---|
| LM-1 | C ✔ | Stale failures marked non-retryable; transcription copy says "upload a different file" (A3) | `api/.../jobs/stale.py:31`; `error_map.KIND_BY_CODE` |
| LM-2 | C ✔ | Concurrent final ratings both 202 → 2 revisions (A5) | `api/.../routes/rating.py:112-135` |
| LM-3 | C ✔ | `speakers/confirm` allowed in `report_ready` → relabels transcript against fixed report (A6) | `api/.../routes/speakers.py:26` |
| LM-4 | C ✔ | Transcript upload overwrites session language with `transcript.language or "en"`; web still shows selector (A7 + C10) | `api/.../routes/transcript.py:131`; `web/.../NewSessionPage.tsx:181-191` |
| LM-5 | C ✔ | Interview-linked session accepts arbitrary `PUT /transcript` → free uncounted evaluation (A8) | `routes/transcript.py`; `repo/firestore.py:~970` |
| LM-6 | C ✔ | Tone lint bypassed: `globals[].onolys.reason` and instance `rationale` shipped raw and rendered (B2) | `engines/miti/.../build.py:93-95`; `web/.../codedRows.ts:49-67` |
| LM-7 | C ✔ | Run deadline not passed to MITI LLM requests → up to ~24 billed calls/batch, cancelled mid-flight (B3) | `code_pass.py:231-240`, `globals_pass ~150`, `tips ~165`; `litellm_client.py:267,360` |
| LM-8 | C+X ✔ | Admin + eval token verification: blocking cert fetch in async path, refetch on any unknown `kid`, no negative cache (B4+B5+Codex M5) | `admin/auth/.../verifier.py:57-77`; `middleware.py:20`; `eval/backend/.../auth.py:19-31` |
| LM-9 | C ✔ | `.txt` parser makes phantom speakers from any `word:` line ("10:32 note:" → speaker "10") (B6, probed) | `engines/.../transcript_txt.py:7` |
| LM-10 | C+X ✔ | Sync storage/Firestore I/O in async handlers (B7 + Codex M4) | `api/.../routes/transcript.py:70-138`; `eval/backend/.../uploads.py` `upload()`, `execute_unit` |
| LM-11 | C ✔ | Dataset session without gold.json makes any run uncreatable; UI ignores `has_gold` (D2) | `eval/backend/.../runs.py:212,261`; `eval/web/.../NewRun.tsx` |
| LM-12 | X ✔ | "Already verified" shown from current user, not link's account (Codex M6) | `web/src/auth/pages/AuthAction.tsx:108` |
| LM-13 | X ✔ | Relay `getToken()` rejection unhandled → stuck Connecting with mic on (Codex M9) | `web/.../live/controller.ts:107` |
| LM-14 | X ✔ | Uploader keeps File refs for tab life; `xhr.timeout` never set (Codex M11) | `web/src/features/upload/uploader.ts:41,106,120-136` |
| LM-15 | X ~ | Lost `/sessions` response strands interview recording (Codex M12) | `InterviewPage.tsx:164`; `api/.../routes/sessions.py:234` |
| LM-16 | C ~ | Speaker confirm buttons re-enable before doc moves → conflicting 2nd confirm (C5) | `SpeakerGate.tsx:62-76` |
| LM-17 | C+X ~ | Signed-PUT vs validate races: original copied without generation precondition; concurrent request_upload+complete deletes session (Codex M1 + A14) | `api/.../jobs/validate.py:230-266`; `storage/gcs.py:56` |
| LM-18 | X ~ | Eval STT polling re-enqueues forever, no deadline (Codex M3) | `eval/backend/.../uploads.py:292-338` |

## LOW
- **api/infra [C]:** A9 prod config doesn't require AUDIO_BUCKET/TASKS_QUEUE/WORKER_URL/VOICE_URL, accepts `combined` (`config.py:200`); A10 AI_* env only on voice svc; A11 api CI not triggered by `config/**`, `docs/contracts/public/**`, `.github/actions/**`; A12 CI not required check, cancel-in-progress on main; A13 worker `last` vs `ctx.attempt` disagree after lease reclaim, lease-busy 503 burns attempt; A15 idempotency hash includes client info → 409 after redeploy; A16 `status=failed` logs on routine user-file rejections → alert noise, no worker/voice/queue alerts; A17 unbounded report `version` int → 500; A18 unguarded `last_used_at` write can 500 API-key requests, ID-token revocation unchecked; A19 voice relay pre-auth socket, uncapped first frame, cross-instance checkpoint overwrite; N1 `PUT /transcript` check+write not atomic (`transcript.py:122-138`).
- **engines/eval [C]:** B8 oneshot `1.0` accepted by jsonschema, rejected by strict pydantic → spend then fail; B9 `locate` exact tier no word boundary ("you"∈"young"), fuzzy accepts one-word swaps; B10 multi-run mean counts vs representative-run instances; B11 stale copy in `data/report.yaml`, always-skipped `reasons_audit`; B12 config drift (prod routes lacks `oneshot`, `routes.py:158` models path, `pack.yaml` no `params:`, `prices.yaml` one model); B13/D9 cancelled eval run shows `failed`, `cancel_requested` not surfaced; B14 `run_detail` inline outputs may exceed 32 MiB; B15 `change_goal` not validated at run creation; B16 repeats weight sessions unequally; B17 cost accounting gaps (lost first-attempt usage, failed-run metrics discarded, unpriced → None).
- **web [C]:** C7 not-found copy blames upload (`SessionPage.tsx:29,138`); C9 raw "Speaker spk_0"; C11 rating card editable after submit ("Draft saved" + "Rating submitted"); C12 upload `complete()` error body dropped; C13 upload auto-retries without backoff; C14 inconsistent report date formats/timezones; C15 missing count shows 0; C16 `document.title` never changes; C17 unknown status crashes dashboard (`chips.ts:11,28`); `useSessionStatus` `drop()` swallows updates held during failed DELETE.
- **web [X]:** M8 reconnect copy "keep talking" while recorder paused (`InterviewPage.tsx:311` vs `controller.ts:170`); M13 transcript-only sessions never set `started_at` (`transcript.py:124`, `progress.py:92`); I2 Settings usage failure shows "Loading…" forever (`Settings.tsx:165`).
- **admin/eval UI [C]:** D3 `change_goal` 10000 vs 4000 limits; D5 eval CSP `frame-src` vs authDomain (mostly FP — admin has same CSP; only bites with custom auth host); D6 admin Shell treats any non-5xx as ok; D7 eval polls stop after one failed GET; D8 eval history silently capped at 100; D10 OpenAPI documents 403 only on `/api-key` ops; D11 eval CORS lacks localhost / no mock mode; D13 admin 403 copy ignores `email_verified` cause.
- **legal [X]:** I1 privacy policy omits Resend (`PrivacyPolicy.tsx:23,48`).

## IMPROVEMENTS
- **[C] infra/security:** staging deployer trusts any repo workflow with project-level Hosting/rules admin + AR write; one Identity Platform pool shared staging+prod; worker mounts full public API; no audio/transcript retention, no account-delete route; actions pinned by tag not SHA; ffmpeg unpinned; `preexec_fn` in multithreaded proc; index deploy parallel to Cloud Run deploy; smoke only `/v1/healthz`.
- **[C] dead code / hygiene:** `reserve_run`/`release_run`, `add_usage`, `get_usage`, `revoke_api_key`, `create_api_key`, `expiry_days`; stale `ensure_alive` docstring; `list_reports` loads full bodies; `/upload-limits` can 500 on bad preset; new SpeechClient per poll; no session-creation cap.
- **[C] engine:** MITI trumping rules only in prompt; `label_for` compares unrounded (3.96 "4.0" labelled fair); duplicated span logic (`miti/prepare` vs `core/spans`); `_clamp_ends` fabricates word end times; language defaults `en` on detect failure; dataset id typo `suspiscious-smoker`.
- **[C] UI:** mobile coded-transcript "Why" column clipped; hard-coded "300 MB, 10 to 20 minutes" copy; `session_too_long` copy mentions API `coded_span`; "Rate session" vs "Your rating" labels; duplicated auth/authFetch in `frontend/` and `eval/web`; admin `index.html` missing viewport meta; raw ISO dates in eval history; `accept="audio/*"` broader than server.
- **[X] tests/CI:** Codex's prioritized regression backlog + five-minute PR-gate plan (see Codex report "Test gaps and five-minute PR plan"): mock emitter bypasses real Firestore mapper (root reason H-1 escaped tests), mutation configs exist but never run, nightly lacks property/browser/eval-persistence jobs.

## Verified clean (no defect)
No owner-check hole on any api route. No fabricated quotes/speakers/timestamps path (all quotes re-sliced from transcript; 4000-case unicode probe clean). MITI math/zero-division OK; formula evaluator whitelist. Admin auth RS256 pinned, aud/iss/exp, allowlist, exact CORS. Eval terminal accounting transactional. Firestore rules owner-only read, no client writes, status doc has no PHI. OpenAPI/types in sync. No `dangerouslySetInnerHTML`; `next` redirect handling sound; CSP clean.

## Severity corrections from verification
Codex H5 high→low (folded into M-4); Codex H3, H4 high→plausible medium-low; A1 high→medium; D5 → mostly false positive; C4 overstated (settles after ~16 min, not never).

## Suggested fix order
1. H-1 (one mapper fix unblocks correct failure UX everywhere) · H-4 · H-5 (small web fixes)
2. H-2 + H-3 (report integrity — silent wrong scores)
3. Server sweeper covering M-1, M-2, M-3 · M-4 discard txn
4. H-6 eval lease · M-7 eval upload path
5. Rest by area.
