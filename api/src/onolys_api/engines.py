"""Explicit production engine registration for the main API."""

from onolys_engine_core.registry import EngineRegistry
from onolys_miti import MitiEngine

from onolys_api.config import Settings


def build_engine_registry(settings: Settings) -> EngineRegistry:
    registry = EngineRegistry(prod_name=settings.prod_engine)
    registry.register(MitiEngine())
    return registry
