"""Load versioned package configs without importing a protocol implementation."""

import hashlib
import json
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal

import yaml
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from onolys_engine_core.errors import ConfigError, InputError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

_FILES = ("config.yaml", "instructions.md", "schema.json")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")


class _Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    version: str
    route: str = Field(default="oneshot", min_length=1)
    max_output_tokens: int = Field(gt=0)
    inputs: list[Literal["transcript", "params"]]
    params_schema: dict[str, Any] | None = None
    schema_hint: bool = False


@dataclass(frozen=True)
class OneshotConfig:
    name: str
    version: str
    route: str
    max_output_tokens: int
    inputs: tuple[str, ...]
    params_schema: dict[str, Any] | None
    schema_hint: bool
    instructions: str
    schema: dict[str, Any]
    config_hash: str


def _root(root: Path | None) -> Path:
    return root if root is not None else Path(str(files("onolys_oneshot").joinpath("configs")))


def _directory(name: str, root: Path) -> Path:
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise InputError("Unknown one-shot config.")
    directory = root / name
    if not directory.is_dir() or directory.resolve().parent != root.resolve():
        raise InputError("Unknown one-shot config.")
    return directory


def config_names(*, root: Path | None = None) -> list[str]:
    """List named packaged configs; unrelated package files are ignored."""
    directory = _root(root)
    if not directory.is_dir():
        return []
    return sorted(
        child.name for child in directory.iterdir()
        if _NAME.fullmatch(child.name) and child.is_dir()
        and child.resolve().parent == directory.resolve()
        and all((child / filename).is_file() for filename in _FILES)
    )


def load_config(name: str, *, root: Path | None = None) -> OneshotConfig:
    """Hash exact file bytes, then validate metadata and both JSON Schemas.

    ``root`` supports isolated synthetic fixtures. Production callers use package data.
    File names and lengths frame each digest component so boundaries are unambiguous.
    """
    directory = _directory(name, _root(root))
    try:
        contents = {filename: (directory / filename).read_bytes() for filename in _FILES}
        metadata = _Metadata.model_validate(yaml.safe_load(contents["config.yaml"]))
        schema = json.loads(contents["schema.json"])
        if metadata.name != name or not isinstance(schema, dict):
            raise ValueError("Config name or schema is invalid")
        if len(set(metadata.inputs)) != len(metadata.inputs):
            raise ValueError("Config inputs must be unique")
        validator_for(schema).check_schema(schema)
        if metadata.params_schema is not None:
            validator_for(metadata.params_schema).check_schema(metadata.params_schema)
        instructions = contents["instructions.md"].decode("utf-8")
    except (OSError, UnicodeError, ValueError, TypeError, yaml.YAMLError,
            ValidationError, SchemaError) as exc:
        raise ConfigError("Invalid one-shot package config.") from exc
    digest = hashlib.sha256()
    for filename, content in contents.items():
        digest.update(filename.encode("ascii") + b"\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return OneshotConfig(
        **metadata.model_dump(exclude={"inputs"}), inputs=tuple(metadata.inputs),
        instructions=instructions, schema=schema, config_hash=digest.hexdigest(),
    )
