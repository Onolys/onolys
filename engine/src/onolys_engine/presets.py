"""Preset catalog metadata with effective model names and no provider credentials."""

from pydantic import BaseModel

from .llm.routes import RouteRegistry, allowed_presets, default_preset_name, resolve_preset


class PresetInfo(BaseModel):
    name: str
    prod: bool
    models: dict[str, str]


def list_presets(registry: RouteRegistry, prod_name: str | None = None) -> list[PresetInfo]:
    """List every preset; API/eval callers apply their own availability filters."""
    selected = prod_name or default_preset_name()
    catalog = []
    for name in allowed_presets(registry):
        routes, _ = resolve_preset(name, registry)
        catalog.append(
            PresetInfo(
                name=name,
                prod=name == selected,
                models={route_name: route.litellm_id for route_name, route in routes.items()},
            )
        )
    return catalog
