# Stage 1A — api/ + infra + CI findings (raw, pre-verification)

Reviewer: sub-agent, commit 6ffbf63. Tests: api offline 1829 passed/5 skipped; ruff clean; infra+ci pytest 91 passed; terraform fmt/actionlint clean; test_eval_image.sh failed (docker apt, env-limited). Not run: Firestore emulator, terraform validate, live/nightly.
Note: reviewer ran scripts/ci/test_*.sh which invoked docker build (unintended); removed its tag.

## Flow map
- Auth: Bearer ID token (verified email) or X-API-Key; worker /tasks/* OIDC outside local/test; voice socket auth on first frame + Origin check.
- Create→upload→validate: POST /sessions; /audio signed PUT; /audio/complete enqueue validate; validate probes/transcodes, moves original, enqueue transcribe; file-check failure deletes session (discard_failed_upload).
- Transcribe→gate→run: STT poll chain → transcript → awaiting_input. Final rating + speaker confirm + transcript ready feed first-run gate (txn: cap, run doc, active_runs+1). Run task → report → release slot.
- Transcript-only: PUT /transcript only in `created` → awaiting_input.
- Retry (transient, ≤3), cancel (txn, charges, releases), delete (mark deleting, blobs, docs, fallback task).
- Stale: no cron; settle_if_stale only on GET /sessions and GET /sessions/{id}.
- Practice interview: create reserves unit; relay checkpoints; end/abandon/sweep → settle_interview (refund <30s, max 3/day); linked session gets free first run (counted=false).
- Authz: no owner-check hole found.

## High
- A1 (jobs/stale.py:94-98, extends Codex M10) active_runs leaks forever: stale settle flips session failed then releases slot in separate txn; if release raises, next read sees failed (not stale) → never retried. MAX_ACTIVE_RUNS=1 → permanent 429 concurrent_runs. Probe: GET 500 then 200 failed, active_runs stays 1. Fix: release in same txn; repair on refused start.
- A2 (routes/sessions.py:547-580, jobs/delete.py) DELETE failing twice leaves hidden `deleting` session: queue 2 attempts, re-enqueue same `{sid}-delete` name deduped; invisible in list/get, no sweep, audio/PHI retained. Static, med-high. Fix: sweep deleting sessions; longer retry.

## Medium
- A3 (jobs/stale.py:31) stale failures marked permanent_internal/user_file, retries_left=0, /retry 409; transcription shows "upload a different file". Probe confirmed. Fix: mark transient.
- A4 (routes/audio.py:145, repo/firestore.py:400) interview orphaned after upload discard: interview `uploaded` linked to deleted session, relink 409, unit lost. Probe confirmed. Fix: reset interview in discard txn.
- A5 (routes/rating.py:115) two concurrent final ratings both 202, 2 revisions. Probe confirmed. Fix: check+write in one txn.
- A6 (routes/speakers.py:26) speakers/confirm allowed in report_ready → flips roles against graded report. Probe confirmed.
- A7 (routes/transcript.py:131) transcript upload overwrites user language with `transcript.language or "en"` (es→en). Probe confirmed. Fix: fall back to session.language.
- A8 (routes/transcript.py, start_first_run) interview-linked session accepts any transcript → free evaluation (counted=false, usage 0). Probe confirmed. Fix: reject PUT /transcript when interview_id set.
- A9 (config.py:200) prod config doesn't require AUDIO_BUCKET/TASKS_QUEUE/WORKER_URL/VOICE_URL; SERVICE_MODE=combined accepted → boots healthy, fails at request time (503 / relative voice URL). Probe confirmed.

## Low
- A10 AI_* env vars only on voice service; api/worker use code defaults (latent drift).
- A11 api CI jobs not triggered by config/**, docs/contracts/public/**, .github/actions/**.
- A12 CI not a required merge check (per workflow comments); cancel-in-progress also applies to main.
- A13 worker `last` flag and ctx.attempt disagree after lease reclaim; lease-busy 503 burns a Cloud Tasks attempt.
- A14 concurrent request_upload + complete → validate finds no staged file and deletes session.
- A15 idempotency hash includes `client` info → replay after web redeploy returns 409.
- A16 logs.failed emits status=failed for routine user-file rejections → prod "failed" alert noise; no worker/voice/queue alerts.
- A17 GET /sessions/{id}/reports/{version} unbounded int → likely 500 on Firestore int64 overflow.
- A18 unguarded last_used_at write can 500 an API-key request; ID-token revocation never checked.
- A19 voice relay accepts socket pre-auth with uncapped first frame; stale connection can overwrite checkpoints across instances.

## Improvements
- A20 staging deployer trusts any workflow in repo, holds project-level Hosting/Firestore-rules admin + AR write; one Identity Platform pool shared staging+prod; worker mounts full public API.
- A21 no audio/transcript retention, no account-delete route; dead code (reserve_run/release_run, add_usage, get_usage, revoke_api_key, create_api_key, expiry_days); ensure_alive docstring names renamed fn.
- A22 Firestore index deploy parallel with Cloud Run deploy; smoke only /v1/healthz; actions pinned by tag not SHA; ffmpeg unpinned; preexec_fn in multithreaded process.
- A23 list_reports loads full bodies; /upload-limits can 500 on bad preset; stale retry_count can dedupe retry task; crash between interview refund counter and unit decrement loses unit; new SpeechClient per poll; no cap on session creation; RunView.run_info returned verbatim.
