"""Scenario loader (ai-interview PRD R1): every file validated at API start, fail fast.

Files live in the engine's packaged `scenarios/` (`scenario.schema.json` + `*.json`).
Only `public_view` fields ever leave the server.
"""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from onolys_engine_core.errors import ConfigError
from onolys_miti.miti import MITI
from onolys_miti.voice.select import allowed_voices

SCHEMA_NAME = "scenario.schema.json"
PUBLIC_FIELDS = ("id", "title", "difficulty", "summary", "language", "voice")


def scenarios_dir() -> Path:
    return MITI.data_dir / "scenarios"


def load_scenarios(
    directory: Path | None = None, voices: list[str] | None = None
) -> dict[str, dict]:
    """All scenarios by id. Raises `ConfigError` (path + JSON pointer only, no content)."""
    d = directory or scenarios_dir()
    try:
        validator = Draft202012Validator(json.loads((d / SCHEMA_NAME).read_text("utf-8")))
    except (OSError, ValueError) as e:
        raise ConfigError(f"scenario schema unreadable in {d}") from e
    allowed = set(voices if voices is not None else allowed_voices())
    out: dict[str, dict] = {}
    for path in sorted(d.glob("*.json")):
        if path.name == SCHEMA_NAME:
            continue
        try:
            sc = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError) as e:
            raise ConfigError(f"scenario {path.name}: not readable JSON") from e
        errors = sorted(validator.iter_errors(sc), key=lambda e: list(e.absolute_path))
        if errors:  # paths only: messages can quote persona text
            where = ", ".join("/" + "/".join(str(p) for p in e.absolute_path) for e in errors[:5])
            raise ConfigError(f"scenario {path.name}: invalid at {where}")
        if sc["id"] in out:
            raise ConfigError(f"scenario {path.name}: duplicate id {sc['id']!r}")
        if sc["voice"] not in allowed:
            raise ConfigError(
                f"scenario {path.name}: voice {sc['voice']!r} is not a configured voice"
            )
        out[sc["id"]] = sc
    if not out:
        raise ConfigError(f"no scenarios found in {d}")
    return out


def public_view(sc: dict[str, Any]) -> dict[str, Any]:
    """`id,title,difficulty,summary,language,voice` only (never persona, hidden_info, rules)."""
    pub = sc["public"]
    return {
        "id": sc["id"], "title": pub["title"], "difficulty": pub["difficulty"],
        "summary": pub["summary"], "language": sc["language"], "voice": sc["voice"],
    }  # fmt: skip
