"""Shared model capabilities for route overrides and eval selection."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from onolys_engine.errors import ConfigError

EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}
_CACHING = {"none", "provider_implicit", "anthropic_ephemeral"}


@dataclass(frozen=True)
class Tier:
    id: str
    efforts: tuple[str, ...]
    default_effort: str


@dataclass(frozen=True)
class Model:
    id: str
    label: str
    provider: str
    api_key_env: str
    caching_mode: str
    supports_temperature: bool
    context_tokens: int
    max_output_tokens: int
    tiers: dict[str, Tier]


def _mapping(value: object, name: str) -> dict:
    if not isinstance(value, dict) or not value:
        raise ConfigError(f"{name} must be a non-empty mapping")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a non-empty string")
    return value


def _positive_int(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ConfigError(f"{name} must be a positive integer")
    return value


def models_path(
    env: Mapping[str, str] | None = None, routes_file: Path | str | None = None
) -> Path:
    """MODELS_FILE, else <routes file dir>/../models.yaml (routes_file, then ROUTES_FILE)."""
    env = os.environ if env is None else env
    if path := env.get("MODELS_FILE"):
        return Path(path)
    # Deployments select config/<environment>/routes.yaml. Capabilities live above it.
    routes = Path(routes_file or env.get("ROUTES_FILE") or "config/staging/routes.yaml")
    return routes.parent.parent / "models.yaml"


def find_model(models: Mapping[str, Model], provider: str, tier: str) -> Model | None:
    """The model block of `provider` that owns `tier` (tier ids are unique across models)."""
    return next((m for m in models.values() if m.provider == provider and tier in m.tiers), None)


def load_models(path: Path | str | None = None) -> dict[str, Model]:
    """Load version 1 capabilities; explicit path wins over MODELS_FILE and ROUTES_FILE."""
    source = Path(path) if path is not None else models_path()
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot load models file {source}: {exc}") from exc
    data = _mapping(data, "models file")
    if type(data.get("version")) is not int or data["version"] != 1:
        raise ConfigError("models file version must be 1")
    entries = _mapping(data.get("models"), "models")
    models = {}
    seen_tiers: set[str] = set()
    for model_id, raw in entries.items():
        model_id = _text(model_id, "model id")
        entry = _mapping(raw, f"model {model_id!r}")
        tiers = {}
        for tier_id, raw_tier in _mapping(entry.get("tiers"), f"{model_id}.tiers").items():
            tier_id = _text(tier_id, "tier id")
            if tier_id in seen_tiers:
                raise ConfigError(f"duplicate tier id {tier_id!r} across models")
            seen_tiers.add(tier_id)
            tier = _mapping(raw_tier, f"tier {tier_id!r}")
            efforts = tier.get("efforts")
            if (
                not isinstance(efforts, list)
                or not efforts
                or any(not isinstance(effort, str) or effort not in EFFORTS for effort in efforts)
            ):
                raise ConfigError(
                    f"tier {tier_id!r}: efforts must be a non-empty list of allowed efforts"
                )
            default = tier.get("default_effort")
            if default not in efforts:
                raise ConfigError(f"tier {tier_id!r}: default_effort must be in efforts")
            tiers[tier_id] = Tier(tier_id, tuple(efforts), default)
        caching = entry.get("caching_mode")
        if not isinstance(caching, str) or caching not in _CACHING:
            raise ConfigError(f"model {model_id!r}: invalid caching_mode")
        temperature = entry.get("supports_temperature")
        if not isinstance(temperature, bool):
            raise ConfigError(f"model {model_id!r}: supports_temperature must be a boolean")
        models[model_id] = Model(
            id=model_id,
            label=_text(entry.get("label"), f"{model_id}.label"),
            provider=_text(entry.get("provider"), f"{model_id}.provider"),
            api_key_env=_text(entry.get("api_key_env"), f"{model_id}.api_key_env"),
            caching_mode=caching,
            supports_temperature=temperature,
            context_tokens=_positive_int(entry.get("context_tokens"), f"{model_id}.context_tokens"),
            max_output_tokens=_positive_int(
                entry.get("max_output_tokens"), f"{model_id}.max_output_tokens"
            ),
            tiers=tiers,
        )
    return models


__all__ = ["Model", "Tier", "find_model", "load_models", "models_path"]
