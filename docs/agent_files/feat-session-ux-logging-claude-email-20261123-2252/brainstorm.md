---
status: approved
summary: Processing-screen clarity, cancel, smart failure handling + traceable logs, Claude for text steps, eval model picker, auth emails via Resend
date: 2026-11-23
---

# Brainstorm — session UX, failures/logging, Claude, auth emails

## TL;DR
Make the processing screen honest (clear current step, % from the start, "you can leave" hint from upload-complete), add a non-destructive **Cancel** (status `cancelled`, charges a limit unit only if transcription started), and replace blanket "busy, retry" errors with a per-failure policy that never charges users for our faults. Log the real provider error and tie every line to the session id so the on-screen Reference finds everything in Logs Explorer. Fix the rating-step outage (no successful rating run on any env since 2026-11-16), move text LLM steps to Claude Sonnet 5.5 (configurable via GitHub vars), give eval a model-config-driven model/tier/effort picker, and send auth emails ourselves via Resend with links to our own `/auth/action`. Eval runs every selected model × tier × effort combination per report, always against a locked-on human baseline, with per-report and combined comparison tables; each combination is isolated and retried up to 3× on retryable errors. Everything targets staging only.

## Problem
Clinician uploads a session recording → validate → transcribe (Google Chirp 3 batch) → user picks clinician speaker + gives own rating → LLM rates (MITI coding, tips, report). Today:
- Step list shows current step only as bold + left border; "Elapsed", progress bar, and "Usually under 5 minutes — you can close this tab…" appear only once state is `running` (`web/src/features/session/SessionPage.tsx:140-179`, `timeline.ts:175`).
- "Check audio" and "Session setup" steps clutter the list.
- Only "Delete session" exists (destructive, `jobs/delete.py`); no cancel, no `cancelled` status.
- Error "A service we depend on is busy…" (`web/src/api/errors.ts:26`, code `upstream_unavailable`) is shown for every LLM error. Real provider error text is never logged (`engines/core/.../llm/litellm_client.py:330` keeps class name only; `miti` logger never configured). Reference shown on the failed card is the **session id**; docs (`docs/reference/infra.md:236-246`) tell you to query `request_id` → mismatch.
- Evidence (Cloud Logging, staging worker rev 00048, session 9521150e…, 2026-11-23 21:35–21:38 UTC): transcription OK; 3 `run` attempts each failed `upstream_unavailable` / `AllRunsFailed` / `LLMUnavailable` within ~0.5s, retried by LiteLLM (so not auth/404/400/429 per client mapping). No successful `miti.done` on any service since 2026-11-16. Installed LiteLLM 1.110.2 does not know `gemini-4-*` or `claude-sonnet-5-5` ids.
- LLM is Gemini via LiteLLM (`config/{env}/routes.yaml`, preset chosen by Terraform `DEFAULT_PRESET`); a `claude` preset (anthropic/claude-sonnet-5-5) and secret `anthropic-api-key-{env}` already exist.
- Firebase verify/reset emails land on a broken hosted page; we can't change the action URL usefully.

## Decision log
| Decision | Alternative rejected | Why |
|---|---|---|
| Size = full design | small change | 10 items across web, worker, infra, eval (Claude) |
| Current step: spinner + "In progress" marker + status line (user asked "make clear"; visual specifics Claude's call) | bold only | Today's bold/border is not noticed |
| Hide "Check audio" and "Session setup" rows (user) | keep | Noise |
| Progress % shown from upload, whole flow = 100%, weighted by typical stage duration, updated within stages (transcription estimated from audio length × elapsed; rating per sub-stage) (user) | show only during `running`; equal steps | User wants continuous honest progress |
| Never show 100% until report ready (Claude) | — | Avoid false completion |
| "You can leave" hint per phase: upload → "Keep this tab open until upload finishes"; after → "You can close this tab — we'll keep working"; at speaker/rating → "We'll wait here for your choice" (user) | literally permanent | Leaving during upload breaks it; input steps wait for user |
| Streaming transcription dropped (user) | streaming STT | Chirp batch has no partial results; speaker pick is manual; high effort, small gain |
| Cancel = stop all processing, keep data, status `cancelled` (user) | cancel = delete | Cancel ≠ delete |
| Cancel shown only on processing page, all in-progress states (uploading → rating) (user) | finished sessions too | Finished sessions use Delete |
| Cancel is a text link, blue default, red on hover; Delete stays red button (user) | button | Visual separation |
| Cancel confirm dialog (like delete). If transcription started: dialog warns it counts toward limit (user) | no dialog | Avoid accidental cancel |
| Click OK → link shows "Cancelling…" + spinner → when everything stopped: "Session cancelled. This counted / did not count toward your limit." (user) | instant | Honest feedback |
| Limit charge on cancel: 1 unit at cancel time if transcription had started and rating not already charged; if rating already started it's already charged, no refund; race (transcription starts while dialog open) → charge (user) | move all charging to transcription start | Same user rule, far less risk |
| Internal (our) failure never counts toward limit (user) | — | Fairness |
| Cancelled session page: "Cancelled" + Delete button; no resume; list shows "Cancelled" chip; nothing else (user) | resume | Simplicity |
| Failure policy table (below) (user ok'd) | blanket "busy, retry" | Retry only where it can succeed; avoid wasting resources/charges |
| Text LLM steps (coding, tips, report) → Claude Sonnet 5.5, effort low; STT stays Chirp (user) | Gemini; Claude for STT | Claude has no audio STT; low keeps "under 5 min"; eval compares |
| Prod provider/model via GitHub Actions vars per env (e.g. `LLM_PROVIDER`, `LLM_MODEL`) passed by deploy workflow to Cloud Run env, overriding route model; API keys stay in Secret Manager; change = re-run deploy (user, Claude's rec) | Firestore admin doc / admin site | Audited + visible, no new write surface |
| Eval: model picker (Gemini / Claude) → only that model's tiers; effort dropdown per tier's allowed levels; context auto = model max, no dropdown (user) | free text; context dropdown | Prevent invalid combos |
| One model config file is source of truth for models→tiers→allowed effort→default effort→context→max output (user/Claude) | scattered | Single place |
| Logs: every app log line from api/worker/engine carries `session_id` when known; provider error text (status, type, message — never prompt/transcript content) logged; `miti` logger wired into JSON logging (Claude) | status quo | Reference must find everything |
| Doc with ready Logs Explorer link by session id (user) | — | User wants to paste reference and see all logs |
| Auth emails sent by API via Resend; Admin SDK generates link; rewritten to `<APP_BASE_URL>/auth/action?mode=…&oobCode=…`; APP_BASE_URL per env from server config, never request (user) | Firebase hosted mail | Hosted page broken |
| Upgrade LiteLLM to a version that knows gemini-4-* and claude-*-5-5 (Claude) | keep 1.110.2 | Likely cause of outage; needed for effort mapping |
| Eval run = cartesian product of selected models × tiers × efforts (multi-select), per report (user) | single preset | Compare all combos |
| Eval results: per-report comparison table (combo rows/cols, diff vs human, MAE) + combined summary page across all reports (MAE, within-1, per combo) (user) | per-session view only | Easy cross-report comparison |
| Human baseline auto-selected and greyed (cannot uncheck) for dataset runs (user) | toggleable | Always compare vs human |
| Transcription once: dataset runs use stored transcripts; uploads transcribe once and reuse across reruns (already true — no change) (verified) | audio-hash cache | Already satisfied |
| Eval unit retry: up to 3 attempts for retryable error classes only (transient provider/5xx/429/timeout); other units unaffected (user) | none | Failure-proof runs |
| Planned unit count shown before Start; block above 499-unit cap with message (Claude) | auto-split runs | Firestore batch limit; keep simple |
| Eval picker replaces "presets" with model × tier × effort selects (Claude) | keep presets | One concept |
| Main-app user Retry button: 5-second countdown shown in button "Retry (5)…(1)" before enabled (user) | immediate | Avoid hammering |
| Retry cap 3 per session; 429/quota treated as temporary (Claude) | per step | Simple, bounded |
| Internal failure at rating step is not counted (user rule overrides old "rating started" rule) (user) | old rule | Fairness |
| Cancel at awaiting_input counts (transcription started) (user) | — | User rule |
| `cancelled` is terminal; only Delete after; cancel result (`counted`) persisted on session so reload shows the message; "Cancelling…" is client-side until POST returns (Claude) | — | Simple, durable |
| Cancel ignores in-flight Chirp job (results discarded), does not kill it (Claude) | cancel LRO | Simpler; cost small |
| Cancel available in states created, uploading, upload_incomplete, validating, transcribing, awaiting_input, running (Claude) | subset | User: all in-progress |
| Finished sessions cannot be re-run (already true: API 409 rating_final) (verified) | — | No change |
| Provider error message logged truncated to 300 chars via safe_log allowlist; GCP project `onolys` for both envs (Claude) | — | PHI-safe |
| Claude Sonnet 5.5 effort low maps via LiteLLM `reasoning_effort: low` (→ adaptive thinking + output_config.effort); verify after LiteLLM upgrade (Claude) | — | — |
| Staging only; prod untouched (user) | prod rollout | Nothing is prod yet |
| Auth email sender "Onolys <no-reply@onolys.com>", simple branded HTML + plain-text; verify endpoint requires auth, reset is unauthenticated and never reveals whether the email exists; rate-limited; fake sender adapter locally; on Resend failure user sees generic "couldn't send, try again" (user/Claude) | Firebase mail | Working links |
| Outage repro + LiteLLM upgrade is the first task (gates Claude switch); if root cause isn't LiteLLM, fixing it stays in scope (Claude) | parallel | Must know cause |

## Design

### A. Processing screen (web)
Files: `web/src/features/session/SessionPage.tsx`, `timeline.ts`, `useSessionStatus.ts`, `slots.tsx`, `web/src/features/dashboard/chips.ts`.
- Steps shown: Upload, Transcribe, Confirm speaker, Your rating (only when `ratingEnabled()`), Rate session (with sub-labels), Report. "Check audio" folded into Upload/Transcribe; "Session setup" row removed.
- Current step: animated spinner icon + "In progress" text + accent color; done = check; pending = muted.
- Progress bar + "N%" + Elapsed shown from upload start. Server (`api/.../jobs/machine.py` STATE_PROGRESS + `jobs/run.py` STAGE_WEIGHTS) owns base %; web interpolates within long stages (transcription: expected ≈ f(audio duration), capped below next stage's base). Waiting-for-user states freeze %.
- Phase hint per decision log.

### B. Cancel
- New state `cancelled` in `api/.../repo/models.py`; transitions from every in-progress state in `jobs/machine.py`.
- `POST /sessions/{id}/cancel`: atomically mark cancel requested, stop work (in-flight Cloud Task handlers check like `jobs/alive.py:ensure_alive` / `deleting`; STT operation abandoned; run slot released), apply charge rule, set `cancelled`, return `{counted: bool}`. Idempotent.
- Charge record stored on session so the UI can show counted/not.
- Web: link + confirm dialog (reuse `DeleteDialog.tsx` pattern), states idle → cancelling (spinner) → cancelled message. Sessions list chip "Cancelled".
- Delete stays as today on finished/failed/cancelled sessions.

### C. Failure handling policy
| Failure kind | Example | User sees | Limit |
|---|---|---|---|
| Temporary, ours/provider | 5xx, 429, timeout | "Try again" button, max 3 per session; after 3 → "start a new session" | Not counted |
| Permanent, ours | model not found, auth/config, bug, repeated bad model output | No retry. "Something went wrong on our side. This did not count toward your limit. Please start a new session." + Reference | Not counted |
| File/user | no speech, speakers not separated, bad format | No retry. "Upload a different file" | Not counted unless rating already started (today's rule) |
| Cancelled | — | "Session cancelled. This counted / did not count toward your limit." | Counted if transcription started |
Server-side silent retries (worker + LiteLLM) unchanged. Classification lives in `api/.../adapters/error_map.py` (split today's catch-all `upstream_unavailable` into transient vs permanent; `LLMError` subclasses carry provider status). Apply to every step (validate, transcribe, run), not only run. Web copy in `web/src/api/errors.ts`, actions in `failureAction`.

### D. Logging
- Wire engine loggers (`miti`, LiteLLM) into the same JSON stderr format; include `session_id`, `run_id`, `step`, `request_id` via context (contextvar set by worker per task and by API per request).
- On provider failure log: provider, model, HTTP status, error type, provider message (truncated, PHI-safe per `docs/implementation/logging-and-phi.md` / `safe_log` allowlist).
- Doc: update `docs/reference/infra.md` runbook (and a short `docs/reference/logging.md`): Reference = session id; Logs Explorer link template `https://console.cloud.google.com/logs/query;query=jsonPayload.session_id%3D%22<ID>%22;duration=P14D?project=onolys`; request_id query for API errors; error_code table.

### E. Rating-step outage
Reproduce the staging `gemini/gemini-4-neon` call with the worker's config to get the real error; upgrade LiteLLM; verify a full staging run succeeds on Claude Sonnet 5.5.

### F. LLM config (prod/staging)
- `config/{env}/routes.yaml` text routes → Claude Sonnet 5.5, effort low. Provider/model overridable by env vars set from GitHub Actions vars in `.github/workflows/_deploy-cloudrun.yml` `env_vars`; document where to change it and that a deploy re-run applies it. Terraform `DEFAULT_PRESET` unchanged or aligned.

### G. Eval model picker
- New config file (e.g. `config/models.yaml`): models `gemini`, `claude`; tiers:
  - gemini: gemini-4-carbon (effort low/medium/high, default medium), gemini-4-neon (low/medium/high, default high), gemini-4-hydrogen (low/medium/high, default high), gemini-4-argon (low/medium/high, default medium); context 1,048,576; max output 65,536.
  - claude: claude-opus-5-5, claude-sonnet-5-5, claude-haiku-5-5; effort low/medium/high/max (defaults: opus medium, sonnet high, haiku medium); context 1M; max output 128K; no temperature.
- Eval API `GET /v1/options` serves it; `eval/web/src/NewRun.tsx` adds model → tier → effort selects; run payload carries them; backend builds routes from them (`eval/backend/.../runs.py`, `engines/core/.../llm/routes.py`).
- Run = product(models × tiers × efforts) per report, plus human unit. Units built in `eval/backend/src/onolys_eval_backend/runs.py:284-300`; count check `:248-252`.
- Human locked for datasets in `eval/web/src/NewRun.tsx:113` and enforced server-side.
- Results: extend `CompareView` (`eval/web/src/Runs.tsx:15`, backend `read_runs.py:89-170`) so each report shows one row/column per combo with diff vs human + per-report error; add a Summary view aggregating across reports (`eval/core/src/onolys_eval/metrics.py:106` aggregate: MAE, within_1).
- Per-unit retry: `execute_unit` (`runs.py:536-555`) retries up to 3× with backoff for retryable classes only.

### H. Auth emails via Resend
Per `docs/reference/web-email-actions.md`: API endpoints generate verify/reset links with Firebase Admin SDK, rewrite to `<APP_BASE_URL>/auth/action?mode=…&oobCode=…` (APP_BASE_URL per env, server config only), send via Resend (API key in Secret Manager). Web `web/src/auth/firebaseService.ts` replaces `sendEmailVerification` (lines ~98, ~127) and `sendPasswordResetEmail` (~124) with calls to the new endpoints. Rate-limit + no user enumeration on reset.

## Goals, non-goals, anti-goals
- Goals: user always knows current step and %; cancel is safe and honest about limits; no user charged for our failure; any Reference finds its logs in one query; rating step works again on Claude; eval can compare engines/models/effort; auth emails land on a working page.
- Non-goals: streaming transcription; admin-site config UI; moving the general charge point to transcription start; changing STT provider.
- Anti-goals: retry buttons that can't succeed; logs with patient content; model switch requiring a code change; cancel that deletes data.

## Open risks
| Risk | Cheapest test |
|---|---|
| Outage cause isn't LiteLLM version | Repro call with debug on first, before other work |
| LiteLLM upgrade changes behavior elsewhere | Run engine + api unit tests after bump |
| Cancel races with in-flight Cloud Tasks | Unit test each state × cancel; handlers check state after each blob/LLM call |
| Resend domain/DNS + API key are owner tasks | List in owner tasks; staging first |
| Claude `max` via LiteLLM unverified (`xhigh` dropped by owner 2026-11-23) | Eval smoke call per model/effort; hide `max` if unsupported |

## Owner-only tasks (user)
- Resend: verify domain onolys.com (SPF/DKIM DNS records; may already be done if Firebase custom SMTP uses Resend), create API key (Sending access), store as Secret Manager `resend-api-key-staging`.
- Set GitHub Actions vars for LLM provider/model (staging only).
- Confirm anthropic-api-key-{env} secret has a valid key.
