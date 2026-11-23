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
- Failures and cancel never delete user data; only the explicit Delete action deletes (owner 2026-11-23). SP03 removes `validate.py` `purge()`-on-failure; staged-object cleanup after a successful move stays. Reason: future "retry with existing upload".
- Interview-linked sessions never consume the evaluation limit (the interview includes its evaluation): cancel charges 0 (SP04), same `exempt` predicate as `start_first_run` (SP03).
- Effort levels: `xhigh` dropped entirely (config, picker, caps, tests). Gemini low/medium/high; Claude low/medium/high/max; `max` keeps a live smoke gate (hidden if unsupported).
- Log provider errors incl. Gemini 400 text (cleaned, 300 chars) and LiteLLM WARNING/ERROR lines unfiltered for now; owner audits logs later (SP02 [DEFERRED] PHI audit).

## Cross-repo dependency
- SP05 needs `Spinner` and `Progress` in `@onolys/ui` (repo `github.com/Onolys/onolys-ui`, local `/root/projects/onolys/onolys-ui`). Verified: tag v0.2.0 exports neither. Add them there, release a new tag, bump `web/package.json` (`#v0.2.0` -> new tag). No inline SVG fallback. Separate repo/PR; gates SP05 web tasks.

## Owner-only tasks
- Resend: verify `onolys.com` (SPF/DKIM), create sending-only API key, store as Secret Manager `resend-api-key-staging`, set `resend_secret_wired=true` for staging and redeploy, then staging smoke (SP07).
- GitHub Actions vars `LLM_PROVIDER` / `LLM_MODEL` for staging (optional; routes.yaml already yields Claude) (SP01).
- Live eval smoke: one unit per provider x effort, owner-run, not CI (SP06 AC8).
- Release a new `@onolys/ui` tag with Spinner/Progress after the library change (SP05; code in the onolys-ui repo).
- Decide: is the rating draft saved server-side during `transcribing`? (SP05, only open item).
- Done by owner: `onolys-app-staging.web.app` added as authorized Firebase domain (SP07).

## Resolved 2026-11-23
- SP01: root cause/LiteLLM pin decided by the probe (AC1/AC2); voice service routes verified at coding; Anthropic egress/quota verified by AC4; `xhigh` dropped, `max` keeps smoke gate.
- SP02: Gemini 400 `provider_error` logged (cleaned, 300 chars); LiteLLM WARNING/ERROR kept unfiltered; voice `configure_logging` checked at task time; PHI audit of logs [DEFERRED] to owner.
- SP03: no delete on failure (new R8, AC7); interview-linked sessions never counted (R5, AC8); STT `InvalidArgument` = user_file (verify on real case); 529 transient / 400 permanent; `counted` on both run doc and session.
- SP04: interview-linked cancel charges 0; cancel keeps all data (confirmed, `ensure_active` purges nothing); `stt_operation` crash uncounted accepted; late-PUT 409 verified at coding.
- SP05: Spinner/Progress added to onolys-ui (cross-repo, no inline SVG); bar hidden on failed/cancelled (R3 fixed); weights/timings calibrated later from logs.
- SP06: `xhigh` removed; `max` live-smoke gated; output caps/timeout tuned after smoke; Anthropic 64K guard confirmed in smoke; dataset gold verified at coding.
- SP07: authorized domain done by owner; IAM starts at `roles/firebaseauth.admin`; routes included in public contracts.

## Still open
- [OPEN] SP05: Is the rating draft saved server-side during `transcribing`? Owner still deciding (check `RatingCard` autosave; else upload-phase hint for that case).
