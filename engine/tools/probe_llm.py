"""Synthetic provider probe. Raw LiteLLM debug output is discarded to protect credentials.

Run from the repository root: python engine/tools/probe_llm.py --route mid
Provider credentials must already be in the environment; this script never prints them.
"""

import argparse
import asyncio
import contextlib
import json
import logging
import os
from dataclasses import replace
from pathlib import Path

from onolys_engine.llm import LiteLLMClient, LLMConfig, LLMRequest
from onolys_engine.llm.litellm_client import _safe_provider_message, _status
from onolys_engine.llm.models import load_models
from onolys_engine.llm.routes import load_registry


def build_probe(route_name="mid", model=None, effort=None):
    path = Path(os.environ.get("ROUTES_FILE") or "config/staging/routes.yaml")
    routes = load_registry(path).routes()
    route = routes[route_name]
    if model:
        provider, _, tier = model.partition("/")
        family = next(
            family for family in load_models().values()
            if family.provider == provider and tier in family.tiers
        )
        route = replace(
            route, litellm_id=model, api_key_env=family.api_key_env,
            caching_mode=family.caching_mode, supports_temperature=family.supports_temperature,
        )
    if effort:
        route = replace(route, extra_params={**route.extra_params, "reasoning_effort": effort})
    request = LLMRequest(
        tier=route_name, system="Return only a JSON object.", user='Return {"ok": true}.',
        response_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
    )
    client = LiteLLMClient(LLMConfig(llm_mode="live", routes={route_name: route}))
    return route, request, client._kwargs(request, route.timeout_s)


async def run_probe(route_name="mid", model=None, effort=None):
    # LiteLLM debug can include request headers and prompts. Disable logging and discard
    # stdout/stderr for the entire provider operation; print only sanitized diagnostics.
    previous_disable = logging.root.manager.disable
    route, request, kwargs = build_probe(route_name, model, effort)
    diagnostics = {"model": route.litellm_id}
    exit_code = 0
    with open(os.devnull, "w") as sink:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            logging.disable(logging.CRITICAL)
            try:
                import litellm

                litellm._turn_on_debug()
                diagnostics["known_model"] = route.litellm_id in litellm.model_cost
                try:
                    info = litellm.get_model_info(route.litellm_id)
                    diagnostics["model_info"] = {
                        key: info.get(key) for key in (
                            "max_tokens", "max_input_tokens", "max_output_tokens",
                            "supports_reasoning", "supports_temperature",
                        )
                    }
                except Exception as exc:
                    diagnostics["model_info_error"] = _safe_provider_message(exc, request, route)
                diagnostics["request"] = {
                    key: kwargs[key] for key in (
                        "max_tokens", "timeout", "reasoning_effort", "temperature", "drop_params"
                    ) if key in kwargs
                }
                response = await litellm.acompletion(**kwargs)
                diagnostics["finish_reason"] = response.choices[0].finish_reason
                diagnostics["success"] = True
            except Exception as exc:
                diagnostics.update(
                    success=False, exc_class=type(exc).__name__, status_code=_status(exc),
                    message=_safe_provider_message(exc, request, route),
                )
                exit_code = 1
            finally:
                # Completion callbacks can log after acompletion returns. Keep provider
                # loggers muted for this standalone probe, including their atexit flush.
                for name, logger in logging.root.manager.loggerDict.items():
                    if name.startswith("LiteLLM") and isinstance(logger, logging.Logger):
                        logger.disabled = True
                logging.disable(previous_disable)
    print(json.dumps(diagnostics, sort_keys=True))
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", default="mid")
    parser.add_argument("--model", help="Known provider/tier override for the synthetic probe")
    parser.add_argument("--effort", choices=("low", "medium", "high", "max"))
    args = parser.parse_args()
    return asyncio.run(run_probe(args.route, args.model, args.effort))


if __name__ == "__main__":
    raise SystemExit(main())
