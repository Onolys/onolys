---
status: draft
summary: Index — 7 sub-projects: LLM outage+Claude, logging, failure policy, cancel, processing screen, eval matrix, auth emails
date: 2026-11-23
---
# Session UX, logging, Claude, auth emails — design index

Brief: [brainstorm.md](brainstorm.md) (approved).

## Sub-projects
| # | Name | Phase | Depends on | Owns (key files) | PRD | status |
|---|---|---|---|---|---|---|
| 01 | LLM outage fix + Claude text steps | 1 (gates 02-06) | none | `config/models.yaml`, `llm/{routes,models}.py`, `config/staging/routes.yaml`, `uv.lock`, `deploy-staging.yml` env_vars | [01](01-llm-outage-claude/PRD.md) | draft |
| 02 | Traceable logging | 2 | 01 | `log_context.py`, `json_logging.py`, `safe_log.py`, `llm/errors.py` (fields), `logs.py`, `docs/reference/logging.md` | [02](02-logging/PRD.md) | draft |
| 03 | Failure policy + retry | 2 | 01, 02 | `adapters/error_map.py`, `jobs/charging.py`, `routes/{runs,sessions}.py`, `llm/errors.py` (`is_transient`), `web/src/api/errors.ts`, `RetryButton.tsx` | [03](03-failure-policy/PRD.md) | draft |
| 04 | Cancel | 2 | 03 (02) | `jobs/{machine,alive,worker}.py`, `repo/limits.py` (`decide_cancel`), `POST /sessions/{id}/cancel`, `CancelLink/ConfirmDialog/CancelledView.tsx` | [04](04-cancel/PRD.md) | draft |
| 05 | Processing screen clarity | 2 | 04 (file order), 03, 01 | `timeline.ts`, `progress.ts`, `useSessionStatus.ts`, `SessionPage.tsx` (steps/progress/hint), status-doc progress fields | [05](05-processing-screen/PRD.md) | draft |
| 06 | Eval model -> tier -> effort matrix | 2 | 01 (03 soft) | `eval/backend/.../{runs,read_runs,catalog}.py`, `eval/web/src/{NewRun,Runs}.tsx`, `llm/routes.py` (`combo_routes`) | [06](06-eval-matrix/PRD.md) | draft |
| 07 | Auth emails via Resend | 1 | none | `routes/auth_email.py`, `email/**`, `adapters/*` email ports, `web/src/auth/*`, `infra/**/secrets|services.tf` | [07](07-auth-emails-resend/PRD.md) | draft |

## Dependency graph
```
01 ─┬─ 02 ── 03 ── 04 ── 05
    └─ 06
07 (independent)
```

## Coding order
- 03 -> 04 -> 05 share `SessionPage.tsx`, `machine.py`, `repo/models.py`, `errors.ts`, `STATUS_FIELDS`; changes are additive, land in that order.
- 01 before 02: both edit `litellm_client.py` `_once` (02 replaces 01's minimal log call).
- Contracts regen (`api/openapi.json`, `docs/contracts/public`, `web/src/api/schema.d.ts`) shared by 03/04/05/07: last merged regenerates; CI drift check.
- `logs.py` `API_FIELDS` edited by 04 and 07 (disjoint additions; trivial rebase).
- 06 imports `is_transient` from 03; local shim if 06 lands first.

## Locked decisions (cross-cutting)
- Naming: model -> tier -> effort (model = family, tier = concrete id, effort = reasoning level); one `config/models.yaml` (01 owns schema).
- Staging only; prod files, Terraform `DEFAULT_PRESET`, `deploy-prod.yml` untouched.
- Never charge users for our faults: transient + permanent_internal always refunded; user_file counted only if LLM started; cancel charges 1 unit only if transcription started and no run reserved.
- Failure kinds: transient / permanent_internal / user_file, classified once in `error_map` (03); retry cap 3 per session, 5 s client countdown.
- `cancelled` is terminal (only Delete after); `counted` persisted; one status field `counted` shared by 03/04.
- Reference shown to user = session id; every log line carries `session_id` (02).
- Provider/model override via GitHub vars `LLM_PROVIDER`/`LLM_MODEL` (staging); effort not overridable.
- Eval cap 499 units; human always included for datasets; unit retry max 3 on transient only.
- Auth emails: Admin SDK link -> rebuilt on `APP_BASE_URL`; reset never reveals account existence; deploys before Resend secret exists.
- STT stays Chirp 3; streaming transcription dropped.

## Owner-only tasks
- Resend: verify `onolys.com` (SPF/DKIM), create sending-only API key, store as Secret Manager `resend-api-key-staging`, set `resend_secret_wired=true` for staging and redeploy, then staging smoke (SP07).
- GitHub Actions vars `LLM_PROVIDER` / `LLM_MODEL` for staging (optional; routes.yaml already yields Claude) (SP01).
- Live eval smoke: one unit per provider x effort, owner-run, not CI (SP06 AC8).
- Confirm: cancel charge for interview-linked sessions (default 0) (SP04); `provider_error` on for 400s (SP02).
- Confirm `onolys-app-staging.web.app` is an authorized Firebase domain (SP07).

## Open questions (consolidated; [default] where PRD gives one)
- SP01: Root cause unknown; LiteLLM version is leading hypothesis (probe decides).
- SP01: First LiteLLM version knowing both id families + `reasoning_effort` mapping; pin after probe.
- SP01: Does voice service load routes (needs same env_vars)?
- SP01: `xhigh`/`max` via `reasoning_effort` unverified (matters for SP06).
- SP01: Cloud Run egress to api.anthropic.com + key quota on first run.
- SP02: Does LiteLLM WARNING/ERROR echo prompt text on provider errors? [verify via stub + forced staging failure; else class+status only]
- SP02: Gemini 400 text may quote content; redactor heuristic [accepted; owner may disable for 400s]
- SP02: Does voice service share `logs.configure`? [grep at task time]
- SP03: Google STT `InvalidArgument`: user_file vs permanent_internal [user_file; check real bad-audio case]
- SP03: Ambiguous provider statuses (529, Gemini 400 overload) [529 transient, 400 permanent; revisit from logs]
- SP03: `counted` on `SessionError` vs run doc only [both; run doc is source]
- SP04: Interview-linked (free first run) cancel charge [0; owner confirm]
- SP04: `stt_operation` unset-crash spends Chirp uncounted [accepted, user-favourable]
- SP04: Does late upload-complete PUT after cancel 409 via `TRANSITIONS`? [verify at coding; add explicit check]
- SP05: Calibrate `stage_expected_s`/weights from staging logs after SP01+SP02 [placeholders now]
- SP05: Does `@onolys/ui` v0.2.0 export Spinner/Progress? [inline SVG fallback]
- SP05: Is rating draft saved server-side during `transcribing`? [check `RatingCard` autosave; else upload-phase hint]
- SP06: LiteLLM mapping of `xhigh`/`max` (drop_params could mislabel) [live smoke gate; remove unsupported efforts]
- SP06: `EFFORT_OUTPUT_CAP` and `timeout_s=300` are guesses [tune after smoke]
- SP06: Anthropic non-streaming large `max_tokens` guard [confirm with 64K on Sonnet/Opus]
- SP06: Do all shipped dataset sessions have gold? [else unit `skipped: no_gold`]
- SP07: Minimal IAM role for `generate_*_link` [try `roles/firebaseauth.admin`, narrow after smoke]
- SP07: Needs `ActionCodeSettings.url` on authorized domain? [assume yes; confirm]
- SP07: Two routes in published `docs/contracts/public` or hidden? [included]

Counts: SP01 5, SP02 3, SP03 3, SP04 3, SP05 3, SP06 4, SP07 3 (24).
