"""Generic run-provenance helpers. No prompt or engine knowledge lives here."""

import dataclasses
import hashlib
import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from onolys_engine_core.llm.routes import Route
from pydantic import BaseModel, ConfigDict, model_serializer

from onolys_miti.stt import SttRun


def hash_files(paths: Iterable[Path], length: int = 16) -> str:
    """Truncated sha256 over the concatenated bytes of `paths`, in the order given."""
    h = hashlib.sha256()
    for p in paths:
        h.update(Path(p).read_bytes())
    return h.hexdigest()[:length]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RouteFacts(_Model):
    litellm_id: str
    provider: str
    structured_output_mode: Literal["json_object", "json_schema"]
    temperature_effective: float | None
    params_hash: str


class PackFacts(_Model):
    id: str
    version: str
    hash: str


class RunUsage(_Model):
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None


class SpanInfo(_Model):
    """How the coded span was chosen."""

    mode: Literal["whole", "explicit", "random_window"]
    start_ms: int | None = None
    end_ms: int | None = None
    start_turn: int | None = None
    end_turn: int | None = None
    duration_s: int | None = None
    seed: str

    @model_serializer(mode="wrap")
    def _serialize(self, handler):
        # Whole-session provenance has no range bounds; explicit ranges carry their form.
        return {key: value for key, value in handler(self).items()
                if key not in {"start_ms", "end_ms", "start_turn", "end_turn"} or value is not None}


class RunInfo(_Model):
    """Provenance of one engine run. Never holds text or key values."""

    engine: str
    code_version: str
    preset: str | None = None
    routes: dict[str, RouteFacts] = {}
    stt: SttRun | None = None
    pack: PackFacts | None = None
    prompt_hashes: dict[str, str] = {}
    n_runs: int = 1
    usage: RunUsage = RunUsage()
    span: SpanInfo | None = None


def code_version() -> str:
    return os.environ.get("GIT_SHA") or "unknown"


def provider_of(litellm_id: str) -> str:
    return litellm_id.split("/", 1)[0] if "/" in litellm_id else "unknown"


def route_facts(route: Route, temperature: float = 0.0) -> RouteFacts:
    """Facts about a resolved route. `params_hash` covers the whole entry (the key's env var
    name at most, never its value). `temperature` is what the client sends by default."""
    entry = json.dumps(dataclasses.asdict(route), sort_keys=True, default=str)
    return RouteFacts(
        litellm_id=route.litellm_id,
        provider=provider_of(route.litellm_id),
        structured_output_mode=route.structured_output_mode,
        temperature_effective=temperature if route.supports_temperature else None,
        params_hash=hashlib.sha256(entry.encode()).hexdigest()[:16],
    )
