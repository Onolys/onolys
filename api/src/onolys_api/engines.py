"""Explicit production engine registration for the main API."""

import os
from collections.abc import Mapping
from typing import Any

from onolys_engine_core.engine import Engine
from onolys_engine_core.errors import InputError
from onolys_engine_core.llm.models import EFFORTS, load_models, models_path
from onolys_engine_core.llm.routes import combo_routes, resolve_preset
from onolys_engine_core.registry import EngineRegistry
from onolys_miti import MitiEngine
from onolys_oneshot import OneshotEngine, config_names

from onolys_api.config import Settings


def build_engine_registry(settings: Settings) -> EngineRegistry:
    registry = EngineRegistry(prod_name=settings.prod_engine)
    registry.register(MitiEngine())
    return registry


def resolve_engine(
    settings: Settings, engine_id: str, registry: EngineRegistry | None = None
) -> Engine:
    """`miti` -> the registry engine; `oneshot:<variant>` -> a variant-bound one-shot, eval only.

    Anything else, or a one-shot id while `eval_mode` is off, is an `InputError`.
    """
    if engine_id == "miti":
        return (registry or build_engine_registry(settings)).get("miti")
    kind, _, variant = engine_id.partition(":")
    if kind == "oneshot" and settings.eval_mode and variant in config_names():
        return OneshotEngine(config=variant)
    raise InputError("Unknown eval engine.")


def override_routes(settings: Settings, base: dict, override: Mapping[str, Any]) -> dict:
    """Eval only: the preset's routes re-pointed at one (model, tier, effort) combo."""
    models = load_models(models_path(os.environ, settings.routes_file or None))
    model = models.get(override.get("model"))
    if model is None or override.get("tier") not in model.tiers:
        raise InputError("Unknown eval model or tier.")
    effort = override.get("effort")
    if effort not in EFFORTS or effort not in model.tiers[override["tier"]].efforts:
        raise InputError("Unknown eval effort.")
    return combo_routes(base, model, override["tier"], effort)


def eval_snapshot(settings, preset, engine_id, override) -> tuple[dict, str]:
    """(route snapshot, engine version) of an eval run: the single source of truth.

    Eval callers MUST build `EvalRunInfo.resolved_route` / `engine_version` with this function;
    the worker rebuilds the same pair from it and fails the run as `eval_config_drift` on any
    difference, so a second implementation would make every eval run fail."""
    routes, _ = resolve_preset(preset)
    if override:
        routes = override_routes(settings, routes, override)
    route = next(iter(routes.values()))
    effort = (override or {}).get("effort") or route.extra_params.get("reasoning_effort")
    snapshot = {
        "litellm_id": route.litellm_id,
        "effort": effort,
        "max_output_tokens": route.max_output_tokens,
        "context_tokens": route.context_tokens,
        "supports_temperature": route.supports_temperature,
        "caching_mode": route.caching_mode,
    }
    return snapshot, resolve_engine(settings, engine_id).version
