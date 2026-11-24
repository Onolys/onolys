---
status: draft
summary: Capture the real staging LLM error, fix it (likely LiteLLM bump), run staging text steps on Claude Sonnet 5.5 low with a GitHub-vars override, and define config/models.yaml (models -> tiers -> efforts) that eval SP06 consumes.
date: 2026-11-23
---
# PRD: SP01 LLM outage fix + Claude for text steps

Repo/branch: Onolys/onolys (local `iaudit`) / `feat/session-ux-logging-claude-email` · Depends on: none (Phase 1, gates 02-06) · Owns: `engines/core/pyproject.toml`, `engines/miti/pyproject.toml`, `uv.lock`, `engines/core/src/onolys_engine_core/llm/{routes.py,models.py (new),litellm_client.py (error capture only)}`, `engines/core/scripts/probe_llm.py` (new), `config/models.yaml` (new), `config/staging/routes.yaml`, `.github/workflows/deploy-staging.yml` (env_vars), `docs/reference/infra.md` (LLM config section)

## TL;DR
No rating run has succeeded on any env since 2026-11-16. First reproduce the staging `gemini/gemini-4-neon` call with the worker config and capture the real provider error. Then fix it (expected: LiteLLM upgrade), move staging text routes to `anthropic/claude-sonnet-5-5` with `reasoning_effort: low`, make provider/model overridable from GitHub vars, and add one model config file that eval SP06 reads. Staging only; prod files untouched.

## Problem
- Evidence (brief): worker rev 00048, session 9521150e…, 2026-11-23 21:35-21:38 UTC: 3 `run` attempts failed `upstream_unavailable`/`AllRunsFailed`/`LLMUnavailable` in ~0.5 s. LiteLLM 1.110.2 (`uv.lock:1001`) does not know `gemini-4-*` or `claude-sonnet-5-5`.
- The real error is invisible: `litellm_client.py:330` keeps only `type(exc).__name__`; `miti` logger is unconfigured. The cause is a hypothesis until captured.
- `engines/core/pyproject.toml:9` and `engines/miti/pyproject.toml:10` pin `litellm>=1.50` only; `uv.lock` is the single effective pin (`grep -n litellm uv.lock`: lock entries for core and miti, one package). `api/`, `eval/*` have no direct litellm dependency (`grep litellm */pyproject.toml`).
- `config/staging/routes.yaml` base routes are Gemini (`cheap`=hydrogen, `mid/strong`=neon; `miti_code/miti_globals/tips` alias `mid`). A `claude` preset already exists; `DEFAULT_PRESET=default` is set from Terraform `var.default_preset` (`infra/modules/environment/services.tf:10`), one value shared by both envs.
- Eval shares the file: `infra/eval-services.tf:25` sets `ROUTES_FILE=config/staging/routes.yaml`; both images `COPY config /app/config`.

## Goals / Non-Goals
**Goals:** real provider error captured and fixed; one successful end-to-end staging run on Claude Sonnet 5.5 low; override via GitHub vars; `config/models.yaml` + validated loader; tests that need no real API.
**Non-goals:** logging redesign (SP02; this SP only adds the minimal error capture below), failure classification (SP03), eval UI (SP06), prod rollout, STT changes, changing `oneshot` route or `test-broken-*` presets.

## Requirements
**R1 Repro first (acceptance: real provider error text captured in the PRD/task notes).**
`engines/core/scripts/probe_llm.py` (in-package per house rule): loads the registry via `ROUTES_FILE=config/staging/routes.yaml`, takes route name (default `mid`), builds kwargs via `LiteLLMClient._kwargs` for a trivial JSON prompt, enables `litellm._turn_on_debug()`, calls `litellm.acompletion` directly, prints exception class, `status_code`, `str(exc)`, and `litellm.get_model_info(<id>)` / `id in litellm.model_cost`. Secret from Secret Manager `gemini-api-key-staging` into env only for the run; never printed. Run on 1.110.2 (expect repro), then on the upgraded version. Matrix: gemini-4-neon, gemini-4-hydrogen, claude-sonnet-5-5. If the cause is not LiteLLM version (key/quota/provider 5xx/`reasoning_effort` rejected/`drop_params` effect), fix it here.
**R2 Minimal error capture.** In `_once` (`litellm_client.py:~330`) log at WARNING via the `miti` logger: provider, model, `status_code`, exception class, message truncated to 300 chars. SP02 owns the full PHI-safe format and context ids; this must not conflict (see Architecture, shared files).
**R3 LiteLLM upgrade.** Raise the floor in both pyprojects to the first version that passes R4; `uv lock --upgrade-package litellm`. Check: `litellm.model_cost` has `anthropic/claude-sonnet-5-5` and `gemini/gemini-4-*`; engine + api unit tests pass; one `reasoning_effort: low` Claude call shows adaptive thinking + effort (via the probe).
**R4 Claude effort.** Claude routes use `extra_params: {reasoning_effort: low}` and `supports_temperature: false` (no temperature on 5.5 family, per brief). No `thinking` key (`disabled` is rejected, as the existing `claude` preset comment says). Thinking tokens count against `max_output_tokens` (16000): verify a full run is not truncated (`finish_reason=length` -> `LLMBadOutput`).
**R5 Staging routes.** In `config/staging/routes.yaml` base routes `cheap`, `mid`, `strong` (and thus `miti_code/miti_globals/tips` via alias) switch to the Claude anchor (`anthropic/claude-sonnet-5-5`, `ANTHROPIC_API_KEY`, `caching_mode: anthropic_ephemeral`, effort low). Gemini anchors stay defined for `oneshot` (eval baseline, unchanged) and `test-broken-*`. The `claude` preset is kept (SP06 retires presets). Prod stays on `config/prod/routes.yaml`, unmodified, so prod is untouched by construction; Terraform `DEFAULT_PRESET`/`default_preset` unchanged (D4).
**R6 Override.** `LLM_PROVIDER` (`gemini|anthropic`) and `LLM_MODEL` (bare model id, e.g. `claude-sonnet-5-5`), read in `routes.py:_apply_env` next to the existing `MITI_MODEL_*`. Semantics: both set -> text routes (`cheap, mid, strong, miti_code, miti_globals, tips`) get `litellm_id=<provider>/<model>`, `api_key_env` and `caching_mode` taken from the provider entry in `models.yaml`; `extra_params` and caps stay as the route has them. Empty/unset = ignored (an unset GitHub var arrives as `""`). Only one set, or unknown provider/model per `models.yaml`: `ConfigError` at startup (fail fast, per `check_api_keys` precedent). `oneshot` is never overridden. Precedence, low to high: routes.yaml base < `MITI_MODEL_*` < `LLM_*` < preset overrides (preset is applied after env at `routes.py:load_registry/_overlay`, so `test-broken-*` still break as designed).
**R7 Wiring.** `deploy-staging.yml` api and worker jobs (and voice if it loads routes; verify at coding with grep, add the same env_vars if it does) add to `env_vars`: `LLM_PROVIDER=${{ vars.LLM_PROVIDER }}` and `LLM_MODEL=${{ vars.LLM_MODEL }}` through the existing `_deploy-cloudrun.yml` `env_vars` input. `deploy-prod.yml` and the reusable workflow are not edited. Eval service does not receive them (it selects explicitly in SP06). Change = set var, re-run deploy. Secret `anthropic-api-key-staging` is already mapped to the worker/api/eval via `var.llm_secrets` (`infra/variables.tf:52`, `modules/environment/services.tf:184`): no Terraform change; verify revision shows the secret ref.
**R8 `config/models.yaml`** (schema below) and `onolys_engine_core/llm/models.py`: `load_models(path|None)` (env `MODELS_FILE`, else `<ROUTES_FILE dir>/../models.yaml`), frozen dataclasses `Model/Tier`, validation: efforts non-empty subset of `low|medium|high|max` (`xhigh` is not a supported effort anywhere, owner 2026-11-23), `default_effort` in `efforts`, positive ints, unique tier ids across models. Contents exactly per brief section G.
**R9 Route/model consistency.** A test loads `config/{staging,prod}/routes.yaml` + `models.yaml` and asserts every non-test route's `litellm_id` is a known `<provider>/<tier>`, its `reasoning_effort` is allowed for that tier, and `max_output_tokens <= tier max`.
**R10 Tests (no live API).** Stub `litellm.acompletion` (the client has `_call()` injection): override matrix (unset, empty, one-of-two, unknown, preset beats env), models loader errors, route/model consistency, probe script kwargs snapshot (Claude: `reasoning_effort=low`, no `temperature`). `LITELLM_LOCAL_MODEL_COST_MAP=True` (CI) used for the "model known" assertion. One manual live smoke (AC4).
**R11 Docs.** `docs/reference/infra.md`: where to change provider/model, precedence, secret names, rollback (set `LLM_PROVIDER=gemini LLM_MODEL=gemini-4-neon` and re-run deploy).

## Architecture
```
GitHub vars LLM_PROVIDER/LLM_MODEL ─ deploy-staging.yml env_vars ─► Cloud Run api/worker env
routes.yaml (staging: Claude text routes) ─┐
MITI_MODEL_* ─ LLM_* (models.yaml lookup) ─┼─► load_registry ─► preset overlay ─► Route ─► LiteLLMClient
config/models.yaml ─► models.py ─► {override validation, route test, SP06 /v1/options}
```
`config/models.yaml` schema (SP06 contract; naming = model -> tier -> effort):
```yaml
version: 1
models:
  claude:                       # "model" = family shown in the first picker
    label: Claude
    provider: anthropic         # LiteLLM prefix
    api_key_env: ANTHROPIC_API_KEY
    caching_mode: anthropic_ephemeral
    supports_temperature: false
    context_tokens: 1000000
    max_output_tokens: 128000
    tiers:                      # "tier" = concrete model id
      claude-sonnet-5-5: {efforts: [low, medium, high, max], default_effort: high}
```
Gemini block likewise (context 1,048,576; max out 65,536; four `gemini-4-*` tiers; efforts `low/medium/high` for all four, so `gemini-4-neon` and `gemini-4-hydrogen` have no `xhigh`). `xhigh` appears nowhere in the file; no test for it.
Shared files: `litellm_client.py` (SP02 builds on R2; SP01 lands first, SP02 rebases and replaces the R2 log call), `routes.py` (SP06 adds a models x tiers x efforts -> `Route` builder using `models.py`), `config/models.yaml` (SP06 consumer; schema changes need SP06 sign-off), `config/staging/routes.yaml`, `uv.lock`.

## Decisions
| # | Decision | Choice | Alternatives considered | Why |
|---|---|---|---|---|
| D1 | Staging switch mechanism | Edit staging base routes to Claude | Set `DEFAULT_PRESET=claude` in Terraform | `default_preset` var is shared by both envs, so it would change prod; file edit is staging-only |
| D2 | Override site | `routes.py:_apply_env` | Per-service code; Terraform vars | One place for api, worker, eval; fits existing `MITI_MODEL_*` back-compat hook |
| D3 | Override vars | `LLM_PROVIDER` + bare `LLM_MODEL`, both required together | Single `LLM_MODEL=provider/id`; per-route vars | Matches brief names; models.yaml supplies key/caching, so no mismatched key |
| D4 | Preset vs env precedence | Preset wins over env | Env wins over all | Forced-failure `test-*` presets must stay failing in staging |
| D5 | Effort not overridable by env | Route `extra_params` only | `LLM_EFFORT` var | Not requested; SP06 owns effort selection |
| D6 | Wiring in callers (`deploy-staging.yml`) | Edit staging caller jobs | Edit `_deploy-cloudrun.yml` | Reusable file also serves prod; keeps prod untouched |
| D7 | models.yaml location | `config/models.yaml` (not per env) | Per-env copy | Capabilities are provider facts, not env choices; routes stay per env |
| D8 | Terraform | No change | Add LLM_* vars to `services.tf` | Provider v6 env set: TF-owned vars show as drift like `GIT_SHA`; a `terraform apply` clears the override until next deploy, falling back to Claude from routes.yaml (safe) |
| D9 | Error capture here | Minimal WARNING log | Wait for SP02 | Acceptance of R1 and later triage need it now; SP02 supersedes |

## Manual steps (owner-only)
- Set GitHub Actions vars `LLM_PROVIDER` / `LLM_MODEL` for staging (optional; routes.yaml already yields Claude).
- Confirmed already: `anthropic-api-key-staging` valid.
- Resend items belong to SP07.

## Risks / Open Questions
- [RESOLVED: default — probe (R1) decides; AC1 records the result] Root cause not yet known; LiteLLM version is only the leading hypothesis.
- [RESOLVED: default — pin chosen after the probe; AC2 verifies `model_cost`] First LiteLLM version that knows both id families and maps `reasoning_effort` for `claude-sonnet-5-5`.
- [RESOLVED: default — verify at coding (grep voice service for routes loading); if yes it gets the same env_vars] Does the voice service load routes (`onolys-voice-staging`)?
- [RESOLVED: `xhigh` dropped entirely (owner 2026-11-23); `max` kept, live smoke gate in SP06, hidden if unsupported (default)] `xhigh`/`max` via LiteLLM `reasoning_effort` unverified; matters for SP06, not for `low`.
- [RESOLVED: default — verified by AC4 staging run] Cloud Run egress to `api.anthropic.com` and key quota/rate limits on first run.
- Risk: thinking tokens vs 16000 cap truncating output (R4 check). Risk: LiteLLM bump changes behavior elsewhere (run core/miti/oneshot/api/eval unit tests, not full suite). [DEFERRED] Prod rollout; `claude` preset removal (SP06).

## Acceptance Criteria
1. Probe output for staging `gemini-4-neon` on 1.110.2 recorded with the real provider error (or a documented "does not reproduce" with evidence).
2. `uv.lock` pins a LiteLLM that has both `claude-sonnet-5-5` and `gemini-4-*` in `model_cost`; impacted unit tests green.
3. `config/staging/routes.yaml` text routes resolve to `anthropic/claude-sonnet-5-5`, `reasoning_effort: low`, no temperature; `config/prod/routes.yaml` diff is empty.
4. Staging deploy, new session end to end reaches `miti.done`/report; log shows model `claude-sonnet-5-5`.
5. Setting `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-4-neon` and re-running deploy switches the worker; unknown value fails startup with a clear error; `test-broken-llm` still fails.
6. `config/models.yaml` loads, validates, matches brief section G, and the route/model consistency test passes.
