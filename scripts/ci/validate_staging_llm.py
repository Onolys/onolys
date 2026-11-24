#!/usr/bin/env python3
"""Validate staging's repository LLM vars with the runtime loader, before cloud writes.

Run with `uv run --frozen --package onolys-engine-core python scripts/ci/validate_staging_llm.py`.
Only these three vars are CI inputs; routes and model capabilities come from the checked-out SHA.
"""
import os
import sys
from pathlib import Path

from onolys_engine_core.errors import ConfigError
from onolys_engine_core.llm.routes import load_registry

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    values = {key: os.environ.get(f"LLM_{key.upper()}", "") for key in ("provider", "model", "effort")}
    try:
        load_registry(
            ROOT / "config/staging/routes.yaml",
            env={f"LLM_{key.upper()}": value for key, value in values.items()},
        )
    except ConfigError as exc:
        print(f"Invalid staging LLM configuration: {exc}", file=sys.stderr)
        return 1
    # The runtime validator accepts only exact lowercase tokens from model capabilities.
    # Emit nothing until the complete set validates, so no partial values can be deployed.
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.writelines(f"{key}={value}\n" for key, value in values.items())
    print("Staging LLM configuration validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
