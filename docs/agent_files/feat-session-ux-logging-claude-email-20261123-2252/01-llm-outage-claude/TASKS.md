---
status: draft
summary: 8 tasks - capture real LLM error, fix LiteLLM, Claude staging routes, LLM_* override, models.yaml, wiring, docs, staging smoke.
date: 2026-11-23
---
# Tasks: SP01 LLM outage fix + Claude for text steps
Source of truth: docs/agent_files/feat-session-ux-logging-claude-email-20261123-2252/01-llm-outage-claude/PRD.md. All PRD Open Questions are RESOLVED (none OPEN). Staging only; prod files stay untouched. Tests use no live API (stub `litellm.acompletion` via the client's `_call()` injection); `LITELLM_LOCAL_MODEL_COST_MAP=True` for "model known" checks.

| # | Task | Depends on | Status |
|---|---|---|---|
| 1 | models.yaml + validated loader | - | todo |
| 2 | Minimal error capture + probe script | - | todo |
| 3 | Run probe on current LiteLLM, record real error | 2 | todo |
| 4 | LiteLLM upgrade (and any other root-cause fix) | 3 | todo |
| 5 | Claude staging routes + route/model consistency test | 1, 4 | todo |
| 6 | LLM_PROVIDER / LLM_MODEL override | 1, 5 | todo |
| 7 | Deploy wiring + infra docs | 6 | todo |
| 8 | Staging end-to-end smoke | 5, 6, 7 | todo |

## Task 1 — models.yaml + validated loader
What it is / what it means: One shared model config (model -> tier -> effort) that the override (this SP) and eval SP06 both read. Traces to D7, R8.
What changes at a high level: Add `config/models.yaml` with the claude and gemini blocks exactly per brief section G (no `xhigh` anywhere). Add `llm/models.py` with `load_models(path|None)` (env `MODELS_FILE`, else `<ROUTES_FILE dir>/../models.yaml`) returning frozen `Model`/`Tier` dataclasses, with validation.
Done when: unit tests pass for: valid file loads; efforts empty/outside `low|medium|high|max` rejected; `default_effort` not in `efforts` rejected; non-positive ints rejected; duplicate tier ids across models rejected; path resolution via `MODELS_FILE` and via routes dir. The real `config/models.yaml` loads and matches brief section G (AC6).

## Task 2 — Minimal error capture + probe script
What it is / what it means: Makes the hidden provider error visible now; SP02 later replaces the log format. Traces to R1, R2, D9.
What changes at a high level: In `litellm_client.py` `_once`, log at WARNING via the `miti` logger: provider, model, `status_code`, exception class, message truncated to 300 chars (no other behavior change). Add in-package `engines/core/scripts/probe_llm.py`: loads registry from `ROUTES_FILE` (default staging), takes route name (default `mid`), builds kwargs via `LiteLLMClient._kwargs`, enables litellm debug, calls `litellm.acompletion` directly, prints exception class, `status_code`, message, and model-known info (`get_model_info` / `model_cost`). API key from env only, never printed.
Done when: tests pass for the warning log (fields present, 300-char truncation, no key leakage) and a probe kwargs snapshot (Claude: `reasoning_effort=low`, no `temperature`).

## Task 3 — Run probe on current LiteLLM, record real error
What it is / what it means: Replace the hypothesis with evidence before changing versions. Traces to R1, AC1.
What changes at a high level: Run the probe on locked LiteLLM 1.110.2 for gemini-4-neon, gemini-4-hydrogen, claude-sonnet-5-5, using the staging secret fetched from Secret Manager into env for the run only. Record real error text and model-known results in the task notes (and a short note in the code/report artifact).
Done when: AC1 evidence recorded (real provider error, or documented "does not reproduce" with evidence) for all three models, and the stated cause is named (LiteLLM version, key, quota, provider 5xx, `reasoning_effort`, `drop_params`). No code change unless the cause is not the version, in which case Task 4 covers the fix.

## Task 4 — LiteLLM upgrade (and any other root-cause fix)
What it is / what it means: Fix the outage at its cause. Traces to R3, R4 (thinking vs token cap).
What changes at a high level: Raise the litellm floor in both engine pyprojects to the first version that passes the checks; `uv lock --upgrade-package litellm`. If Task 3 found a different cause, fix that here. Re-run the probe on the new version, including one `reasoning_effort: low` Claude call.
Done when: `uv.lock` pins a LiteLLM whose `model_cost` has `anthropic/claude-sonnet-5-5` and `gemini/gemini-4-*` (test with the local cost map); probe shows adaptive thinking plus effort for Claude; a full-length output is not truncated (`finish_reason` not `length`) with the 16000 cap; core, miti, oneshot, api and eval unit tests green (AC2, not the full suite).

## Task 5 — Claude staging routes + route/model consistency test
What it is / what it means: Staging text steps run on Claude Sonnet 5.5 low, prod unchanged by construction. Traces to D1, R4, R5, R9.
What changes at a high level: In `config/staging/routes.yaml`, base routes `cheap`, `mid`, `strong` (and via alias `miti_code`, `miti_globals`, `tips`) switch to the Claude anchor: `anthropic/claude-sonnet-5-5`, `ANTHROPIC_API_KEY`, `caching_mode: anthropic_ephemeral`, `extra_params: {reasoning_effort: low}`, `supports_temperature: false`, no `thinking` key. Keep Gemini anchors for `oneshot` and `test-broken-*`; keep the `claude` preset; do not touch Terraform `DEFAULT_PRESET` or `config/prod/routes.yaml`.
Done when: tests pass for staging text routes resolving to the Claude id, effort low, no temperature; `oneshot` and `test-broken-*` unchanged; a consistency test over staging and prod routes plus `models.yaml` (every non-test `litellm_id` is a known `<provider>/<tier>`, effort allowed for that tier, `max_output_tokens <=` tier max); `config/prod/routes.yaml` diff empty (AC3).

## Task 6 — LLM_PROVIDER / LLM_MODEL override
What it is / what it means: Switch text-step provider/model from GitHub vars without editing files. Traces to D2, D3, D4, D5, R6.
What changes at a high level: In `routes.py:_apply_env`, read both vars next to `MITI_MODEL_*`. Both set: text routes (`cheap, mid, strong, miti_code, miti_globals, tips`) take `litellm_id=<provider>/<model>` plus `api_key_env` and `caching_mode` from `models.yaml`; `extra_params` and caps unchanged. Empty or unset ignored. One set only, or unknown provider/model: `ConfigError` at startup. `oneshot` never overridden. Precedence: routes.yaml < `MITI_MODEL_*` < `LLM_*` < preset overlay. No effort env var.
Done when: tests pass for: unset; empty strings; one-of-two; unknown provider; unknown model; valid gemini and anthropic overrides; `oneshot` untouched; `test-broken-llm` preset still beats the env override (AC5 startup/failure parts).

## Task 7 — Deploy wiring + infra docs
What it is / what it means: Make the vars reach the services and document how to operate them. Traces to D6, D8, R7, R11.
What changes at a high level: In `deploy-staging.yml`, add `LLM_PROVIDER` and `LLM_MODEL` (from `vars.*`) to `env_vars` of the api and worker jobs, and of voice only if a grep shows it loads routes. Do not edit `deploy-prod.yml`, `_deploy-cloudrun.yml`, eval service config, or Terraform; verify the Anthropic secret ref is already mapped. Update the LLM config section of `docs/reference/infra.md`: where to change provider/model, precedence, secret names, rollback (`LLM_PROVIDER=gemini LLM_MODEL=gemini-4-neon` then re-run deploy), and the Terraform-apply drift note.
Done when: workflow YAML parses and the diff touches only the staging caller (a lint or yaml-load check); docs cover the listed items; the voice grep result is recorded in task notes.

## Task 8 — Staging end-to-end smoke
What it is / what it means: Live proof on staging; the only step that uses a real API. Traces to AC4, AC5, R10 (one manual live smoke).
What changes at a high level: After deploy (via dev-ship), run a new session end to end, check the worker log shows model `claude-sonnet-5-5` and reaches `miti.done`/report. Then set `LLM_PROVIDER=gemini` + `LLM_MODEL=gemini-4-neon`, re-run deploy, confirm the worker switches; confirm an unknown value fails startup with a clear error and `test-broken-llm` still fails. No new code.
Done when: results recorded (session id, log lines) for AC4 and AC5. If setting the GitHub vars is needed it is an owner step.

## Owner steps
- Set GitHub Actions vars `LLM_PROVIDER` / `LLM_MODEL` for staging (optional; routes.yaml already yields Claude). Needed for Task 8 AC5 switch test.
