"""Explicit production engine registration for the main API."""

from onolys_engine_core.engine import Engine
from onolys_engine_core.errors import InputError
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
