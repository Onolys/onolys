"""Static checks: the legacy prod root matches live prod (provider shells, deploy-managed env, prod-only operator inputs).

Deploy workflows set GIT_SHA and LLM_PROVIDER/LLM_MODEL/LLM_EFFORT on every api/worker deploy. The provider's Cloud Run
`env` is a set (single entries cannot be ignored), so Terraform owns those values from variables instead of fighting them.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "modules" / "environment"
LEGACY_VARS = (ROOT / "variables.tf").read_text()
SERVICES = (MOD / "services.tf").read_text()
VOICE = (MOD / "voice.tf").read_text()


def block(src, header):
    m = re.search(re.escape(header) + r" \{", src)
    assert m, f"missing {header}"
    i, depth = m.end(), 1
    while depth:
        depth += {"{": 1, "}": -1}.get(src[i], 0)
        i += 1
    return src[m.start():i]


def test_legacy_default_provider_secrets_include_openai():
    # openai-api-key-prod exists live; the isolated root's defaults already declare all three providers.
    default = block(LEGACY_VARS, 'variable "llm_secrets"')
    for key, base in (("GEMINI_API_KEY", "gemini-api-key"), ("ANTHROPIC_API_KEY", "anthropic-api-key"),
                      ("OPENAI_API_KEY", "openai-api-key")):
        assert re.search(rf'{key}\s*=\s*"{base}"', default), key


def test_module_exposes_deploy_managed_llm_vars():
    mv = (MOD / "variables.tf").read_text()
    for name in ("llm_provider", "llm_model", "llm_effort"):
        v = block(mv, f'variable "{name}"')
        assert "default     = null" in v or "default = null" in v, name


def test_api_and_worker_emit_llm_env_voice_does_not():
    for svc in ('resource "google_cloud_run_v2_service" "api"', 'resource "google_cloud_run_v2_service" "worker"'):
        assert "local.llm_env" in block(SERVICES, svc), svc
    assert "local.llm_env" not in block(SERVICES, 'resource "google_cloud_run_v2_service" "eval_backend"')
    for name in ("LLM_PROVIDER", "LLM_MODEL", "LLM_EFFORT"):
        assert f'name = "{name}"' in SERVICES, name
    assert "LLM_" not in VOICE


def test_legacy_prod_passes_llm_vars_defaulting_blank():
    prod = block((ROOT / "main.tf").read_text(), 'module "prod"')
    for name in ("llm_provider", "llm_model", "llm_effort"):
        assert re.search(rf"{name}\s*=\s*var\.{name}\b", prod), name
        v = block(LEGACY_VARS, f'variable "{name}"')
        # deploy-prod always sets all three (blank clears), so blank is the matching default
        assert 'default     = ""' in v, name


def test_isolated_root_passes_llm_vars():
    iso = ROOT / "isolated-environment"
    main, variables = (iso / "main.tf").read_text(), (iso / "variables.tf").read_text()
    for name in ("llm_provider", "llm_model", "llm_effort"):
        assert re.search(rf"{name}\s*=\s*var\.{name}\b", main), name
        assert f'variable "{name}"' in variables, name


def test_operator_tfvars_example_is_prod_only():
    ex = (ROOT / "terraform.tfvars.example").read_text()
    assert "staging" not in re.sub(r"#.*", "", ex)
    assert re.search(r"resend_secret_wired\s*=\s*\{\s*prod\s*=", ex)
    assert re.search(r"git_sha\s*=\s*\{\s*prod\s*=", ex)
    for name in ("llm_provider", "llm_model", "llm_effort"):
        assert name in ex
