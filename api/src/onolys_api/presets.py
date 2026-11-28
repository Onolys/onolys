"""Preset allowlist + STT resolution for `POST /sessions`.

Users pick only a preset *name*. Its `stt` is a key into stt_providers.yaml, resolved once
through the engine's `select_stt`; the result is stored on the session. Provider and model names are
never written here.
"""

import logging
import os
from collections.abc import Mapping
from pathlib import Path

from onolys_engine_core.errors import ConfigError, InputError
from onolys_engine_core.llm.routes import (
    DEFAULT_PRESET_ENV,
    RouteRegistry,
    default_preset_name,
    load_registry,
    resolve_preset,
)
from onolys_engine_core.presets import PresetInfo, list_presets
from onolys_miti.stt.select import STT_FILE_NAME, load_stt_config, select_stt

from onolys_api.audio import DEFAULT_MAX_DURATION_S
from onolys_api.config import LOCAL_ENVS, Settings
from onolys_api.repo.models import SttInfo

log = logging.getLogger(__name__)
TEST_PRESET_PREFIX = "test-"  # forced-failure presets: every env except prod


class UnknownPreset(Exception):
    pass


class PresetResolver:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._registry: RouteRegistry | None = None
        self._stt_config: dict | None = None

    def _load(self) -> tuple[RouteRegistry, dict]:
        if self._registry is None or self._stt_config is None:
            s = self._settings
            routes = Path(s.routes_file) if s.routes_file else None
            registry = load_registry(routes)
            stt_path = None
            if routes is not None and (routes.parent / STT_FILE_NAME).is_file():
                stt_path = routes.parent / STT_FILE_NAME
            self._stt_config = load_stt_config(stt_path)
            self._registry = registry
        return self._registry, self._stt_config

    def public_names(self) -> set[str]:
        """Presets a user may name: default, ENABLED_EXTRA_PRESETS, `test-*` outside prod."""
        registry, _ = self._load()
        s = self._settings
        names = {self._default_name(), *s.extra_presets}
        if s.env != "prod":
            names |= {n for n in registry.presets if n.startswith(TEST_PRESET_PREFIX)}
        return names

    def presets(self) -> list[PresetInfo]:
        """Public preset metadata; availability stays in this API layer."""
        registry, _ = self._load()
        allowed = self.public_names()
        return [p for p in list_presets(registry, self._default_name()) if p.name in allowed]

    def _default_name(self) -> str:
        return default_preset_name({DEFAULT_PRESET_ENV: self._settings.default_preset})

    def check_keys(self, environ: Mapping[str, str] | None = None) -> None:
        """Every enabled preset must exist and have its `api_key_env` set: fail fast in
        staging/prod, warn locally."""
        env = os.environ if environ is None else environ
        registry, _ = self._load()
        missing: dict[str, list[str]] = {}
        for name in sorted(self.public_names()):
            if name not in registry.presets and name != self._default_name():
                raise ConfigError(f"enabled preset {name!r} is not in the routes file")
            routes, _ = resolve_preset(name, registry, {DEFAULT_PRESET_ENV: name})
            for r in routes.values():
                if r.api_key_env and not env.get(r.api_key_env):
                    missing.setdefault(r.api_key_env, []).append(name)
        for var, presets in sorted(missing.items()):
            msg = f"{var} not set (needed by presets: {', '.join(sorted(set(presets)))})"
            if self._settings.env in LOCAL_ENVS:
                log.warning(msg)
            else:
                raise ConfigError(msg)

    def resolve(self, preset: str | None, language: str) -> tuple[str, SttInfo]:
        """(preset name, stt info). Unknown preset -> UnknownPreset."""
        registry, stt_config = self._load()
        env = {DEFAULT_PRESET_ENV: self._settings.default_preset}
        name = preset or default_preset_name(env)
        if name not in self.public_names():
            raise UnknownPreset("not available")
        try:
            _, stt_key = resolve_preset(name, registry, env)
        except InputError:
            raise UnknownPreset("unknown preset") from None
        params = select_stt(stt_key, language, config=stt_config)
        return name, SttInfo(provider=params.provider, model=params.model, language=params.language)

    def max_audio_s(self, provider: str | None, model: str | None) -> float:
        """Longest audio the session STT takes (`max_audio_s` on its entry, else 20 min)."""
        _, stt_config = self._load()
        for entry in stt_config["providers"].values():
            if entry.get("provider") == provider and entry.get("model") == model:
                return float(entry.get("max_audio_s", DEFAULT_MAX_DURATION_S))
        return DEFAULT_MAX_DURATION_S
